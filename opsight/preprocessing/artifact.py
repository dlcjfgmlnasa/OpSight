"""Artifact removal — physiological clipping + short NaN-gap interpolation.
아티팩트 제거 — physiological clipping + short NaN-gap interpolation.

Reference: BFM `data/parser/vitaldb.py` 의 range-check + NaN-gap fill.
본 module 은 *minimum subset* — 1st/2nd-derivative spike detection 같은
heavy artifact removal 은 prototype scope 밖.
"""
from __future__ import annotations

import numpy as np


def clip_to_physiological(
    arr: np.ndarray, *, min_val: float, max_val: float,
) -> tuple[np.ndarray, dict[str, float]]:
    """Mask out-of-range samples to NaN.
    범위 밖 sample 을 NaN 으로 mask.

    real_case_run_findings Issue #1 ("MAP −9 / 344 sensor artifact") 의 직접 대응.

    Args:
        arr: 1-D float numpy array.
        min_val / max_val: physiological plausible bounds.

    Returns:
        (cleaned_arr, report) where ``report = {n_low, n_high, ratio_clipped}``.
        (cleaned_arr, report). report 에 clip 통계 포함.
    """
    if arr.ndim != 1:
        raise ValueError(f"expected 1-D array, got shape {arr.shape}")

    cleaned = arr.astype(np.float64, copy=True)
    # Pre-existing NaN preserved
    pre_nan = np.isnan(cleaned)
    below = (cleaned < min_val) & ~pre_nan
    above = (cleaned > max_val) & ~pre_nan
    cleaned[below] = np.nan
    cleaned[above] = np.nan

    n_total = int(arr.size)
    report = {
        "n_total": n_total,
        "n_below": int(below.sum()),
        "n_above": int(above.sum()),
        "ratio_clipped": float((below | above).sum()) / max(1, n_total),
        "pre_existing_nan_ratio": float(pre_nan.sum()) / max(1, n_total),
    }
    return cleaned, report


def fill_short_nan_gaps(
    arr: np.ndarray, *, max_gap_samples: int,
) -> tuple[np.ndarray, dict[str, int]]:
    """Linearly interpolate NaN gaps shorter than ``max_gap_samples``.
    ``max_gap_samples`` 미만 NaN 구간을 선형 interpolation 으로 채움.

    Longer gaps stay NaN. Boundary NaN (head / tail) never extrapolated.
    더 긴 gap 은 NaN 유지. 시작/끝 NaN 은 extrapolation 안 함.

    Args:
        arr: 1-D float numpy array.
        max_gap_samples: longest NaN-run length to fill.

    Returns:
        (filled_arr, report) with ``n_filled`` + ``n_left_nan``.
    """
    if arr.ndim != 1:
        raise ValueError(f"expected 1-D array, got shape {arr.shape}")

    out = arr.astype(np.float64, copy=True)
    nan_mask = np.isnan(out)
    if not nan_mask.any():
        return out, {"n_filled": 0, "n_left_nan": 0, "n_skipped_long_gap": 0}

    # Find contiguous NaN runs / 연속 NaN 구간 찾기
    n = len(out)
    n_filled = 0
    n_left_nan = 0
    n_skipped_long_gap = 0

    # Identify run boundaries via diff / diff 로 run 경계 식별
    diff = np.diff(nan_mask.astype(np.int8), prepend=0, append=0)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]

    for start, end in zip(starts, ends):
        gap_len = end - start
        # Boundary NaN — no extrapolation
        if start == 0 or end == n:
            n_left_nan += gap_len
            continue
        if gap_len > max_gap_samples:
            n_skipped_long_gap += gap_len
            n_left_nan += gap_len
            continue
        # Linear interpolation between out[start-1] and out[end]
        left_val = out[start - 1]
        right_val = out[end]
        if np.isnan(left_val) or np.isnan(right_val):
            # neighbor itself NaN — shouldn't happen given run extraction
            n_left_nan += gap_len
            continue
        out[start:end] = np.linspace(
            left_val, right_val, num=gap_len + 2,
        )[1:-1]
        n_filled += gap_len

    return out, {
        "n_filled": int(n_filled),
        "n_left_nan": int(n_left_nan),
        "n_skipped_long_gap": int(n_skipped_long_gap),
    }


__all__ = ["clip_to_physiological", "fill_short_nan_gaps"]
