"""EMR tools 8–12 — **STUB** placeholder data (plan_1.8 task 5).
EMR tool 8–12 — **STUB** placeholder 데이터 (plan_1.8 task 5).

⚠️ This module returns hard-coded fake EMR data so the LangGraph skeleton
   can call the full 16-tool surface end-to-end. **It is replaced by the real
   implementation in plan_1.3_emr_tools.md.**
⚠️ 본 module은 hard-coded fake EMR data를 반환하여 LangGraph skeleton이
   16-tool surface 전체를 end-to-end로 호출 가능하게 한다. **plan_1.3에서
   실제 구현으로 대체된다.**

Clinical Fact Guard (project_brief §13.1): the fake data here has no clinical
meaning. Any downstream consumer rendering it to a clinician MUST mark it
``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`` or refuse to render.
임상 사실 가드 (project_brief §13.1): 본 module의 fake data는 임상 의미가
없다. 임상의에게 렌더링하는 모든 consumer는 반드시
``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`` marker를 부착하거나
렌더링을 거부해야 한다.

The leakage guard (§13.2) is still enforced — time-window queries beyond
``clock.now_s`` will error out, matching the contract the real EMR tools
will follow.
Leakage guard (§13.2)는 여전히 강제된다 — ``clock.now_s`` 이후의 time-window
조회는 error 반환 (real EMR tool 계약과 동일).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.tools.envelope import ToolError, ToolRequest, ToolResponse

if TYPE_CHECKING:
    from opsight.sim_clock import SimClock


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
            ),
            quality_meta={"emr_stub": True},
            latency_ms=0.0,
        )
    return None


def _ok(
    request: ToolRequest,
    result: dict,
    latency_ms: float,
    *,
    clinician_review: bool = True,
) -> ToolResponse:
    """Wrap a success EMR result with the standard ``emr_stub`` marker.
    표준 ``emr_stub`` marker가 부착된 성공 EMR 결과 wrap.
    """
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result,
        quality_meta={
            "emr_stub": True,
            "clinical_review_required": clinician_review,
        },
        latency_ms=latency_ms,
    )


def _resolve_window(args: dict) -> tuple[float, float]:
    """Extract ``(start_s, end_s)`` from request args; raise on bad shape.
    request args에서 ``(start_s, end_s)`` 추출; 잘못된 shape는 raise.
    """
    tw = args.get("time_window")
    if not (isinstance(tw, (list, tuple)) and len(tw) == 2):
        raise ValueError(f"time_window must be a 2-element list (got {tw!r})")
    return float(tw[0]), float(tw[1])


# ── Tool 8 — query_anesthesia_drugs ──


def tool_query_anesthesia_drugs(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Stub anesthesia-drug return (RFTN20, PPF20, SEVO first-class per brief §4.3).
    Stub anesthesia drug 반환 (brief §4.3 first-class: RFTN20 / PPF20 / SEVO).
    """
    t0 = time.perf_counter()
    try:
        start_s, end_s = _resolve_window(request.args)
    except ValueError as exc:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(type="invalid_args", message=str(exc)),
            quality_meta={"emr_stub": True},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err
    fake = {
        "drugs": [
            {"name": "remifentanil",   "amount": 0.10, "unit": "mcg/kg/min",
             "timestamp_s": (start_s + end_s) / 2, "channel": "Orchestra/RFTN20_CE"},
            {"name": "propofol",       "amount": 3.0,  "unit": "mcg/mL",
             "timestamp_s": (start_s + end_s) / 2, "channel": "Orchestra/PPF20_CE"},
            {"name": "sevoflurane",    "amount": 1.8,  "unit": "%",
             "timestamp_s": (start_s + end_s) / 2, "channel": "Primus/EXP_SEVO"},
        ]
    }
    return _ok(request, fake, (time.perf_counter() - t0) * 1000)


# ── Tool 9 — query_vasoactive_drugs ──


def tool_query_vasoactive_drugs(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Stub vasoactive drug return.
    Stub 혈관활성 약물 반환.
    """
    t0 = time.perf_counter()
    try:
        start_s, end_s = _resolve_window(request.args)
    except ValueError as exc:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(type="invalid_args", message=str(exc)),
            quality_meta={"emr_stub": True},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err
    fake = {
        "drugs": [
            # Empty by default — plan_1.3 will replace with real data.
            # 기본 빈 list — plan_1.3에서 실 데이터로 대체.
        ]
    }
    return _ok(request, fake, (time.perf_counter() - t0) * 1000)


# ── Tool 10 — query_fluid_blood ──


def tool_query_fluid_blood(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Stub fluid / blood-product return.
    Stub 수액 / 수혈 반환.
    """
    t0 = time.perf_counter()
    try:
        start_s, end_s = _resolve_window(request.args)
    except ValueError as exc:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(type="invalid_args", message=str(exc)),
            quality_meta={"emr_stub": True},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err
    fake = {
        "fluids":         [{"name": "crystalloid", "volume_ml": 500, "timestamp_s": start_s}],
        "blood_products": [],
    }
    return _ok(request, fake, (time.perf_counter() - t0) * 1000)


# ── Tool 11 — query_surgery_progress ──


def tool_query_surgery_progress(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Stub surgery-progress return — heuristic phase.
    Stub 수술 진행 반환 — 휴리스틱 phase.
    """
    t0 = time.perf_counter()
    current_time = float(request.args.get("current_time", clock.now_s))
    err = _leakage_guard(request, clock, current_time)
    if err is not None:
        return err
    # Heuristic phase / 휴리스틱 phase: first 15 min = induction, last 10 min =
    # emergence, in between = maintenance. Stub assumes 2h surgery.
    # 첫 15분 = induction, 마지막 10분 = emergence, 그 외 = maintenance. Stub은
    # 2h 수술 가정.
    total = 7200.0
    elapsed_min = current_time / 60.0
    if elapsed_min < 15:
        phase = "induction"
    elif elapsed_min > (total / 60.0) - 10:
        phase = "emergence"
    else:
        phase = "maintenance"
    fake = {
        "phase": phase,
        "elapsed_min": elapsed_min,
        "estimated_remaining_min": max(0.0, (total / 60.0) - elapsed_min),
    }
    return _ok(request, fake, (time.perf_counter() - t0) * 1000)


# ── Tool 12 — query_patient_baseline ──


def tool_query_patient_baseline(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Stub patient-baseline return (case-level metadata).
    Stub patient baseline 반환 (case 수준 metadata).
    """
    t0 = time.perf_counter()
    # No time-window for baseline; no leakage guard needed beyond sim_time itself.
    # baseline은 time-window 없음; sim_time 자체 외 leakage guard 불필요.
    fake = {
        "age": 65,
        "sex": "M",
        "asa": 2,
        "comorbidities": ["HTN"],
        "baseline_bp": 130.0,
        "labs": {"hb_g_dl": 12.5, "cr_mg_dl": 0.9},
    }
    return _ok(request, fake, (time.perf_counter() - t0) * 1000)


__all__ = [
    "tool_query_anesthesia_drugs",
    "tool_query_vasoactive_drugs",
    "tool_query_fluid_blood",
    "tool_query_surgery_progress",
    "tool_query_patient_baseline",
]
