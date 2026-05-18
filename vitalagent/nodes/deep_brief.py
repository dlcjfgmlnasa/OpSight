"""Deep brief node (plan_1.8 task 8).
Deep brief node (plan_1.8 task 8).

Triggered by the rule engine. Runs the full 16-tool sweep (FM 7 + EMR 5 +
Knowledge / Auxiliary placeholders), then renders the 9-section Korean
brief via the placeholder LLM.
Rule engine에 의해 trigger. 16-tool 전체 sweep 실행 (FM 7 + EMR 5 +
Knowledge / Auxiliary placeholder) 후 placeholder LLM으로 9-section 한글
브리프 렌더링.

Latency target / Latency 목표: < 60 sec (project_brief §6.2).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from vitalagent.llm.placeholder import render_deep_brief
from vitalagent.state import AgentState, BriefRecord
from vitalagent.tools.envelope import ToolRequest, ToolResponse
from vitalagent.tools.registry import TOOLS, call_tool

if TYPE_CHECKING:
    import torch

    from vitalagent.fm.interface import BiosignalFMInterface
    from vitalagent.sim_clock import SimClock
    from vitalagent.trace import TraceWriter


# Tool call args for the deep sweep / Deep sweep용 tool 호출 args.
# Keyed by tool name. Each value is a callable that returns ``args`` given
# state + modalities (so the deep sweep can vary horizon / window etc.).
# tool 이름 → state + modalities를 받아 ``args`` dict를 반환하는 callable 매핑.


def _deep_args(name: str, state: AgentState, modalities: list[str]) -> dict:
    """Return args for a deep-sweep tool call.
    Deep sweep tool 호출용 args 반환.
    """
    if name == "predict_hypotension":
        return {"horizon_min": 5, "available_modalities": modalities}
    if name == "predict_cardiac_arrest":
        return {"horizon_min": 5, "available_modalities": modalities}
    if name == "assess_signal_quality":
        return {"modality": modalities[0] if modalities else "ABP"}
    if name == "cross_modal_consistency":
        if len(modalities) >= 2:
            return {"modality_pair": [modalities[0], modalities[1]]}
        return {"modality_pair": [modalities[0] if modalities else "ABP", "ABP"]}
    if name == "temporal_trend_analysis":
        return {"modality": modalities[0] if modalities else "ABP", "window_min": 5}
    if name == "forecast_signal":
        return {"modality": modalities[0] if modalities else "ABP", "horizon_min": 5}
    if name == "anomaly_score":
        return {"modality": modalities[0] if modalities else "ABP"}
    if name in ("query_anesthesia_drugs", "query_vasoactive_drugs", "query_fluid_blood"):
        window_start = max(0.0, state.sim_time_s - 300.0)  # last 5 min
        return {"time_window": [window_start, state.sim_time_s]}
    if name == "query_surgery_progress":
        return {"current_time": state.sim_time_s}
    if name == "query_patient_baseline":
        return {}
    # Knowledge / Comparative (13–14) — STUB calls / Knowledge 비교 (13–14) STUB 호출
    if name == "find_similar_cases":
        return {
            "k": 5,
            "surgery_type": "general",
            "current_state": {"sim_time_s": state.sim_time_s},
        }
    if name == "intervention_response_prediction":
        # 본 deep sweep 에서는 placeholder intervention 으로 호출 (실 사용 시 LLM 결정)
        # Placeholder intervention for the deep sweep (in real use, decided by LLM)
        return {
            "intervention": {"name": "no_op", "amount": 0.0, "unit": "none"},
            "horizon_min": 5,
            "current_state": {"sim_time_s": state.sim_time_s},
        }
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
    if name == "get_current_vitals":
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
    raise ValueError(f"unknown deep tool: {name}")


def run_deep_brief(
    state: AgentState,
    *,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    modalities: list[str],
    trigger_reason: str,
    trace: TraceWriter | None = None,
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
        resp = call_tool(tool_name, req, fm=fm, clock=clock, signal=signal)
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

    # Surgery context from the EMR query 11 result.
    # EMR tool 11 결과에서 surgery context 추출.
    surgery_phase = "maintenance"
    elapsed_min = state.sim_time_s / 60.0
    for r in tool_results:
        if r.tool_name == "query_surgery_progress" and r.ok and r.result is not None:
            surgery_phase = str(r.result.get("phase", surgery_phase))
            elapsed_min = float(r.result.get("elapsed_min", elapsed_min))
            break

    sections = render_deep_brief(
        tool_results,
        surgery_type="general",
        surgery_phase=surgery_phase,
        elapsed_min=elapsed_min,
    )
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
