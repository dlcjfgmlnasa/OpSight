"""Tool: summarize_current_state — rule-based integrated state assessment.
rule-based 통합 현재 상태 평가 (get_current_state 스냅샷 + get_signal_trend 방향 합성).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    _error_response,
    _leakage_guard,
    _ok,
)
from opsight.tools.signal_state_tools.extractors import (
    tool_get_current_state,
    tool_get_signal_trend,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# Phrasing enforcement: 단정 어조 ban + [CLINICIAN-REVIEW] marker 강제.
# brief §13.1 (Clinical Fact Guard) 일관.
_CLINICIAN_REVIEW_MARKER = "[CLINICIAN-REVIEW: 의료진 검토 필요]"

# Lit-standard threshold (heuristic; 임상의 검토 필요).
_MAP_NORMAL_LOW = 65.0
_MAP_NORMAL_HIGH = 110.0
_HR_NORMAL_LOW = 50.0
_HR_NORMAL_HIGH = 100.0
_SPO2_NORMAL_LOW = 92.0
_BIS_TOO_LIGHT = 60.0
_BIS_TOO_DEEP = 40.0

# Trend direction → conditional Korean clause (Clinical Fact Guard 어조 유지).
# 실제 drift(falling/rising)만 절로 붙여 salience 유지 — stable/unknown 은 생략
# (raw direction 은 result["trend_directions"] 에 그대로 노출되어 LLM 이 참조).
_DIRECTION_KO = {
    "falling": "하강 추세",
    "rising": "상승 추세",
}


def _trend_clause(trends: dict[str, Any], field: str) -> str:
    """Trailing trend clause for a vital field — only for active drift.
    vital field 의 추세 절(clause). falling/rising 에만 붙고 stable/unknown 은 ''.
    """
    direction = trends.get(field, {}).get("direction")
    ko = _DIRECTION_KO.get(direction)
    return f", 최근 {ko}" if ko is not None else ""


def tool_summarize_current_state(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Synthesize current state from get_current_state + get_signal_trend (rule-based).
    get_current_state 스냅샷 + get_signal_trend 방향을 합성한 rule-based 평가.
    순간 임계값 위반에 "최근 하강/상승 추세" 절을 덧붙여 transient 와 지속 drift 를 구분.

    ⚠️ Phrasing enforcement (ADR-016, brief §13.1):
        - Conditional phrasing only ("X 가능성을 시사함")
        - No diagnostic assertions, no dose recommendations
        - [CLINICIAN-REVIEW: 의료진 검토 필요] marker MANDATORY

    ADR-018: rule-based threshold path is the accepted Phase 1 implementation.
    ADR-014 Tier 0 supervised head (#14) is deferred — numerics-based threshold
    synthesis is sufficient for §[Signal status] grounding.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    # Inline call to get_current_state — direct function call (same package) to
    # avoid full dispatch overhead. Reuses leakage guard already passed above.
    state_resp = tool_get_current_state(
        ToolRequest(case_id=request.case_id, sim_time_s=request.sim_time_s,
                    tool_name="get_current_state", args={}),
        clock, signal,
    )
    if not state_resp.ok or state_resp.result is None:
        # Shouldn't happen given the leakage guard above passed; conservative fallback.
        return _error_response(
            request, "tool_internal_error",
            "internal: get_current_state failed",
            (time.perf_counter() - t0) * 1000.0,
        )
    v = state_resp.result.get("vitals", {})

    # Trend overlay — direction per vital over the trailing window. Distinguishes
    # a sustained drift (e.g. MAP 62 falling) from a transient at-threshold blip.
    # Graceful: on any failure, trends stays empty and clauses simply omit.
    # 추세 overlay — 순간 임계값과 지속 추세를 구분. 실패 시 빈 dict 로 graceful degrade.
    trend_resp = tool_get_signal_trend(
        ToolRequest(case_id=request.case_id, sim_time_s=request.sim_time_s,
                    tool_name="get_signal_trend", args={}),
        clock, signal,
    )
    trends: dict[str, Any] = (
        trend_resp.result.get("trends", {})
        if trend_resp.ok and trend_resp.result is not None
        else {}
    )

    # Rule-based state synthesis / Rule-based 상태 합성
    concerns: list[str] = []

    # Hemodynamic state from MAP
    map_val = v.get("map_mmHg")
    if map_val is None:
        hemodynamic_state = "unknown"
        concerns.append("MAP 미가용 — 혈역학 평가 제한")
    elif map_val < _MAP_NORMAL_LOW:
        hemodynamic_state = "caution_low_pressure"
        concerns.append(f"MAP {map_val:.0f} mmHg 가 65 mmHg 미만{_trend_clause(trends, 'map_mmHg')} 가능성을 시사함")
    elif map_val > _MAP_NORMAL_HIGH:
        hemodynamic_state = "caution_high_pressure"
        concerns.append(f"MAP {map_val:.0f} mmHg 가 110 mmHg 초과{_trend_clause(trends, 'map_mmHg')} 가능성을 시사함")
    else:
        hemodynamic_state = "stable"

    # HR check
    hr_val = v.get("hr_bpm")
    if hr_val is not None:
        if hr_val < _HR_NORMAL_LOW:
            concerns.append(f"HR {hr_val:.0f} bpm 가 50 bpm 미만{_trend_clause(trends, 'hr_bpm')} 가능성을 시사함")
        elif hr_val > _HR_NORMAL_HIGH:
            concerns.append(f"HR {hr_val:.0f} bpm 가 100 bpm 초과{_trend_clause(trends, 'hr_bpm')} 가능성을 시사함")

    # Anesthesia state from BIS
    bis_val = v.get("bis")
    if bis_val is None:
        anesthesia_state = "unknown"
    elif bis_val < _BIS_TOO_DEEP:
        anesthesia_state = "possibly_deep"
        concerns.append(f"BIS {bis_val:.0f} 가 40 미만{_trend_clause(trends, 'bis')} 가능성을 시사함")
    elif bis_val > _BIS_TOO_LIGHT:
        anesthesia_state = "possibly_light"
        concerns.append(f"BIS {bis_val:.0f} 가 60 초과{_trend_clause(trends, 'bis')} 가능성을 시사함")
    else:
        anesthesia_state = "adequate_range"

    # Respiratory state from SpO2 + EtCO2
    spo2_val = v.get("spo2_pct")
    etco2_val = v.get("etco2_mmHg")
    if spo2_val is None and etco2_val is None:
        respiratory_state = "unknown"
    elif spo2_val is not None and spo2_val < _SPO2_NORMAL_LOW:
        respiratory_state = "caution_low_spo2"
        concerns.append(f"SpO2 {spo2_val:.0f}% 가 92% 미만{_trend_clause(trends, 'spo2_pct')} 가능성을 시사함")
    else:
        respiratory_state = "stable"

    # Overall assessment — conditional phrasing + mandatory marker
    if not concerns:
        overall = (
            "현재 가용한 활력 징후 는 안정 범위 내 가능성을 시사함. "
            "임상의의 종합 판단이 필요할 수 있다. "
            + _CLINICIAN_REVIEW_MARKER
        )
    else:
        overall = (
            f"{len(concerns)}건의 관찰 항목이 있으며 임상의의 판단이 필요할 수 있다. "
            + _CLINICIAN_REVIEW_MARKER
        )

    result = {
        "hemodynamic_state": hemodynamic_state,
        "anesthesia_state": anesthesia_state,
        "respiratory_state": respiratory_state,
        "key_concerns": concerns,
        "overall_assessment": overall,
        # Trend direction per vital that fed a concern (transparency for the
        # Deep brief LLM; '' when the vital had no trend signal).
        "trend_directions": {f: t.get("direction") for f, t in trends.items()},
        "meta": {
            # ADR-018: rule_based. Tier 0 supervised head (ADR-014 #14) deferred.
            "tier0_status": "rule_based",
            "rule": "rule_based_threshold_synthesis_with_trend_overlay",
            "vitals_source": state_resp.result.get("meta", {}),
        },
    }
    return _ok(
        request, result, (time.perf_counter() - t0) * 1000.0,
        quality_meta={
            "tier0_status": "rule_based",
            "clinical_review_required": True,
        },
    )
