"""Tests for opsight.nodes.investigate — bounded ReAct + alarm gate (ADR-023).
opsight.nodes.investigate 테스트 — bounded ReAct + 알람 rule gate.

- LLM 이 tool 을 골라 호출 → 관찰 → final assessment
- max_steps 도달 시 hit_step_limit
- whitelist 밖/미등록 tool 은 거부(호출 안 함)
- alarm_gate: LLM 예측치 → rule 이 알람 결정 (LLM 아님)

Hermetic: scripted InvestigatorLLM double — 실제 vLLM 불필요.

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_investigate.py -v
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.nodes.investigate import (
    DEFAULT_INVESTIGATE_TOOLS,
    InvestigateAction,
    InvestigationContext,
    InvestigatorLLM,
    alarm_gate,
    llm_investigate,
)
from opsight.router import Route, RouteDecision
from opsight.sim_clock import SimClock


# ── Fixtures / doubles ──


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)
    return c


@pytest.fixture
def signal() -> dict[str, torch.Tensor]:
    return {
        "MAP": torch.from_numpy(np.full(300, 68.0, dtype=np.float32)),
        "HR": torch.from_numpy(np.full(300, 88.0, dtype=np.float32)),
    }


@pytest.fixture
def ambiguous_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.AMBIGUOUS,
        reasons=["borderline: map_mmHg=63.0"],
        clear_breaches=[],
        borderline=["map_mmHg=63.0"],
        missing=[],
    )


class _Scripted:
    """Replays a fixed action list; pads with a final action when exhausted."""

    name = "scripted-investigator"

    def __init__(self, actions: list[InvestigateAction]) -> None:
        self._a = list(actions)
        self._i = 0
        self.contexts: list[InvestigationContext] = []

    def decide(self, context: InvestigationContext) -> InvestigateAction:
        self.contexts.append(context)
        if self._i < len(self._a):
            act = self._a[self._i]
            self._i += 1
            return act
        return InvestigateAction(kind="final", assessment={})


class _AlwaysTool:
    """Never finalizes — always asks for the same tool (drives step-limit)."""

    name = "always-tool-investigator"

    def __init__(self, tool: str) -> None:
        self._t = tool

    def decide(self, context: InvestigationContext) -> InvestigateAction:
        return InvestigateAction(kind="tool_call", tool_name=self._t, args={})


def _run(client, decision, clock, signal, **kw):
    return llm_investigate(
        route_decision=decision, vitals={"map_mmHg": 63.0},
        clock=clock, signal=signal, llm_client=client,
        case_id="c1", sim_time_s=30.0, **kw,
    )


# ── Loop behaviour ──


def test_tool_then_final(clock, signal, ambiguous_decision) -> None:
    client = _Scripted([
        InvestigateAction(kind="tool_call", tool_name="get_signal_trend", args={}),
        InvestigateAction(kind="final",
                          assessment={"hypotension_risk": 0.8, "rationale": "MAP drift"}),
    ])
    res = _run(client, ambiguous_decision, clock, signal)
    assert res.tools_used == ["get_signal_trend"]
    assert res.hit_step_limit is False
    assert res.steps == 1                      # final emitted on step index 1
    assert res.assessment["hypotension_risk"] == 0.8
    assert len(res.observations) == 1 and res.observations[0].ok


def test_step_limit_reached(clock, signal, ambiguous_decision) -> None:
    res = _run(_AlwaysTool("get_signal_trend"), ambiguous_decision, clock, signal,
               max_steps=3)
    assert res.hit_step_limit is True
    assert res.steps == 3
    assert res.tools_used == ["get_signal_trend"] * 3
    assert res.assessment == {}


def test_context_accumulates_observations(clock, signal, ambiguous_decision) -> None:
    client = _Scripted([
        InvestigateAction(kind="tool_call", tool_name="get_signal_trend", args={}),
        InvestigateAction(kind="tool_call", tool_name="assess_variability",
                          args={"modality": "HR"}),
        InvestigateAction(kind="final", assessment={"hypotension_risk": 0.2}),
    ])
    res = _run(client, ambiguous_decision, clock, signal)
    assert res.tools_used == ["get_signal_trend", "assess_variability"]
    # 3rd decide() call saw the 2 prior observations.
    assert len(client.contexts[2].observations) == 2


# ── Whitelist / safety ──


def test_non_whitelisted_tool_rejected(clock, signal, ambiguous_decision) -> None:
    # get_patient_context IS registered but NOT in the investigate whitelist.
    assert "get_patient_context" not in DEFAULT_INVESTIGATE_TOOLS
    client = _Scripted([
        InvestigateAction(kind="tool_call", tool_name="get_patient_context", args={}),
        InvestigateAction(kind="final", assessment={"hypotension_risk": 0.1}),
    ])
    res = _run(client, ambiguous_decision, clock, signal)
    assert res.tools_used == []                # rejected, not called
    assert res.assessment["hypotension_risk"] == 0.1


def test_unknown_tool_rejected(clock, signal, ambiguous_decision) -> None:
    client = _Scripted([
        InvestigateAction(kind="tool_call", tool_name="nonexistent_tool", args={}),
        InvestigateAction(kind="final", assessment={}),
    ])
    res = _run(client, ambiguous_decision, clock, signal)
    assert res.tools_used == []


def test_scripted_double_satisfies_protocol() -> None:
    assert isinstance(_Scripted([]), InvestigatorLLM)


# ── Alarm rule gate ──


def test_alarm_gate_fires_above_tau() -> None:
    fire, reason = alarm_gate({"hypotension_risk": 0.8})
    assert fire is True
    assert "hypotension_risk" in reason


def test_alarm_gate_silent_below_tau() -> None:
    assert alarm_gate({"hypotension_risk": 0.5}) == (False, "investigation_below_alarm_gate")


def test_alarm_gate_handles_missing_and_bool() -> None:
    assert alarm_gate({})[0] is False
    assert alarm_gate({"hypotension_risk": True})[0] is False  # bool is not a real risk


def test_alarm_gate_custom_tau() -> None:
    assert alarm_gate({"hypotension_risk": 0.55}, tau=0.5)[0] is True
