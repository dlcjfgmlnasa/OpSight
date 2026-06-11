"""Tool: predict_cardiac_arrest — [DEFERRED Stage 2] FM cardiac-arrest forecast.
심정지 위험 예측 (FM head) — Stage 2 FM 통합 시 구현.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools._common import _deferred

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_predict_cardiac_arrest(
    request: ToolRequest, clock: SimClock, signal: dict[str, torch.Tensor]
) -> ToolResponse:
    """[DEFERRED] Forecast cardiac-arrest risk over a horizon (FM head)."""
    return _deferred(request, time.perf_counter())
