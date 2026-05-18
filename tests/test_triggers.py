"""Trigger engine unit tests (plan_1.8 task 7).
Trigger engine 단위 테스트 (plan_1.8 task 7).

Tests every trigger with at least one positive and one negative case, plus
ordering / cooldown semantics.
모든 trigger를 최소 positive + negative 1쌍씩 검증 + ordering / cooldown 의미.
"""
from __future__ import annotations

import pytest

from vitalagent.state import AgentState, QualitySample, RiskSample
from vitalagent.tools.envelope import ToolResponse
from vitalagent.triggers import (
    ARREST_RISK_THRESHOLD,
    CONSISTENCY_GOOD_QUALITY_GATE,
    CONSISTENCY_THRESHOLD,
    DEEP_COOLDOWN_S,
    HYPOTENSION_RISK_THRESHOLD,
    PERIODIC_CHECK_INTERVAL_S,
    QUALITY_DROP_THRESHOLD,
    RISK_DELTA_THRESHOLD,
    RISK_DELTA_WINDOW_S,
    should_escalate,
)


def _state(**kwargs) -> AgentState:
    """Helper to build an AgentState with defaults / 기본값 AgentState 생성."""
    defaults: dict = {"case_id": "c1", "trace_id": "t1"}
    defaults.update(kwargs)
    return AgentState(**defaults)


# ── Trigger 1: hypotension risk > 0.7 ──


def test_trigger_hypotension_positive() -> None:
    s = _state(
        sim_time_s=30.0,
        risk_history=[
            RiskSample(sim_time_s=30.0, risk_type="hypotension_h5", risk=0.85, uncertainty=0.1),
        ],
    )
    fire, reason = should_escalate(s)
    assert fire
    assert reason is not None and "hypotension_risk_gt" in reason


def test_trigger_hypotension_negative_low_risk() -> None:
    s = _state(
        sim_time_s=30.0,
        risk_history=[
            RiskSample(sim_time_s=30.0, risk_type="hypotension_h5", risk=0.30, uncertainty=0.1),
        ],
    )
    fire, reason = should_escalate(s)
    assert not fire and reason is None


# ── Trigger 2: rapid risk increase ──


def test_trigger_rapid_increase_positive() -> None:
    s = _state(
        sim_time_s=60.0,
        risk_history=[
            RiskSample(sim_time_s=30.0, risk_type="hypotension_h5", risk=0.20, uncertainty=0.1),
            RiskSample(sim_time_s=60.0, risk_type="hypotension_h5", risk=0.60, uncertainty=0.1),
        ],
    )
    fire, reason = should_escalate(s)
    assert fire
    assert reason is not None and "rapid_risk_increase" in reason


def test_trigger_rapid_increase_negative_small_delta() -> None:
    s = _state(
        sim_time_s=60.0,
        risk_history=[
            RiskSample(sim_time_s=30.0, risk_type="hypotension_h5", risk=0.20, uncertainty=0.1),
            RiskSample(sim_time_s=60.0, risk_type="hypotension_h5", risk=0.30, uncertainty=0.1),
        ],
    )
    fire, _ = should_escalate(s)
    assert not fire


# ── Trigger 3: quality drop > 0.3 ──


def test_trigger_quality_drop_positive() -> None:
    s = _state(
        sim_time_s=60.0,
        quality_history=[
            QualitySample(sim_time_s=30.0, modality="ABP", score=0.90),
            QualitySample(sim_time_s=60.0, modality="ABP", score=0.40),
        ],
    )
    fire, reason = should_escalate(s)
    assert fire and reason is not None and "quality_drop" in reason


def test_trigger_quality_drop_negative_no_drop() -> None:
    s = _state(
        sim_time_s=60.0,
        quality_history=[
            QualitySample(sim_time_s=30.0, modality="ABP", score=0.90),
            QualitySample(sim_time_s=60.0, modality="ABP", score=0.85),
        ],
    )
    fire, _ = should_escalate(s)
    assert not fire


# ── Trigger 4: cross-modal inconsistency under good quality ──


def test_trigger_inconsistency_positive() -> None:
    s = _state(
        sim_time_s=60.0,
        quality_history=[
            QualitySample(sim_time_s=60.0, modality="ABP", score=0.85),
            QualitySample(sim_time_s=60.0, modality="PPG", score=0.80),
        ],
        last_tool_results=[
            ToolResponse(
                case_id="c1", sim_time_s=60.0, tool_name="cross_modal_consistency",
                args={}, result={"score": 0.30}, quality_meta={}, latency_ms=0.0,
            )
        ],
    )
    fire, reason = should_escalate(s)
    assert fire and reason is not None and "cross_modal_inconsistency" in reason


