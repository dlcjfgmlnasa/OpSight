"""Deep brief node (plan_1.8 task 8).
Deep brief node (plan_1.8 task 8).

Triggered by the rule engine. Runs the full tool sweep (EMR + Knowledge /
Auxiliary + Signal Access; FM-backed tools removed — Biosignal Foundation
Model decoupled), then renders the 9-section Korean brief via the placeholder
LLM.
Rule engine 에 의해 trigger. 전체 tool sweep 실행 (EMR + Knowledge / Auxiliary +
Signal Access; FM 기반 tool 제거 — Biosignal Foundation Model 분리) 후
placeholder LLM 으로 9-section 한글 브리프 렌더링.

Latency target / Latency 목표: < 60 sec (project_brief §6.2).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from opsight.state import AgentState, BriefRecord
from opsight.envelope import ToolRequest, ToolResponse
from opsight.registry import TOOLS, call_tool

if TYPE_CHECKING:
    import torch

    from opsight.llm.client import LLMClient
    from opsight.sim_clock import SimClock
    from opsight.trace import TraceWriter


# Tool call args for the deep sweep / Deep sweep용 tool 호출 args.
# Keyed by tool name. Each value is a callable that returns ``args`` given
# state + modalities (so the deep sweep can vary horizon / window etc.).
# tool 이름 → state + modalities를 받아 ``args`` dict를 반환하는 callable 매핑.


def _deep_args(name: str, state: AgentState, modalities: list[str]) -> dict:
    """Return args for a deep-sweep tool call.
    Deep sweep tool 호출용 args 반환.
    """
    # Auxiliary (15–16) / Auxiliary tool 15–16
    if name == "surgery_context_awareness":
        return {"surgery_type": "general", "phase": "maintenance"}
    if name == "quality_aware_synthesis":
        # Fuse the two risk predictions if both were called earlier in this sweep.
        # 본 sweep 에서 호출된 risk prediction 두 개를 fuse.
        return {
            "predictions": [
                {"value": 0.0, "quality": 0.5, "source": "placeholder_a"},
                {"value": 0.0, "quality": 0.5, "source": "placeholder_b"},
            ],
            "method": "weighted_mean",
        }
    # Signal Access (17–21) — ADR-016 / plan_1.3.5
    # Signal Access (17–21) — ADR-016 / plan_1.3.5
    if name == "get_current_state":
        return {}
    if name == "get_signal_trend":
        return {}
    if name == "describe_signal":
        return {"modality": modalities[0] if modalities else "ABP", "window_min": 5}
    if name == "assess_variability":
        # Default to HR (HRV) if available, else MAP (BPV), else PPG.
        # HR (HRV) 우선, 부재 시 MAP (BPV), 그 다음 PPG.
        for m in ("HR", "ABP", "MAP", "PPG"):
            if m in modalities:
                return {"modality": m}
        return {"modality": modalities[0] if modalities else "HR"}
    if name == "compare_to_baseline":
        return {"modality": modalities[0] if modalities else "ABP",
                "sampling_rate_hz": 500.0}
    if name == "summarize_current_state":
        return {}
    # Model tools — FM-backed (Mock FM rule_based tier)
    if name == "predict_hypotension":
        return {}
    raise ValueError(f"unknown deep tool: {name}")


def run_deep_brief(
    state: AgentState,
    *,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    modalities: list[str],
    trigger_reason: str,
    trace: TraceWriter | None = None,
    llm_client: LLMClient | None = None,
) -> AgentState:
    """Execute one deep-brief sweep and return the updated state.
    Deep brief sweep 한 번을 실행하고 갱신된 state를 반환한다.
    """
    t0 = time.perf_counter()

    tool_results: list[ToolResponse] = []
    for tool_name, spec in TOOLS.items():
        try:
            args = _deep_args(tool_name, state, modalities)
        except ValueError:
            # Unknown / unsupported tools (Knowledge / Auxiliary 13–16 TBD).
            # 알 수 없는 / 미지원 tool (Knowledge / Auxiliary 13–16 TBD)은 skip.
            continue
        req = ToolRequest(
            case_id=state.case_id,
            sim_time_s=state.sim_time_s,
            tool_name=tool_name,
            args=args,
        )
        if trace is not None:
            trace.event("tool_call", {"tool": tool_name, "args": args}, sim_time_s=state.sim_time_s)
        resp = call_tool(tool_name, req, clock=clock, signal=signal)
        tool_results.append(resp)
        if trace is not None:
            trace.event(
                "tool_result",
                {
                    "tool": tool_name,
                    "ok": resp.ok,
                    "latency_ms": resp.latency_ms,
                    "result_keys": list(resp.result or {}),
                },
                sim_time_s=state.sim_time_s,
            )

    # Surgery phase / elapsed — EMR surgery-progress tool removed, so fall back
    # to a sim-time estimate (real phase wiring is a later rebuild step).
    # EMR surgery-progress tool 제거 → sim-time 추정으로 fallback (실 phase 배선은
    # 추후 rebuild 단계).
    surgery_phase = "maintenance"
    elapsed_min = state.sim_time_s / 60.0

    # Inject case-level patient context (ADR-018) as a synthetic tool result so
    # the brief's §[Surgery context] is patient-aware, without changing brief()'s
    # signature. Populated once by the case-init node; None for synthetic cases.
    # case_baseline(ADR-018)을 합성 tool result 로 주입 — §[Surgery context]가 환자
    # 인지하게. case-init node 가 1회 채움; synthetic case 는 None.
    brief_inputs = list(tool_results)
    if state.case_baseline is not None:
        brief_inputs.insert(0, ToolResponse(
            case_id=state.case_id, sim_time_s=state.sim_time_s,
            tool_name="case_baseline", args={},
            result=dict(state.case_baseline),
            quality_meta={"source": "case_init_cache"}, latency_ms=0.0,
        ))

    # Brief sections only when a (vLLM-backed) client is wired; otherwise the
    # deep record is created with empty sections (structural placeholder).
    # brief section 은 (vLLM) client 가 연결됐을 때만 생성 — 미연결 시 빈 section.
    if llm_client is not None:
        sections = llm_client.brief(
            brief_inputs,
            surgery_type="general",
            surgery_phase=surgery_phase,
            elapsed_min=elapsed_min,
        )
    else:
        sections = {}
    latency_ms = (time.perf_counter() - t0) * 1000.0
    record = BriefRecord(
        sim_time_s=state.sim_time_s,
        trigger_reason=trigger_reason,
        sections=sections,
        latency_ms=latency_ms,
    )

    if trace is not None:
        trace.event(
            "brief",
            {
                "trigger_reason": trigger_reason,
                "latency_ms": latency_ms,
                "sections": sections,
            },
            sim_time_s=state.sim_time_s,
        )

    new_state = state.model_copy(
        update={
            "mode": "deep",
            "last_tool_results": tool_results,
            "brief_history": [*state.brief_history, record],
            "last_deep_trigger_time_s": state.sim_time_s,
        }
    )
    # Clear any on-demand request flag after handling.
    # 처리 후 on-demand flag 클리어.
    if new_state.scratch.get("clinician_on_demand"):
        new_state.scratch["clinician_on_demand"] = False
    return new_state


__all__ = ["run_deep_brief"]
