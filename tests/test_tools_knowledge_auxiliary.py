"""Tests for plan_1.7 tools 13–16 (knowledge + auxiliary).
plan_1.7 tool 13–16 (knowledge + auxiliary) 테스트.

Tool 13–15 are STUBs; tool 16 is a full deterministic implementation.
Tool 13–15 는 STUB; tool 16 은 정식 deterministic 구현.
"""
from __future__ import annotations

import math

import pytest

from vitalagent.sim_clock import SimClock
from vitalagent.tools.auxiliary_tools import (
    tool_quality_aware_synthesis,
    tool_surgery_context_awareness,
)
from vitalagent.tools.envelope import ToolRequest
from vitalagent.tools.knowledge_tools_stub import (
    tool_find_similar_cases,
    tool_intervention_response_prediction,
)
from vitalagent.tools.registry import TOOLS, call_tool


# ── Fixtures / Fixture ──


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)  # now_s = 60.0
    return c


def _req(tool_name: str, args: dict, sim_time_s: float = 30.0) -> ToolRequest:
    return ToolRequest(
        case_id="c-001",
        sim_time_s=sim_time_s,
        tool_name=tool_name,
        args=args,
    )


# ── Tool 13 — find_similar_cases ──


def test_find_similar_cases_stub_returns_empty_list(clock):
    resp = tool_find_similar_cases(
        _req("find_similar_cases", {"k": 5, "surgery_type": "general"}),
        clock,
    )
    assert resp.ok
    assert resp.result is not None
    assert resp.result["similar_cases"] == []
    assert resp.quality_meta["unimplemented_in_prototype"] is True
    assert resp.quality_meta["clinical_review_required"] is True


def test_find_similar_cases_k_out_of_range(clock):
    resp = tool_find_similar_cases(_req("find_similar_cases", {"k": 99}), clock)
    assert not resp.ok
    assert resp.error is not None
    assert resp.error.type == "invalid_args"


def test_find_similar_cases_leakage_violation(clock):
    # current_state.sim_time_s > clock.now_s (=60) → leakage
    resp = tool_find_similar_cases(
        _req(
            "find_similar_cases",
            {"k": 5, "current_state": {"sim_time_s": 9999.0}},
        ),
        clock,
    )
    assert not resp.ok
    assert resp.error is not None
    assert resp.error.type == "leakage_violation"


# ── Tool 14 — intervention_response_prediction ──


def test_intervention_response_stub_returns_empty_distribution(clock):
    resp = tool_intervention_response_prediction(
        _req(
            "intervention_response_prediction",
            {
                "intervention": {"name": "norepinephrine", "amount": 0.05, "unit": "mcg/kg/min"},
                "horizon_min": 5,
            },
        ),
        clock,
    )
    assert resp.ok
    dist = resp.result["response_distribution"]
    assert len(dist["mean"]) == 5
    assert len(dist["p10"]) == 5
    assert len(dist["p90"]) == 5
    assert resp.result["n_reference_cases"] == 0
    assert resp.quality_meta["clinical_review_required"] is True


