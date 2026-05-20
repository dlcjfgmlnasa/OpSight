"""Tests for Tool 11 / 12 real-data lookup via cases.csv (Sprint 7.11).
Tool 11 / 12 의 cases.csv 실 데이터 lookup 테스트 (Sprint 7.11).

Covers:
- Real lookup path when case_id is "vitaldb-N" and cases.csv cache exists.
- Mock fallback path for non-vitaldb case ids (synth-X, c1, etc.).
- Mock fallback when caseid is unknown to the cache.
- Phase boundaries via anestart / opstart / opend / aneend.
- Leakage guard on Tool 11 still works.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from opsight.sim_clock import SimClock
from opsight.tools.envelope import ToolRequest
from opsight.tools.emr_tools_stub import (
    _extract_vitaldb_case_id,
    _load_cases_cache,
    _surgery_progress_from_case,
    _baseline_from_case,
    tool_query_surgery_progress,
    tool_query_patient_baseline,
)


CASES_CSV = Path(__file__).resolve().parents[1] / "docs" / "notebooks" / "_cache" / "cases.csv"
_HAS_CACHE = CASES_CSV.exists()


# ── case_id parsing ──


def test_extract_case_id_vitaldb_form() -> None:
    assert _extract_vitaldb_case_id("vitaldb-3") == 3
    assert _extract_vitaldb_case_id("vitaldb-12345") == 12345


def test_extract_case_id_non_vitaldb_returns_none() -> None:
    assert _extract_vitaldb_case_id("synth-001") is None
    assert _extract_vitaldb_case_id("c1") is None
    assert _extract_vitaldb_case_id("vitaldb-abc") is None
    assert _extract_vitaldb_case_id("VITALDB-3") is None  # case-sensitive


# ── _surgery_progress_from_case unit ──


def test_phase_boundaries_via_case_row() -> None:
    """Phase transitions at anestart / opstart / opend / aneend."""
    row = {"anestart": 100.0, "opstart": 200.0, "opend": 1000.0, "aneend": 1200.0}
    # Before anestart
    r = _surgery_progress_from_case(row, current_time=50.0)
    assert r["phase"] == "pre_anesthesia"
    # Between anestart and opstart
    r = _surgery_progress_from_case(row, current_time=150.0)
    assert r["phase"] == "induction"
    # Between opstart and opend
    r = _surgery_progress_from_case(row, current_time=500.0)
    assert r["phase"] == "maintenance"
    # Between opend and aneend
    r = _surgery_progress_from_case(row, current_time=1100.0)
    assert r["phase"] == "emergence"
    # After aneend
    r = _surgery_progress_from_case(row, current_time=1300.0)
    assert r["phase"] == "post_op"


def test_elapsed_min_anchored_to_anestart() -> None:
    """elapsed_min measured from anestart (not from sim_time 0)."""
    row = {"anestart": 60.0, "opstart": 120.0, "opend": 600.0, "aneend": 660.0}
    r = _surgery_progress_from_case(row, current_time=300.0)
    # 300s - 60s = 240s = 4 min
    assert r["elapsed_min"] == pytest.approx(4.0)
    # Remaining: 660 - 300 = 360s = 6 min
    assert r["estimated_remaining_min"] == pytest.approx(6.0)


# ── _baseline_from_case unit ──


def test_baseline_row_extracts_demographics_and_labs() -> None:
    row = {
        "age": 62.0, "sex": "M", "asa": 2.0,
        "height": 170.0, "weight": 70.0, "bmi": 24.2,
        "preop_htn": 1, "preop_dm": 0,
        "preop_hb": 13.5, "preop_cr": 0.9,
        "preop_k": 4.2, "preop_na": 138.0, "preop_alb": 4.0,
        "department": "General surgery", "optype": "colectomy",
        "approach": "open", "ane_type": "general", "emop": 0,
    }
    r = _baseline_from_case(row)
    assert r["age"] == 62.0
    assert r["sex"] == "M"
    assert r["comorbidities"] == ["HTN"]
    assert r["labs"]["hb_g_dl"] == 13.5
    assert r["labs"]["cr_mg_dl"] == 0.9
    assert r["source"] == "cases_csv"
    assert r["emop"] is False


def test_baseline_row_collects_multiple_comorbidities() -> None:
    row = {"preop_htn": 1, "preop_dm": 1, "age": 70, "sex": "F", "asa": 3,
           "height": 160, "weight": 60, "bmi": 23, "preop_hb": None,
           "preop_cr": None, "preop_k": None, "preop_na": None, "preop_alb": None,
           "department": None, "optype": None, "approach": None,
           "ane_type": None, "emop": 1}
    r = _baseline_from_case(row)
    assert r["comorbidities"] == ["HTN", "DM"]
    assert r["emop"] is True


# ── Tool wrappers — mock fallback paths (always available) ──


def test_query_surgery_progress_falls_back_for_non_vitaldb_id() -> None:
    clock = SimClock(start_s=0.0); clock.tick(300.0)
    req = ToolRequest(case_id="synth-001", sim_time_s=300.0,
                      tool_name="query_surgery_progress", args={})
    resp = tool_query_surgery_progress(req, clock)
    assert resp.ok
    assert resp.result["source"] == "mock_fallback"
    assert resp.result["fallback_reason"] == "case_id_not_vitaldb_form"


def test_query_patient_baseline_falls_back_for_non_vitaldb_id() -> None:
    clock = SimClock(start_s=0.0)
    req = ToolRequest(case_id="c1", sim_time_s=0.0,
                      tool_name="query_patient_baseline", args={})
    resp = tool_query_patient_baseline(req, clock)
    assert resp.ok
    assert resp.result["source"] == "mock_fallback"
    # Mock has age=65, sex=M, asa=2 baseline.
    assert resp.result["age"] == 65


def test_query_surgery_progress_leakage_guard_still_fires() -> None:
    clock = SimClock(start_s=0.0); clock.tick(100.0)
    req = ToolRequest(case_id="vitaldb-3", sim_time_s=100.0,
                      tool_name="query_surgery_progress",
                      args={"current_time": 200.0})  # > clock.now_s=100
    resp = tool_query_surgery_progress(req, clock)
    assert not resp.ok
    assert resp.error is not None
    assert resp.error.type == "leakage_violation"


# ── Real-lookup paths (skipped when cache absent) ──


@pytest.mark.skipif(not _HAS_CACHE, reason="cases.csv cache not built")
def test_query_patient_baseline_real_lookup_returns_case_specific_values() -> None:
    """vitaldb-3 should produce different baseline than vitaldb-4 (real data).
    vitaldb-3 와 vitaldb-4 의 baseline 이 달라야 함 (real data 차별화).
    """
    cache = _load_cases_cache()
    assert cache is not None and 3 in cache and 4 in cache

    clock = SimClock(start_s=0.0)
    r3 = tool_query_patient_baseline(
        ToolRequest(case_id="vitaldb-3", sim_time_s=0.0,
                    tool_name="query_patient_baseline", args={}),
        clock,
    ).result
    r4 = tool_query_patient_baseline(
        ToolRequest(case_id="vitaldb-4", sim_time_s=0.0,
                    tool_name="query_patient_baseline", args={}),
        clock,
    ).result
    # Both should hit real-data path
    assert r3["source"] == "cases_csv"
    assert r4["source"] == "cases_csv"
    # At least one demographic should differ between case 3 and 4
    # (per manifest: case 3 age 62 ASA 1, case 4 age 74 ASA 2)
    differ = (r3["age"] != r4["age"]) or (r3["asa"] != r4["asa"])
    assert differ, f"case 3 and 4 baselines unexpectedly identical: {r3}, {r4}"


@pytest.mark.skipif(not _HAS_CACHE, reason="cases.csv cache not built")
def test_query_surgery_progress_real_lookup_uses_case_timings() -> None:
    """The case-specific opstart/opend should be present in result.
    Case-specific opstart/opend 가 결과에 포함됨.
    """
    cache = _load_cases_cache()
    assert cache is not None and 3 in cache

    # Tick to t=60s (well-defined positive sim time)
    clock = SimClock(start_s=0.0); clock.tick(60.0)
    resp = tool_query_surgery_progress(
        ToolRequest(case_id="vitaldb-3", sim_time_s=60.0,
                    tool_name="query_surgery_progress", args={}),
        clock,
    )
    assert resp.ok
    assert resp.result["source"] == "cases_csv"
    # Phase must be one of the well-defined enum values.
    # Phase 가 정의된 enum 값 중 하나.
    assert resp.result["phase"] in (
        "pre_anesthesia", "induction", "maintenance", "emergence", "post_op",
    )
    # case-specific timings present in result
    assert "anestart_s" in resp.result and "opend_s" in resp.result


def test_query_patient_baseline_falls_back_for_unknown_caseid() -> None:
    """A vitaldb-N where N is out of range → mock fallback, no crash.
    범위 밖 vitaldb-N → mock fallback, crash 없음.
    """
    clock = SimClock(start_s=0.0)
    resp = tool_query_patient_baseline(
        ToolRequest(case_id="vitaldb-999999999", sim_time_s=0.0,
                    tool_name="query_patient_baseline", args={}),
        clock,
    )
    assert resp.ok
    # Either real cache returns ok with no row, OR cache absent → both fallback
    # Real cache + unknown id → "caseid_X_not_in_cache"
    # No cache → "cases_csv_missing"
    if resp.result["source"] == "mock_fallback":
        assert resp.result["fallback_reason"].startswith(
            ("caseid_", "cases_csv_missing")
        )
