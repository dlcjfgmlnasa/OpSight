"""Tests for EMR Tool 8/9/10 real signal-lookup (Sprint 7.12).
EMR Tool 8/9/10 의 실 signal-lookup 테스트 (Sprint 7.12).

Tool 8 (query_anesthesia_drugs)  — RFTN20 / PPF20 / SEVO from Orchestra/Primus.
Tool 9 (query_vasoactive_drugs)  — PHEN / NEPI / DOPA / EPI from Orchestra.
Tool 10 (query_fluid_blood)      — honest "not streamable" reason marker.

Covers: drug detection from non-zero infusion, empty result when inactive,
window slicing, leakage guard, invalid args, registry dispatch (needs_signal).
"""
from __future__ import annotations

import numpy as np
import torch

from opsight.sim_clock import SimClock
from opsight.tools.envelope import ToolRequest
from opsight.tools.emr_tools_stub import (
    tool_query_anesthesia_drugs,
    tool_query_vasoactive_drugs,
    tool_query_fluid_blood,
)
from opsight.tools.registry import call_tool


def _clock_at(t: float) -> SimClock:
    c = SimClock(start_s=0.0)
    if t > 0:
        c.tick(t)
    return c


def _req(tool: str, args: dict, sim_time_s: float = 600.0) -> ToolRequest:
    return ToolRequest(case_id="vitaldb-3", sim_time_s=sim_time_s,
                       tool_name=tool, args=args)


# ── Tool 8 — query_anesthesia_drugs ──


def test_anesthesia_remifentanil_detected() -> None:
    """RFTN_CE + RFTN_rate non-zero in window → remifentanil reported."""
    clock = _clock_at(600.0)
    signal = {
        "RFTN_CE": torch.full((600,), 3.5),     # ng/mL effect-site
        "RFTN_rate": torch.full((600,), 8.0),   # mL/h
    }
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    names = [d["name"] for d in resp.result["drugs"]]
    assert "remifentanil" in names
    rftn = next(d for d in resp.result["drugs"] if d["name"] == "remifentanil")
    assert rftn["ce"] == 3.5
    assert rftn["mean_rate"] == 8.0
    assert rftn["channel"] == "Orchestra/RFTN20"
    assert resp.result["source"] == "signal_lookup"


def test_anesthesia_sevoflurane_via_primus_alias() -> None:
    """SEVO_exp (Primus alias) non-zero → sevoflurane reported."""
    clock = _clock_at(600.0)
    signal = {"SEVO_exp": torch.full((600,), 1.8)}
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    names = [d["name"] for d in resp.result["drugs"]]
    assert "sevoflurane" in names


def test_anesthesia_all_zero_infusion_skipped() -> None:
    """Channel present but all-zero (no infusion) → drug not listed."""
    clock = _clock_at(600.0)
    signal = {"PPF_CE": torch.zeros(600), "PPF_rate": torch.zeros(600)}
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    assert resp.result["drugs"] == []


def test_anesthesia_empty_when_no_drug_signal() -> None:
    """No anesthesia channels at all → empty drugs."""
    clock = _clock_at(600.0)
    signal = {"HR": torch.full((600,), 75.0)}
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    assert resp.result["drugs"] == []


def test_anesthesia_window_slicing() -> None:
    """Drug active only in last 100s of a 600s window → still detected,
    timestamp within window."""
    clock = _clock_at(600.0)
    rate = torch.zeros(600)
    rate[500:600] = 5.0  # active only 500-600s
    signal = {"RFTN_rate": rate}
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    rftn = next(d for d in resp.result["drugs"] if d["name"] == "remifentanil")
    assert rftn["mean_rate"] == 5.0   # mean over non-zero only
    # Narrower window that excludes the active region → not detected
    resp2 = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 400.0]}), clock, signal)
    assert resp2.result["drugs"] == []


def test_anesthesia_leakage_guard() -> None:
    """time_window end beyond clock.now_s → leakage_violation."""
    clock = _clock_at(300.0)
    signal = {"RFTN_rate": torch.full((600,), 8.0)}
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}, sim_time_s=300.0),
        clock, signal)
    assert not resp.ok
    assert resp.error is not None and resp.error.type == "leakage_violation"


def test_anesthesia_invalid_args() -> None:
    """Missing time_window → invalid_args error."""
    clock = _clock_at(600.0)
    resp = tool_query_anesthesia_drugs(
        _req("query_anesthesia_drugs", {}), clock, {"RFTN_rate": torch.zeros(10)})
    assert not resp.ok
    assert resp.error is not None and resp.error.type == "invalid_args"


# ── Tool 9 — query_vasoactive_drugs ──


