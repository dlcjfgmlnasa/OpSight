"""Shallow loop node (plan_1.8 task 8).
Shallow loop node (plan_1.8 task 8).

Runs every 30 s. Calls the 5 quick FM tools, records risk / quality samples
into the state, and renders a one-sentence narration via the placeholder LLM.
30초마다 실행. 5개 quick FM tool 호출 + state에 risk / quality sample 기록 +
placeholder LLM으로 1문장 narration 렌더링.

Latency target / Latency 목표: < 15 sec (project_brief §6.1).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from vitalagent.llm.placeholder import render_shallow_narration
from vitalagent.state import AgentState, QualitySample, RiskSample
from vitalagent.tools.envelope import ToolRequest, ToolResponse
from vitalagent.tools.registry import SHALLOW_TOOL_NAMES, call_tool

if TYPE_CHECKING:
    import torch

    from vitalagent.fm.interface import BiosignalFMInterface
    from vitalagent.sim_clock import SimClock
    from vitalagent.trace import TraceWriter


def _shallow_tool_args(name: str, modalities: list[str]) -> dict:
    """Return the args dict for a shallow-loop tool call.
    Shallow loop tool 호출용 args dict 반환.
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
        # Fallback when only one modality is present / modality 1개일 때 fallback.
        return {"modality_pair": [modalities[0] if modalities else "ABP", "ABP"]}
    if name == "anomaly_score":
        return {"modality": modalities[0] if modalities else "ABP"}
    raise ValueError(f"unknown shallow tool: {name}")


def run_shallow_loop(
    state: AgentState,
    *,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    modalities: list[str],
    trace: TraceWriter | None = None,
) -> AgentState:
    """Execute one shallow-loop tick and return the updated state.
    Shallow loop tick 한 번을 실행하고 갱신된 state를 반환한다.

    Steps / 단계:
    1. Call each shallow tool sequentially (parallel left for plan_2.x).
       각 shallow tool을 순차 호출 (parallel은 plan_2.x로 미룸).
    2. Collect ``ToolResponse`` list; record risk / quality samples.
       ``ToolResponse`` list 수집; risk / quality sample 기록.
    3. Render 1-sentence narration.
       1문장 narration 렌더링.
    4. Append trace events if a writer is provided.
       Trace writer가 제공되면 이벤트 append.

    Returns:
        new ``AgentState`` (functional update via ``model_copy``).
        functional update로 새 ``AgentState``.
    """
    tool_results: list[ToolResponse] = []
    for tool_name in SHALLOW_TOOL_NAMES:
        args = _shallow_tool_args(tool_name, modalities)
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

    # Extract risk / quality samples for state history / state history용 sample 추출.
    new_risk: list[RiskSample] = list(state.risk_history)
    new_quality: list[QualitySample] = list(state.quality_history)
    for r in tool_results:
        if not r.ok or r.result is None:
            continue
        if r.tool_name == "predict_hypotension":
            new_risk.append(
                RiskSample(
                    sim_time_s=state.sim_time_s,
                    risk_type=f"hypotension_h{r.result.get('horizon_min', 5)}",
                    risk=float(r.result.get("risk", 0.0)),
                    uncertainty=float(r.result.get("uncertainty", 0.0)),
                )
            )
        elif r.tool_name == "predict_cardiac_arrest":
            new_risk.append(
                RiskSample(
                    sim_time_s=state.sim_time_s,
                    risk_type=f"arrest_h{r.result.get('horizon_min', 5)}",
                    risk=float(r.result.get("risk", 0.0)),
                    uncertainty=float(r.result.get("uncertainty", 0.0)),
                )
            )
        elif r.tool_name == "assess_signal_quality":
            modality = r.args.get("modality")
            if isinstance(modality, str):
                new_quality.append(
                    QualitySample(
                        sim_time_s=state.sim_time_s,
                        modality=modality,
                        score=float(r.result.get("score", 0.0)),
                    )
                )

    narration = render_shallow_narration(tool_results)
    if trace is not None:
        trace.event("narration", {"text": narration}, sim_time_s=state.sim_time_s)

    new_state = state.model_copy(
        update={
            "mode": "shallow",
            "last_tool_results": tool_results,
            "risk_history": new_risk,
            "quality_history": new_quality,
        }
    )
    # Stash narration in scratch for the StateGraph caller to surface.
    # StateGraph caller가 노출할 수 있게 scratch에 narration 보관.
    new_state.scratch["narration"] = narration
    return new_state


__all__ = ["run_shallow_loop"]
