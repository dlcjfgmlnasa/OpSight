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


def _state(vitals: dict, trends: dict | None = None,
           quality: float | None = None) -> AgentState:
    results = [
        ToolResponse(case_id="c1", sim_time_s=30.0, tool_name="get_current_state",
                     result={"vitals": vitals}, quality_meta={}, latency_ms=0.0),
        ToolResponse(case_id="c1", sim_time_s=30.0, tool_name="summarize_current_state",
                     result={"trend_directions": trends or {}}, quality_meta={}, latency_ms=0.0),
    ]
    if quality is not None:
        results.append(ToolResponse(
            case_id="c1", sim_time_s=30.0, tool_name="assess_signal_quality",
            result={"primary_worst": quality}, quality_meta={}, latency_ms=0.0))
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


# ── Escalation signal (ADR-023 §5): alarm → deep-brief trigger ──


def test_obvious_alarm_sets_escalation_signal(clock) -> None:
    st = _state({"map_mmHg": 45.0})
    out = run_triage(st, clock=clock, signal={})
    assert out.scratch["triage_alarm_reason"] is not None
    assert "obvious_alarm" in out.scratch["triage_alarm_reason"]


def test_obvious_normal_clears_escalation_signal(clock) -> None:
    st = _state({"map_mmHg": 85.0, "hr_bpm": 72.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={})
    assert out.scratch["triage_alarm_reason"] is None


def test_investigation_alarm_sets_escalation_signal(clock) -> None:
    st = _state({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    out = run_triage(st, clock=clock, signal={},
                     llm_client=_FinalInvestigator({"hypotension_risk": 0.8}))
    assert "investigation" in out.scratch["triage_alarm_reason"]


def test_investigation_alarm_suppressed_on_artifact_quality(clock) -> None:
    # MAP 20 with artifact-quality signal: investigation says risk 1.0 but the
    # alarm is SUPPRESSED (likely line flush, not real). (ADR-023 / case-1 finding.)
    st = _state({"map_mmHg": 20.0, "hr_bpm": 75.0}, quality=0.2)  # artifact-low
    out = run_triage(st, clock=clock, signal={},
                     llm_client=_FinalInvestigator({"hypotension_risk": 1.0}))
    assert out.alarm_history == []                       # suppressed
    assert "alarm_suppressed" in out.scratch["last_investigation"]
    assert out.scratch.get("triage_alarm_reason") is None


def test_investigation_alarm_not_suppressed_on_good_quality(clock) -> None:
    # MAP 63 borderline → ambiguous → investigation; good quality → alarm fires.
    st = _state({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0}, quality=0.9)
    out = run_triage(st, clock=clock, signal={},
                     llm_client=_FinalInvestigator({"hypotension_risk": 0.9}))
    assert len(out.alarm_history) == 1                   # fires
    assert out.alarm_history[0].source == "investigation"


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


def test_triage_alarm_drives_deep_brief_in_graph() -> None:
    """ADR-023 §5: a triage alarm escalates to a deep brief (no clinician on-demand).

    Uses a CLEAN low-MAP signal (good SQI) so it is a genuine obvious_alarm — a
    flatlined/zeros signal would correctly route to ambiguous (possible artifact).
    """
    import numpy as np
    import torch

    from opsight.graph import build_graph

    gclock = SimClock(start_s=0.0)
    rng = np.random.default_rng(0)
    # Clean pulsatile ABP around 45 → MAP ~45 (clear breach) + high quality.
    # 다른 vital 은 정상 범위 상수 → 결측/품질 문제 없음 → 진짜 obvious_alarm.
    signal = {
        "ABP": torch.from_numpy(rng.normal(45.0, 2.0, 3000).astype(np.float32)),
        "HR": torch.from_numpy(np.full(60, 80.0, dtype=np.float32)),
        "SpO2": torch.from_numpy(np.full(60, 98.0, dtype=np.float32)),
        "BIS": torch.from_numpy(np.full(60, 50.0, dtype=np.float32)),
    }
    graph = build_graph(
        clock=gclock, signal=signal, modalities=["ABP", "HR", "SpO2", "BIS"],
        max_ticks=3, tick_sim_advance_s=30.0,
    )
    # No clinician_on_demand set → escalation comes purely from the triage alarm.
    final = graph.invoke(AgentState(case_id="c1", trace_id="t1"), {"recursion_limit": 50})
    fs = final if isinstance(final, AgentState) else AgentState.model_validate(final)
    assert fs.scratch.get("last_route") == "obvious_alarm"
    assert len(fs.alarm_history) >= 1
    assert len(fs.brief_history) >= 1  # alarm → deep brief followed


def test_flatline_signal_routes_to_ambiguous_not_alarm() -> None:
    """Quality gate (ADR-023): a flatlined (zeros) signal → low SQI → a clear
    breach is treated as a possible artifact → AMBIGUOUS, not an immediate alarm.
    """
    import torch

    from opsight.graph import build_graph

    gclock = SimClock(start_s=0.0)
    signal = {
        "ABP": torch.zeros(30 * 500), "ECG_II": torch.zeros(30 * 500),
        "PPG": torch.zeros(30 * 500), "BIS": torch.zeros(30 * 100),
    }
    graph = build_graph(
        clock=gclock, signal=signal, modalities=["ABP", "ECG_II", "PPG", "BIS"],
        max_ticks=1, tick_sim_advance_s=30.0,
    )
    final = graph.invoke(AgentState(case_id="c1", trace_id="t1"), {"recursion_limit": 50})
    fs = final if isinstance(final, AgentState) else AgentState.model_validate(final)
    assert fs.scratch.get("last_route") == "ambiguous"
    # No decide()-capable client → investigation skipped → no blind alarm.
    assert fs.alarm_history == []
