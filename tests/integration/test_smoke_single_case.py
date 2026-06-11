"""Single-case end-to-end smoke test (plan_1.8 task 9).
단일 case end-to-end smoke 테스트 (plan_1.8 task 9).

Runs the compiled dual-mode StateGraph against Mock FM Tier 1 (Stub) for a
single synthetic case. Verifies:
Mock FM Tier 1 (Stub)로 단일 synthetic case에 대해 compiled dual-mode
StateGraph를 실행한다. 검증 항목:

- The graph runs without exceptions / 예외 없이 graph 실행
- Shallow loop ticks advance sim-time by 30 s each / Shallow tick이
  sim-time을 30초씩 진행
- At least one trigger fires within ``max_ticks`` (use clinician on-demand
  to make the test deterministic) / 적어도 한 trigger가 발화 (deterministic
  위해 clinician on-demand 사용)
- Brief 9-section template renders end-to-end / 브리프 9 section 렌더링
- Trace JSONL is captured / Trace JSONL 캡쳐
- No data-leakage error during execution / 실행 중 data leakage error 없음

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/integration/test_smoke_single_case.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import torch

from opsight.graph import build_graph
from opsight.sim_clock import SimClock
from opsight.state import AgentState
from opsight.trace import TraceWriter, read_trace

if TYPE_CHECKING:
    from opsight.envelope import ToolResponse


# ── Deterministic LLM test double ──
# Production code intentionally has NO placeholder LLM (removed in the
# false-alarm-agent rebuild); the brief is generated only by the vLLM-backed
# client. This test-only double satisfies the ``LLMClient`` Protocol so the
# end-to-end smoke test can verify the brief pipeline structure (9 sections +
# Clinical Fact Guard markers) without a real model / GPU.
# production 에는 placeholder LLM 이 없으므로(rebuild 에서 제거), brief 구조 검증을
# 위해 ``LLMClient`` Protocol 을 만족하는 테스트 전용 double 을 둔다.


class _DeterministicLLMClient:
    """Deterministic ``LLMClient`` test double — no real model, no GPU."""

    name = "deterministic-test-double"

    _MARKER = "[CLINICIAN-REVIEW: 의료진 검토 필요]"
    _SECTIONS = (
        "Surgery context", "Signal status", "Assessment confidence",
        "Risk evaluation", "Evidence", "Intraoperative context",
        "Similar trajectory", "Recommendations", "Limitations",
    )

    def narrate(self, tool_results: list[ToolResponse]) -> str:
        return f"[안정] {len(tool_results)}개 tool 결과 기반 narration (deterministic stub)."

    def brief(
        self,
        tool_results: list[ToolResponse],
        *,
        surgery_type: str,
        surgery_phase: str,
        elapsed_min: float,
    ) -> dict[str, str]:
        n = len(tool_results)
        sections = {
            name: (
                f"{name}: deterministic stub "
                f"({surgery_type}/{surgery_phase}, {elapsed_min:.0f}min, {n} tool results)."
            )
            for name in self._SECTIONS
        }
        # Clinical Fact Guard markers required by the brief contract.
        sections["Recommendations"] += " " + self._MARKER
        sections["Limitations"] += " " + self._MARKER
        return sections


# ── Fixtures ──


@pytest.fixture
def signal() -> dict[str, torch.Tensor]:
    """30 s synthetic 4-modality signal (zeros).
    30초 synthetic 4-modality 신호 (zeros).
    """
    return {
        "ABP":    torch.zeros(30 * 500),
        "ECG_II": torch.zeros(30 * 500),
        "PPG":    torch.zeros(30 * 500),
        "BIS":    torch.zeros(30 * 100),
    }


@pytest.fixture
def modalities() -> list[str]:
    return ["ABP", "ECG_II", "PPG", "BIS"]


# ── Tests ──


def test_smoke_graph_runs_end_to_end(tmp_path: Path, signal, modalities) -> None:
    """Graph runs without exceptions; both shallow and deep nodes fire.
    Graph가 예외 없이 실행; shallow + deep 모두 발화.
    """
    clock = SimClock(start_s=0.0)
    trace_path = tmp_path / "trace.jsonl"

    initial = AgentState(
        case_id="synthetic-case-1",
        trace_id="smoke-run-1",
        # Force a deterministic deep escalation on tick 2.
        # tick 2에서 deterministic deep escalation 강제.
        scratch={"clinician_on_demand_at_tick": 2},
    )

    with TraceWriter(trace_path, trace_id="smoke-run-1", case_id="synthetic-case-1") as tw:
        # Subclass approach: the StateGraph re-evaluates the conditional edge
        # after each shallow tick. We set the on-demand flag mid-run by using
        # the trace writer's "tick" event observation (alternatively, inject
        # it via the scratch field at the right tick).
        # StateGraph는 각 shallow tick 후 conditional edge를 재평가. tick 도중에
        # on-demand flag를 set하려면 trace writer "tick" 이벤트로 관찰하거나
        # 적절한 tick에서 scratch 필드를 주입한다. 본 테스트는 단순화를 위해
        # 시작 시점에 on-demand=True로 set하여 첫 trigger 발화 보장.
        initial.scratch["clinician_on_demand"] = True
        graph = build_graph(
            clock=clock,
            signal=signal,
            modalities=modalities,
            max_ticks=5,
            tick_sim_advance_s=30.0,
            trace=tw,
            llm_client=_DeterministicLLMClient(),
        )
        final = graph.invoke(initial, {"recursion_limit": 50})

    # final state from LangGraph is a dict-like; reconstruct as AgentState.
    # LangGraph 최종 state는 dict-like; AgentState로 reconstruct.
    final_state = (
        final if isinstance(final, AgentState) else AgentState.model_validate(final)
    )

    # 1) Time advanced by 30 s × max_ticks (=150s)
    # 1) sim-time이 30초 × max_ticks (=150초) 진행
    assert final_state.sim_time_s == pytest.approx(150.0), final_state.sim_time_s

    # 2) At least one deep brief was emitted (clinician on-demand on tick 1).
    # 2) 최소 1개 deep brief 발화 (tick 1의 clinician on-demand).
    assert len(final_state.brief_history) >= 1, (
        f"expected at least 1 deep brief, got {len(final_state.brief_history)}"
    )
    first_brief = final_state.brief_history[0]
    assert set(first_brief.sections.keys()) == {
        "Surgery context",
        "Signal status",
        "Assessment confidence",
        "Risk evaluation",
        "Evidence",
        "Intraoperative context",
        "Similar trajectory",
        "Recommendations",
        "Limitations",
    }
    assert "[CLINICIAN-REVIEW" in first_brief.sections["Recommendations"]
    assert "[CLINICIAN-REVIEW" in first_brief.sections["Limitations"]

    # 3) Trace JSONL captured / Trace JSONL 캡쳐.
    events = read_trace(trace_path)
    assert len(events) > 0
    event_types = {e["event"] for e in events}
    assert {"tick", "tool_call", "tool_result", "narration", "brief"} <= event_types

    # 5) Every event has the standard envelope / 모든 이벤트가 표준 envelope.
    for e in events:
        assert set(e.keys()) == {"trace_id", "case_id", "sim_time_s", "wall_time_ms", "event", "payload"}
        assert e["trace_id"] == "smoke-run-1"
        assert e["case_id"] == "synthetic-case-1"


def test_smoke_no_leakage_within_graph_run(tmp_path: Path, signal, modalities) -> None:
    """No tool_result event reports a ``leakage_violation`` during the run.
    실행 중 어떤 tool_result도 ``leakage_violation``을 보고하지 않는다.
    """
    clock = SimClock(start_s=0.0)
    trace_path = tmp_path / "trace.jsonl"
    initial = AgentState(case_id="c1", trace_id="t1", scratch={"clinician_on_demand": True})
    with TraceWriter(trace_path, trace_id="t1", case_id="c1") as tw:
        graph = build_graph(
            clock=clock, signal=signal, modalities=modalities,
            max_ticks=3, trace=tw,
        )
        graph.invoke(initial, {"recursion_limit": 50})
    events = read_trace(trace_path)
    tool_results = [e for e in events if e["event"] == "tool_result"]
    assert tool_results, "expected at least one tool_result event"
    for e in tool_results:
        assert e["payload"]["ok"], f"unexpected tool failure: {e}"
