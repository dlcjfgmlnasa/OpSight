"""Sampling-rate detection + simple resample.
Sampling rate 감지 + 단순 resample.

Reference: BFM `data/parser/_common.py::resample_to_target` (scipy.signal.resample_poly).
본 module 은 numpy-only 단순 구현 — prototype scope. 정확한 resampling 이
필요하면 scipy 사용 권장.
"""
from __future__ import annotations

import numpy as np


def detect_sampling_rate(
    arr_length: int, total_duration_s: float,
) -> float:
    """Detect sampling rate Hz from array length + total duration.
    Array 길이 + 총 duration 에서 sampling rate (Hz) 감지.

    real_case_run_findings Issue #3 ("Sampling rate mismatch") 의 자동 추론용.

    Args:
        arr_length: number of samples.
        total_duration_s: covered time span in seconds.

    Returns:
        Sampling rate in Hz. Returns 0.0 if duration <= 0.
    """
    if total_duration_s <= 0:
        return 0.0
    return float(arr_length) / float(total_duration_s)


def resample_numpy(
    arr: np.ndarray, *, source_hz: float, target_hz: float,
) -> np.ndarray:
    """Simple resample via linear interpolation.
    선형 interpolation 으로 단순 resample.

    For prototype use only. scipy.signal.resample_poly is preferred when
    available (BFM upstream). NaN samples are preserved across resample:
    target sample inherits NaN if any source neighbor is NaN.
    Prototype 용. NaN 은 보존 (target sample 의 source neighbor 중 NaN 이
    있으면 target 도 NaN).
    """
    if arr.ndim != 1:
        raise ValueError(f"expected 1-D array, got shape {arr.shape}")
    if source_hz <= 0 or target_hz <= 0:
        raise ValueError(f"sampling rates must be positive (source={source_hz}, target={target_hz})")
    if source_hz == target_hz:
        return arr.astype(np.float64, copy=True)

    n_source = arr.size
    duration_s = n_source / source_hz
    n_target = int(round(duration_s * target_hz))
    if n_target <= 1:
        return np.array([float(np.nanmean(arr))], dtype=np.float64)

    src_indices = np.linspace(0, n_source - 1, num=n_target, dtype=np.float64)
    src_floor = np.floor(src_indices).astype(np.int64)
    src_ceil = np.minimum(src_floor + 1, n_source - 1)
    frac = src_indices - src_floor

    src_arr = arr.astype(np.float64)
    # NaN propagation: result is NaN if either neighbor is NaN
    nan_mask = np.isnan(src_arr[src_floor]) | np.isnan(src_arr[src_ceil])
    # Replace NaN with 0 for arithmetic, then re-mask
    safe = np.where(np.isnan(src_arr), 0.0, src_arr)
    out = (1.0 - frac) * safe[src_floor] + frac * safe[src_ceil]
    out[nan_mask] = np.nan
    return out


__all__ = ["detect_sampling_rate", "resample_numpy"]
