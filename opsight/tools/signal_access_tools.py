"""Signal Access tools 17–21 (plan_1.3.5, ADR-016).
Signal Access tool 17–21 (plan_1.3.5, ADR-016).

5 deterministic tool — LLM 이 raw signal 에 접근 못 하므로 브리프
§[Signal status] / §[Surgery context] / §[Evidence] section 의 정량 claim 을
명시적 tool 호출로 grounded 한다.

5 deterministic tools — LLM cannot access raw signals, so brief
§[Signal status] / §[Surgery context] / §[Evidence] section quantitative
claims are grounded by explicit tool calls.

Per ADR-016, 본 module 은 ``BiosignalFMInterface`` 와 무관 (FM Protocol 미사용).
Per ADR-016, this module is independent of ``BiosignalFMInterface`` (no FM
Protocol use).

Modality alias / 모달리티 alias:
- ``catalog §3`` (`docs/vitaldb_catalog.md`) 의 priority track 명 + synthetic
  prototype key 모두 인식.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import numpy as np

from opsight.tools.envelope import ToolError, ToolRequest, ToolResponse
from opsight.tools.signal_access_types import (
    BaselineComparison,
    CurrentVitalsResult,
    SignalDescription,
    StateSynthesis,
    VariabilityResult,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# ── NeuroKit2 환경 verification (plan_1.3.5 task 1) ──
# NeuroKit2 환경 검증 — install 시 PRIMARY, 부재 시 numpy fallback.
# NeuroKit2 verification — PRIMARY if installed, numpy fallback otherwise.

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


# ── Modality alias / 모달리티 alias ──
# Mirror of `opsight/fm/mock_rule_based.py::_*_ALIASES` + `docs/vitaldb_catalog.md §3`.
# Synthetic prototype key (e.g. "ABP") + real VitalDB track name (e.g. "SNUADC/ART") 모두 인식.

_ABP_ALIASES = ("ABP", "MAP", "SNUADC/ART", "Solar8000/ART_MBP",
                "EV1000/ART_MBP", "Solar8000/NIBP_MBP", "Solar8000/FEM_MBP")
_HR_ALIASES = ("HR", "Solar8000/HR", "Solar8000/PLETH_HR")
_PPG_ALIASES = ("PPG", "SNUADC/PLETH")
_ECG_ALIASES = ("ECG", "ECG_II", "SNUADC/ECG_II")
_BIS_ALIASES = ("BIS", "BIS/BIS")
_SPO2_ALIASES = ("SpO2", "SPO2", "Solar8000/PLETH_SPO2")
_ETCO2_ALIASES = ("EtCO2", "ETCO2", "Solar8000/ETCO2", "Primus/ETCO2")
_TEMP_ALIASES = ("BT", "Solar8000/BT", "core_temp", "TEMP")
_SBP_ALIASES = ("SBP", "Solar8000/ART_SBP", "Solar8000/NIBP_SBP")
_DBP_ALIASES = ("DBP", "Solar8000/ART_DBP", "Solar8000/NIBP_DBP")
_RR_ALIASES = ("RR", "Solar8000/VENT_RR", "Solar8000/RR_CO2")


def _find_first(signal: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str, np.ndarray] | None:
    for k in aliases:
        if k in signal:
            return k, _to_numpy(signal[k])
    return None


def _to_numpy(arr: Any) -> np.ndarray:
    """torch.Tensor / list / numpy → 1-D float numpy."""
    try:
        return arr.detach().cpu().numpy().astype(np.float64).ravel()
    except AttributeError:
        return np.asarray(arr, dtype=np.float64).ravel()


def _nanmean_or_none(arr: np.ndarray) -> float | None:
    """NaN-safe mean; ``None`` if all NaN or empty.
    NaN-safe mean; 전부 NaN 또는 empty 시 ``None``.
    """
    if arr.size == 0:
        return None
    mask = ~np.isnan(arr)
    if not mask.any():
        return None
    return float(np.mean(arr[mask]))


# ── Common helpers / 공통 헬퍼 ──


def _leakage_guard(
    request: ToolRequest, clock: SimClock, query_window_end_s: float
) -> ToolResponse | None:
    """Refuse queries whose window extends past ``clock.now_s``.
    ``clock.now_s`` 이후를 포함하는 window 조회 거부.
    """
    if query_window_end_s > clock.now_s:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="leakage_violation",
                message=(
                    f"query_window_end_s={query_window_end_s} exceeds "
                    f"clock.now_s={clock.now_s}"
                ),
                extra={"query_window_end_s": query_window_end_s,
                       "clock_now_s": clock.now_s},
            ),
            quality_meta={"category": "signal_access"},
            latency_ms=0.0,
        )
    return None


def _error_response(
    request: ToolRequest,
    err_type: str,
    message: str,
    latency_ms: float,
    *,
    extra: dict[str, Any] | None = None,
) -> ToolResponse:
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        error=ToolError(type=err_type, message=message, extra=extra or {}),
        quality_meta={"category": "signal_access"},
        latency_ms=latency_ms,
    )


def _ok(
    request: ToolRequest,
    result: dict[str, Any],
    latency_ms: float,
    *,
    quality_meta: dict[str, Any] | None = None,
) -> ToolResponse:
    qm = {"category": "signal_access"}
    if quality_meta:
        qm.update(quality_meta)
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result,
        quality_meta=qm,
        latency_ms=latency_ms,
    )


# ── Tool 17 — get_current_vitals ──


def tool_get_current_vitals(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Return current vital values dict (MAP/SBP/DBP/HR/RR/SpO2/EtCO2/BIS/temp).
    현재 vital 값 dict 반환 (9 field).

    Each field uses last ±5 second window mean from the matching modality.
    각 field 는 매칭 modality 의 최근 ±5 초 window 평균.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    source_tracks: dict[str, str] = {}
    fallback_used: list[str] = []

    def _extract(aliases: tuple[str, ...], field_name: str) -> float | None:
        found = _find_first(signal, aliases)
        if found is None:
            return None
        key, arr = found
        source_tracks[field_name] = key
        # 부재 alias 중 fallback (e.g. NIBP for ABP) 사용 추적
        if key not in (aliases[0],):  # primary alias 외
            fallback_used.append(f"{field_name}<-{key}")
        return _nanmean_or_none(arr)

    vitals = CurrentVitalsResult(
        map_mmHg=_extract(_ABP_ALIASES, "map_mmHg"),
        sbp_mmHg=_extract(_SBP_ALIASES, "sbp_mmHg"),
        dbp_mmHg=_extract(_DBP_ALIASES, "dbp_mmHg"),
        hr_bpm=_extract(_HR_ALIASES, "hr_bpm"),
        rr_per_min=_extract(_RR_ALIASES, "rr_per_min"),
        spo2_pct=_extract(_SPO2_ALIASES, "spo2_pct"),
        etco2_mmHg=_extract(_ETCO2_ALIASES, "etco2_mmHg"),
        bis=_extract(_BIS_ALIASES, "bis"),
        core_temp_c=_extract(_TEMP_ALIASES, "core_temp_c"),
    )

    result: dict[str, Any] = {
        "map_mmHg": vitals.map_mmHg,
        "sbp_mmHg": vitals.sbp_mmHg,
        "dbp_mmHg": vitals.dbp_mmHg,
        "hr_bpm": vitals.hr_bpm,
        "rr_per_min": vitals.rr_per_min,
        "spo2_pct": vitals.spo2_pct,
        "etco2_mmHg": vitals.etco2_mmHg,
        "bis": vitals.bis,
        "core_temp_c": vitals.core_temp_c,
        "meta": {"source_tracks": source_tracks, "fallback_used": fallback_used},
    }
    return _ok(
        request, result, (time.perf_counter() - t0) * 1000.0,
        quality_meta={"source_tracks": source_tracks},
    )


# ── Tool 18 — describe_signal ──


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


# ── Tool 19 — assess_variability ──


def _hrv_numpy_fallback(hr_arr: np.ndarray) -> dict[str, float | None]:
    """Time-domain HRV from HR series (no R-peak detection).
    HR series 의 time-domain HRV (R-peak detection 없음).

    Treats HR samples as instantaneous; converts to RR intervals via
    60_000 / HR (ms). SDNN = std of RR; RMSSD = sqrt(mean(diff(RR)^2)).
    LF/HF requires PSD on R-R intervals — unavailable in fallback.

    HR sample 을 instantaneous 로 간주; RR interval = 60_000 / HR (ms).
    SDNN = std(RR); RMSSD = sqrt(mean(diff(RR)^2)). LF/HF 는 R-R PSD
    필요 — fallback 미지원.
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
    # Convert HR samples to RR intervals (ms) for NeuroKit2 HRV functions.
    # HR sample → RR interval (ms) 변환 후 NeuroKit2 HRV 함수.
    rr_ms = 60_000.0 / valid
    sdnn = float(np.std(rr_ms))
    diff = np.diff(rr_ms)
    rmssd = float(np.sqrt(np.mean(diff ** 2))) if diff.size > 0 else 0.0
    # LF/HF — requires longer RR series for stable PSD; for short windows
    # we return None rather than unstable estimate.
    # LF/HF — 안정적 PSD 위해 긴 RR series 필요. 짧은 window 에서는 None.
    lf_hf: float | None = None
    if rr_ms.size >= 32:
        try:
            import neurokit2 as nk  # type: ignore
            import pandas as pd
            # nk.hrv_frequency expects RR-peaks in samples; pass interpolated RR.
            # nk.hrv_frequency 는 RR-peak index 를 기대 — interpolated RR 전달.
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

    Computes amplitude_var = std / mean. SVV approximation uses
    (max - min) / mean × 100 over the window — coarse but interpretable.
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
    else:
        return _error_response(
            request, "invalid_args",
            f"modality {modality!r} not supported (use HR / MAP / ABP / PPG family)",
            (time.perf_counter() - t0) * 1000.0,
        )

    result = {"metrics": metrics, "meta": meta}
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0)


