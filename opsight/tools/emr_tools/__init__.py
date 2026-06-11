"""EMR tools — preoperative / patient-context tools.
EMR tool — 수술 전 / 환자 컨텍스트 tool.

The EMR tool group (구 tools 8–12: drug lookup, EMR queries, knowledge) was
removed from the Stage-1 skeleton in the false-alarm-agent rebuild (commit
1105925, 2026-06-10) and deferred to Stage 2.
EMR tool 그룹(구 8–12)은 false-alarm-agent rebuild 에서 제거되어 Stage 2 로 deferred.

``get_patient_context`` is the **first revived member**, brought forward because
it reads only preoperative, leakage-free case metadata (no time-series, no
postop/outcome). The remaining EMR tools stay deferred until Stage 2.
``get_patient_context`` 는 **먼저 부활한 첫 멤버** — 수술 전·누수 0 메타데이터만
읽으므로 당겨왔다. 나머지 EMR tool 은 Stage 2 까지 deferred.

Layout (한 tool = 한 모듈, 공용 헬퍼 + 누수 화이트리스트는 ``_common``):
- ``get_patient_context`` (get_patient_context.py) — age/sex/bmi/asa/department/opname/dx.
"""
from __future__ import annotations

from opsight.tools.emr_tools.get_patient_context import tool_get_patient_context

__all__ = ["tool_get_patient_context"]
