"""FM-backed tool wrappers (plan_1.8 task 5, FM tools 1–7).
FM 기반 tool wrapper (plan_1.8 task 5, FM tool 1–7).

Each FM tool is a small wrapper that:
각 FM tool은 다음을 수행하는 작은 wrapper다:
1. Validates the request via the leakage guard.
   Leakage guard로 request를 검증한다.
2. Calls the corresponding ``BiosignalFMInterface`` method.
   해당 ``BiosignalFMInterface`` method를 호출한다.
3. Wraps the Result into a :class:`ToolResponse` envelope.
   결과를 :class:`ToolResponse` envelope으로 wrap한다.

⚠️ Tool layer depends ONLY on ``BiosignalFMInterface`` — no concrete FM
   class is imported here (ADR-011 swap mechanism).
⚠️ Tool layer는 ``BiosignalFMInterface``에만 의존한다 — concrete FM
   class를 본 모듈에서 import하지 않는다 (ADR-011 swap 메커니즘).

Signal payload contract: the caller supplies a ``dict[str, torch.Tensor]``
keyed by modality. The current stub FM does not actually inspect the
content; the contract is preserved for the real-FM swap.
Signal payload 계약: 호출자는 modality를 key로 하는 ``dict[str, torch.Tensor]``를
제공한다. 현재 stub FM은 content를 실제로 검사하지 않지만, 계약은 real-FM
swap을 위해 보존된다.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from vitalagent.tools.envelope import ToolError, ToolRequest, ToolResponse

if TYPE_CHECKING:
    import torch

    from vitalagent.fm.interface import BiosignalFMInterface
    from vitalagent.sim_clock import SimClock


# ── Helpers / 헬퍼 ──


def _leakage_guard(request: ToolRequest, clock: SimClock) -> ToolResponse | None:
    """Return a leakage-error ``ToolResponse`` if the request violates §13.2.
    request가 §13.2를 위반하면 leakage-error ``ToolResponse``를 반환한다.

    Tools use the simulated clock as the canonical time horizon.
    Tool은 simulated clock을 정식 시간 horizon으로 사용한다.
    """
    # The request itself carries sim_time_s; we double-check it matches the
    # clock's current view (no time travel). A future enhancement can let
    # tools query historical windows ``[t0, t1]`` with ``t1 ≤ clock.now_s``.
    # Request 자체가 sim_time_s를 운반 — clock의 현재 view와 일치하는지
    # double-check (시간 이동 금지). 향후 확장: tool이 ``t1 ≤ clock.now_s``
    # 인 historical window ``[t0, t1]``을 조회 가능.
    if request.sim_time_s > clock.now_s:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="leakage_violation",
                message=(
                    f"request.sim_time_s={request.sim_time_s} exceeds "
                    f"clock.now_s={clock.now_s}"
                ),
            ),
            quality_meta={},
            latency_ms=0.0,
        )
    return None


def _build_response(
    request: ToolRequest,
    result_payload: dict[str, Any],
    quality_meta: dict[str, Any],
    latency_ms: float,
) -> ToolResponse:
    """Construct a success ``ToolResponse`` / 성공 ``ToolResponse`` 생성."""
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result_payload,
        quality_meta=quality_meta,
        latency_ms=latency_ms,
    )


# ── 7 FM tools / 7개 FM tool ──
#
# Each tool takes (request, fm, clock, signal). ``signal`` is the modality
# payload normally produced by signal-ingest-engineer; for the stub-only
# skeleton an empty dict is acceptable.
# 각 tool은 (request, fm, clock, signal)을 받는다. ``signal``은 normally
# signal-ingest-engineer가 생성하는 modality payload — stub-only skeleton
# 에서는 빈 dict도 허용.


def tool_predict_hypotension(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 1 — predict hypotension within ``horizon_min``.
    Tool 1 — ``horizon_min`` 내 저혈압 예측.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    horizon_min = int(request.args.get("horizon_min", 5))
    available_modalities = list(request.args.get("available_modalities", list(signal)))
    r = fm.predict_hypotension(signal, horizon_min, available_modalities)
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta}, latency_ms)


def tool_predict_cardiac_arrest(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 2 — predict cardiac arrest within ``horizon_min``.
    Tool 2 — ``horizon_min`` 내 심정지 예측.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    horizon_min = int(request.args.get("horizon_min", 5))
    available_modalities = list(request.args.get("available_modalities", list(signal)))
    r = fm.predict_cardiac_arrest(signal, horizon_min, available_modalities)
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta}, latency_ms)


def tool_assess_signal_quality(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 3 — assess signal quality for one modality.
    Tool 3 — 단일 modality 신호 품질 평가.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    modality = str(request.args["modality"])
    r = fm.assess_signal_quality(signal, modality)
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta, "modality": modality}, latency_ms)


def tool_cross_modal_consistency(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 4 — cross-modal consistency for a modality pair.
    Tool 4 — modality 쌍 cross-modal 일관성.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    pair = tuple(request.args["modality_pair"])
    if len(pair) != 2:
        return ToolResponse(
            case_id=request.case_id,
            sim_time_s=request.sim_time_s,
            tool_name=request.tool_name,
            args=dict(request.args),
            error=ToolError(
                type="invalid_args",
                message=f"modality_pair must be a 2-tuple (got {pair!r})",
            ),
            quality_meta={},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    r = fm.cross_modal_consistency(signal, (str(pair[0]), str(pair[1])))
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta, "modality_pair": list(pair)}, latency_ms)


def tool_temporal_trend_analysis(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 5 — temporal trend over a window.
    Tool 5 — window에 대한 시간적 trend.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    modality = str(request.args["modality"])
    window_min = int(request.args.get("window_min", 5))
    r = fm.temporal_trend(signal, modality, window_min)
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta, "modality": modality}, latency_ms)


def tool_forecast_signal(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 6 — forecast modality trajectory.
    Tool 6 — modality trajectory 예측.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    modality = str(request.args["modality"])
    horizon_min = int(request.args.get("horizon_min", 5))
    r = fm.forecast_signal(signal, modality, horizon_min)
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta, "modality": modality}, latency_ms)


def tool_anomaly_score(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Tool 7 — anomaly score for a modality window.
    Tool 7 — modality window의 anomaly score.
    """
    err = _leakage_guard(request, clock)
    if err is not None:
        return err
    t0 = time.perf_counter()
    modality = str(request.args["modality"])
    r = fm.anomaly_score(signal, modality)
    latency_ms = (time.perf_counter() - t0) * 1000
    return _build_response(request, asdict(r), {"fm_meta": r.meta, "modality": modality}, latency_ms)


__all__ = [
    "tool_predict_hypotension",
    "tool_predict_cardiac_arrest",
    "tool_assess_signal_quality",
    "tool_cross_modal_consistency",
    "tool_temporal_trend_analysis",
    "tool_forecast_signal",
    "tool_anomaly_score",
]
