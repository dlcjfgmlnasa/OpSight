"""Tool envelope — minimal Pydantic models (plan_1.8 task 2).
Tool envelope — 최소 Pydantic 모델 (plan_1.8 task 2).

⚠️ Ownership transfer / 소유권 이전:
   This module is a **minimal** inline definition created for plan_1.8 to
   unblock the LangGraph skeleton. ``plan_1.7_tool_spec.md`` is the authoritative
   owner of the envelope schema; when plan_1.7 lands, this module will be
   superseded or extended in coordination with langgraph-engineer +
   llm-prompt-engineer.
   본 module은 LangGraph skeleton 작업을 unblock하기 위한 plan_1.8용 **최소**
   inline 정의다. envelope schema의 정식 owner는 ``plan_1.7_tool_spec.md``이며,
   plan_1.7 도착 시 본 module은 대체되거나 langgraph-engineer +
   llm-prompt-engineer의 협의 하에 확장된다.

Schema source: ``docs/project_brief.md §7`` (tool suite) and the
``plan_1.7`` task "Define the common tool envelope".
Schema 출처: ``docs/project_brief.md §7`` 및 ``plan_1.7``의 "공통 tool envelope".

Mandatory fields per plan_1.7:
plan_1.7 필수 필드:
- ``case_id``, ``sim_time_s``, ``tool_name``, ``args``, ``result``,
  ``quality_meta``, ``latency_ms``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolRequest(BaseModel):
    """Tool call request envelope / Tool 호출 요청 envelope.

    Carries the simulated clock so the leakage guard can refuse out-of-bounds
    queries (project_brief §13.2).
    Leakage guard가 시간 범위 외 query를 거부할 수 있도록 simulated clock 운반
    (project_brief §13.2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    sim_time_s: float
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    """Structured error info attached to a failed ``ToolResponse``.
    실패한 ``ToolResponse``에 첨부되는 구조화된 에러 정보.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str   # e.g. "leakage_violation", "tool_internal_error"
    message: str
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolResponse(BaseModel):
    """Tool call response envelope / Tool 호출 응답 envelope.

    Either ``result`` is populated (success) or ``error`` is populated
    (failure). Never both. Quality / latency observability fields are always
    present.
    성공 시 ``result``, 실패 시 ``error``. 둘 다 동시에 채우지 않는다.
    품질 / latency observability 필드는 항상 존재한다.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    sim_time_s: float
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: ToolError | None = None
    # ``quality_meta`` carries quality-aware claim provenance — every tool
    # (mock or real) must populate this. Keys are tool-specific; see
    # docs/fm_interface_guide.md §1 for FM Result.meta conventions.
    # ``quality_meta``는 quality-aware claim의 출처를 담는다 — 모든 tool
    # (mock / real)이 채워야 한다. key는 tool별로 다르며 FM Result.meta
    # 컨벤션은 docs/fm_interface_guide.md §1 참조.
    quality_meta: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        """``True`` if the call succeeded / 성공 여부."""
        return self.error is None


__all__ = ["ToolRequest", "ToolResponse", "ToolError"]
