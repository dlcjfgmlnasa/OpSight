"""plan_1.3 task (final) — EMR tools 8–12 + leakage guard, on 3 sample cases.
plan_1.3 task (final) — EMR tool 8-12 + leakage guard, 3 sample case 검증.

Scope of THIS file (kept distinct from the older Sprint-7 tests to avoid
duplication):
  - The shared ``opsight.tools._leakage_guard`` primitive (plan_1.3 task 1):
    ``assert_le`` + the envelope-aware ``leakage_guard`` + its de-duplication
    across EMR / Signal Access consumers.
  - ADR-021 §"Tool 출력 스키마 강화" schema conformance on tools 8 / 9 / 10
    (``event_capture_mode`` / ``per_event_timestamps_available`` /
    ``clinical_review_required``).
  - All 5 EMR tools exercised across 3 sample cases (vitaldb-3 with signal,
    a synthetic non-vitaldb id, an out-of-range vitaldb id).
  - MANDATORY negative test: query_window_end > sim-clock t → leakage_violation
    on every time-window tool.

Older granular drug-detection / cases.csv tests live in
``tests/test_emr_drug_lookup.py`` and ``tests/test_emr_tools_real_lookup.py``.
"""
from __future__ import annotations

import pytest
import torch

from opsight.sim_clock import SimClock
from opsight.tools._leakage_guard import (
    LeakageViolation,
    assert_le,
    leakage_guard,
)
from opsight.tools.emr_tools_stub import (
    tool_query_anesthesia_drugs,
    tool_query_fluid_blood,
    tool_query_patient_baseline,
    tool_query_surgery_progress,
    tool_query_vasoactive_drugs,
)
from opsight.tools.envelope import ToolRequest


# ── Fixtures / 3 sample cases ──


def _clock_at(t: float) -> SimClock:
    c = SimClock(start_s=0.0)
    if t > 0:
        c.tick(t)
    return c


def _req(tool: str, args: dict, *, case_id: str = "vitaldb-3",
         sim_time_s: float = 600.0) -> ToolRequest:
    return ToolRequest(case_id=case_id, sim_time_s=sim_time_s,
                       tool_name=tool, args=args)


# Three representative case ids used across the suite.
# 본 suite 전반에서 쓰는 3개 대표 case id.
SAMPLE_CASE_IDS = ("vitaldb-3", "synth-001", "vitaldb-999999999")


def _signal_with_anesthesia() -> dict[str, torch.Tensor]:
    """A 600s case running TIVA (remifentanil + propofol)."""
    return {
        "RFTN_CE": torch.full((600,), 3.5),
        "RFTN_rate": torch.full((600,), 8.0),
        "PPF_CE": torch.full((600,), 2.5),
        "PPF_rate": torch.full((600,), 12.0),
    }


# ── plan_1.3 task 1 — shared leakage guard primitive ──


class TestLeakageGuardPrimitive:
    def test_assert_le_passes_at_or_before_t(self) -> None:
        assert_le(600.0, 600.0)   # boundary — equal is allowed
        assert_le(600.0, 300.0)   # window ends before t

    def test_assert_le_raises_past_t(self) -> None:
        with pytest.raises(LeakageViolation) as exc:
            assert_le(300.0, 600.0)
        assert exc.value.t == 300.0
        assert exc.value.query_window_end == 600.0

    def test_leakage_guard_returns_none_in_bounds(self) -> None:
        clock = _clock_at(600.0)
        req = _req("query_fluid_blood", {"time_window": [0.0, 600.0]})
        assert leakage_guard(req, clock, 600.0) is None

    def test_leakage_guard_returns_error_response_out_of_bounds(self) -> None:
        clock = _clock_at(300.0)
        req = _req("query_fluid_blood", {"time_window": [0.0, 600.0]},
                   sim_time_s=300.0)
        resp = leakage_guard(req, clock, 600.0,
                             quality_meta={"emr_stub": True})
        assert resp is not None and not resp.ok
        assert resp.error is not None
        assert resp.error.type == "leakage_violation"
        assert resp.quality_meta == {"emr_stub": True}

    def test_leakage_guard_include_extra_signal_access_shape(self) -> None:
        """Signal Access consumers opt into ToolError.extra payload."""
        clock = _clock_at(300.0)
        req = _req("describe_signal", {}, sim_time_s=600.0)
        resp = leakage_guard(req, clock, 600.0,
                             quality_meta={"category": "signal_access"},
                             include_extra=True)
        assert resp is not None and resp.error is not None
        assert resp.error.extra == {
            "query_window_end_s": 600.0, "clock_now_s": 300.0,
        }

    def test_emr_and_signal_access_share_one_module(self) -> None:
        """The de-dup refactor: both consumers bind the same shared callable."""
        from opsight.tools import _leakage_guard as shared
        from opsight.tools import emr_tools_stub, signal_access_tools

        assert emr_tools_stub._shared_leakage_guard is shared.leakage_guard
        assert signal_access_tools._shared_leakage_guard is shared.leakage_guard


