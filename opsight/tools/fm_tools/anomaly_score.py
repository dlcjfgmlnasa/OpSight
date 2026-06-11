"""Tool: anomaly_score — [DEFERRED Stage 2] FM reconstruction-based anomaly score.
재구성 기반 이상치 점수 (FM) — Stage 2 FM 통합 시 구현.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools._common import _deferred

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_anomaly_score(
    request: ToolRequest, clock: SimClock, signal: dict[str, torch.Tensor]
) -> ToolResponse:
    """[DEFERRED] Reconstruction-based anomaly score from the FM."""
    return _deferred(request, time.perf_counter())