def test_trigger_inconsistency_negative_low_quality_gate() -> None:
    # quality is below the "good" gate → trigger does NOT fire
    # quality가 "good" gate 아래 → trigger 발화하지 않음
    s = _state(
        sim_time_s=60.0,
        quality_history=[
            QualitySample(sim_time_s=60.0, modality="ABP", score=0.30),
            QualitySample(sim_time_s=60.0, modality="PPG", score=0.30),
        ],
        last_tool_results=[
            ToolResponse(
                case_id="c1", sim_time_s=60.0, tool_name="cross_modal_consistency",
                args={}, result={"score": 0.10}, quality_meta={}, latency_ms=0.0,
            )
        ],
    )
    fire, _ = should_escalate(s)
    assert not fire


# ── Trigger 5: arrest risk > 0.5 ──


def test_trigger_arrest_positive() -> None:
    s = _state(
        sim_time_s=60.0,
        risk_history=[
            RiskSample(sim_time_s=60.0, risk_type="arrest_h5", risk=0.60, uncertainty=0.1),
        ],
    )
    fire, reason = should_escalate(s)
    assert fire and reason is not None and "arrest_risk_gt" in reason


def test_trigger_arrest_negative_low_risk() -> None:
    s = _state(
        sim_time_s=60.0,
        risk_history=[
            RiskSample(sim_time_s=60.0, risk_type="arrest_h5", risk=0.10, uncertainty=0.1),
        ],
    )
    fire, _ = should_escalate(s)
    assert not fire


# ── Trigger 6: clinician on-demand ──


def test_trigger_clinician_on_demand_positive() -> None:
    s = _state(
        sim_time_s=30.0,
        scratch={"clinician_on_demand": True},
    )
    fire, reason = should_escalate(s)
    assert fire and reason == "clinician_on_demand"


def test_trigger_clinician_on_demand_bypasses_cooldown() -> None:
    """Clinician on-demand fires even within cooldown.
    Clinician on-demand는 cooldown 안에서도 발화.
    """
    s = _state(
        sim_time_s=30.0,
        scratch={"clinician_on_demand": True},
        last_deep_trigger_time_s=20.0,  # within 60s cooldown
    )
    fire, reason = should_escalate(s)
    assert fire and reason == "clinician_on_demand"


# ── Trigger 7: periodic check ──


def test_trigger_periodic_positive_first_check() -> None:
    s = _state(sim_time_s=PERIODIC_CHECK_INTERVAL_S + 1)
    fire, reason = should_escalate(s)
    assert fire and reason is not None and "periodic_check" in reason


def test_trigger_periodic_positive_after_last_deep() -> None:
    s = _state(
        sim_time_s=PERIODIC_CHECK_INTERVAL_S * 2 + 10,
        last_deep_trigger_time_s=PERIODIC_CHECK_INTERVAL_S * 1,
    )
    fire, reason = should_escalate(s)
    assert fire and reason is not None and "periodic_check" in reason


def test_trigger_periodic_negative_too_early() -> None:
    s = _state(sim_time_s=PERIODIC_CHECK_INTERVAL_S - 30)
    fire, _ = should_escalate(s)
    assert not fire


# ── Cooldown semantics ──


def test_cooldown_blocks_non_acute_triggers() -> None:
    """Within cooldown, hypotension trigger does not fire.
    Cooldown 안에서는 hypotension trigger 발화하지 않는다.
    """
    s = _state(
        sim_time_s=30.0,
        risk_history=[
            RiskSample(sim_time_s=30.0, risk_type="hypotension_h5", risk=0.85, uncertainty=0.1),
        ],
        last_deep_trigger_time_s=20.0,
    )
    fire, _ = should_escalate(s)
    assert not fire


def test_cooldown_bypassed_by_arrest() -> None:
    """Arrest bypasses cooldown (acute event).
    Arrest는 cooldown을 우회한다 (acute event).
    """
    s = _state(
        sim_time_s=30.0,
        risk_history=[
            RiskSample(sim_time_s=30.0, risk_type="arrest_h5", risk=0.80, uncertainty=0.1),
        ],
        last_deep_trigger_time_s=20.0,
    )
    fire, reason = should_escalate(s)
    assert fire and reason is not None and "arrest_risk_gt" in reason


def test_cooldown_expires_after_60s() -> None:
    """After 60s, non-acute triggers can fire again.
    60초 후 non-acute trigger 재발화 가능.
    """
    s = _state(
        sim_time_s=100.0,
        risk_history=[
            RiskSample(sim_time_s=100.0, risk_type="hypotension_h5", risk=0.85, uncertainty=0.1),
        ],
        last_deep_trigger_time_s=20.0,  # 80s ago — past cooldown
    )
    fire, reason = should_escalate(s)
    assert fire and reason is not None


# ── No-data baseline ──


def test_no_data_does_not_fire() -> None:
    """Fresh state with no observations should not fire any trigger.
    관찰 없는 fresh state는 어떤 trigger도 발화하지 않는다.
    """
    s = _state(sim_time_s=5.0)
    fire, reason = should_escalate(s)
    assert not fire and reason is None
