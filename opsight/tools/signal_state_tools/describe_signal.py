"""Tool: describe_signal — NaN-safe statistical summary of a modality window.
modality window 의 NaN-safe 통계 요약.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    _error_response,
    _leakage_guard,
    _ok,
    _to_numpy,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


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
        result = {
            "mean": None, "std": None, "min": None, "max": None,
            "median": None, "iqr": None, "missing_ratio": 1.0, "n_samples": 0,
            "meta": {"modality": modality, "note": "empty signal"},
        }
    else:
        missing = float(np.mean(np.isnan(arr)))
        if missing >= 1.0:
            result = {
                "mean": None, "std": None, "min": None, "max": None,
                "median": None, "iqr": None, "missing_ratio": 1.0,
                "n_samples": n,
                "meta": {"modality": modality, "note": "all NaN"},
            }
        else:
            valid = arr[~np.isnan(arr)]
            p25 = float(np.percentile(valid, 25))
            p75 = float(np.percentile(valid, 75))
            result = {
                "mean": float(np.mean(valid)),
                "std": float(np.std(valid)),
                "min": float(np.min(valid)),
                "max": float(np.max(valid)),
                "median": float(np.median(valid)),
                "iqr": p75 - p25,
                "missing_ratio": missing,
                "n_samples": n,
                "meta": {"modality": modality},
            }

    return _ok(request, result, (time.perf_counter() - t0) * 1000.0)