def test_intervention_response_invalid_intervention_arg(clock):
    resp = tool_intervention_response_prediction(
        _req("intervention_response_prediction", {"intervention": "wrong_type"}),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_intervention_response_missing_name(clock):
    resp = tool_intervention_response_prediction(
        _req("intervention_response_prediction", {"intervention": {"amount": 0.05}}),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_intervention_response_leakage_violation(clock):
    resp = tool_intervention_response_prediction(
        _req(
            "intervention_response_prediction",
            {
                "intervention": {"name": "norepi"},
                "current_state": {"sim_time_s": 9999.0},
            },
        ),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "leakage_violation"


# ── Tool 15 — surgery_context_awareness ──


def test_surgery_context_general_maintenance(clock):
    resp = tool_surgery_context_awareness(
        _req("surgery_context_awareness", {"surgery_type": "general", "phase": "maintenance"}),
        clock,
    )
    assert resp.ok
    assert len(resp.result["common_events"]) > 0
    assert "CLINICIAN-REVIEW" in resp.result["phase_hint"]
    assert resp.quality_meta["clinical_review_required"] is True


def test_surgery_context_loads_yaml_when_available(clock):
    """Tool 15 의 source 가 'yaml' (plan_1.5 완료) — 'fallback_hardcoded' 가 아니어야.
    Tool 15 source = 'yaml' (plan_1.5 done), not 'fallback_hardcoded'.
    """
    resp = tool_surgery_context_awareness(
        _req("surgery_context_awareness", {"surgery_type": "general", "phase": "maintenance"}),
        clock,
    )
    assert resp.ok
    # yaml-backed when surgery_context.yaml exists
    assert resp.result["meta"]["source"] == "yaml"
    assert resp.result["meta"]["yaml_version"] == "v1"
    # phase hint must include the CLINICIAN-REVIEW marker from yaml
    # phase hint 는 yaml 의 clinical_review marker 포함
    assert "이형철 교수님 그룹 검토 필요" in resp.result["phase_hint"]


def test_surgery_context_yaml_covers_all_4_surgery_types(clock):
    """4 surgery type × 3 phase = 12 cell 모두 yaml 에서 hint 반환.
    All 12 (4 types × 3 phases) cells return yaml-backed hints.
    """
    types = ["general", "thoracic", "gynecology", "urology"]
    phases = ["induction", "maintenance", "emergence"]
    for st in types:
        for ph in phases:
            r = tool_surgery_context_awareness(
                _req("surgery_context_awareness", {"surgery_type": st, "phase": ph}),
                clock,
            )
            assert r.ok, f"{st}/{ph} failed: {r.error}"
            assert r.result["meta"]["source"] == "yaml"
            assert "CLINICIAN-REVIEW" in r.result["phase_hint"], (
                f"{st}/{ph} missing CLINICIAN-REVIEW marker: {r.result['phase_hint']}"
            )


def test_surgery_context_unknown_type(clock):
    resp = tool_surgery_context_awareness(
        _req("surgery_context_awareness", {"surgery_type": "mars_surgery", "phase": "maintenance"}),
        clock,
    )
    assert resp.ok
    assert resp.result["common_events"] == []
    assert "미정의" in resp.result["phase_hint"]


def test_surgery_context_missing_type(clock):
    resp = tool_surgery_context_awareness(
        _req("surgery_context_awareness", {}),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


# ── Tool 16 — quality_aware_synthesis (full implementation) ──


def test_synthesis_weighted_mean_basic(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {
                "predictions": [
                    {"value": 70.0, "quality": 1.0, "source": "ABP"},
                    {"value": 80.0, "quality": 1.0, "source": "PPG"},
                ],
                "method": "weighted_mean",
            },
        ),
        clock,
    )
    assert resp.ok
    assert resp.result["fused_value"] == pytest.approx(75.0)
    assert resp.result["effective_quality"] == pytest.approx(1.0)
    assert set(resp.result["contributors"]) == {"ABP", "PPG"}
    assert resp.quality_meta["deterministic"] is True


def test_synthesis_weighted_mean_unequal_qualities(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {
                "predictions": [
                    {"value": 50.0, "quality": 0.9, "source": "a"},
                    {"value": 100.0, "quality": 0.1, "source": "b"},
                ],
                "method": "weighted_mean",
            },
        ),
        clock,
    )
    expected = (50 * 0.9 + 100 * 0.1) / (0.9 + 0.1)
    assert resp.result["fused_value"] == pytest.approx(expected)


def test_synthesis_max_quality(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {
                "predictions": [
                    {"value": 50.0, "quality": 0.3, "source": "a"},
                    {"value": 100.0, "quality": 0.9, "source": "b"},
                ],
                "method": "max_quality",
            },
        ),
        clock,
    )
    assert resp.ok
    assert resp.result["fused_value"] == 100.0
    assert resp.result["effective_quality"] == 0.9
    assert resp.result["contributors"] == ["b"]


def test_synthesis_min_uncertainty(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {
                "predictions": [
                    {"value": 50.0, "quality": 0.4, "source": "a"},
                    {"value": 75.0, "quality": 0.7, "source": "b"},
                ],
                "method": "min_uncertainty",
            },
        ),
        clock,
    )
    assert resp.ok
    # min uncertainty == max quality
    assert resp.result["fused_value"] == 75.0


