"""Tests for opsight.router — rule-based triage router (ADR-023).
opsight.router 테스트 — rule 기반 triage router.

- clear breach → OBVIOUS_ALARM (품질 양호 시)
- clear breach + 품질 저하/불일치 → AMBIGUOUS (artifact 의심)
- borderline / 결측 / in-range drift → AMBIGUOUS
- 여유 정상 → OBVIOUS_NORMAL
- extract_router_inputs: shallow sweep 결과 → (vitals, trends)

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_router.py -v
"""
from __future__ import annotations

from opsight.envelope import ToolResponse
from opsight.router import (
    Route,
    RouterConfig,
    extract_router_inputs,
    route_tick,
)


# ── OBVIOUS_ALARM ──


def test_clear_low_map_is_obvious_alarm() -> None:
    # MAP 55 < 65 - margin(5) = 60 → clear breach, 품질 정보 없음 → 알람 허용(recall-first)
    d = route_tick({"map_mmHg": 55.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    assert d.route is Route.OBVIOUS_ALARM
    assert any("map_mmHg" in c for c in d.clear_breaches)


def test_clear_high_map_is_obvious_alarm() -> None:
    d = route_tick({"map_mmHg": 130.0})  # > 110 + 5
    assert d.route is Route.OBVIOUS_ALARM


# ── OBVIOUS_NORMAL ──


def test_comfortably_normal_is_obvious_normal() -> None:
    d = route_tick({"map_mmHg": 85.0, "hr_bpm": 72.0, "spo2_pct": 98.0, "bis": 50.0})
    assert d.route is Route.OBVIOUS_NORMAL
    assert not d.clear_breaches and not d.borderline and not d.missing


# ── AMBIGUOUS ──


def test_borderline_map_is_ambiguous() -> None:
    # MAP 63: 60 (=65-5) <= 63 < 65 → borderline (not clear)
    d = route_tick({"map_mmHg": 63.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})
    assert d.route is Route.AMBIGUOUS
    assert any("map_mmHg" in b for b in d.borderline)
    assert not d.clear_breaches


def test_missing_map_is_ambiguous() -> None:
    d = route_tick({"hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0})  # map absent
    assert d.route is Route.AMBIGUOUS
    assert "map_mmHg" in d.missing


def test_in_range_but_falling_toward_low_is_ambiguous() -> None:
    # MAP 68 in range, but falling and within margin above low (65+5=70) → borderline
    d = route_tick(
        {"map_mmHg": 68.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0},
        {"map_mmHg": "falling"},
    )
    assert d.route is Route.AMBIGUOUS
    assert any("map_mmHg" in b for b in d.borderline)


def test_in_range_stable_near_low_is_not_flagged() -> None:
    # Same MAP 68 but stable (no drift) → normal, no borderline.
    d = route_tick(
        {"map_mmHg": 68.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0},
        {"map_mmHg": "stable"},
    )
    assert d.route is Route.OBVIOUS_NORMAL


def test_clear_breach_with_low_quality_downgraded_to_ambiguous() -> None:
    # MAP 55 clear breach, but quality below gate → could be artifact → investigate.
    d = route_tick({"map_mmHg": 55.0}, quality=0.5)
    assert d.route is Route.AMBIGUOUS
    assert any("quality_below_gate" in r for r in d.reasons)


def test_clear_breach_with_good_quality_stays_alarm() -> None:
    d = route_tick({"map_mmHg": 55.0, "hr_bpm": 75.0, "spo2_pct": 98.0, "bis": 50.0},
                   quality=0.9, agreement=0.9)
    assert d.route is Route.OBVIOUS_ALARM


def test_low_agreement_alone_is_ambiguous() -> None:
    # All vitals normal, but modalities disagree → investigate.
    d = route_tick({"map_mmHg": 85.0, "hr_bpm": 72.0, "spo2_pct": 98.0, "bis": 50.0},
                   agreement=0.2)
    assert d.route is Route.AMBIGUOUS


# ── Config injection ──


def test_custom_config_widens_margin() -> None:
    # With a wide margin, MAP 55 becomes borderline instead of clear (65-15=50; 55>=50).
    cfg = RouterConfig(
        thresholds={"map_mmHg": (65.0, 110.0)},
        margins={"map_mmHg": 15.0},
    )
    d = route_tick({"map_mmHg": 55.0}, config=cfg)
    assert d.route is Route.AMBIGUOUS
    assert any("map_mmHg" in b for b in d.borderline)
    assert not d.clear_breaches


# ── extract_router_inputs ──


def _resp(tool_name: str, result: dict) -> ToolResponse:
    return ToolResponse(
        case_id="c1", sim_time_s=30.0, tool_name=tool_name,
        result=result, quality_meta={}, latency_ms=0.0,
    )


def test_extract_router_inputs_pulls_vitals_and_trends() -> None:
    results = [
        _resp("get_current_state", {"vitals": {"map_mmHg": 62.0, "hr_bpm": 88.0}}),
        _resp("summarize_current_state", {"trend_directions": {"map_mmHg": "falling"}}),
    ]
    vitals, trends = extract_router_inputs(results)
    assert vitals == {"map_mmHg": 62.0, "hr_bpm": 88.0}
    assert trends == {"map_mmHg": "falling"}


def test_extract_router_inputs_degrades_on_missing_tools() -> None:
    vitals, trends = extract_router_inputs([])
    assert vitals == {} and trends == {}


def test_end_to_end_extract_then_route() -> None:
    results = [
        _resp("get_current_state", {"vitals": {"map_mmHg": 68.0, "hr_bpm": 75.0,
                                               "spo2_pct": 98.0, "bis": 50.0}}),
        _resp("summarize_current_state", {"trend_directions": {"map_mmHg": "falling"}}),
    ]
    vitals, trends = extract_router_inputs(results)
    d = route_tick(vitals, trends)
    assert d.route is Route.AMBIGUOUS  # 68 falling toward 65 → borderline
