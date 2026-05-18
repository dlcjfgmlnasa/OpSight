"""Knowledge / Comparative tools 13–14 — **STUB** (plan_1.7).
Knowledge / Comparative tool 13–14 — **STUB** (plan_1.7).

⚠️ Stage 1 prototype 단계에서는 STUB. Real 구현은:
   - Tool 13 (find_similar_cases): plan_1.2 cohort manifest + retrieval index 합류 후
   - Tool 14 (intervention_response_prediction): ADR-013 결정 후
⚠️ STUB in Stage 1 prototype. Real implementations depend on:
   - Tool 13: plan_1.2 cohort manifest + retrieval index
   - Tool 14: ADR-013 decision

Schema 정식 spec / Schema authoritative spec: ``docs/tool_spec/knowledge_tools.md``.

Clinical Fact Guard (project_brief §13.1):
- Tool 13: similar case 의 outcome 을 *예측* 으로 단정 금지
- Tool 14: **Dose 권고 금지** — historical statistical response 만 보고
  All clinical claims require ``[CLINICIAN-REVIEW]`` marker.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from vitalagent.tools.envelope import ToolError, ToolRequest, ToolResponse

if TYPE_CHECKING:
    from vitalagent.sim_clock import SimClock


# ── Helper / 헬퍼 ──


def _leakage_guard(
    request: ToolRequest, clock: SimClock, query_window_end_s: float
) -> ToolResponse | None:
    """Refuse queries whose window extends past the current sim-time.
    현재 sim-time 이후를 포함하는 window 조회를 거부한다.
    """
    if query_window_end_s > clock.now_s:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="leakage_violation",
                message=(
                    f"query_window_end_s={query_window_end_s} exceeds "
                    f"clock.now_s={clock.now_s}"
                ),
                extra={"query_window_end_s": query_window_end_s, "clock_now_s": clock.now_s},
            ),
            quality_meta={"unimplemented_in_prototype": True},
            latency_ms=0.0,
        )
    return None


def _stub_response(
    request: ToolRequest, result: dict[str, Any], latency_ms: float
) -> ToolResponse:
    """Wrap a STUB response with ``unimplemented_in_prototype`` marker.
    ``unimplemented_in_prototype`` marker가 부착된 STUB 응답 wrap.
    """
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result,
        quality_meta={
            "unimplemented_in_prototype": True,
            "clinical_review_required": True,
        },
        latency_ms=latency_ms,
    )


# ── Tool 13 — find_similar_cases ──


def tool_find_similar_cases(request: ToolRequest, clock: SimClock) -> ToolResponse:
    """STUB — returns empty list of similar cases.
    STUB — 빈 similar case list 반환.

    Schema: ``docs/tool_spec/knowledge_tools.md`` §"Tool 13".
    Real implementation: post plan_1.2 (cohort manifest) + retrieval index.
    """
    t0 = time.perf_counter()

    # current_state 가 미래 데이터 포함하면 leakage / current_state may include future
    current_state = request.args.get("current_state") or {}
    state_sim_time = float(current_state.get("sim_time_s", request.sim_time_s))
    err = _leakage_guard(request, clock, state_sim_time)
    if err is not None:
        return err

    k = int(request.args.get("k", 5))
    if not (1 <= k <= 20):
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="invalid_args",
                message=f"k must be in [1, 20], got {k}",
            ),
            quality_meta={"unimplemented_in_prototype": True},
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    result: dict[str, Any] = {
        "similar_cases": [],
        "meta": {
            "cohort_index_version": None,
            "retrieval_method": "stub",
            "note": "Stage 1 prototype STUB — real implementation pending plan_1.2",
        },
    }
    return _stub_response(request, result, (time.perf_counter() - t0) * 1000.0)


# ── Tool 14 — intervention_response_prediction ──


def tool_intervention_response_prediction(
    request: ToolRequest, clock: SimClock
) -> ToolResponse:
    """STUB — returns empty response distribution.
    STUB — 빈 response distribution 반환.

    ⚠️ Dose 권고 금지 — historical statistical response 만 보고하는 schema.
    ⚠️ NOT a dose recommendation — reports historical statistical response only.

    Schema: ``docs/tool_spec/knowledge_tools.md`` §"Tool 14".
    Real implementation: post ADR-013 decision.
    """
    t0 = time.perf_counter()

    current_state = request.args.get("current_state") or {}
    state_sim_time = float(current_state.get("sim_time_s", request.sim_time_s))
    err = _leakage_guard(request, clock, state_sim_time)
    if err is not None:
        return err

    intervention = request.args.get("intervention")
    if not isinstance(intervention, dict) or "name" not in intervention:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="invalid_args",
                message="intervention must be an object with a 'name' field",
            ),
            quality_meta={"unimplemented_in_prototype": True},
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    horizon_min = int(request.args.get("horizon_min", 5))
    empty_traj = [0.0] * horizon_min

    result: dict[str, Any] = {
        "response_distribution": {
            "mean": empty_traj,
            "p10": empty_traj,
            "p90": empty_traj,
            "metric": "unknown",
        },
        "n_reference_cases": 0,
        "meta": {
            "cohort_index_version": None,
            "model_version": "stub",
            "clinical_review_required": True,
            "note": "Stage 1 prototype STUB — real implementation pending ADR-013",
        },
    }
    return _stub_response(request, result, (time.perf_counter() - t0) * 1000.0)


__all__ = [
    "tool_find_similar_cases",
    "tool_intervention_response_prediction",
]
