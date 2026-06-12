"""Tool: assess_signal_quality — rule-based per-modality signal quality (SQI).
규칙 기반 모달리티별 신호 품질 점수 (SQI).

각 트랙의 신뢰도를 [0,1] 로 채점한다 — "지금 이 신호를 믿어도 되나". quality-aware
추론의 producer: router 의 quality gate 에 먹여 "애매한 noise"(경계 + 품질 저하 →
ambiguous)를 감지하게 한다.

지표(셋, 결정적):
- **missing_ratio** — NaN 비율 (센서 단선 / 결측).
- **range_violation** — 센서 타당 범위 밖 비율 (물리적으로 불가 → 아티팩트).
- **flatline** — 분산 ~0. **파형 트랙(ABP/PPG/ECG)에만** 적용 — 맥동해야 정상이므로.
  수치 vital(HR=75 고정 등)은 정상적으로 상수일 수 있어 제외.

⚠️ Rule-based v1 (FM 미사용). FM 인코더 latent 기반 품질은 Stage 2 에서 model_tools
   (구 ``assess_signal_quality`` FM tool)가 대체/보강한다. 둘은 quality_aware_synthesis
   로 융합 가능.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import numpy as np

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    DEFAULT_CURRENT_WINDOW_S,
    _error_response,
    _leakage_guard,
    _ok,
    _resolve_rate,
    _to_numpy,
    _trailing,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# Sensor-plausibility bounds — NOT clinical thresholds (MAP 65 등은 router/summarize).
# 벗어나면 물리적으로 불가 → 아티팩트. (generous 한 sensor 한계)
# Low bounds exclude physiologically-impossible values (a live MAP < ~10 mmHg is
# artifact, not physiology — sensor off / flatline at 0).
_PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "ABP": (10.0, 300.0), "ART": (10.0, 300.0), "MAP": (10.0, 250.0),
    "SBP": (10.0, 300.0), "DBP": (5.0, 200.0), "HR": (0.0, 300.0),
    "PR": (0.0, 300.0), "SpO2": (0.0, 100.0), "BIS": (0.0, 100.0),
    "EtCO2": (0.0, 150.0), "RR": (0.0, 80.0), "BT": (20.0, 45.0),
}
# Waveform vs numeric is decided by SAMPLING RATE, not track name — a numeric MBP
# aliased to "ABP" must NOT be treated as a pulsatile waveform (real-data finding,
# demo_real_stream case 1, 2026-06-12). ≥ this rate → pulsatile waveform.
# 파형/수치 구분은 이름이 아니라 SAMPLING RATE 로 — "ABP" 로 alias 된 수치 MBP 를
# 파형으로 오인하면 안 됨. (≥ 이 rate → 맥동 파형)
_WAVEFORM_RATE_HZ: float = 50.0
_FLATLINE_STD_EPS: float = 1e-3
_FLATLINE_PENALTY: float = 0.2

# Max plausible |Δ| between consecutive NUMERIC samples (~1 Hz); above → artifact
# (e.g., MAP 80→20 in one sample = line flush/zeroing, not physiology).
# 인접 수치 sample 간 물리적 최대 변화 — 초과 시 아티팩트 (MAP 80→20 = 라인 flush 등).
_MAX_JUMP: dict[str, float] = {
    "ABP": 25.0, "ART": 25.0, "MAP": 25.0, "SBP": 30.0, "DBP": 25.0,
    "HR": 30.0, "PR": 30.0, "SpO2": 8.0, "EtCO2": 15.0,
}
_JUMP_PENALTY: float = 0.2

# Sparse numeric vitals are NORMAL: Solar8000 updates every ~2 s, so at 1 Hz a
# window is ~50% NaN even for a perfectly good signal. Tolerate missing up to this
# ratio; only penalize beyond (real sensor loss). (real-data finding, case 1.)
# 수치 vital 은 sparse 가 정상(Solar8000 ~2초 갱신) → 이 비율까지 결측 허용.
_MISSING_TOLERANCE: float = 0.5

# Primary hemodynamic / oxygenation channels — the router alarms on these, so the
# quality signal it consumes is the worst of THESE (not sparse BT/EtCO2/BIS).
# 주요 혈역학/산소화 채널 — router quality 는 이들의 worst (sparse BT/EtCO2/BIS 제외).
_PRIMARY_MARKERS: tuple[str, ...] = ("ABP", "ART", "MAP", "HR", "PR", "SPO2", "PLETH")


def _sqi_one(arr: np.ndarray, track_key: str, rate_hz: float) -> dict[str, Any]:
    """SQI for one modality window → {sqi, missing_ratio, flatline, sudden_jump, ...}.

    Flatline (pulsatile waveform stuck) vs sudden-jump (numeric vital with an
    implausible sample-to-sample step) are mutually exclusive, chosen by rate.
    flatline(파형 정지) vs sudden-jump(수치 vital 물리적 불가 급변) — rate 로 택일.
    """
    n = int(arr.size)
    if n == 0:
        return {"sqi": 0.0, "missing_ratio": 1.0, "flatline": False,
                "sudden_jump": False, "range_violation_ratio": 0.0,
                "n_samples": 0, "note": "empty"}
    missing = float(np.mean(np.isnan(arr)))
    if missing >= 1.0:
        return {"sqi": 0.0, "missing_ratio": 1.0, "flatline": False,
                "sudden_jump": False, "range_violation_ratio": 0.0,
                "n_samples": n, "note": "all NaN"}
    valid = arr[~np.isnan(arr)]
    rng = _PLAUSIBLE_RANGE.get(track_key)
    viol = float(np.mean((valid < rng[0]) | (valid > rng[1]))) if rng is not None else 0.0

    flat = jump = False
    if rate_hz >= _WAVEFORM_RATE_HZ:
        # Pulsatile waveform: a flat (near-zero variance) window is an artifact.
        flat = bool(float(np.std(valid)) < _FLATLINE_STD_EPS)
    else:
        # Numeric vital: an implausible step between samples is an artifact.
        max_jump = _MAX_JUMP.get(track_key)
        if max_jump is not None and valid.size >= 2:
            jump = bool(float(np.max(np.abs(np.diff(valid)))) > max_jump)

    # Tolerate sparse sampling; penalize only missing beyond the tolerance.
    eff_missing = max(0.0, (missing - _MISSING_TOLERANCE)) / (1.0 - _MISSING_TOLERANCE)
    sqi = (1.0 - eff_missing) * (1.0 - viol)
    if flat:
        sqi *= _FLATLINE_PENALTY
    if jump:
        sqi *= _JUMP_PENALTY
    sqi = float(max(0.0, min(1.0, sqi)))
    return {"sqi": round(sqi, 3), "missing_ratio": round(missing, 3),
            "flatline": flat, "sudden_jump": jump,
            "range_violation_ratio": round(viol, 3), "n_samples": n}


def tool_assess_signal_quality(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Per-modality rule-based signal quality over a trailing window.
    최근 window 의 모달리티별 규칙 기반 신호 품질.

    Args (``request.args``):
        modality: optional single track to score; omitted → all present tracks.
        window_s: trailing window length (default 10 s).
        sampling_rate_hz / sampling_rates_hz: rate resolution (see _common).

    Result:
        ``scores`` {track: sqi}, ``overall`` (mean), ``worst`` (min),
        ``details`` {track: indicators}, ``meta``.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    window_s = float(request.args.get("window_s", DEFAULT_CURRENT_WINDOW_S))
    requested = request.args.get("modality")
    if requested is not None:
        if not isinstance(requested, str):
            return _error_response(request, "invalid_args", "modality must be a string",
                                   (time.perf_counter() - t0) * 1000.0)
        if requested not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {requested!r} not in signal (available: {sorted(signal)})",
                (time.perf_counter() - t0) * 1000.0)
        tracks = [requested]
    else:
        tracks = list(signal)

    scores: dict[str, float] = {}
    details: dict[str, Any] = {}
    for tk in tracks:
        rate = _resolve_rate(tk, request.args)
        window = _trailing(_to_numpy(signal[tk]), window_s, rate)
        d = _sqi_one(window, tk, rate)
        scores[tk] = d["sqi"]
        details[tk] = d

    vals = list(scores.values())
    overall = float(round(sum(vals) / len(vals), 3)) if vals else None
    worst = float(min(vals)) if vals else None
    # Worst over PRIMARY hemodynamic/oxygenation channels only — the router's
    # quality gate uses this (a dead sparse BT/EtCO2 must not gate alarms).
    primary = [s for tk, s in scores.items()
               if any(m in tk.upper() for m in _PRIMARY_MARKERS)]
    primary_worst = float(min(primary)) if primary else None

    result = {
        "scores": scores,
        "overall": overall,
        "worst": worst,
        "primary_worst": primary_worst,
        "details": details,
        "meta": {"window_s": window_s, "n_tracks": len(scores),
                 "method": "rule_based_sqi"},
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"method": "rule_based_sqi"})
