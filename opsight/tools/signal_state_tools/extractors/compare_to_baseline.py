"""Tool: compare_to_baseline — current modality mean vs preop / intraop baseline.
현재 modality 평균과 baseline 비교.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    _error_response,
    _leakage_guard,
    _nanmean_or_none,
    _ok,
    _to_numpy,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


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
        result = {
            "baseline_value": None,
            "current_value": current_value,
            "absolute_change": None,
            "percent_change": None,
            "direction": "unknown",
            "meta": {"baseline_source": "none", "modality": modality},
        }
    else:
        abs_change = current_value - baseline_value
        pct_change = (abs_change / baseline_value * 100.0) if abs(baseline_value) > 1e-6 else 0.0
        if abs_change > 1e-3:
            direction = "up"
        elif abs_change < -1e-3:
            direction = "down"
        else:
            direction = "stable"
        result = {
            "baseline_value": baseline_value,
            "current_value": current_value,
            "absolute_change": abs_change,
            "percent_change": pct_change,
            "direction": direction,
            "meta": {"baseline_source": baseline_source, "modality": modality},
        }

    return _ok(
        request, result, (time.perf_counter() - t0) * 1000.0,
        quality_meta={"baseline_source": result["meta"]["baseline_source"]},
    )
