"""Signal-state tools — deterministic signal access (ADR-016, amended 2026-06-10).
신호 상태 tool — 결정적 signal access (ADR-016, 2026-06-10 개정).

LLM (text-only) 은 raw signal 에 직접 접근할 수 없으므로, 브리프
§[Signal status] / §[Surgery context] / §[Evidence] section 의 정량 claim 을
명시적 tool 호출로 grounded 한다. 본 module 은 ADR-016 의 "Signal Access" 카테고리를
``signal_state`` 로 통합·개명한 결과다 (구 ``signal_state.py`` + ``signal_access_tools.py``
병합). Per ADR-016 / ADR-011, ``BiosignalFMInterface`` 와 무관 (FM Protocol 미사용).

6 deterministic tools (순수 numpy, FM/LLM 없음, 결정적):
- ``get_current_state``  — 현재 vital 스냅샷 (trailing-window 평균).
- ``get_signal_trend``   — vital 별 시간적 추세 (slope / 방향 / delta / R²).
- ``describe_signal``    — modality window 통계 (mean/std/min/max/median/IQR/missing).
- ``assess_variability`` — 변동성 metric (HR→HRV, MAP/CVP/PAP→BPV, PPG→SVV).
- ``compare_to_baseline``— preop / intraop-early baseline 대비 변화.
- ``summarize_current_state`` — rule-based 통합 현재 상태 평가.

Contract / 계약:
- 공유 envelope (``ToolRequest`` / ``ToolResponse``) + time-leakage guard 재사용 —
  sim-time ``t`` 에서 ``t`` 이하만 읽음.

Sampling-rate note / 샘플링 레이트 주의:
    tool 은 timestamp 없는 raw array 를 받으므로 window 길이에 modality 별 rate 가
    필요하다. 해석 순서: ``sampling_rates_hz[mod]`` → ``sampling_rate_hz`` →
    ``DEFAULT_SAMPLING_RATE_HZ``. streaming layer 가 실제 rate 를 전달한다.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import numpy as np

from opsight.tools._leakage_guard import leakage_guard as _shared_leakage_guard
from opsight.tools.envelope import ToolError, ToolRequest, ToolResponse
from opsight.tools.signal_access_types import (
    BaselineComparison,
    SignalDescription,
    StateSynthesis,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# ── NeuroKit2 환경 verification ──
# NeuroKit2 검증 — install 시 PRIMARY (HRV LF/HF), 부재 시 numpy fallback.

try:
    import neurokit2 as nk  # type: ignore  # noqa: F401
    USE_NEUROKIT = True
    _NK_VERSION: str | None = None  # type: ignore[assignment]
    try:
        import neurokit2 as _nk_mod  # type: ignore
        _NK_VERSION = getattr(_nk_mod, "__version__", None)
    except Exception:
        _NK_VERSION = None
except ImportError:
    USE_NEUROKIT = False
    _NK_VERSION = None


# ── Defaults / 기본값 ──
# 수치 vital 은 저속(~0.5–1Hz). waveform 은 args 로 override. 1Hz 가 정직한 기본.
DEFAULT_SAMPLING_RATE_HZ: float = 1.0
DEFAULT_CURRENT_WINDOW_S: float = 10.0
DEFAULT_TREND_WINDOW_S: float = 300.0  # 5 min
DEFAULT_STABLE_PCT: float = 5.0        # |delta%| below this → "stable"


# ── Vital → track-alias map (synthetic keys + real VitalDB track names) ──
# Field order is the canonical output order. First matching alias wins.
# field 순서가 출력 순서. 첫 매칭 alias 채택.

_VITAL_ALIASES: dict[str, tuple[str, ...]] = {
    "map_mmHg": ("ABP", "MAP", "Solar8000/ART_MBP", "Solar8000/NIBP_MBP",
                 "SNUADC/ART", "EV1000/ART_MBP", "Solar8000/FEM_MBP"),
    "sbp_mmHg": ("SBP", "Solar8000/ART_SBP", "Solar8000/NIBP_SBP"),
    "dbp_mmHg": ("DBP", "Solar8000/ART_DBP", "Solar8000/NIBP_DBP"),
    "hr_bpm": ("HR", "Solar8000/HR", "Solar8000/PLETH_HR"),
    "spo2_pct": ("SpO2", "SPO2", "Solar8000/PLETH_SPO2"),
    "etco2_mmHg": ("EtCO2", "ETCO2", "Solar8000/ETCO2", "Primus/ETCO2"),
    "rr_per_min": ("RR", "Solar8000/RR", "Solar8000/VENT_RR", "Solar8000/RR_CO2"),
    "bis": ("BIS", "BIS/BIS"),
    "core_temp_c": ("BT", "Solar8000/BT", "TEMP", "core_temp"),
}

# Family aliases for variability routing. Numeric-vital families are derived from
# the canonical map; waveform-only families (no numeric vital field) stand alone.
# 변동성 routing 용 family alias — 수치 vital 은 canonical map 에서 파생,
# waveform 전용(PPG/CVP/PAP)은 별도 정의.
_HR_ALIASES: tuple[str, ...] = _VITAL_ALIASES["hr_bpm"]
_ABP_ALIASES: tuple[str, ...] = _VITAL_ALIASES["map_mmHg"]
_PPG_ALIASES = ("PPG", "SNUADC/PLETH")
_CVP_ALIASES = ("CVP", "CVP_MEAN", "SNUADC/CVP", "Solar8000/CVP", "EV1000/CVP")
_PAP_ALIASES = (
    "PAP_MBP", "PAP_SBP", "PAP_DBP",
    "Solar8000/PA_MBP", "Solar8000/PA_SBP", "Solar8000/PA_DBP",
)


# ── numpy helpers / numpy 헬퍼 ──
def _to_numpy(arr: Any) -> np.ndarray:
    """torch.Tensor / list / ndarray → 1-D float64 numpy."""
    try:
        return arr.detach().cpu().numpy().astype(np.float64).ravel()
    except AttributeError:
        return np.asarray(arr, dtype=np.float64).ravel()


def _nanmean_or_none(arr: np.ndarray) -> float | None:
    """NaN-safe mean; ``None`` when empty or all-NaN."""
    if arr.size == 0:
        return None
    mask = ~np.isnan(arr)
    if not mask.any():
        return None
    return float(np.mean(arr[mask]))


def _find_first(signal: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str, np.ndarray] | None:
    """First present alias → (track_key, array). ``None`` if no alias present."""
    for key in aliases:
        if key in signal:
            return key, _to_numpy(signal[key])
    return None


def _resolve_rate(track_key: str, args: dict[str, Any]) -> float:
    """Per-modality sampling rate from args, else single rate, else default."""
    rates = args.get("sampling_rates_hz")
    if isinstance(rates, dict) and track_key in rates:
        try:
            return float(rates[track_key])
        except (TypeError, ValueError):
            pass
    single = args.get("sampling_rate_hz")
    if single is not None:
        try:
            return float(single)
        except (TypeError, ValueError):
            pass
    return DEFAULT_SAMPLING_RATE_HZ


def _trailing(arr: np.ndarray, window_s: float, rate_hz: float) -> np.ndarray:
    """Last ``window_s`` seconds of ``arr`` given ``rate_hz`` (whole array if shorter)."""
    n = int(round(window_s * rate_hz))
    if n <= 0 or n >= arr.size:
        return arr
    return arr[-n:]


# ── envelope helpers / envelope 헬퍼 ──


def _leakage_guard(
    request: ToolRequest, clock: SimClock, query_window_end_s: float | None = None
) -> ToolResponse | None:
    """Refuse queries whose window extends past ``clock.now_s``.
    ``clock.now_s`` 이후를 포함하는 window 조회 거부.

    Thin wrapper over the shared ``opsight.tools._leakage_guard`` primitive that
    tags the ``{"category": "signal_state"}`` quality_meta marker. Window end
    defaults to ``request.sim_time_s`` (current sim-time).
    공유 leakage guard primitive 의 thin wrapper — signal_state marker.
    window end 기본값은 ``request.sim_time_s``.
    """
    end = float(request.sim_time_s) if query_window_end_s is None else query_window_end_s
    return _shared_leakage_guard(
        request, clock, end,
        quality_meta={"category": "signal_state"},
        include_extra=True,
    )


def _ok(request: ToolRequest, result: dict[str, Any], latency_ms: float,
        *, quality_meta: dict[str, Any] | None = None) -> ToolResponse:
    qm: dict[str, Any] = {"category": "signal_state"}
    if quality_meta:
        qm.update(quality_meta)
    return ToolResponse(
        case_id=request.case_id, sim_time_s=request.sim_time_s,
        tool_name=request.tool_name, args=dict(request.args),
        result=result, quality_meta=qm, latency_ms=latency_ms,
    )


def _error_response(
    request: ToolRequest, err_type: str, message: str, latency_ms: float,
    *, extra: dict[str, Any] | None = None,
) -> ToolResponse:
    return ToolResponse(
        case_id=request.case_id, sim_time_s=request.sim_time_s,
        tool_name=request.tool_name, args=dict(request.args),
        error=ToolError(type=err_type, message=message, extra=extra or {}),
        quality_meta={"category": "signal_state"}, latency_ms=latency_ms,
    )


# ── Tool: get_current_state ──


def tool_get_current_state(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Current vital snapshot — trailing-window mean per available vital.
    현재 vital 스냅샷 — 가용 vital 별 최근 window 평균.

    Args (``request.args``):
        window_s: trailing window length in seconds (default 10).
            최근 window 길이 (초, 기본 10).
        sampling_rate_hz / sampling_rates_hz: rate resolution (see module docs).

    Result:
        ``vitals``  — {field: value|None} for every known vital field.
        ``available`` / ``missing`` — field names with / without a present track.
        ``window_s``, ``meta.source_tracks``, ``meta.n_samples``.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock)
    if err is not None:
        return err

    window_s = float(request.args.get("window_s", DEFAULT_CURRENT_WINDOW_S))
    if window_s <= 0:
        return _error_response(request, "invalid_args",
                               f"window_s must be positive (got {window_s})",
                               (time.perf_counter() - t0) * 1000.0)

    vitals: dict[str, float | None] = {}
    source_tracks: dict[str, str] = {}
    n_samples: dict[str, int] = {}
    available: list[str] = []
    missing: list[str] = []

    for field, aliases in _VITAL_ALIASES.items():
        found = _find_first(signal, aliases)
        if found is None:
            vitals[field] = None
            missing.append(field)
            continue
        track_key, arr = found
        rate = _resolve_rate(track_key, request.args)
        window = _trailing(arr, window_s, rate)
        value = _nanmean_or_none(window)
        vitals[field] = value
        source_tracks[field] = track_key
        n_samples[field] = int(window.size)
        (available if value is not None else missing).append(field)

    result: dict[str, Any] = {
        "vitals": vitals,
        "window_s": window_s,
        "available": available,
        "missing": missing,
        "meta": {"source_tracks": source_tracks, "n_samples": n_samples},
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"source_tracks": source_tracks})


# ── Tool: get_signal_trend ──


def _trend_one(arr: np.ndarray, rate_hz: float, stable_pct: float) -> dict[str, Any]:
    """Linear-fit trend for one modality window.
    단일 modality window 의 선형 추세.

    Uses least-squares slope over valid samples (robust to endpoint noise) plus
    sub-window means for start/end (first / last 20 %). Direction is decided by
    the percent change band.
    유효 sample 에 대한 least-squares slope + 시작/끝 sub-window 평균(앞/뒤 20%).
    방향은 percent 변화 band 로 결정.
    """
    valid_mask = ~np.isnan(arr)
    n_valid = int(valid_mask.sum())
    if n_valid < 2:
        return {"direction": "unknown", "slope_per_min": None,
                "start_value": None, "end_value": None, "delta": None,
                "delta_pct": None, "r_squared": None, "n_samples": int(arr.size),
                "note": "insufficient valid samples"}

    idx = np.arange(arr.size, dtype=np.float64)
    t_s = idx[valid_mask] / rate_hz          # seconds within window
    y = arr[valid_mask]

    # Least-squares line y = a*t + b.
    a, b = np.polyfit(t_s, y, 1)
    slope_per_min = float(a * 60.0)

    # R² of the fit (confidence the trend is linear, not noise).
    yhat = a * t_s + b
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else None

    # Robust start / end via 20 % sub-window means.
    k = max(1, n_valid // 5)
    start_value = float(np.mean(y[:k]))
    end_value = float(np.mean(y[-k:]))
    delta = end_value - start_value
    delta_pct = (delta / start_value * 100.0) if abs(start_value) > 1e-9 else None

    if delta_pct is None:
        direction = "rising" if delta > 0 else "falling" if delta < 0 else "stable"
    elif abs(delta_pct) < stable_pct:
        direction = "stable"
    else:
        direction = "rising" if delta > 0 else "falling"

    return {
        "direction": direction,
        "slope_per_min": round(slope_per_min, 4),
        "start_value": round(start_value, 3),
        "end_value": round(end_value, 3),
        "delta": round(delta, 3),
        "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
        "r_squared": round(r_squared, 3) if r_squared is not None else None,
        "n_samples": int(arr.size),
    }


def _field_for(name: str) -> str | None:
    """Resolve a vital field from a field name or a track alias.
    field 이름 또는 track alias 로부터 vital field 해석.
    """
    if name in _VITAL_ALIASES:
        return name
    for field, aliases in _VITAL_ALIASES.items():
        if name in aliases:
            return field
    return None


def tool_get_signal_trend(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Temporal trend per vital over a trailing window.
    최근 window 동안 vital 별 시간적 추세.

    Args (``request.args``):
        modality: optional single vital field (e.g. "map_mmHg") or track key.
            When omitted, every available known vital is analysed.
            단일 vital field / track key. 생략 시 가용 vital 전부 분석.
        window_s: trailing window length in seconds (default 300 = 5 min).
        stable_pct: |delta%| below this is reported "stable" (default 5).
        sampling_rate_hz / sampling_rates_hz: rate resolution (see module docs).

    Result:
        ``trends`` — {field: {direction, slope_per_min, start_value, end_value,
        delta, delta_pct, r_squared, n_samples}}.
        ``window_s``, ``meta.source_tracks``.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock)
    if err is not None:
        return err

    window_s = float(request.args.get("window_s", DEFAULT_TREND_WINDOW_S))
    if window_s <= 0:
        return _error_response(request, "invalid_args",
                               f"window_s must be positive (got {window_s})",
                               (time.perf_counter() - t0) * 1000.0)
    stable_pct = float(request.args.get("stable_pct", DEFAULT_STABLE_PCT))

    # Resolve which fields to analyse.
    requested = request.args.get("modality")
    if requested is not None:
        if not isinstance(requested, str):
            return _error_response(request, "invalid_args", "modality must be a string",
                                   (time.perf_counter() - t0) * 1000.0)
        field = _field_for(requested)
        if field is None:
            return _error_response(request, "invalid_args",
                                   f"modality {requested!r} not a known vital "
                                   f"(known: {sorted(_VITAL_ALIASES)})",
                                   (time.perf_counter() - t0) * 1000.0)
        fields = [field]
    else:
        fields = list(_VITAL_ALIASES)

    trends: dict[str, Any] = {}
    source_tracks: dict[str, str] = {}
    for field in fields:
        found = _find_first(signal, _VITAL_ALIASES[field])
        if found is None:
            continue  # only report vitals actually present
        track_key, arr = found
        rate = _resolve_rate(track_key, request.args)
        window = _trailing(arr, window_s, rate)
        trends[field] = _trend_one(window, rate, stable_pct)
        source_tracks[field] = track_key

    if requested is not None and not trends:
        return _error_response(request, "invalid_args",
                               f"modality {requested!r} resolved to field "
                               f"{fields[0]!r} but no matching track in signal",
                               (time.perf_counter() - t0) * 1000.0)

    result: dict[str, Any] = {
        "trends": trends,
        "window_s": window_s,
        "meta": {"source_tracks": source_tracks, "stable_pct": stable_pct},
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"source_tracks": source_tracks})


# ── Tool: describe_signal ──


def tool_describe_signal(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Statistical summary of a modality window.
    Modality window 의 통계 요약.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    modality = request.args.get("modality")
    if not isinstance(modality, str):
        return _error_response(
            request, "invalid_args", "modality must be a string",
            (time.perf_counter() - t0) * 1000.0,
        )
    if modality not in signal:
        return _error_response(
            request, "invalid_args",
            f"modality {modality!r} not in signal (available: {sorted(signal)})",
            (time.perf_counter() - t0) * 1000.0,
        )

    arr = _to_numpy(signal[modality])
    n = int(arr.size)
    if n == 0:
        desc = SignalDescription(
            mean=None, std=None, min=None, max=None, median=None, iqr=None,
            missing_ratio=1.0, n_samples=0,
            meta={"modality": modality, "note": "empty signal"},
        )
    else:
        missing = float(np.mean(np.isnan(arr)))
        if missing >= 1.0:
            desc = SignalDescription(
                mean=None, std=None, min=None, max=None, median=None, iqr=None,
                missing_ratio=1.0, n_samples=n,
                meta={"modality": modality, "note": "all NaN"},
            )
        else:
            valid = arr[~np.isnan(arr)]
            p25 = float(np.percentile(valid, 25))
            p75 = float(np.percentile(valid, 75))
            desc = SignalDescription(
                mean=float(np.mean(valid)),
                std=float(np.std(valid)),
                min=float(np.min(valid)),
                max=float(np.max(valid)),
                median=float(np.median(valid)),
                iqr=p75 - p25,
                missing_ratio=missing,
                n_samples=n,
                meta={"modality": modality},
            )

    result = {
        "mean": desc.mean,
        "std": desc.std,
        "min": desc.min,
        "max": desc.max,
        "median": desc.median,
        "iqr": desc.iqr,
        "missing_ratio": desc.missing_ratio,
        "n_samples": desc.n_samples,
        "meta": desc.meta,
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0)


# ── Tool: assess_variability ──


def _hrv_numpy_fallback(hr_arr: np.ndarray) -> dict[str, float | None]:
    """Time-domain HRV from HR series (no R-peak detection).
    HR series 의 time-domain HRV (R-peak detection 없음).

    Treats HR samples as instantaneous; converts to RR intervals via
    60_000 / HR (ms). SDNN = std of RR; RMSSD = sqrt(mean(diff(RR)^2)).
    LF/HF requires PSD on R-R intervals — unavailable in fallback.
    HR sample 을 instantaneous 로 간주; RR interval = 60_000 / HR (ms).
    """
    valid = hr_arr[~np.isnan(hr_arr) & (hr_arr > 0)]
    if valid.size < 2:
        return {"SDNN_ms": None, "RMSSD_ms": None, "LF_HF_ratio": None}
    rr_ms = 60_000.0 / valid
    sdnn = float(np.std(rr_ms))
    diff = np.diff(rr_ms)
    rmssd = float(np.sqrt(np.mean(diff ** 2))) if diff.size > 0 else 0.0
    return {"SDNN_ms": sdnn, "RMSSD_ms": rmssd, "LF_HF_ratio": None}


def _hrv_neurokit(hr_arr: np.ndarray) -> dict[str, float | None]:
    """NeuroKit2-based HRV — PRIMARY when NeuroKit2 installed.
    NeuroKit2 기반 HRV — NeuroKit2 설치 시 PRIMARY.
    """
    valid = hr_arr[~np.isnan(hr_arr) & (hr_arr > 0)]
    if valid.size < 2:
        return {"SDNN_ms": None, "RMSSD_ms": None, "LF_HF_ratio": None}
    # HR sample → RR interval (ms) 변환 후 NeuroKit2 HRV 함수.
    rr_ms = 60_000.0 / valid
    sdnn = float(np.std(rr_ms))
    diff = np.diff(rr_ms)
    rmssd = float(np.sqrt(np.mean(diff ** 2))) if diff.size > 0 else 0.0
    # LF/HF — 안정적 PSD 위해 긴 RR series 필요. 짧은 window 에서는 None.
    lf_hf: float | None = None
    if rr_ms.size >= 32:
        try:
            import neurokit2 as nk  # type: ignore
            import pandas as pd
            hrv_freq = nk.hrv_frequency(
                rr_ms.astype(np.float64), sampling_rate=1, show=False
            )
            if isinstance(hrv_freq, pd.DataFrame) and "HRV_LFHF" in hrv_freq.columns:
                v = hrv_freq["HRV_LFHF"].iloc[0]
                lf_hf = float(v) if not np.isnan(v) else None
        except Exception:
            lf_hf = None
    return {"SDNN_ms": sdnn, "RMSSD_ms": rmssd, "LF_HF_ratio": lf_hf}


def _bpv_metrics(arr: np.ndarray) -> dict[str, float | None]:
    """Blood pressure variability — SD + ARV (Average Real Variability).
    혈압 변동성 — SD + ARV.
    """
    valid = arr[~np.isnan(arr)]
    if valid.size < 2:
        return {"SD_mmHg": None, "ARV_mmHg": None}
    sd = float(np.std(valid))
    diff = np.diff(valid)
    arv = float(np.mean(np.abs(diff))) if diff.size > 0 else 0.0
    return {"SD_mmHg": sd, "ARV_mmHg": arv}


def _ppg_metrics(arr: np.ndarray) -> dict[str, float | None]:
    """PPG amplitude variation + SVV approximation.
    PPG 진폭 변동 + SVV 근사.

    amplitude_var = std/mean. SVV 근사 = (max - min) / mean × 100 —
    개략적이지만 해석 가능.
    """
    valid = arr[~np.isnan(arr)]
    if valid.size < 2:
        return {"amplitude_var": None, "SVV_pct": None}
    mean = float(np.mean(valid))
    if abs(mean) < 1e-6:
        return {"amplitude_var": None, "SVV_pct": None}
    std = float(np.std(valid))
    amp_var = std / mean
    svv = float((np.max(valid) - np.min(valid)) / mean * 100.0)
    return {"amplitude_var": amp_var, "SVV_pct": svv}


def tool_assess_variability(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Variability metrics per modality (HRV / BPV / SVV).
    Modality 별 변동성 metric (HRV / BPV / SVV).
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    modality = request.args.get("modality")
    if not isinstance(modality, str):
        return _error_response(
            request, "invalid_args", "modality must be a string",
            (time.perf_counter() - t0) * 1000.0,
        )

    # HR family → HRV
    if modality in _HR_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = _hrv_neurokit(arr) if USE_NEUROKIT else _hrv_numpy_fallback(arr)
        meta: dict[str, Any] = {
            "modality": modality,
            "modality_class": "HR",
            "implementation": "neurokit" if USE_NEUROKIT else "numpy_fallback",
        }
        if not USE_NEUROKIT:
            meta["unavailable_metrics"] = ["LF_HF_ratio"]
        if USE_NEUROKIT and _NK_VERSION:
            meta["neurokit_version"] = _NK_VERSION
    # ABP/MAP family → BPV
    elif modality in _ABP_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = _bpv_metrics(arr)
        meta = {"modality": modality, "modality_class": "MAP",
                "implementation": "numpy"}
    # PPG family → amplitude/SVV
    elif modality in _PPG_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = _ppg_metrics(arr)
        meta = {"modality": modality, "modality_class": "PPG",
                "implementation": "numpy"}
    # CVP / PAP → BPV-style variability (SD + ARV).
    # [CLINICIAN-REVIEW: 의료진 검토 필요] — CVP는 호흡 swing 분리,
    # PAP는 pulmonary HTN context와 함께 해석 필요.
    elif modality in _CVP_ALIASES or modality in _PAP_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = _bpv_metrics(arr)
        modality_class = "CVP" if modality in _CVP_ALIASES else "PAP"
        meta = {"modality": modality, "modality_class": modality_class,
                "implementation": "numpy"}
    else:
        return _error_response(
            request, "invalid_args",
            f"modality {modality!r} not supported (use HR / MAP / ABP / PPG / CVP / PAP family)",
            (time.perf_counter() - t0) * 1000.0,
        )

    result = {"metrics": metrics, "meta": meta}
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0)


# ── Tool: compare_to_baseline ──


def _compute_intraop_baseline(
    signal: dict[str, torch.Tensor], modality: str, sampling_rate_hz: float
) -> float | None:
    """First 10-minute mean of the modality (intraop fallback baseline).
    Modality 의 초기 10 분 평균 (intraop fallback baseline).
    """
    if modality not in signal:
        return None
    arr = _to_numpy(signal[modality])
    if arr.size == 0:
        return None
    n_first_10min = int(min(arr.size, 10 * 60 * sampling_rate_hz))
    if n_first_10min < 2:
        return None
    first_window = arr[:n_first_10min]
    valid = first_window[~np.isnan(first_window)]
    if valid.size < 2:
        return None
    return float(np.mean(valid))


def tool_compare_to_baseline(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Compare current modality mean to baseline.
    현재 modality 평균과 baseline 비교.

    Baseline priority / Baseline 우선순위:
        (1) ``request.args.preop_baseline`` (preop_bp 등 from query_patient_baseline)
        (2) intraop first 10 min mean of the modality
        (3) ``None`` (meta.baseline_source = "none")
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    modality = request.args.get("modality")
    if not isinstance(modality, str):
        return _error_response(
            request, "invalid_args", "modality must be a string",
            (time.perf_counter() - t0) * 1000.0,
        )
    if modality not in signal:
        return _error_response(
            request, "invalid_args",
            f"modality {modality!r} not in signal",
            (time.perf_counter() - t0) * 1000.0,
        )

    arr = _to_numpy(signal[modality])
    current_value = _nanmean_or_none(arr)
    if current_value is None:
        return _error_response(
            request, "invalid_args",
            f"modality {modality!r} contains no valid samples",
            (time.perf_counter() - t0) * 1000.0,
        )

    sampling_rate_hz = float(request.args.get("sampling_rate_hz", 500.0))

    preop = request.args.get("preop_baseline")
    if preop is not None:
        try:
            baseline_value: float | None = float(preop)
            baseline_source = "preop"
        except (TypeError, ValueError):
            baseline_value = None
            baseline_source = "none"
    else:
        baseline_value = None
        baseline_source = "none"

    # Fallback to intraop early 10 min
    if baseline_value is None:
        baseline_value = _compute_intraop_baseline(signal, modality, sampling_rate_hz)
        if baseline_value is not None:
            baseline_source = "intraop_early_10min"

    if baseline_value is None:
        comp = BaselineComparison(
            baseline_value=None,
            current_value=current_value,
            absolute_change=None,
            percent_change=None,
            direction="unknown",
            meta={"baseline_source": "none", "modality": modality},
        )
    else:
        abs_change = current_value - baseline_value
        pct_change = (abs_change / baseline_value * 100.0) if abs(baseline_value) > 1e-6 else 0.0
        if abs_change > 1e-3:
            direction = "up"
        elif abs_change < -1e-3:
            direction = "down"
        else:
            direction = "stable"
        comp = BaselineComparison(
            baseline_value=baseline_value,
            current_value=current_value,
            absolute_change=abs_change,
            percent_change=pct_change,
            direction=direction,
            meta={"baseline_source": baseline_source, "modality": modality},
        )

    result = {
        "baseline_value": comp.baseline_value,
        "current_value": comp.current_value,
        "absolute_change": comp.absolute_change,
        "percent_change": comp.percent_change,
        "direction": comp.direction,
        "meta": comp.meta,
    }
    return _ok(
        request, result, (time.perf_counter() - t0) * 1000.0,
        quality_meta={"baseline_source": comp.meta["baseline_source"]},
    )


# ── Tool: summarize_current_state (rule-based) ──

# Phrasing enforcement: 단정 어조 ban + [CLINICIAN-REVIEW] marker 강제.
# brief §13.1 (Clinical Fact Guard) 일관.
_CLINICIAN_REVIEW_MARKER = "[CLINICIAN-REVIEW: 의료진 검토 필요]"

# Lit-standard threshold (heuristic; 임상의 검토 필요).
_MAP_NORMAL_LOW = 65.0
_MAP_NORMAL_HIGH = 110.0
_HR_NORMAL_LOW = 50.0
_HR_NORMAL_HIGH = 100.0
_SPO2_NORMAL_LOW = 92.0
_BIS_TOO_LIGHT = 60.0
_BIS_TOO_DEEP = 40.0


def tool_summarize_current_state(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Synthesize current state from get_current_state (rule-based threshold path).
    get_current_state 출력을 합성한 rule-based 현재 상태 평가.

    ⚠️ Phrasing enforcement (ADR-016, brief §13.1):
        - Conditional phrasing only ("X 가능성을 시사함")
        - No diagnostic assertions, no dose recommendations
        - [CLINICIAN-REVIEW: 의료진 검토 필요] marker MANDATORY

    ADR-018: rule-based threshold path is the accepted Phase 1 implementation.
    ADR-014 Tier 0 supervised head (#14) is deferred — numerics-based threshold
    synthesis is sufficient for §[Signal status] grounding.
    ADR-018: rule-based threshold path 가 Phase 1. ADR-014 supervised head
    는 deferred — numerics threshold 합성이 §[Signal status] grounding 에 충분.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    # Inline call to get_current_state — direct function call (same module) to
    # avoid full dispatch overhead. Reuses leakage guard already passed above.
    # get_current_state 인라인 호출 — full dispatch overhead 회피.
    state_resp = tool_get_current_state(
        ToolRequest(case_id=request.case_id, sim_time_s=request.sim_time_s,
                    tool_name="get_current_state", args={}),
        clock, signal,
    )
    if not state_resp.ok or state_resp.result is None:
        # Shouldn't happen given the leakage guard above passed; conservative fallback.
        return _error_response(
            request, "tool_internal_error",
            "internal: get_current_state failed",
            (time.perf_counter() - t0) * 1000.0,
        )
    v = state_resp.result.get("vitals", {})

    # Rule-based state synthesis / Rule-based 상태 합성
    concerns: list[str] = []

    # Hemodynamic state from MAP
    map_val = v.get("map_mmHg")
    if map_val is None:
        hemodynamic_state = "unknown"
        concerns.append("MAP 미가용 — 혈역학 평가 제한")
    elif map_val < _MAP_NORMAL_LOW:
        hemodynamic_state = "caution_low_pressure"
        concerns.append(f"MAP {map_val:.0f} mmHg 가 65 mmHg 미만 가능성을 시사함")
    elif map_val > _MAP_NORMAL_HIGH:
        hemodynamic_state = "caution_high_pressure"
        concerns.append(f"MAP {map_val:.0f} mmHg 가 110 mmHg 초과 가능성을 시사함")
    else:
        hemodynamic_state = "stable"

    # HR check
    hr_val = v.get("hr_bpm")
    if hr_val is not None:
        if hr_val < _HR_NORMAL_LOW:
            concerns.append(f"HR {hr_val:.0f} bpm 가 50 bpm 미만 가능성을 시사함")
        elif hr_val > _HR_NORMAL_HIGH:
            concerns.append(f"HR {hr_val:.0f} bpm 가 100 bpm 초과 가능성을 시사함")

    # Anesthesia state from BIS
    bis_val = v.get("bis")
    if bis_val is None:
        anesthesia_state = "unknown"
    elif bis_val < _BIS_TOO_DEEP:
        anesthesia_state = "possibly_deep"
        concerns.append(f"BIS {bis_val:.0f} 가 40 미만 가능성을 시사함")
    elif bis_val > _BIS_TOO_LIGHT:
        anesthesia_state = "possibly_light"
        concerns.append(f"BIS {bis_val:.0f} 가 60 초과 가능성을 시사함")
    else:
        anesthesia_state = "adequate_range"

    # Respiratory state from SpO2 + EtCO2
    spo2_val = v.get("spo2_pct")
    etco2_val = v.get("etco2_mmHg")
    if spo2_val is None and etco2_val is None:
        respiratory_state = "unknown"
    elif spo2_val is not None and spo2_val < _SPO2_NORMAL_LOW:
        respiratory_state = "caution_low_spo2"
        concerns.append(f"SpO2 {spo2_val:.0f}% 가 92% 미만 가능성을 시사함")
    else:
        respiratory_state = "stable"

    # Overall assessment — conditional phrasing + mandatory marker
    if not concerns:
        overall = (
            "현재 가용한 활력 징후 는 안정 범위 내 가능성을 시사함. "
            "임상의의 종합 판단이 필요할 수 있다. "
            + _CLINICIAN_REVIEW_MARKER
        )
    else:
        overall = (
            f"{len(concerns)}건의 관찰 항목이 있으며 임상의의 판단이 필요할 수 있다. "
            + _CLINICIAN_REVIEW_MARKER
        )

    synth = StateSynthesis(
        hemodynamic_state=hemodynamic_state,
        anesthesia_state=anesthesia_state,
        respiratory_state=respiratory_state,
        key_concerns=concerns,
        overall_assessment=overall,
        meta={
            # ADR-018: rule_based. Tier 0 supervised head (ADR-014 #14) deferred.
            "tier0_status": "rule_based",
            "rule": "rule_based_threshold_synthesis",
            "vitals_source": state_resp.result.get("meta", {}),
        },
    )

    result = {
        "hemodynamic_state": synth.hemodynamic_state,
        "anesthesia_state": synth.anesthesia_state,
        "respiratory_state": synth.respiratory_state,
        "key_concerns": synth.key_concerns,
        "overall_assessment": synth.overall_assessment,
        "meta": synth.meta,
    }
    return _ok(
        request, result, (time.perf_counter() - t0) * 1000.0,
        quality_meta={
            "tier0_status": "rule_based",
            "clinical_review_required": True,
        },
    )


__all__ = [
    "USE_NEUROKIT",
    "tool_get_current_state",
    "tool_get_signal_trend",
    "tool_describe_signal",
    "tool_assess_variability",
    "tool_compare_to_baseline",
    "tool_summarize_current_state",
    "DEFAULT_SAMPLING_RATE_HZ",
    "DEFAULT_CURRENT_WINDOW_S",
    "DEFAULT_TREND_WINDOW_S",
]
