"""Tests for opsight.tools.emr_tools.get_patient_context.
opsight.tools.emr_tools.get_patient_context 테스트.

- preop-safe 필드를 반환하고 누수 컬럼(intraop_*/outcome)은 절대 surface 안 함
- NaN → None + missing_fields 보고
- 미존재 / 비정수 caseid → invalid_args, cases 부재 → missing_dependency
- category="emr", Clinical Fact Guard (값만, 임상 판정 문구 없음)

Hermetic: ``load_cases`` 를 monkeypatch 하여 gitignore 된 실제 cache 에 의존하지 않음.

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_emr_tools.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

import opsight.tools.emr_tools.get_patient_context as gpc
from opsight.envelope import ToolRequest
from opsight.registry import TOOLS, call_tool
from opsight.sim_clock import SimClock
from opsight.tools.emr_tools._common import LEAKAGE_FORBIDDEN_FIELDS
from opsight.tools.emr_tools.get_patient_context import tool_get_patient_context


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)  # now_s = 60.0
    return c


def _cases_df() -> pd.DataFrame:
    """Synthetic VitalDB cases row carrying BOTH preop-safe + forbidden columns.
    누수 컬럼이 source 에 존재해도 result 에 절대 새지 않음을 증명하기 위함.
    """
    return pd.DataFrame([
        {
            "caseid": 1,
            # preop-safe
            "age": 67, "sex": "M", "bmi": 24.1, "asa": 3,
            "department": "General surgery",
            "opname": "Low anterior resection", "dx": "Rectal cancer",
            # forbidden — MUST NEVER surface
            "intraop_ebl": 500, "intraop_ftn": 250, "death_inhosp": 0,
            "icu_days": 2, "opend": 12345, "caseend": 20000,
        },
        {
            "caseid": 2,
            "age": 54, "sex": "F", "bmi": float("nan"), "asa": 2,
            "department": "Thoracic surgery", "opname": "Lobectomy",
            "dx": float("nan"),
            "intraop_ebl": 100, "death_inhosp": 0, "icu_days": 0,
        },
    ])


def _req(case_id: str, sim_time_s: float = 30.0) -> ToolRequest:
    return ToolRequest(case_id=case_id, sim_time_s=sim_time_s,
                       tool_name="get_patient_context", args={})


@pytest.fixture(autouse=True)
def _patch_cases(monkeypatch) -> None:
    """Inject the synthetic cohort for every test (no real cache I/O)."""
    df = _cases_df()
    monkeypatch.setattr(gpc, "load_cases", lambda: df)


# ── Happy path ──


def test_returns_preop_safe_fields(clock) -> None:
    r = tool_get_patient_context(_req("1"), clock)
    assert r.ok, r.error
    res = r.result
    assert res["caseid"] == 1
    assert res["demographics"] == {"age": 67, "sex": "M", "bmi": 24.1}
    assert res["risk"] == {"asa": 3}
    assert res["surgery"]["opname"] == "Low anterior resection"
    assert res["surgery"]["dx"] == "Rectal cancer"
    # age / asa surfaced as python int (not numpy / float)
    assert isinstance(res["demographics"]["age"], int)
    assert isinstance(res["risk"]["asa"], int)
    assert res["meta"]["missing_fields"] == []


def test_category_is_emr(clock) -> None:
    r = tool_get_patient_context(_req("1"), clock)
    assert r.quality_meta["category"] == "emr"
    # Clinical Fact Guard — tool emits values only, defers interpretation.
    assert r.quality_meta["clinical_interpretation"] == "deferred_to_llm"


# ── Leakage contract ──


def _all_keys(obj) -> set[str]:
    """Recursively collect every dict key in a nested structure."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            keys |= _all_keys(v)
    return keys


def test_forbidden_columns_never_surface(clock) -> None:
    """Even though the source row has intraop_*/outcome columns, the result
    dict must contain none of them — the leakage whitelist guarantee.
    """
    r = tool_get_patient_context(_req("1"), clock)
    assert r.ok
    leaked = _all_keys(r.result) & LEAKAGE_FORBIDDEN_FIELDS
    assert not leaked, f"leakage: forbidden columns surfaced: {leaked}"
    # Also assert specific high-risk values are absent anywhere in the payload.
    import json
    blob = json.dumps(r.result)
    for forbidden_val in ("12345", "20000"):  # opend / caseend
        assert forbidden_val not in blob


def test_nan_becomes_none_and_reported_missing(clock) -> None:
    r = tool_get_patient_context(_req("2"), clock)
    assert r.ok
    res = r.result
    assert res["demographics"]["bmi"] is None
    assert res["surgery"]["dx"] is None
    assert set(res["meta"]["missing_fields"]) == {"bmi", "dx"}
    assert "bmi" not in res["meta"]["fields_returned"]


# ── Error modes ──


def test_unknown_caseid_invalid_args(clock) -> None:
    r = tool_get_patient_context(_req("999999"), clock)
    assert not r.ok
    assert r.error.type == "invalid_args"


def test_non_integer_case_id_invalid_args(clock) -> None:
    r = tool_get_patient_context(_req("synthetic-case-1"), clock)
    assert not r.ok
    assert r.error.type == "invalid_args"


def test_missing_cases_dependency(clock, monkeypatch) -> None:
    monkeypatch.setattr(gpc, "load_cases", lambda: None)
    r = tool_get_patient_context(_req("1"), clock)
    assert not r.ok
    assert r.error.type == "missing_dependency"


# ── Registry integration ──


def test_registered_as_emr_clock_only(clock) -> None:
    spec = TOOLS["get_patient_context"]
    assert spec.category == "emr"
    assert spec.needs_signal is False
    # dispatched without a signal arg
    r = call_tool("get_patient_context", _req("1"), clock=clock)
    assert r.ok, r.error
    assert r.result["caseid"] == 1


def test_not_in_shallow_sweep() -> None:
    from opsight.registry import SHALLOW_TOOL_NAMES
    assert "get_patient_context" not in SHALLOW_TOOL_NAMES
