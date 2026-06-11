"""MAP / ABP / CVP / PAP family → blood pressure variability (BPV).
혈압 계열 (MAP/ABP/CVP/PAP) → 혈압 변동성 (BPV).
"""
from __future__ import annotations

import numpy as np


def bpv_metrics(arr: np.ndarray) -> dict[str, float | None]:
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