# ── Tool 8 — query_anesthesia_drugs (ADR-021 infusion_track) ──


class TestTool8Anesthesia:
    def test_reports_active_tiva_drugs(self) -> None:
        resp = tool_query_anesthesia_drugs(
            _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}),
            _clock_at(600.0), _signal_with_anesthesia())
        assert resp.ok
        names = {d["name"] for d in resp.result["drugs"]}
        assert {"remifentanil", "propofol"} <= names

    def test_adr021_meta_infusion_track(self) -> None:
        resp = tool_query_anesthesia_drugs(
            _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}),
            _clock_at(600.0), _signal_with_anesthesia())
        meta = resp.result["meta"]
        assert meta["event_capture_mode"] == "infusion_track"
        assert meta["per_event_timestamps_available"] is True
        assert meta["clinical_review_required"] is False

    def test_leakage_violation(self) -> None:
        resp = tool_query_anesthesia_drugs(
            _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]},
                 sim_time_s=300.0),
            _clock_at(300.0), _signal_with_anesthesia())
        assert not resp.ok and resp.error.type == "leakage_violation"


# ── Tool 9 — query_vasoactive_drugs (ADR-021 hybrid) ──


class TestTool9Vasoactive:
    def test_infusion_track_when_orchestra_active(self) -> None:
        signal = {"NEPI": torch.full((600,), 0.08)}
        resp = tool_query_vasoactive_drugs(
            _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}),
            _clock_at(600.0), signal)
        assert resp.ok
        assert resp.result["unobservable_bolus_window"] is False
        assert resp.result["meta"]["event_capture_mode"] == "infusion_track"
        assert {e["name"] for e in resp.result["events"]} == {"norepinephrine"}

    def test_stub_bolus_unobservable_default_path(self) -> None:
        """Non-cardiac default: no infusion channel → bolus unobservable."""
        resp = tool_query_vasoactive_drugs(
            _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}),
            _clock_at(600.0), {"HR": torch.full((600,), 72.0)})
        assert resp.ok
        assert resp.result["events"] == []
        assert resp.result["unobservable_bolus_window"] is True
        meta = resp.result["meta"]
        assert meta["event_capture_mode"] == "stub_bolus_unobservable"
        assert meta["per_event_timestamps_available"] is False
        assert meta["clinical_review_required"] is True

    def test_no_drugs_legacy_key_absent(self) -> None:
        """Schema migrated drugs → events (ADR-021)."""
        resp = tool_query_vasoactive_drugs(
            _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}),
            _clock_at(600.0), {})
        assert "drugs" not in resp.result
        assert "events" in resp.result

    def test_leakage_violation(self) -> None:
        resp = tool_query_vasoactive_drugs(
            _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]},
                 sim_time_s=300.0),
            _clock_at(300.0), {"PHEN": torch.full((600,), 20.0)})
        assert not resp.ok and resp.error.type == "leakage_violation"


# ── Tool 10 — query_fluid_blood (ADR-021 indefinite stub) ──


class TestTool10FluidBlood:
    def test_honest_unavailable_with_adr021_meta(self) -> None:
        resp = tool_query_fluid_blood(
            _req("query_fluid_blood", {"time_window": [0.0, 600.0]}),
            _clock_at(600.0))
        assert resp.ok
        assert resp.result["fluids"] == []
        assert resp.result["blood_products"] == []
        meta = resp.result["meta"]
        assert meta["event_capture_mode"] == "stub_case_end_only"
        assert meta["per_event_timestamps_available"] is False
        assert meta["clinical_review_required"] is True

    def test_leakage_violation(self) -> None:
        resp = tool_query_fluid_blood(
            _req("query_fluid_blood", {"time_window": [0.0, 600.0]},
                 sim_time_s=300.0),
            _clock_at(300.0))
        assert not resp.ok and resp.error.type == "leakage_violation"


