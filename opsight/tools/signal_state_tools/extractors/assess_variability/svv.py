"""PPG family → amplitude variation + stroke-volume-variation (SVV) approximation.
PPG 계열 → 진폭 변동 + SVV 근사.
"""
from __future__ import annotations

import numpy as np


def svv_metrics(arr: np.ndarray) -> dict[str, float | None]:
    """PPG amplitude variation + SVV approximation.
    PPG 진폭 변동 + SVV 근사.

    amplitude_var = std/mean. SVV 근사 = (max - min) / mean × 100.
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
