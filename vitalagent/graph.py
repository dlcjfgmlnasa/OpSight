"""LangGraph wiring (plan_1.8 task 8).
LangGraph wiring (plan_1.8 task 8).

Wires the shallow / deep nodes into a StateGraph. Edges:
shallow / deep node를 StateGraph로 연결. Edge:

    START → shallow → (escalate?) → deep → shallow → END (after N ticks)

The graph runs for a configurable number of ticks per simulated case. Each
tick advances :class:`SimClock` by 30 s. Trigger evaluation happens in a
conditional edge after each shallow tick.
Graph는 시뮬레이션 case당 configurable 횟수만큼 실행된다. 각 tick은
:class:`SimClock`을 30초 진행. Trigger 평가는 각 shallow tick 후 conditional
edge에서 수행.

FM is consumed ONLY through :class:`BiosignalFMInterface` here — no
concrete-class import (ADR-011 swap mechanism, project_brief §13).
본 module에서 FM은 :class:`BiosignalFMInterface`를 통해서만 소비된다 —
concrete class import 금지 (ADR-011 swap, brief §13).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from langgraph.graph import END, START, StateGraph

from vitalagent.nodes.deep_brief import run_deep_brief
from vitalagent.nodes.shallow_loop import run_shallow_loop
from vitalagent.state import AgentState
from vitalagent.triggers import should_escalate

if TYPE_CHECKING:
    import torch

    from vitalagent.fm.interface import BiosignalFMInterface
    from vitalagent.sim_clock import SimClock
    from vitalagent.trace import TraceWriter


def build_graph(
    *,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    modalities: list[str],
    max_ticks: int = 20,
    tick_sim_advance_s: float = 30.0,
    trace: TraceWriter | None = None,
):
    """Build a compiled dual-mode StateGraph.
    Compiled dual-mode StateGraph를 빌드한다.

    The returned graph, when invoked with an initial :class:`AgentState`,
    runs up to ``max_ticks`` shallow ticks. After each tick, the trigger
    engine decides whether to fire a deep brief. The simulated clock
    advances by ``tick_sim_advance_s`` per shallow tick.
    초기 :class:`AgentState`로 호출되면 ``max_ticks`` 회의 shallow tick을
    실행한다. 각 tick 후 trigger engine이 deep brief 발화 여부를 결정.
    Simulated clock은 shallow tick당 ``tick_sim_advance_s``만큼 진행.

    Args:
        fm: Protocol-compliant FM backend (mock_stub / mock_rule_based /
            real). Consumed via Protocol only.
        clock: SimClock instance.
        signal: dict modality → torch.Tensor (synthetic OK).
        modalities: list of modality names present in ``signal``.
        max_ticks: maximum shallow ticks before END.
        tick_sim_advance_s: simulated seconds per tick (30 by default).
        trace: optional :class:`TraceWriter` for event logging.

    Returns:
        Compiled LangGraph runnable.
    """

    def _shallow_node(state: AgentState) -> AgentState:
        # Advance the sim clock BEFORE running the shallow loop / shallow loop
        # 실행 전에 sim clock 진행.
        clock.tick(tick_sim_advance_s)
        state = state.model_copy(
            update={
                "sim_time_s": clock.now_s,
                "scratch": {**state.scratch, "tick_count": state.scratch.get("tick_count", 0) + 1},
            }
        )
        if trace is not None:
            trace.event("tick", {"tick_count": state.scratch["tick_count"]}, sim_time_s=state.sim_time_s)
        return run_shallow_loop(
            state, fm=fm, clock=clock, signal=signal, modalities=modalities, trace=trace
        )

    def _deep_node(state: AgentState) -> AgentState:
        _fire, reason = should_escalate(state)
        # ``reason`` is non-None here because ``_route`` only routes to deep
        # when the trigger fires.
        # ``_route``가 trigger 발화 시에만 deep으로 라우팅하므로 ``reason``은
        # 여기서 항상 non-None.
        assert reason is not None
        if trace is not None:
            trace.event("trigger", {"reason": reason}, sim_time_s=state.sim_time_s)
        return run_deep_brief(
            state,
            fm=fm,
            clock=clock,
            signal=signal,
            modalities=modalities,
            trigger_reason=reason,
            trace=trace,
        )

    def _route(state: AgentState) -> str:
        """Conditional edge: deep vs continue vs end.
        조건부 edge: deep vs continue vs end.
        """
        tick_count = state.scratch.get("tick_count", 0)
        if tick_count >= max_ticks:
            return "end"
        fire, _reason = should_escalate(state)
        if fire:
            return "deep"
        return "shallow"

    graph: StateGraph = StateGraph(AgentState)
    graph.add_node("shallow", _shallow_node)
    graph.add_node("deep", _deep_node)
    graph.add_edge(START, "shallow")
    graph.add_conditional_edges(
        "shallow",
        _route,
        {"shallow": "shallow", "deep": "deep", "end": END},
    )
    # After deep, return to shallow to continue ticking / deep 후 shallow로 복귀.
    graph.add_edge("deep", "shallow")
    return graph.compile()


__all__ = ["build_graph"]