def test_vasoactive_phenylephrine_detected() -> None:
    """PHEN rate non-zero → phenylephrine reported as infusion_track event."""
    clock = _clock_at(600.0)
    rate = torch.zeros(600)
    rate[300:600] = 25.0
    signal = {"PHEN": rate}
    resp = tool_query_vasoactive_drugs(
        _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    names = [d["name"] for d in resp.result["events"]]
    assert "phenylephrine" in names
    phen = next(d for d in resp.result["events"] if d["name"] == "phenylephrine")
    assert phen["mean_rate"] == 25.0
    assert phen["latest_rate"] == 25.0
    # ADR-021 hybrid: infusion observed → infusion_track, observable window.
    assert resp.result["unobservable_bolus_window"] is False
    assert resp.result["meta"]["event_capture_mode"] == "infusion_track"


def test_vasoactive_empty_lists_channels_checked() -> None:
    """No vasoactive active → empty events, unobservable_bolus_window True."""
    clock = _clock_at(600.0)
    signal = {"HR": torch.full((600,), 75.0)}
    resp = tool_query_vasoactive_drugs(
        _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    assert resp.ok
    assert resp.result["events"] == []
    # 4 vasoactive channels always reported as checked
    assert len(resp.result["channels_checked"]) == 4
    assert "Orchestra/PHEN_RATE" in resp.result["channels_checked"]
    # ADR-021 hybrid: no infusion → bolus window unobservable, review required.
    assert resp.result["unobservable_bolus_window"] is True
    assert resp.result["meta"]["event_capture_mode"] == "stub_bolus_unobservable"
    assert resp.result["meta"]["clinical_review_required"] is True


def test_vasoactive_multiple_drugs() -> None:
    """Both PHEN and NEPI active → both reported as events."""
    clock = _clock_at(600.0)
    signal = {
        "PHEN": torch.full((600,), 20.0),
        "NEPI": torch.full((600,), 0.05),
    }
    resp = tool_query_vasoactive_drugs(
        _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}), clock, signal)
    names = {d["name"] for d in resp.result["events"]}
    assert names == {"phenylephrine", "norepinephrine"}


def test_vasoactive_leakage_guard() -> None:
    clock = _clock_at(300.0)
    signal = {"PHEN": torch.full((600,), 20.0)}
    resp = tool_query_vasoactive_drugs(
        _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}, sim_time_s=300.0),
        clock, signal)
    assert not resp.ok
    assert resp.error is not None and resp.error.type == "leakage_violation"


# ── Tool 10 — query_fluid_blood ──


def test_fluid_blood_honest_reason() -> None:
    """Always returns empty + fluid_blood_not_streamable reason."""
    clock = _clock_at(600.0)
    resp = tool_query_fluid_blood(
        _req("query_fluid_blood", {"time_window": [0.0, 600.0]}), clock)
    assert resp.ok
    assert resp.result["fluids"] == []
    assert resp.result["blood_products"] == []
    assert resp.result["reason"] == "fluid_blood_not_streamable"
    assert resp.result["source"] == "honest_unavailable"
    assert "explanation" in resp.result


def test_fluid_blood_leakage_guard() -> None:
    clock = _clock_at(300.0)
    resp = tool_query_fluid_blood(
        _req("query_fluid_blood", {"time_window": [0.0, 600.0]}, sim_time_s=300.0),
        clock)
    assert not resp.ok
    assert resp.error is not None and resp.error.type == "leakage_violation"


# ── Registry dispatch (needs_signal=True for Tool 8/9) ──


def test_registry_dispatch_anesthesia_drugs_with_signal() -> None:
    """call_tool routes query_anesthesia_drugs with the signal argument."""
    clock = _clock_at(600.0)
    signal = {"RFTN_rate": torch.full((600,), 8.0)}
    resp = call_tool(
        "query_anesthesia_drugs",
        _req("query_anesthesia_drugs", {"time_window": [0.0, 600.0]}),
        clock=clock, signal=signal)
    assert resp.ok
    assert any(d["name"] == "remifentanil" for d in resp.result["drugs"])


def test_registry_dispatch_vasoactive_drugs_with_signal() -> None:
    clock = _clock_at(600.0)
    signal = {"PHEN": torch.full((600,), 20.0)}
    resp = call_tool(
        "query_vasoactive_drugs",
        _req("query_vasoactive_drugs", {"time_window": [0.0, 600.0]}),
        clock=clock, signal=signal)
    assert resp.ok
    assert any(d["name"] == "phenylephrine" for d in resp.result["events"])


def test_registry_dispatch_fluid_blood_no_signal() -> None:
    """query_fluid_blood dispatches without signal (needs_signal=False)."""
    clock = _clock_at(600.0)
    resp = call_tool(
        "query_fluid_blood",
        _req("query_fluid_blood", {"time_window": [0.0, 600.0]}),
        clock=clock)
    assert resp.ok
    assert resp.result["reason"] == "fluid_blood_not_streamable"
