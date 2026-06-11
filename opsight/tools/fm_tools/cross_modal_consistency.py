"""Tool: cross_modal_consistency — [DEFERRED Stage 2] FM cross-modal agreement.
모달리티 간 일관성 점수 (FM latent) — Stage 2 FM 통합 시 구현.

Note: trigger #4 (``opsight/triggers.py::_check_cross_modal_inconsistency``)
consumes this tool's ``result.score``; the trigger stays dormant until this
lands at Stage 2.
주의: trigger #4 가 본 tool 의 ``result.score`` 를 소비한다. Stage 2 복원 전까지
trigger #4 는 dormant.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools._common import _deferred

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_cross_modal_consistency(
    request: ToolRequest, clock: SimClock, signal: dict[str, torch.Tensor]
) -> ToolResponse:
    """[DEFERRED] Cross-modal agreement score (FM latent) — feeds trigger #4."""
    return _deferred(request, time.perf_counter())
