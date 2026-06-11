"""Tool: predict_hypotension — [DEFERRED Stage 2] FM hypotension-risk forecast.
저혈압 위험 예측 (FM head) — Stage 2 FM 통합 시 구현.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools._common import _deferred

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_predict_hypotension(
    request: ToolRequest, clock: SimClock, signal: dict[str, torch.Tensor]
) -> ToolResponse:
    """[DEFERRED] Forecast hypotension risk over a horizon (FM head)."""
    return _deferred(request, time.perf_counter())
