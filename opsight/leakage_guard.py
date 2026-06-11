"""Shared time-leakage guard primitive (plan_1.3 task 1).
공유 time-leakage guard primitive (plan_1.3 task 1).

project_brief §13.2 (No-data-leakage rule): at simulated time ``t`` a tool may
only read data at or before ``t``. Any time-window query whose end exceeds the
sim-clock ``clock.now_s`` must fail explicitly rather than silently leak future
information.
project_brief §13.2 (데이터 누수 금지): 시뮬레이션 시점 ``t`` 에서는 ``t`` 이하의
데이터만 읽을 수 있다. window 끝이 sim-clock ``clock.now_s`` 를 초과하는 모든
조회는 미래 정보를 조용히 누설하지 않고 명시적으로 실패해야 한다.

This module is the single source of truth for the guard. The signal-state tools
(``opsight/tools/signal_state_tools.py``) consume it (ADR-021 §"Leakage guard
일관성"; plan_1.3.5 reuses the same guard).
본 module 은 guard 의 단일 진실 원천이다. EMR tool 과 Signal Access tool 이 모두
소비한다 (ADR-021; plan_1.3.5 동일 guard 재사용).

Two entry points:
- ``assert_le(t, query_window_end)`` — the bare primitive (plan_1.3 task 1
  signature). Raises ``LeakageViolation`` when ``query_window_end > t``.
- ``leakage_guard(request, clock, query_window_end_s, ...)`` — the envelope-aware
  wrapper that converts a violation into the structured ``ToolResponse`` /
  ``leakage_violation`` error shape callers already depend on.
두 진입점: ``assert_le`` (bare primitive) + ``leakage_guard`` (envelope wrapper).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opsight.envelope import ToolError, ToolRequest, ToolResponse

if TYPE_CHECKING:
    from opsight.sim_clock import SimClock


class LeakageViolation(AssertionError):
    """Raised by ``assert_le`` when a query window extends past the sim clock.
    query window 이 sim clock 을 초과할 때 ``assert_le`` 가 raise.
    """

    def __init__(self, t: float, query_window_end: float) -> None:
        self.t = t
        self.query_window_end = query_window_end
        super().__init__(
            f"query_window_end={query_window_end} exceeds sim-time t={t}"
        )


def assert_le(t: float, query_window_end: float) -> None:
    """Assert ``query_window_end <= t`` (plan_1.3 task 1 primitive).
    ``query_window_end <= t`` 를 단언한다 (plan_1.3 task 1 primitive).

    Args:
        t: current simulated clock value (seconds). 현재 시뮬레이션 clock (초).
        query_window_end: end of the requested data window (seconds).
            요청된 데이터 window 의 끝 (초).

    Raises:
        LeakageViolation: when ``query_window_end > t`` (future-data leakage).
            ``query_window_end > t`` (미래 데이터 누수) 일 때.
    """
    if query_window_end > t:
        raise LeakageViolation(t, query_window_end)


def leakage_guard(
    request: ToolRequest,
    clock: SimClock,
    query_window_end_s: float,
    *,
    quality_meta: dict[str, Any] | None = None,
    include_extra: bool = False,
) -> ToolResponse | None:
    """Envelope-aware leakage guard.
    Envelope 인지 leakage guard.

    Returns ``None`` when the query is in-bounds (caller proceeds), or a
    ``ToolResponse`` carrying a ``leakage_violation`` ``ToolError`` when the
    window end exceeds ``clock.now_s`` (caller returns it directly).
    조회가 범위 내면 ``None`` 반환 (caller 진행), window 끝이 ``clock.now_s`` 를
    초과하면 ``leakage_violation`` 에러를 담은 ``ToolResponse`` 반환.

    Args:
        request: the tool request envelope.
        clock: simulated clock — ``clock.now_s`` is the read boundary.
        query_window_end_s: end of the requested data window (seconds).
        quality_meta: quality_meta to attach to the error response. Defaults to
            ``{}`` so callers can pass their category marker (e.g.
            ``{"emr_stub": True}`` or ``{"category": "signal_access"}``).
        include_extra: when ``True``, attach ``query_window_end_s`` /
            ``clock_now_s`` to ``ToolError.extra`` (Signal Access convention).
    """
    if query_window_end_s > clock.now_s:
        extra: dict[str, Any] = {}
        if include_extra:
            extra = {
                "query_window_end_s": query_window_end_s,
                "clock_now_s": clock.now_s,
            }
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="leakage_violation",
                message=(
                    f"query_window_end_s={query_window_end_s} exceeds "
                    f"clock.now_s={clock.now_s}"
                ),
                extra=extra,
            ),
            quality_meta=dict(quality_meta) if quality_meta else {},
            latency_ms=0.0,
        )
    return None


__all__ = ["LeakageViolation", "assert_le", "leakage_guard"]
