"""Baselines for hypotension prediction (plan_1.4).
저혈압 예측 baseline (plan_1.4).

본 module 은 4 개 baseline 의 정식 구현 (logreg / LSTM / xgb / hatib-style)
+ 공통 label / feature / split + FM-adapter (plan_1.7.5 Tier 3 mock FM unblock) 를
제공한다.

This module ships 4 baselines (logreg / LSTM / xgb / hatib-style) plus
shared label / feature / split utilities and an FM adapter that wraps any
baseline as ``BiosignalFMInterface`` (unblocks plan_1.7.5 Tier 3 Mock FM).
"""
from __future__ import annotations

from vitalagent.baselines.fm_adapter import BaselineFMAdapter
from vitalagent.baselines.types import (
    BaselineConfig,
    BaselinePredictor,
    BaselineResult,
)

__all__ = [
    "BaselineFMAdapter",
    "BaselineConfig",
    "BaselinePredictor",
    "BaselineResult",
]
