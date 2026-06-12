"""Triage step — wires the router + investigation into the shallow tick (ADR-023).
Triage 단계 — router + 조사를 shallow tick 에 배선 (ADR-023).

Runs AFTER ``run_shallow_loop`` on each tick. Classifies the tick with the
rule-based :func:`route_tick`, then dispatches:

- ``OBVIOUS_ALARM``  → record a ``"rule"`` alarm immediately.
- ``OBVIOUS_NORMAL`` → nothing.
- ``AMBIGUOUS``      → run bounded LLM investigation (if a decide()-capable
  client is available), then the rule ``alarm_gate`` decides whether to alarm.

자율성 경계(ADR-023): LLM 은 ``AMBIGUOUS`` 조사 안에서만 tool 을 고르고, **알람은
항상 rule**(obvious_alarm 또는 ``alarm_gate``)이 결정한다. decide() 가능한 client 가
없으면 조사는 graceful 하게 skip 된다(알람 안전성 유지 — 애매는 알람 없이 통과).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from opsight.nodes.investigate import (
    DEFAULT_INVESTIGATE_TOOLS,
    MAX_INVESTIGATE_STEPS,
    InvestigatorLLM,
    alarm_gate,
    llm_investigate,
)
from opsight.router import (
    DEFAULT_CONFIG,
    Route,
    RouterConfig,
    extract_router_inputs,
    route_tick,
)
from opsight.state import AgentState, AlarmRecord

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock
    from opsight.trace import TraceWriter


def run_triage(
    state: AgentState,
    *,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    llm_client: object | None = None,
    trace: TraceWriter | None = None,
    router_config: RouterConfig = DEFAULT_CONFIG,
    investigate_tools: tuple[str, ...] = DEFAULT_INVESTIGATE_TOOLS,
    max_investigate_steps: int = MAX_INVESTIGATE_STEPS,
) -> AgentState:
    """Classify the current tick and raise alarms per the tiered policy (ADR-023).
    현재 tick 을 분류하고 tiered 정책에 따라 알람을 올린다 (ADR-023).

    Reads vitals/trends from ``state.last_tool_results`` (the shallow sweep).
    Returns a new ``AgentState`` with ``alarm_history`` / ``scratch`` updated;
    never raises on a missing/limited LLM (graceful degrade).
    """
    vitals, trends, quality = extract_router_inputs(state.last_tool_results)
    # quality from assess_signal_quality (SQI); agreement (cross-modal) has no
    # producer yet → None (skip). A clear breach on low-quality signal routes to
    # investigation (possible artifact) instead of an immediate alarm (ADR-023).
    decision = route_tick(vitals, trends, quality=quality, config=router_config)

    alarms = list(state.alarm_history)
    scratch = dict(state.scratch)
    scratch["last_route"] = decision.route.value
    # Per-tick deep-escalation signal (ADR-023 §5): set to the alarm reason when
    # a rule/investigation alarm is confirmed THIS tick; ``should_escalate`` reads
    # it to fire the deep brief. Reset each tick so a stale alarm doesn't persist.
    # 매 tick deep escalation 신호 — 이번 tick 알람 확정 시 reason 세팅(없으면 None).
    scratch["triage_alarm_reason"] = None

    if trace is not None:
        trace.event(
            "route",
            {"route": decision.route.value, "reasons": decision.reasons},
            sim_time_s=state.sim_time_s,
        )

    if decision.route is Route.OBVIOUS_ALARM:
        reason = "; ".join(decision.reasons) or "obvious_alarm"
        alarms.append(AlarmRecord(
            sim_time_s=state.sim_time_s, source="rule",
            route=decision.route.value, reason=reason,
        ))
        scratch["triage_alarm_reason"] = f"obvious_alarm ({reason})"
        if trace is not None:
            trace.event("alarm", {"source": "rule", "reason": reason},
                        sim_time_s=state.sim_time_s)

    elif decision.route is Route.AMBIGUOUS:
        if isinstance(llm_client, InvestigatorLLM):
            result = llm_investigate(
                route_decision=decision, vitals=vitals,
                clock=clock, signal=signal, llm_client=llm_client,
                case_id=state.case_id, sim_time_s=state.sim_time_s,
                available_tools=investigate_tools, max_steps=max_investigate_steps,
                trace=trace,
            )
            scratch["last_investigation"] = {
                "assessment": result.assessment,
                "tools_used": result.tools_used,
                "steps": result.steps,
                "hit_step_limit": result.hit_step_limit,
            }
            fire, gate_reason = alarm_gate(result.assessment)
            if fire:
                alarms.append(AlarmRecord(
                    sim_time_s=state.sim_time_s, source="investigation",
                    route=decision.route.value, reason=gate_reason,
                ))
                scratch["triage_alarm_reason"] = f"investigation ({gate_reason})"
                if trace is not None:
                    trace.event("alarm", {"source": "investigation", "reason": gate_reason},
                                sim_time_s=state.sim_time_s)
        else:
            # No decide()-capable client → investigation skipped (graceful).
            scratch["last_investigation"] = {"skipped": "no_investigator_llm"}
            if trace is not None:
                trace.event("investigate_skipped", {"reason": "no_investigator_llm"},
                            sim_time_s=state.sim_time_s)

    # OBVIOUS_NORMAL → no action.

    return state.model_copy(update={"alarm_history": alarms, "scratch": scratch})


__all__ = ["run_triage"]
