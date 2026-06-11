"""FM-based tools (deferred placeholder package — Stage 2 FM integration).
FM 기반 tool (예비 placeholder 패키지 — Stage 2 FM 통합 시 복원).

⚠️ STATUS / 상태:
   These 7 tools were the old FM-based prediction category (구 tools 1–7) removed
   from the Stage-1 skeleton in the false-alarm-agent rebuild (commit 1105925,
   2026-06-10; project_brief §7.6). They are **NOT registered** in
   ``opsight/registry.py`` yet — the authoritative registry holds 8 tools
   (auxiliary 2 + signal_state 6) until the Biosignal FM lands.
   본 7개 tool 은 구 FM-based prediction 카테고리(구 1–7)로, false-alarm-agent
   rebuild 에서 제거됨. 아직 registry 에 **미등록** — FM 도착 전까지 authoritative
   registry 는 8 tool 만 보유한다.

Layout / 구성 (한 tool = 한 모듈, ``signal_state_tools`` 와 동일; 공용 헬퍼는 ``_common``):
each stub returns a deterministic ``not_implemented`` envelope (category ``"fm"``)
rather than raising, so an accidental call degrades gracefully. Stage-2 FM-head
implementations replace each module's body independently.
각 stub 은 예외 대신 결정론적 ``not_implemented`` envelope(category ``"fm"``)를
반환해 오호출 시 graceful degrade. Stage-2 에서 모듈 본문을 독립적으로 교체한다.

Restoration owner / 복원 담당:
- FM backend is consumed through the ``BiosignalFMInterface`` Protocol (ADR-011,
  owned by langgraph-engineer). The backend-injection mechanism is a Stage-2
  design decision and is intentionally NOT fixed here.
- FM 백엔드는 ``BiosignalFMInterface`` Protocol(ADR-011, langgraph-engineer 소유)로
  소비된다. 백엔드 주입 방식은 Stage-2 설계 사항으로 여기서 확정하지 않는다.

Spec source / spec 출처: ``.plans/stage1_preparation/plan_1.7_tool_spec.md`` (구 1–7),
``docs/decisions/ADR-011-mock-fm-strategy.md``, ``ADR-019`` (waveform morphology, Proposed-Deferred).
"""
from __future__ import annotations

from opsight.tools.fm_tools._common import FM_TOOL_PLAN
from opsight.tools.fm_tools.anomaly_score import tool_anomaly_score
from opsight.tools.fm_tools.assess_signal_quality import tool_assess_signal_quality
from opsight.tools.fm_tools.cross_modal_consistency import tool_cross_modal_consistency
from opsight.tools.fm_tools.forecast_signal import tool_forecast_signal
from opsight.tools.fm_tools.predict_cardiac_arrest import tool_predict_cardiac_arrest
from opsight.tools.fm_tools.predict_hypotension import tool_predict_hypotension
from opsight.tools.fm_tools.temporal_trend_analysis import tool_temporal_trend_analysis

__all__ = [
    "FM_TOOL_PLAN",
    "tool_predict_hypotension",
    "tool_predict_cardiac_arrest",
    "tool_assess_signal_quality",
    "tool_cross_modal_consistency",
    "tool_temporal_trend_analysis",
    "tool_forecast_signal",
    "tool_anomaly_score",
]
