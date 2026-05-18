"""Hypotension label definition (plan_1.4 data contract).
저혈압 라벨 정의 (plan_1.4 data contract).

Brief §5 mirror:
    label_h5  = (MAP < 65 sustained ≥ 1 min within next 5 min)
    label_h15 = (MAP < 65 sustained ≥ 1 min within next 15 min)

Brief §5 미러:
    label_h5  = (다음 5분 안에 MAP < 65 가 ≥ 1분 지속)
    label_h15 = (다음 15분 안에 MAP < 65 가 ≥ 1분 지속)
"""
from __future__ import annotations

from typing import Any

import numpy as np


HYPOTENSION_MAP_THRESHOLD_MMHG: float = 65.0
HYPOTENSION_MIN_DURATION_S: float = 60.0


def label_hypotension_window(
    map_trace: np.ndarray,
    sampling_rate_hz: float,
    horizon_s: float,
    *,
    map_threshold_mmhg: float = HYPOTENSION_MAP_THRESHOLD_MMHG,
    min_duration_s: float = HYPOTENSION_MIN_DURATION_S,
) -> int:
    """Return 1 if hypotension event occurs in ``map_trace[:horizon_s]``.
    ``map_trace[:horizon_s]`` 안에 저혈압 event 발생 시 1 반환.

    Args:
        map_trace: future MAP samples (1-D), values in mmHg. Must start at the
            prediction point (sample 0 = t+0).
            미래 MAP sample (1-D, mmHg). sample 0 = 예측 시점.
        sampling_rate_hz: samples per second / 초당 sample 수.
        horizon_s: prediction horizon in seconds / 예측 horizon (초).
        map_threshold_mmhg: MAP threshold for hypotension / 저혈압 MAP 임계.
        min_duration_s: minimum sustained duration / 최소 지속 시간.

    Returns:
        0 or 1.
    """
    arr = np.asarray(map_trace, dtype=np.float64)
    horizon_samples = int(round(horizon_s * sampling_rate_hz))
    horizon_samples = min(horizon_samples, len(arr))
    if horizon_samples <= 0:
        return 0
    window = arr[:horizon_samples]

    # NaN-safe: NaN 은 "no event" 로 처리
    # NaN-safe: NaN treated as "no event"
    below = np.where(np.isnan(window), False, window < map_threshold_mmhg)

    min_samples = int(round(min_duration_s * sampling_rate_hz))
    if min_samples <= 0:
        return int(below.any())

    # 연속 True run 의 최대 길이 / max length of consecutive True run
    if not below.any():
        return 0
    # vectorized run-length / vectorized run-length 계산
    runs = np.diff(np.flatnonzero(np.r_[True, below[:-1] != below[1:], True]))
    # runs alternates [first_run_len, ...] for True/False per below[0]
    if below[0]:
        true_runs = runs[::2]
    else:
        true_runs = runs[1::2]
    if len(true_runs) == 0:
        return 0
    return int(true_runs.max() >= min_samples)


def label_h5(map_trace: np.ndarray, sampling_rate_hz: float, **kwargs: Any) -> int:
    """Label at 5-minute horizon / 5분 horizon label."""
    return label_hypotension_window(map_trace, sampling_rate_hz, horizon_s=300.0, **kwargs)


def label_h15(map_trace: np.ndarray, sampling_rate_hz: float, **kwargs: Any) -> int:
    """Label at 15-minute horizon / 15분 horizon label."""
    return label_hypotension_window(map_trace, sampling_rate_hz, horizon_s=900.0, **kwargs)


__all__ = [
    "HYPOTENSION_MAP_THRESHOLD_MMHG",
    "HYPOTENSION_MIN_DURATION_S",
    "label_hypotension_window",
    "label_h5",
    "label_h15",
]
