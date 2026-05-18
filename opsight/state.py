"""LangGraph ``AgentState`` schema (plan_1.8 task 3).
LangGraph ``AgentState`` 스키마 (plan_1.8 task 3).

Single source of truth for state that flows between LangGraph nodes
(``shallow_loop``, ``deep_brief``, etc.). State is serializable so traces can
be persisted to JSONL.
``shallow_loop``, ``deep_brief`` 등 LangGraph node 사이를 흐르는 state의 단일
진실 원천. trace를 JSONL로 영속화할 수 있도록 직렬화 가능하다.

Spec: ``docs/project_brief.md §6`` (Dual-Mode Architecture).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opsight.tools.envelope import ToolResponse


Mode = Literal["shallow", "deep"]
"""Agent loop mode / Agent loop 모드.

- ``shallow``: 30-second tick light cycle / 30초 tick 가벼운 cycle.
- ``deep``  : event-triggered full sweep / 이벤트 trigger full sweep.
"""


class RiskSample(BaseModel):
    """Single risk observation captured during a shallow tick.
    단일 shallow tick에서 캡쳐된 risk 관찰값.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sim_time_s: float
    risk_type: str            # e.g. "hypotension_h5", "arrest_h5"
    risk: float
    uncertainty: float


class QualitySample(BaseModel):
    """Single per-modality quality observation.
    단일 modality 품질 관찰값.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sim_time_s: float
    modality: str
    score: float


class BriefRecord(BaseModel):
    """One deep-mode brief emitted by the agent.
    Agent가 발화한 deep-mode 브리프 하나.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sim_time_s: float
    trigger_reason: str       # e.g. "hypotension_risk_gt_0.7"
    sections: dict[str, str]  # 9-section brief — section name → text
    latency_ms: float = 0.0


class AgentState(BaseModel):
    """Mutable LangGraph state for VitalAgent / VitalAgent LangGraph state.

    Pydantic ``BaseModel`` for typed validation. State is intended to be
    *replaced* by node functions returning a new ``AgentState`` (functional
    update). Direct in-place mutation works but is discouraged.
    Pydantic ``BaseModel``로 type 검증. State는 node 함수가 새 ``AgentState``를
    반환하는 functional update 방식이 권장된다. in-place 변경도 가능하지만
    권장하지 않는다.
    """

    # Pydantic v2 config: forbid extra fields, but allow mutation since
    # LangGraph nodes mutate state (functional update on top is still possible).
    # Pydantic v2 config: 추가 필드 금지, 단 LangGraph node가 state를 변경하므로
    # mutation 허용 (functional update도 그 위에서 가능).
    model_config = ConfigDict(extra="forbid")

    # ── Identity / 식별 ──
    case_id: str
    trace_id: str

    # ── Clock / 시계 ──
    sim_time_s: float = 0.0
    """Simulated time in seconds since case start.
    Case 시작 후 시뮬레이션 시간 (초).

    Tools MUST refuse data with timestamps > ``sim_time_s`` (project_brief §13.2).
    Tool은 timestamp > ``sim_time_s``인 데이터를 거부해야 한다 (brief §13.2).
    """

    # ── Mode / 모드 ──
    mode: Mode = "shallow"

    # ── History buffers / 히스토리 버퍼 ──
    last_tool_results: list[ToolResponse] = Field(default_factory=list)
    """Tool responses from the most recent node invocation.
    가장 최근 node 호출의 tool 응답.
    """

    risk_history: list[RiskSample] = Field(default_factory=list)
    quality_history: list[QualitySample] = Field(default_factory=list)
    brief_history: list[BriefRecord] = Field(default_factory=list)

    # ── Trigger bookkeeping / Trigger 추적 ──
    last_deep_trigger_time_s: float | None = None
    """``sim_time_s`` at which the most recent deep escalation fired.
    가장 최근 deep escalation이 발화한 ``sim_time_s``.

    Used by the trigger engine to enforce the 60-second cooldown.
    Trigger engine이 60초 cooldown 강제용으로 사용.
    """

    # ── Free-form scratchpad / 자유 형식 scratchpad ──
    scratch: dict[str, Any] = Field(default_factory=dict)
    """Free-form per-node state (e.g. accumulated counters).
    Node별 자유 형식 state (예: 누적 counter).

    Schema-free intentionally; do not rely on any particular key.
    의도적 schema-free; 특정 key의 존재를 가정하지 않는다.
    """


__all__ = ["AgentState", "Mode", "RiskSample", "QualitySample", "BriefRecord"]
