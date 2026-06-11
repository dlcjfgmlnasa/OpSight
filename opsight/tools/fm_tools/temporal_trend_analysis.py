"""Tool: temporal_trend_analysis — [DEFERRED Stage 2] FM temporal trend.
FM 기반 시간적 추세 / 변화점 분석 — Stage 2 FM 통합 시 구현.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools._common import _deferred

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_temporal_trend_analysis(
    request: ToolRequest, clock: SimClock, signal: dict[str, torch.Tensor]
) -> ToolResponse:
    """[DEFERRED] FM-derived temporal trend / change-point over a window."""
    return _deferred(request, time.perf_counter())