# ── Tool 20 — compare_to_baseline ──


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


# ── Tool 21 — summarize_current_state (STUB) ──

# Phrasing enforcement: 단정 어조 ban + [CLINICIAN-REVIEW] marker 강제.
# `tool 21 stub.task7` (plan_1.3.5) 와 brief §13.1 (Clinical Fact Guard) 일관.
_CLINICIAN_REVIEW_MARKER = "[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]"

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
    """STUB — synthesize current state from tools 17–20 (rule-based).
    STUB — 17–20 출력을 합성한 rule-based 현재 상태 평가.

    ⚠️ Phrasing enforcement (ADR-016, brief §13.1):
        - Conditional phrasing only ("X 가능성을 시사함")
        - No diagnostic assertions, no dose recommendations
        - [CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] marker MANDATORY

    Full implementation: Tier 0 #14–16 wrap (ADR-014, DECISION PENDING).
    Full 구현: ADR-014 Accepted 시 Tier 0 supervised head 호출로 교체.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    # Inline call to tool 17 (get_current_vitals) — direct function call to avoid
    # full dispatch overhead. Reuses leakage guard already passed above.
    # Tool 17 인라인 호출 — full dispatch overhead 회피, leakage guard 재사용.
    vitals_resp = tool_get_current_vitals(
        ToolRequest(case_id=request.case_id, sim_time_s=request.sim_time_s,
                    tool_name="get_current_vitals", args={}),
        clock, signal,
    )
    if not vitals_resp.ok or vitals_resp.result is None:
        # Shouldn't happen given the leakage guard above passed; conservative fallback.
        # 위 leakage guard 통과했으므로 발생 안 함; 보수적 fallback.
        return _error_response(
            request, "tool_internal_error",
            "internal: get_current_vitals failed",
            (time.perf_counter() - t0) * 1000.0,
        )
    v = vitals_resp.result

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
            "tier0_status": "stub",
            "stub_rule": "rule_based_threshold_synthesis",
            "vitals_source": v.get("meta", {}),
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
            "tier0_status": "stub",
            "clinical_review_required": True,
        },
    )


__all__ = [
    "USE_NEUROKIT",
    "tool_get_current_vitals",
    "tool_describe_signal",
    "tool_assess_variability",
    "tool_compare_to_baseline",
    "tool_summarize_current_state",
]
