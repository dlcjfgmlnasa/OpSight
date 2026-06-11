"""FM-based tools (deferred placeholder package — Stage 2 FM integration).
FM 기반 tool (예비 placeholder 패키지 — Stage 2 FM 통합 시 구현).

⚠️ STATUS / 상태:
   Scoped down to a **single flagship tool**, ``predict_hypotension`` (early
   intraoperative hypotension prediction — the most validated FM target). The
   other 6 FM-prediction stubs were dropped (YAGNI): brady/tachy etc. are
   rule-tier, not FM, and extra predictors carry clinical-validation burden.
   They can be re-added one file at a time when needed.
   플래그십 **단일 tool** ``predict_hypotension`` (저혈압 조기 예측 — FM 가 정말
   필요한 검증된 target) 로 축소. 나머지 6개 stub 은 제거 (YAGNI) — 서맥/빈맥 등은
   rule-tier 이고, 예측기 추가는 임상 검증 부담을 늘린다. 필요 시 한 파일씩 재추가.

   ``predict_hypotension`` 은 아직 registry 에 **미등록** — Biosignal FM 도착 전까지
   authoritative registry 는 9 tool (auxiliary 2 + signal_state 6 + emr 1) 만 보유.

The stub returns a deterministic ``not_implemented`` envelope (category ``"fm"``)
rather than raising, so an accidental call degrades gracefully. The Stage-2
FM-head implementation replaces the module body.
stub 은 예외 대신 결정론적 ``not_implemented`` envelope(category ``"fm"``)를 반환해
오호출 시 graceful degrade. Stage-2 에서 모듈 본문을 교체한다.

Restoration owner / 구현 담당:
- FM backend is consumed through the ``BiosignalFMInterface`` Protocol (ADR-011,
  owned by langgraph-engineer). The backend-injection mechanism is a Stage-2
  design decision and is intentionally NOT fixed here.
- FM 백엔드는 ``BiosignalFMInterface`` Protocol(ADR-011, langgraph-engineer 소유)로
  소비된다. 백엔드 주입 방식은 Stage-2 설계 사항으로 여기서 확정하지 않는다.

Spec source / spec 출처: ``.plans/stage1_preparation/plan_1.7_tool_spec.md``,
``docs/decisions/ADR-011-mock-fm-strategy.md``.
"""
from __future__ import annotations

from opsight.tools.fm_tools._common import FM_TOOL_PLAN
from opsight.tools.fm_tools.predict_hypotension import tool_predict_hypotension

__all__ = [
    "FM_TOOL_PLAN",
    "tool_predict_hypotension",
]
