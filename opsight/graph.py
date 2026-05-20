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

from opsight.nodes.deep_brief import run_deep_brief
from opsight.nodes.shallow_loop import run_shallow_loop
from opsight.signal_stream import SignalStream, stream_from_full_signal
from opsight.state import AgentState
from opsight.tools.envelope import ToolRequest
from opsight.tools.registry import call_tool
from opsight.triggers import should_escalate

if TYPE_CHECKING:
    import torch

    from opsight.fm.interface import BiosignalFMInterface
    from opsight.llm.client import LLMClient
    from opsight.sim_clock import SimClock
    from opsight.trace import TraceWriter


def build_graph(
    *,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor] | None = None,
    modalities: list[str],
    max_ticks: int = 20,
    tick_sim_advance_s: float = 30.0,
    trace: TraceWriter | None = None,
    signal_stream: SignalStream | None = None,
    llm_client: LLMClient | None = None,
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
        signal: legacy — full signal dict (entire trajectory exposed to tools).
            Use *either* ``signal`` or ``signal_stream``, not both.
        modalities: list of modality names present in ``signal`` / ``signal_stream``.
        max_ticks: maximum shallow ticks before END.
        tick_sim_advance_s: simulated seconds per tick (30 by default).
        trace: optional :class:`TraceWriter` for event logging.
        signal_stream: streaming-aware signal source (Sprint 6 — Issue #2).
            When provided, tools see only samples up to ``clock.now_s`` —
            strict real-time framing (brief §10).
            Legacy ``signal`` is wrapped into a stream automatically when
            ``signal_stream`` is None.

    Returns:
        Compiled LangGraph runnable.
    """
    # Streaming wiring (Sprint 6, real_case_run_findings Issue #2)
    # Stream wiring: 어느 한 쪽만 들어와야 한다.
    if signal_stream is not None and signal is not None:
        raise ValueError("pass either signal OR signal_stream, not both")
    if signal_stream is None:
        if signal is None:
            raise ValueError("must pass signal or signal_stream")
        # Wrap legacy full-signal in a stream for uniform downstream API.
        # Legacy full-signal 을 stream 으로 wrap (downstream 일관성).
        signal_stream = stream_from_full_signal(signal)

    def _case_init_node(state: AgentState) -> AgentState:
        """Run once at graph entry — populate case_baseline cache (ADR-018).
        그래프 진입 시 1회 실행 — case_baseline 캐시 채움 (ADR-018).

        Calls ``query_patient_baseline`` (Tool 12) which has no time-window
        leakage concern; result cached in ``state.case_baseline`` and
        injected into every subsequent shallow / deep narration prompt.
        Failure mode (tool error) → ``case_baseline`` remains ``None`` and
        downstream prompts simply omit baseline context (graceful degrade).
        """
        req = ToolRequest(
            case_id=state.case_id,
            sim_time_s=state.sim_time_s,
            tool_name="query_patient_baseline",
            args={},
        )
        resp = call_tool("query_patient_baseline", req, fm=fm, clock=clock,
                         signal=signal_stream.view_until(state.sim_time_s))
        if trace is not None:
            trace.event("case_init",
                        {"ok": resp.ok,
                         "baseline_keys": list((resp.result or {}).keys())},
                        sim_time_s=state.sim_time_s)
        baseline = resp.result if resp.ok and resp.result is not None else None
        return state.model_copy(update={"case_baseline": baseline})

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
        # Slice signal at sim_time — strict real-time view (Issue #2 fix).
        # sim_time 까지 slice — strict real-time view (Issue #2).
        sliced = signal_stream.view_until(state.sim_time_s)
        return run_shallow_loop(
            state, fm=fm, clock=clock, signal=sliced, modalities=modalities,
            trace=trace, llm_client=llm_client,
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
        sliced = signal_stream.view_until(state.sim_time_s)
        return run_deep_brief(
            state,
            fm=fm,
            clock=clock,
            signal=sliced,
            modalities=modalities,
            trigger_reason=reason,
            trace=trace,
            llm_client=llm_client,
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
    graph.add_node("case_init", _case_init_node)
    graph.add_node("shallow", _shallow_node)
    graph.add_node("deep", _deep_node)
    # ADR-018: case_init runs once at START before the shallow tick loop.
    # ADR-018: case_init 가 START 직후 1회 실행 후 shallow tick loop 진입.
    graph.add_edge(START, "case_init")
    graph.add_edge("case_init", "shallow")
    graph.add_conditional_edges(
        "shallow",
        _route,
        {"shallow": "shallow", "deep": "deep", "end": END},
    )
    # After deep, return to shallow to continue ticking / deep 후 shallow로 복귀.
    graph.add_edge("deep", "shallow")
    return graph.compile()


__all__ = ["build_graph"]
