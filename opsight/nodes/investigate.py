"""LLM investigation node — bounded ReAct for ambiguous ticks (ADR-023).
LLM 조사 node — 애매 케이스용 bounded ReAct (ADR-023).

Router 가 ``AMBIGUOUS`` 로 분류한 tick 에서만 호출된다. LLM 이 **스스로 적절한
tool 을 골라**(예: get_signal_trend, assess_variability, [Stage 2] predict_hypotension)
호출·관찰·재판단을 반복하고(ReAct), 최종 assessment 를 낸다.

자율성 경계(ADR-023):
- 본 node 안에서만 LLM tool-selection 이 허용된다(bounded by ``max_steps``).
- tool 호출은 whitelist(``available_tools``)로 제한되고, ``call_tool`` 내부의
  leakage_guard 가 호출 주체와 무관하게 미래 데이터를 차단한다(자율성 ⟂ 누수).
- **최종 알람은 LLM 이 아니라 rule gate(:func:`alarm_gate`)가 결정한다.** LLM 은
  정보(예측치/근거)만 제공한다.

⚠️ 본 module 은 **골격**이다. 실제 ``decide()`` (vLLM tool-calling)는 langgraph-
   engineer 가 Stage 2 에 구현한다(ADR-011 / ADR-023). 여기서는 Protocol + 루프 +
   rule gate 를 정의하고 deterministic double 로 검증한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from opsight.envelope import ToolRequest
from opsight.registry import TOOLS, call_tool

if TYPE_CHECKING:
    import torch

    from opsight.envelope import ToolResponse
    from opsight.router import RouteDecision
    from opsight.sim_clock import SimClock
    from opsight.trace import TraceWriter


# ── Config / 설정 ──

# Tools the LLM may select during investigation. Subset of the registry — the
# signal-state extractors (deeper signal inspection). ``predict_hypotension``
# joins once it is registered (Stage 2, ADR-023).
# 조사 중 LLM 이 고를 수 있는 tool whitelist (레지스트리의 부분집합).
DEFAULT_INVESTIGATE_TOOLS: tuple[str, ...] = (
    "get_signal_trend",
    "describe_signal",
    "assess_variability",
    "compare_to_baseline",
    # "predict_hypotension",  # 등록 후 합류 (Stage 2)
)

MAX_INVESTIGATE_STEPS: int = 6  # bounded ReAct — 무한루프 방지 상한

# Alarm rule gate threshold [CLINICIAN-REVIEW: 의료진 검토 필요] — align with HPI
# cutoff (ADR-023 open question). LLM 예측치를 알람으로 옮기는 rule 임계 τ.
_ALARM_RISK_TAU: float = 0.7


# ── Data structures / 데이터 구조 ──


@dataclass(frozen=True)
class InvestigateAction:
    """One ReAct step the LLM emits / LLM 이 내는 한 ReAct step.

    ``kind="tool_call"`` → ``tool_name`` + ``args`` 로 도구 호출.
    ``kind="final"``     → ``assessment`` 으로 조사 종료.
    """

    kind: Literal["tool_call", "final"]
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None


@dataclass(frozen=True)
class InvestigationContext:
    """What the LLM sees at each decide() step / 매 step LLM 이 보는 맥락."""

    route_decision: RouteDecision
    vitals: dict[str, Any]
    observations: list[ToolResponse]      # 지금까지 호출한 tool 결과
    available_tools: tuple[str, ...]
    step: int
    max_steps: int


@dataclass(frozen=True)
class InvestigationResult:
    """Outcome of one investigation / 한 조사의 결과."""

    assessment: dict[str, Any]            # LLM 최종 assessment (예: hypotension_risk)
    tools_used: list[str]
    steps: int
    hit_step_limit: bool
    observations: list[ToolResponse] = field(default_factory=list)


@runtime_checkable
class InvestigatorLLM(Protocol):
    """LLM surface for ReAct tool-selection (separate from narrate/brief).
    ReAct tool 선택용 LLM surface (narrate/brief 와 분리 — interface segregation).
    """

    def decide(self, context: InvestigationContext) -> InvestigateAction:
        """Pick the next action given the running context.
        현재 맥락에서 다음 action(도구 호출 또는 종료)을 고른다.
        """
        ...


# ── Bounded ReAct loop / Bounded ReAct 루프 ──


def llm_investigate(
    *,
    route_decision: RouteDecision,
    vitals: dict[str, Any],
    clock: SimClock,
    signal: dict[str, torch.Tensor],
    llm_client: InvestigatorLLM,
    case_id: str,
    sim_time_s: float,
    available_tools: tuple[str, ...] = DEFAULT_INVESTIGATE_TOOLS,
    max_steps: int = MAX_INVESTIGATE_STEPS,
    trace: TraceWriter | None = None,
) -> InvestigationResult:
    """Run a bounded LLM-driven tool-selection loop for an ambiguous tick.
    애매 tick 에 대해 bounded LLM tool-선택 루프를 돌린다.

    The LLM picks a whitelisted tool, observes the (leakage-guarded) result, and
    repeats until it emits a ``final`` action or ``max_steps`` is reached.
    LLM 이 whitelist tool 을 고르고 (leakage-guard 된) 결과를 관찰, ``final`` 또는
    ``max_steps`` 까지 반복.
    """
    observations: list[ToolResponse] = []
    tools_used: list[str] = []

    for step in range(max_steps):
        ctx = InvestigationContext(
            route_decision=route_decision,
            vitals=vitals,
            observations=list(observations),
            available_tools=available_tools,
            step=step,
            max_steps=max_steps,
        )
        action = llm_client.decide(ctx)

        if action.kind == "final":
            if trace is not None:
                trace.event("investigate_final",
                            {"step": step, "assessment": action.assessment or {}},
                            sim_time_s=sim_time_s)
            return InvestigationResult(
                assessment=action.assessment or {},
                tools_used=tools_used,
                steps=step,
                hit_step_limit=False,
                observations=observations,
            )

        # tool_call — enforce whitelist + registry membership (safety).
        name = action.tool_name
        if name not in available_tools or name not in TOOLS:
            # LLM 이 비허용/미등록 tool 을 고르면 호출하지 않고 step 만 소비.
            if trace is not None:
                trace.event("investigate_rejected",
                            {"step": step, "tool": name}, sim_time_s=sim_time_s)
            continue

        req = ToolRequest(case_id=case_id, sim_time_s=sim_time_s,
                          tool_name=name, args=action.args or {})
        if trace is not None:
            trace.event("tool_call", {"tool": name, "args": req.args}, sim_time_s=sim_time_s)
        resp = call_tool(name, req, clock=clock, signal=signal)
        observations.append(resp)
        tools_used.append(name)
        if trace is not None:
            trace.event("tool_result",
                        {"tool": name, "ok": resp.ok, "latency_ms": resp.latency_ms},
                        sim_time_s=sim_time_s)

    # Step budget exhausted without a final assessment.
    return InvestigationResult(
        assessment={},
        tools_used=tools_used,
        steps=max_steps,
        hit_step_limit=True,
        observations=observations,
    )


# ── Alarm rule gate / 알람 rule gate ──


def alarm_gate(
    assessment: dict[str, Any], *, tau: float = _ALARM_RISK_TAU
) -> tuple[bool, str]:
    """Decide alarm from an investigation assessment — RULE, not LLM (ADR-023).
    조사 assessment 로부터 알람 여부를 결정 — LLM 이 아니라 RULE (ADR-023).

    LLM 은 ``hypotension_risk`` 같은 예측치를 제공할 뿐, 알람 발화는 본 rule gate 가
    한다. 이로써 LLM 이 실제 위험을 못 끄고 헛알람도 못 울린다(patient-safety 결정성).
    """
    risk = assessment.get("hypotension_risk")
    if isinstance(risk, (int, float)) and not isinstance(risk, bool) and risk >= tau:
        return True, f"investigation_hypotension_risk_ge_{tau} (risk={float(risk):.2f})"
    return False, "investigation_below_alarm_gate"


__all__ = [
    "DEFAULT_INVESTIGATE_TOOLS",
    "MAX_INVESTIGATE_STEPS",
    "InvestigateAction",
    "InvestigationContext",
    "InvestigationResult",
    "InvestigatorLLM",
    "llm_investigate",
    "alarm_gate",
]
