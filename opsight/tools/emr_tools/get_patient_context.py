"""Tool: get_patient_context — preoperative patient context from VitalDB cases.
수술 전 환자 컨텍스트 (VitalDB ``cases`` 메타데이터, 누수-0 화이트리스트).

case_id → 환자가 "어떤 환자인지"의 정량 source (Brief §[Surgery context] grounding):
인구통계(age/sex/bmi) + 위험도(asa) + 수술(department/opname/dx). 값만 반환하며
임상 판정 문구는 출력하지 않는다 — 해석 시 ``[CLINICIAN-REVIEW]`` marker 부착은
Brief LLM 책임 (Clinical Fact Guard, brief §13.1).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opsight.leakage_guard import leakage_guard
from opsight.tools.emr_tools._common import (
    INT_FIELDS,
    PREOP_SAFE_FIELDS,
    _error_response,
    _ok,
    load_cases,
)

if TYPE_CHECKING:
    from opsight.envelope import ToolRequest, ToolResponse
    from opsight.sim_clock import SimClock


def tool_get_patient_context(
    request: ToolRequest, clock: SimClock
) -> ToolResponse:
    """Preoperative patient context for ``request.case_id`` (clock-only tool).
    ``request.case_id`` 의 수술 전 환자 컨텍스트 (signal 불필요, clock-only).

    Leakage: preop metadata is fixed before the case (window end = 0.0), so it
    is always ≤ ``clock.now_s``; the real protection is the ``PREOP_SAFE_FIELDS``
    whitelist — postop/outcome/``intraop_*`` columns are structurally never read.
    누수: preop 데이터는 case 시작 전 확정(window 끝 = 0.0)이라 항상 now 이하 —
    실질 방어는 화이트리스트 컬럼만 읽는 것.

    Errors:
        invalid_args: case_id 가 정수 caseid 가 아니거나 cohort 에 없음.
        missing_dependency: VitalDB cases 메타데이터를 로드할 수 없음.
    """
    t0 = time.perf_counter()
    err = leakage_guard(request, clock, 0.0, quality_meta={"category": "emr"})
    if err is not None:
        return err

    # VitalDB key is an integer caseid.
    try:
        cid = int(request.case_id)
    except (TypeError, ValueError):
        return _error_response(
            request, "invalid_args",
            f"case_id {request.case_id!r} is not a VitalDB integer caseid",
            (time.perf_counter() - t0) * 1000.0,
        )

    cases = load_cases()
    if cases is None:
        return _error_response(
            request, "missing_dependency",
            "VitalDB cases metadata unavailable (cache absent + fetch failed)",
            (time.perf_counter() - t0) * 1000.0,
            extra={"expected_cache": "docs/notebooks/_cache/cases.csv"},
        )

    rows = cases[cases["caseid"] == cid]
    if len(rows) == 0:
        return _error_response(
            request, "invalid_args",
            f"caseid {cid} not found in VitalDB cases",
            (time.perf_counter() - t0) * 1000.0,
        )
    row = rows.iloc[0]

    import pandas as pd

    # Read ONLY whitelisted preop-safe columns; NaN → None.
    fields: dict[str, Any] = {}
    missing: list[str] = []
    for col in PREOP_SAFE_FIELDS:
        raw = row[col] if col in row.index else None
        if raw is None or pd.isna(raw):
            fields[col] = None
            missing.append(col)
            continue
        val = raw.item() if hasattr(raw, "item") else raw
        fields[col] = int(val) if col in INT_FIELDS else val

    result = {
        "caseid": cid,
        "demographics": {
            "age": fields["age"], "sex": fields["sex"], "bmi": fields["bmi"],
        },
        "risk": {"asa": fields["asa"]},
        "surgery": {
            "department": fields["department"],
            "opname": fields["opname"],
            "dx": fields["dx"],
        },
        "meta": {
            "source": "vitaldb_cases_csv",
            "leakage_policy": "preop_safe_whitelist",
            "fields_returned": [c for c in PREOP_SAFE_FIELDS if c not in missing],
            "missing_fields": missing,
        },
    }
    return _ok(
        request, result, (time.perf_counter() - t0) * 1000.0,
        quality_meta={
            "source": "vitaldb_cases",
            "clinical_interpretation": "deferred_to_llm",
        },
    )