# ── Tool 11 — query_surgery_progress ──


class TestTool11SurgeryProgress:
    def test_phase_enum_valid(self) -> None:
        resp = tool_query_surgery_progress(
            _req("query_surgery_progress", {"current_time": 600.0}),
            _clock_at(600.0))
        assert resp.ok
        assert resp.result["phase"] in (
            "pre_anesthesia", "induction", "maintenance", "emergence", "post_op",
        )

    def test_leakage_violation(self) -> None:
        resp = tool_query_surgery_progress(
            _req("query_surgery_progress", {"current_time": 600.0},
                 sim_time_s=300.0),
            _clock_at(300.0))
        assert not resp.ok and resp.error.type == "leakage_violation"


# ── Tool 12 — query_patient_baseline (no time-window; no leakage surface) ──


class TestTool12Baseline:
    def test_returns_baseline_fields(self) -> None:
        resp = tool_query_patient_baseline(
            _req("query_patient_baseline", {}, case_id="synth-001",
                 sim_time_s=0.0),
            _clock_at(0.0))
        assert resp.ok
        # Mock fallback path is always available regardless of cache presence.
        assert "age" in resp.result and "labs" in resp.result


# ── 3-sample-case sweep: every time-window tool refuses future windows ──


@pytest.mark.parametrize("case_id", SAMPLE_CASE_IDS)
def test_all_window_tools_reject_future_window(case_id: str) -> None:
    """Negative test across 3 sample cases — query_window_end > t fails.
    3 sample case 전반 negative test — query_window_end > t 는 실패.
    """
    clock = _clock_at(300.0)  # sim clock at t=300
    signal = _signal_with_anesthesia()
    future = {"time_window": [0.0, 600.0]}  # window end 600 > t=300

    r8 = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", future, case_id=case_id, sim_time_s=300.0),
        clock, signal)
    r9 = tool_query_vasoactive_drugs(
        _req("query_vasoactive_drugs", future, case_id=case_id, sim_time_s=300.0),
        clock, signal)
    r10 = tool_query_fluid_blood(
        _req("query_fluid_blood", future, case_id=case_id, sim_time_s=300.0),
        clock)
    r11 = tool_query_surgery_progress(
        _req("query_surgery_progress", {"current_time": 600.0},
             case_id=case_id, sim_time_s=300.0),
        clock)

    for resp in (r8, r9, r10, r11):
        assert not resp.ok, f"{resp.tool_name} should reject future window"
        assert resp.error is not None
        assert resp.error.type == "leakage_violation"


@pytest.mark.parametrize("case_id", SAMPLE_CASE_IDS)
def test_all_tools_run_in_bounds(case_id: str) -> None:
    """All 5 tools succeed (ok=True) with an in-bounds window on each case."""
    clock = _clock_at(600.0)
    signal = _signal_with_anesthesia()
    in_bounds = {"time_window": [0.0, 600.0]}

    responses = [
        tool_query_anesthesia_drugs(
            _req("query_anesthesia_drugs", in_bounds, case_id=case_id), clock, signal),
        tool_query_vasoactive_drugs(
            _req("query_vasoactive_drugs", in_bounds, case_id=case_id), clock, signal),
        tool_query_fluid_blood(
            _req("query_fluid_blood", in_bounds, case_id=case_id), clock),
        tool_query_surgery_progress(
            _req("query_surgery_progress", {"current_time": 600.0},
                 case_id=case_id), clock),
        tool_query_patient_baseline(
            _req("query_patient_baseline", {}, case_id=case_id, sim_time_s=0.0),
            _clock_at(0.0)),
    ]
    for resp in responses:
        assert resp.ok, f"{resp.tool_name} unexpectedly failed: {resp.error}"
        # Latency hook populated on every tool (quality_meta observability).
        assert resp.latency_ms >= 0.0
