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
_PLAUSIBLE_RANGE: dict[str, tuple[float, float]] = {
    "ABP": (0.0, 300.0), "ART": (0.0, 300.0), "MAP": (0.0, 250.0),
    "SBP": (0.0, 300.0), "DBP": (0.0, 200.0), "HR": (0.0, 300.0),
    "PR": (0.0, 300.0), "SpO2": (0.0, 100.0), "BIS": (0.0, 100.0),
    "EtCO2": (0.0, 150.0), "RR": (0.0, 80.0), "BT": (20.0, 45.0),
}
# Pulsatile waveform markers — flatline is an artifact only here.
# 맥동 파형 marker — flatline 은 여기서만 아티팩트.
_WAVEFORM_MARKERS: tuple[str, ...] = ("ABP", "ART", "PPG", "PLETH", "ECG")
_FLATLINE_STD_EPS: float = 1e-3
_FLATLINE_PENALTY: float = 0.2


def _is_waveform(track_key: str) -> bool:
    k = track_key.upper()
    return any(m in k for m in _WAVEFORM_MARKERS)


def _sqi_one(arr: np.ndarray, track_key: str) -> dict[str, Any]:
    """SQI for one modality window → {sqi, missing_ratio, flatline, range_violation_ratio}."""
    n = int(arr.size)
    if n == 0:
        return {"sqi": 0.0, "missing_ratio": 1.0, "flatline": False,
                "range_violation_ratio": 0.0, "n_samples": 0, "note": "empty"}
    missing = float(np.mean(np.isnan(arr)))
    if missing >= 1.0:
        return {"sqi": 0.0, "missing_ratio": 1.0, "flatline": False,
                "range_violation_ratio": 0.0, "n_samples": n, "note": "all NaN"}
    valid = arr[~np.isnan(arr)]
    rng = _PLAUSIBLE_RANGE.get(track_key)
    viol = float(np.mean((valid < rng[0]) | (valid > rng[1]))) if rng is not None else 0.0
    flat = bool(_is_waveform(track_key) and float(np.std(valid)) < _FLATLINE_STD_EPS)
    sqi = (1.0 - missing) * (1.0 - viol)
    if flat:
        sqi *= _FLATLINE_PENALTY
    sqi = float(max(0.0, min(1.0, sqi)))
    return {"sqi": round(sqi, 3), "missing_ratio": round(missing, 3),
            "flatline": flat, "range_violation_ratio": round(viol, 3),
            "n_samples": n}


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
        d = _sqi_one(window, tk)
        scores[tk] = d["sqi"]
        details[tk] = d

    vals = list(scores.values())
    overall = float(round(sum(vals) / len(vals), 3)) if vals else None
    worst = float(min(vals)) if vals else None

    result = {
        "scores": scores,
        "overall": overall,
        "worst": worst,
        "details": details,
        "meta": {"window_s": window_s, "n_tracks": len(scores),
                 "method": "rule_based_sqi"},
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"method": "rule_based_sqi"})
