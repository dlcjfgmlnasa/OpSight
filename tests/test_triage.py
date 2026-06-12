"""Tests for opsight.nodes.triage — router + investigation wiring (ADR-023).
opsight.nodes.triage 테스트 — router + 조사 배선.

- OBVIOUS_ALARM  → rule 알람 기록
- OBVIOUS_NORMAL → 알람 없음
- AMBIGUOUS + investigator → 조사 실행 + alarm_gate 가 알람 결정
- AMBIGUOUS + client 없음 → graceful skip (알람 없음)
- scratch["last_route"] 기록

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_triage.py -v
"""
from __future__ import annotations

import pytest

from opsight.envelope import ToolResponse
from opsight.nodes.investigate import InvestigateAction, InvestigationContext
from opsight.nodes.triage import run_triage
from opsight.sim_clock import SimClock
from opsight.state import AgentState


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)
    return c


def _state(vitals: dict, trends: dict | None = None) -> AgentState:
    results = [
        ToolResponse(case_id="c1", sim_time_s=30.0, tool_name="get_current_state",
                     result={"vitals": vitals}, quality_meta={}, latency_ms=0.0),
        ToolResponse(case_id="c1", sim_time_s=30.0, tool_name="summarize_current_state",
                     result={"trend_directions": trends or {}}, quality_meta={}, latency_ms=0.0),
    ]
    return AgentState(case_id="c1", trace_id="t1", sim_time_s=30.0,
                      last_tool_results=results)


class _FinalInvestigator:
    """Returns a final assessment immediately (no tool calls)."""

    name = "final-investigator"

    def __init__(self, assessment: dict) -> None:
        self._a = assessment

    def decide(self, context: InvestigationContext) -> InvestigateAction:
        return InvestigateAction(kind="final", assessment=self._a)


# ── Obvious paths ──


def test_obvious_alarm_records_rule_alarm(clock) -> None:
    st = _state({"map_mmHg": 55.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={})
    assert out.scratch["last_route"] == "obvious_alarm"
    assert len(out.alarm_history) == 1
    a = out.alarm_history[0]
    assert a.source == "rule" and a.route == "obvious_alarm"


def test_obvious_normal_no_alarm(clock) -> None:
    st = _state({"map_mmHg": 85.0, "hr_bpm": 72.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={})
    assert out.scratch["last_route"] == "obvious_normal"
    assert out.alarm_history == []


# ── Ambiguous → investigation ──


def test_ambiguous_with_investigator_high_risk_alarms(clock) -> None:
    st = _state({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={},
                     llm_client=_FinalInvestigator({"hypotension_risk": 0.8}))
    assert out.scratch["last_route"] == "ambiguous"
    assert out.scratch["last_investigation"]["assessment"]["hypotension_risk"] == 0.8
    assert len(out.alarm_history) == 1
    assert out.alarm_history[0].source == "investigation"


def test_ambiguous_with_investigator_low_risk_no_alarm(clock) -> None:
    st = _state({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={},
                     llm_client=_FinalInvestigator({"hypotension_risk": 0.2}))
    assert out.alarm_history == []
    assert out.scratch["last_investigation"]["assessment"]["hypotension_risk"] == 0.2


def test_ambiguous_without_client_skips_gracefully(clock) -> None:
    st = _state({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={}, llm_client=None)
    assert out.scratch["last_route"] == "ambiguous"
    assert out.scratch["last_investigation"] == {"skipped": "no_investigator_llm"}
    assert out.alarm_history == []


def test_non_investigator_client_skips(clock) -> None:
    # A narrate/brief-only client (no decide()) must not trigger investigation.
    class _NarrateOnly:
        name = "narrate-only"
        def narrate(self, tool_results): return ""
    st = _state({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={}, llm_client=_NarrateOnly())
    assert out.scratch["last_investigation"] == {"skipped": "no_investigator_llm"}
    assert out.alarm_history == []


def test_alarm_history_accumulates_across_ticks(clock) -> None:
    st = _state({"map_mmHg": 55.0})
    out1 = run_triage(st, clock=clock, signal={})
    out2 = run_triage(out1, clock=clock, signal={})
    assert len(out2.alarm_history) == 2  # functional update preserves prior alarms


# ── Graph integration ──


def test_triage_runs_inside_compiled_graph() -> None:
    """run_triage executes on every shallow tick of the compiled graph."""
    import torch

    from opsight.graph import build_graph

    gclock = SimClock(start_s=0.0)
    signal = {
        "ABP": torch.zeros(30 * 500), "ECG_II": torch.zeros(30 * 500),
        "PPG": torch.zeros(30 * 500), "BIS": torch.zeros(30 * 100),
    }
    graph = build_graph(
        clock=gclock, signal=signal, modalities=["ABP", "ECG_II", "PPG", "BIS"],
        max_ticks=2, tick_sim_advance_s=30.0,
    )
    final = graph.invoke(AgentState(case_id="c1", trace_id="t1"), {"recursion_limit": 50})
    final_state = final if isinstance(final, AgentState) else AgentState.model_validate(final)
    # Triage ran → a route was recorded each tick.
    assert final_state.scratch.get("last_route") in {
        "obvious_alarm", "obvious_normal", "ambiguous",
    }
