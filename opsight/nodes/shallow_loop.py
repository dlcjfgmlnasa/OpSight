"""Shallow loop node (plan_1.8 task 8).
Shallow loop node (plan_1.8 task 8).

Runs every 30 s. Calls the quick shallow tools (rule-based current-state +
cheap EMR context), then renders a one-sentence narration via the placeholder
LLM. FM-backed forecast tools removed (Biosignal Foundation Model decoupled).
30초마다 실행. quick shallow tool (rule-based 현재상태 + cheap EMR context) 호출
후 placeholder LLM 으로 1문장 narration 렌더링. FM forecast tool 제거됨
(Biosignal Foundation Model 분리).

Latency target / Latency 목표: < 15 sec (project_brief §6.1).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from opsight.state import AgentState
from opsight.envelope import ToolRequest, ToolResponse
from opsight.registry import SHALLOW_TOOL_NAMES, call_tool

if TYPE_CHECKING:
    import torch

    from opsight.llm.client import LLMClient
    from opsight.sim_clock import SimClock
    from opsight.trace import TraceWriter


def _shallow_tool_args(
    name: str, state: AgentState, modalities: list[str]
) -> dict:
    """Return the args dict for a shallow-loop tool call.
    Shallow loop tool 호출용 args dict 반환.

    Rule-based current-state + cheap EMR context (FM forecast tools removed).
    Rule-based 현재상태 + cheap EMR context (FM forecast tool 제거).
    """
    if name == "summarize_current_state":
        return {}
    if name == "get_current_state":
        return {}
    raise ValueError(f"unknown shallow tool: {name}")


def run_shallow_loop(
    state: AgentState,
    *,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    modalities: list[str],
    trace: TraceWriter | None = None,
    llm_client: LLMClient | None = None,
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
        args = _shallow_tool_args(tool_name, state, modalities)
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

    # Risk / quality history previously sourced from FM forecast tools; with FM
    # decoupled there is no producer here, so history carries forward unchanged.
    # risk / quality history 는 FM forecast tool 이 채우던 값 — FM 분리로 producer
    # 가 없어 history 는 변경 없이 그대로 이어진다.

    # ADR-018: inject case_baseline as a synthetic tool result so the LLM sees
    # patient context (age / sex / ASA / preop baseline) without changing the
    # narrate() signature.
    # ADR-018: case_baseline 을 합성 tool result 로 주입 — narrate() signature
    # 변경 없이 LLM 이 환자 맥락 (age / sex / ASA / preop baseline) 을 볼 수
    # 있게 함.
    narration_inputs = list(tool_results)
    if state.case_baseline is not None:
        narration_inputs.insert(0, ToolResponse(
            case_id=state.case_id,
            sim_time_s=state.sim_time_s,
            tool_name="case_baseline",
            args={},
            result=dict(state.case_baseline),
            quality_meta={"source": "case_init_cache"},
            latency_ms=0.0,
        ))

    # LLM narration only when a (vLLM-backed) client is wired; otherwise the
    # tick still records tool results but emits no narration text.
    # narration 은 (vLLM) client 가 연결됐을 때만 생성 — 미연결 시 tool 결과는
    # 기록하되 narration 텍스트는 생략.
    narration = llm_client.narrate(narration_inputs) if llm_client is not None else ""
    if trace is not None:
        trace.event("narration", {"text": narration}, sim_time_s=state.sim_time_s)

    new_state = state.model_copy(
        update={
            "mode": "shallow",
            "last_tool_results": tool_results,
        }
    )
    # Stash narration in scratch for the StateGraph caller to surface.
    # StateGraph caller가 노출할 수 있게 scratch에 narration 보관.
    new_state.scratch["narration"] = narration
    return new_state


__all__ = ["run_shallow_loop"]
