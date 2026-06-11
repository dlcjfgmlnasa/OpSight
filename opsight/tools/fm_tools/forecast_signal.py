"""Tool: forecast_signal — [DEFERRED Stage 2] FM near-future trajectory forecast.
근미래 신호 궤적 예측 (FM decoder) — Stage 2 FM 통합 시 구현.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools._common import _deferred

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_forecast_signal(
    request: ToolRequest, clock: SimClock, signal: dict[str, torch.Tensor]
) -> ToolResponse:
    """[DEFERRED] Forecast a modality's near-future trajectory (FM decoder)."""
    return _deferred(request, time.perf_counter())
