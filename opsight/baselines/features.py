"""Baseline feature extraction (plan_1.4 shared utilities).
Baseline feature 추출 (plan_1.4 공유 유틸).

Lit-standard ABP-derived features + cross-modal HRV/RR + EMR baseline.
임상 lit. 표준 ABP feature + cross-modal HRV/RR + EMR baseline.
"""
from __future__ import annotations

from typing import Any

import numpy as np


# ── ABP modality alias / ABP modality alias ──
# Mirror of opsight.fm.mock_rule_based._ABP_ALIASES (catalog §2 / §3)
# opsight.fm.mock_rule_based._ABP_ALIASES 미러 (catalog §2 / §3)
_ABP_ALIASES = ("ABP", "SNUADC/ART", "Solar8000/ART_MBP", "EV1000/ART_MBP")
_HR_ALIASES = ("HR", "Solar8000/HR", "Solar8000/PLETH_HR")
_PPG_ALIASES = ("PPG", "SNUADC/PLETH")


def _to_numpy(arr: Any) -> np.ndarray:
    """Convert torch.Tensor / list / numpy → 1-D float numpy.
    torch.Tensor / list / numpy → 1-D float numpy.
    """
    try:
        # torch.Tensor
        return arr.detach().cpu().numpy().astype(np.float64).ravel()
    except AttributeError:
        return np.asarray(arr, dtype=np.float64).ravel()


def _find_first(signal: dict[str, Any], aliases: tuple[str, ...]) -> np.ndarray | None:
    """Return first matching modality's array, or ``None``.
    첫 매칭 modality 의 array 반환, 또는 ``None``.
    """
    for k in aliases:
        if k in signal:
            return _to_numpy(signal[k])
    return None


# ── Feature spec / Feature spec ──


ABP_FEATURE_NAMES: tuple[str, ...] = (
    "map_mean",
    "map_std",
    "map_slope_per_min",
    "map_min",
    "map_max",
    "map_p10",
    "map_p90",
    "map_below_70_ratio",
    "map_below_65_ratio",
    "map_above_100_ratio",
)


def extract_abp_features(
    signal: dict[str, Any], sampling_rate_hz: float = 500.0
) -> np.ndarray:
    """Extract 10 lit-standard ABP features from a recent window.
    최근 window 에서 10 가지 lit-standard ABP feature 추출.

    Returns:
        1-D numpy array of length 10. NaN-padded if ABP absent.
        길이 10 의 1-D numpy. ABP 부재 시 NaN-pad.
    """
    abp = _find_first(signal, _ABP_ALIASES)
    if abp is None or len(abp) == 0:
        return np.full(len(ABP_FEATURE_NAMES), np.nan, dtype=np.float64)

    arr = np.asarray(abp, dtype=np.float64)
    mask = ~np.isnan(arr)
    if not mask.any():
        return np.full(len(ABP_FEATURE_NAMES), np.nan, dtype=np.float64)

    valid = arr[mask]
    mean = float(np.mean(valid))
    std = float(np.std(valid))
    p10 = float(np.percentile(valid, 10))
    p90 = float(np.percentile(valid, 90))
    vmin = float(np.min(valid))
    vmax = float(np.max(valid))

    # slope per minute / 분당 slope
    n = len(arr)
    if n >= 2:
        x = np.arange(n, dtype=np.float64)
        # robust linear fit on non-NaN samples / NaN 제외 robust linear fit
        try:
            slope, _intercept = np.polyfit(x[mask], valid, 1)
            slope_per_min = float(slope * sampling_rate_hz * 60.0)
        except (np.linalg.LinAlgError, ValueError):
            slope_per_min = 0.0
    else:
        slope_per_min = 0.0

    below_70 = float(np.mean(valid < 70.0))
    below_65 = float(np.mean(valid < 65.0))
    above_100 = float(np.mean(valid > 100.0))

    return np.array(
        [mean, std, slope_per_min, vmin, vmax, p10, p90, below_70, below_65, above_100],
        dtype=np.float64,
    )


MULTIMODAL_FEATURE_NAMES: tuple[str, ...] = (
    *ABP_FEATURE_NAMES,
    "hr_mean",
    "hr_std",
    "ppg_mean",
    "ppg_std",
    "n_modalities",
)


def extract_multimodal_features(
    signal: dict[str, Any], sampling_rate_hz: float = 500.0
) -> np.ndarray:
    """Extract ABP + HR + PPG summary features (15 total).
    ABP + HR + PPG 요약 feature 추출 (총 15).
    """
    abp_feats = extract_abp_features(signal, sampling_rate_hz=sampling_rate_hz)

    hr = _find_first(signal, _HR_ALIASES)
    if hr is None or len(hr) == 0:
        hr_mean, hr_std = np.nan, np.nan
    else:
        hr_arr = np.asarray(hr, dtype=np.float64)
        if np.isnan(hr_arr).all():
            hr_mean, hr_std = np.nan, np.nan
        else:
            hr_mean = float(np.nanmean(hr_arr))
            hr_std = float(np.nanstd(hr_arr))

    ppg = _find_first(signal, _PPG_ALIASES)
    if ppg is None or len(ppg) == 0:
        ppg_mean, ppg_std = np.nan, np.nan
    else:
        ppg_arr = np.asarray(ppg, dtype=np.float64)
        if np.isnan(ppg_arr).all():
            ppg_mean, ppg_std = np.nan, np.nan
        else:
            ppg_mean = float(np.nanmean(ppg_arr))
            ppg_std = float(np.nanstd(ppg_arr))

    n_modalities = float(
        (abp_feats[0] == abp_feats[0])  # not NaN
        + (hr_mean == hr_mean)
        + (ppg_mean == ppg_mean)
    )

    return np.concatenate(
        [abp_feats, np.array([hr_mean, hr_std, ppg_mean, ppg_std, n_modalities])]
    )


__all__ = [
    "ABP_FEATURE_NAMES",
    "MULTIMODAL_FEATURE_NAMES",
    "extract_abp_features",
    "extract_multimodal_features",
]