def test_synthesis_all_zero_quality_yields_nan(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {
                "predictions": [
                    {"value": 50.0, "quality": 0.0, "source": "a"},
                    {"value": 100.0, "quality": 0.0, "source": "b"},
                ],
                "method": "weighted_mean",
            },
        ),
        clock,
    )
    assert resp.ok
    assert math.isnan(resp.result["fused_value"])
    assert resp.result["effective_quality"] == 0.0
    assert resp.result["contributors"] == []


def test_synthesis_empty_predictions(clock):
    resp = tool_quality_aware_synthesis(
        _req("quality_aware_synthesis", {"predictions": []}),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_synthesis_invalid_method(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {"predictions": [{"value": 1.0, "quality": 1.0}], "method": "geometric_mean"},
        ),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_synthesis_invalid_quality_range(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {"predictions": [{"value": 1.0, "quality": 1.5}]},
        ),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_synthesis_missing_value_field(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {"predictions": [{"quality": 0.5}]},
        ),
        clock,
    )
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_synthesis_single_prediction_passthrough(clock):
    resp = tool_quality_aware_synthesis(
        _req(
            "quality_aware_synthesis",
            {"predictions": [{"value": 42.0, "quality": 0.8, "source": "lonely"}]},
        ),
        clock,
    )
    assert resp.ok
    assert resp.result["fused_value"] == 42.0


# ── Registry integration / Registry 통합 ──


def test_registry_contains_all_21_tools():
    """21-tool registry (plan_1.3.5 추가 후) / Registry after plan_1.3.5."""
    expected = {
        # FM (1–7)
        "predict_hypotension",
        "predict_cardiac_arrest",
        "assess_signal_quality",
        "cross_modal_consistency",
        "temporal_trend_analysis",
        "forecast_signal",
        "anomaly_score",
        # EMR (8–12)
        "query_anesthesia_drugs",
        "query_vasoactive_drugs",
        "query_fluid_blood",
        "query_surgery_progress",
        "query_patient_baseline",
        # Knowledge (13–14)
        "find_similar_cases",
        "intervention_response_prediction",
        # Auxiliary (15–16)
        "surgery_context_awareness",
        "quality_aware_synthesis",
        # Signal Access (17–21) — ADR-016 / plan_1.3.5
        "get_current_vitals",
        "describe_signal",
        "assess_variability",
        "compare_to_baseline",
        "summarize_current_state",
    }
    assert set(TOOLS.keys()) == expected


def test_registry_categories():
    fm_count = sum(1 for s in TOOLS.values() if s.category == "fm")
    emr_count = sum(1 for s in TOOLS.values() if s.category == "emr")
    knowledge_count = sum(1 for s in TOOLS.values() if s.category == "knowledge")
    auxiliary_count = sum(1 for s in TOOLS.values() if s.category == "auxiliary")
    signal_access_count = sum(1 for s in TOOLS.values() if s.category == "signal_access")
    assert fm_count == 7
    assert emr_count == 5
    assert knowledge_count == 2
    assert auxiliary_count == 2
    assert signal_access_count == 5


def test_call_tool_routes_new_tools(clock):
    # Knowledge / Auxiliary tools 는 needs_fm=False — clock-only dispatch.
    # Knowledge / Auxiliary tool 은 needs_fm=False — clock-only dispatch.
    for name in (
        "find_similar_cases",
        "intervention_response_prediction",
        "surgery_context_awareness",
        "quality_aware_synthesis",
    ):
        req = _req(name, _minimal_args_for(name))
        resp = call_tool(name, req, clock=clock)
        # 모두 성공 또는 명시적 ok=False (intervention 의 missing name 같은 경우는 제외)
        # All succeed or explicit ok=False; here all are valid args
        assert resp.ok, f"tool {name} unexpectedly failed: {resp.error}"


def _minimal_args_for(name: str) -> dict:
    if name == "find_similar_cases":
        return {"k": 3, "current_state": {"sim_time_s": 30.0}}
    if name == "intervention_response_prediction":
        return {
            "intervention": {"name": "noop"},
            "horizon_min": 5,
            "current_state": {"sim_time_s": 30.0},
        }
    if name == "surgery_context_awareness":
        return {"surgery_type": "general", "phase": "maintenance"}
    if name == "quality_aware_synthesis":
        return {
            "predictions": [{"value": 1.0, "quality": 0.5}, {"value": 2.0, "quality": 0.5}]
        }
    raise ValueError(name)
