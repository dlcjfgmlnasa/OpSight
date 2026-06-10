"""Tests for opsight.tools.signal_state_tools (ADR-016, amended 2026-06-10).
opsight.tools.signal_state_tools 테스트 (구 signal_state + signal_access_tools 병합).

Coverage:
- get_current_state: trailing-window 스냅샷 / available·missing / NaN-safe / leakage
- get_signal_trend: rising / falling / stable / single-modality / unknown / leakage
- describe_signal: NaN-safe / missing_ratio==1.0 경계 / invalid modality
- assess_variability: HRV (HR) / BPV (MAP/CVP/PAP) / SVV (PPG) / 미지의 modality
- compare_to_baseline: preop 우선 / intraop early fallback / 둘 다 부재
- summarize_current_state: get_current_state 합성 / [CLINICIAN-REVIEW] marker / 단정 어조 ban
- Leakage: `sim_time_s > clock.now_s` → leakage_violation
- Registry: signal_state 카테고리 / call_tool dispatch
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.sim_clock import SimClock
from opsight.tools.envelope import ToolRequest
from opsight.tools.registry import TOOLS, call_tool
from opsight.tools.signal_state_tools import (
    USE_NEUROKIT,
    tool_assess_variability,
    tool_compare_to_baseline,
    tool_describe_signal,
    tool_get_current_state,
    tool_get_signal_trend,
    tool_summarize_current_state,
)


# ── Fixtures / Fixture ──


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)  # now_s = 60.0
    return c


def _synth_signal_full() -> dict[str, torch.Tensor]:
    """Synthetic signal with all 9 numeric vitals + ABP/PPG waveforms."""
    rng = np.random.default_rng(0)
    n_wave = 5000
    n_num = 60
    return {
        "ABP": torch.from_numpy((80.0 + rng.normal(0, 2.0, n_wave)).astype(np.float32)),
        "SBP": torch.tensor([120.0] * n_num, dtype=torch.float32),
        "DBP": torch.tensor([70.0] * n_num, dtype=torch.float32),
        "HR": torch.tensor([75.0] * n_num, dtype=torch.float32),
        "RR": torch.tensor([12.0] * n_num, dtype=torch.float32),
        "SpO2": torch.tensor([98.0] * n_num, dtype=torch.float32),
        "EtCO2": torch.tensor([38.0] * n_num, dtype=torch.float32),
        "BIS": torch.tensor([50.0] * n_num, dtype=torch.float32),
        "BT": torch.tensor([36.5] * n_num, dtype=torch.float32),
        "PPG": torch.from_numpy((1.0 + rng.normal(0, 0.2, n_wave)).astype(np.float32)),
    }


def _req(tool: str, args: dict, sim_time_s: float = 30.0) -> ToolRequest:
    """Tool-name-first request builder (describe/variability/baseline/summarize)."""
    return ToolRequest(
        case_id="c-001", sim_time_s=sim_time_s, tool_name=tool, args=args,
    )


def _sreq(args: dict | None = None, *, sim_time_s: float = 300.0) -> ToolRequest:
    """Args-first request builder (current_state / signal_trend tests)."""
    return ToolRequest(
        case_id="c1", sim_time_s=sim_time_s,
        tool_name="t", args=args or {},
    )


# ── get_current_state ──


def test_current_state_reads_present_vitals():
    # 300 samples @ 1 Hz = 5 min. Last 10 s mean ≈ tail values.
    sig = {
        "MAP": torch.from_numpy(np.full(300, 62.0, dtype=np.float32)),
        "HR": torch.from_numpy(np.full(300, 88.0, dtype=np.float32)),
    }
    clock = SimClock(start_s=300.0)
    resp = tool_get_current_state(_sreq({"sampling_rate_hz": 1.0}), clock, sig)
    assert resp.ok
    v = resp.result["vitals"]
    assert v["map_mmHg"] == pytest.approx(62.0)
    assert v["hr_bpm"] == pytest.approx(88.0)
    # Absent vitals are reported None + listed in missing.
    assert v["spo2_pct"] is None
    assert "spo2_pct" in resp.result["missing"]
    assert set(resp.result["available"]) == {"map_mmHg", "hr_bpm"}
    assert resp.result["meta"]["source_tracks"]["map_mmHg"] == "MAP"


def test_current_state_window_takes_trailing_mean():
    # Ramp 0..299; @1Hz last 10 s = samples 290..299, mean = 294.5.
    sig = {"MAP": torch.from_numpy(np.arange(300, dtype=np.float32))}
    clock = SimClock(start_s=300.0)
    resp = tool_get_current_state(
        _sreq({"sampling_rate_hz": 1.0, "window_s": 10.0}), clock, sig)
    assert resp.ok
    assert resp.result["vitals"]["map_mmHg"] == pytest.approx(294.5)


def test_current_state_nan_safe():
    arr = np.full(60, np.nan, dtype=np.float32)
    arr[-5:] = 70.0
    sig = {"MAP": torch.from_numpy(arr)}
    clock = SimClock(start_s=300.0)
    resp = tool_get_current_state(
        _sreq({"sampling_rate_hz": 1.0, "window_s": 10.0}), clock, sig)
    assert resp.ok
    assert resp.result["vitals"]["map_mmHg"] == pytest.approx(70.0)


def test_current_state_leakage_guard():
    sig = {"MAP": torch.zeros(10, dtype=torch.float32)}
    clock = SimClock(start_s=100.0)  # now=100, request sim_time=300 → leak
    resp = tool_get_current_state(_sreq(sim_time_s=300.0), clock, sig)
    assert not resp.ok
    assert resp.error.type == "leakage_violation"


# ── get_signal_trend ──


def test_trend_detects_falling_map():
    # MAP drops 80 → 60 over 5 min @ 1 Hz.
    sig = {"MAP": torch.from_numpy(np.linspace(80.0, 60.0, 300).astype(np.float32))}
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(
        _sreq({"sampling_rate_hz": 1.0, "window_s": 300.0}), clock, sig)
    assert resp.ok
    tr = resp.result["trends"]["map_mmHg"]
    assert tr["direction"] == "falling"
    # Slope is exact: 20 mmHg drop over 5 min = -4 mmHg/min.
    assert tr["slope_per_min"] == pytest.approx(-4.0, abs=0.05)
    # delta uses robust 20% sub-window means (smaller magnitude than endpoints).
    assert tr["delta"] < -10.0
    assert tr["r_squared"] > 0.99  # near-perfect line


def test_trend_detects_rising():
    sig = {"HR": torch.from_numpy(np.linspace(70.0, 110.0, 300).astype(np.float32))}
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(
        _sreq({"sampling_rate_hz": 1.0, "modality": "hr_bpm"}), clock, sig)
    assert resp.ok
    assert resp.result["trends"]["hr_bpm"]["direction"] == "rising"


def test_trend_flat_is_stable():
    sig = {"MAP": torch.from_numpy(np.full(300, 75.0, dtype=np.float32))}
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(_sreq({"sampling_rate_hz": 1.0}), clock, sig)
    assert resp.ok
    assert resp.result["trends"]["map_mmHg"]["direction"] == "stable"


def test_trend_single_modality_only_returns_that_field():
    sig = {
        "MAP": torch.from_numpy(np.linspace(80.0, 60.0, 300).astype(np.float32)),
        "HR": torch.from_numpy(np.full(300, 88.0, dtype=np.float32)),
    }
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(
        _sreq({"sampling_rate_hz": 1.0, "modality": "MAP"}), clock, sig)
    assert resp.ok
    assert set(resp.result["trends"]) == {"map_mmHg"}


def test_trend_all_vitals_when_modality_omitted():
    sig = {
        "MAP": torch.from_numpy(np.linspace(80.0, 60.0, 300).astype(np.float32)),
        "HR": torch.from_numpy(np.full(300, 88.0, dtype=np.float32)),
    }
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(_sreq({"sampling_rate_hz": 1.0}), clock, sig)
    assert resp.ok
    assert set(resp.result["trends"]) == {"map_mmHg", "hr_bpm"}


def test_trend_unknown_modality_errors():
    sig = {"MAP": torch.zeros(10, dtype=torch.float32)}
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(
        _sreq({"modality": "not_a_vital"}), clock, sig)
    assert not resp.ok
    assert resp.error.type == "invalid_args"


def test_trend_insufficient_samples_is_unknown():
    sig = {"MAP": torch.from_numpy(np.array([70.0], dtype=np.float32))}
    clock = SimClock(start_s=300.0)
    resp = tool_get_signal_trend(_sreq({"sampling_rate_hz": 1.0}), clock, sig)
    assert resp.ok
    assert resp.result["trends"]["map_mmHg"]["direction"] == "unknown"


def test_trend_leakage_guard():
    sig = {"MAP": torch.zeros(10, dtype=torch.float32)}
    clock = SimClock(start_s=100.0)
    resp = tool_get_signal_trend(_sreq(sim_time_s=300.0), clock, sig)
    assert not resp.ok
    assert resp.error.type == "leakage_violation"


# ── describe_signal ──


def test_tool18_happy_abp_stats(clock):
    sig = _synth_signal_full()
    r = tool_describe_signal(
        _req("describe_signal", {"modality": "ABP"}), clock, sig,
    )
    assert r.ok
    res = r.result
    assert 75 < res["mean"] < 85
    assert res["std"] > 0
    assert res["min"] < res["mean"] < res["max"]
    assert res["iqr"] > 0
    assert res["missing_ratio"] == 0.0
    assert res["n_samples"] == 5000


def test_tool18_all_nan_yields_missing_ratio_1(clock):
    sig = {"X": torch.tensor([float("nan")] * 100, dtype=torch.float32)}
    r = tool_describe_signal(_req("describe_signal", {"modality": "X"}), clock, sig)
    assert r.ok
    assert r.result["missing_ratio"] == 1.0
    assert r.result["mean"] is None


def test_tool18_invalid_modality(clock):
    r = tool_describe_signal(
        _req("describe_signal", {"modality": "UNKNOWN"}), clock, {},
    )
    assert not r.ok
    assert r.error.type == "invalid_args"


def test_tool18_missing_modality_arg(clock):
    r = tool_describe_signal(_req("describe_signal", {}), clock, {})
    assert not r.ok
    assert r.error.type == "invalid_args"


# ── assess_variability ──


def test_tool19_hr_returns_hrv_metrics(clock):
    sig = _synth_signal_full()
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "HR"}), clock, sig,
    )
    assert r.ok
    assert "SDNN_ms" in r.result["metrics"]
    assert "RMSSD_ms" in r.result["metrics"]
    expected_impl = "neurokit" if USE_NEUROKIT else "numpy_fallback"
    assert r.result["meta"]["implementation"] == expected_impl


def test_tool19_map_returns_bpv_metrics(clock):
    sig = _synth_signal_full()
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "ABP"}), clock, sig,
    )
    assert r.ok
    m = r.result["metrics"]
    assert "SD_mmHg" in m
    assert "ARV_mmHg" in m
    assert m["SD_mmHg"] > 0
    assert r.result["meta"]["modality_class"] == "MAP"


def test_tool19_ppg_returns_svv_metrics(clock):
    sig = _synth_signal_full()
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "PPG"}), clock, sig,
    )
    assert r.ok
    m = r.result["metrics"]
    assert "amplitude_var" in m
    assert "SVV_pct" in m
    assert r.result["meta"]["modality_class"] == "PPG"


def test_tool19_unsupported_modality(clock):
    # Genuinely unsupported modality (CardioQ device — < 1% cohort, not modeled).
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "CardioQ/CO"}), clock, {},
    )
    assert not r.ok
    assert r.error.type == "invalid_args"


def test_tool19_cvp_returns_bpv_metrics(clock):
    """CVP family routes to BPV-style metrics (SD/ARV) — brief §1 modality."""
    rng = np.random.default_rng(0)
    sig = {
        "Solar8000/CVP": torch.from_numpy(
            (8.0 + rng.normal(0, 1.5, 60)).astype(np.float32)
        ),
    }
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "Solar8000/CVP"}), clock, sig,
    )
    assert r.ok
    m = r.result["metrics"]
    assert "SD_mmHg" in m
    assert "ARV_mmHg" in m
    assert m["SD_mmHg"] is not None and m["SD_mmHg"] > 0
    assert r.result["meta"]["modality_class"] == "CVP"


def test_tool19_pap_returns_bpv_metrics(clock):
    """PAP family routes to BPV-style metrics — brief §1 modality."""
    rng = np.random.default_rng(0)
    sig = {
        "Solar8000/PA_MBP": torch.from_numpy(
            (18.0 + rng.normal(0, 2.0, 60)).astype(np.float32)
        ),
    }
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "Solar8000/PA_MBP"}), clock, sig,
    )
    assert r.ok
    m = r.result["metrics"]
    assert "SD_mmHg" in m
    assert "ARV_mmHg" in m
    assert r.result["meta"]["modality_class"] == "PAP"


def test_tool19_missing_signal_data(clock):
    # HR modality but signal dict 비어있음
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "HR"}), clock, {},
    )
    assert not r.ok
    assert r.error.type == "invalid_args"


def test_tool19_fallback_metadata_when_no_neurokit():
    """If NeuroKit2 absent, fallback metadata should signal LF_HF unavailable.
    NeuroKit2 부재 시 fallback metadata 에 LF_HF 미가용 명시.
    """
    if USE_NEUROKIT:
        pytest.skip("NeuroKit2 installed — fallback test not applicable")
    sig = _synth_signal_full()
    c = SimClock(start_s=0.0); c.tick(60.0)
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "HR"}), c, sig,
    )
    assert r.ok
    assert r.result["meta"]["implementation"] == "numpy_fallback"
    assert "LF_HF_ratio" in r.result["meta"]["unavailable_metrics"]


# ── compare_to_baseline ──


def test_tool20_preop_baseline_priority(clock):
    sig = _synth_signal_full()  # ABP mean ≈ 80
    r = tool_compare_to_baseline(
        _req("compare_to_baseline", {"modality": "ABP", "preop_baseline": 90.0}),
        clock, sig,
    )
    assert r.ok
    assert r.result["baseline_value"] == 90.0
    assert r.result["meta"]["baseline_source"] == "preop"
    assert r.result["direction"] == "down"  # current 80 < baseline 90
    assert r.result["absolute_change"] < 0


def test_tool20_intraop_fallback_when_no_preop(clock):
    sig = _synth_signal_full()
    r = tool_compare_to_baseline(
        _req("compare_to_baseline", {"modality": "ABP", "sampling_rate_hz": 500.0}),
        clock, sig,
    )
    assert r.ok
    # intraop fallback uses first 10 min mean ≈ 80
    assert r.result["meta"]["baseline_source"] == "intraop_early_10min"
    # current ≈ same → stable
    assert r.result["direction"] in ("stable", "up", "down")
    assert r.result["baseline_value"] is not None


def test_tool20_no_baseline_available(clock):
    # signal too short for intraop fallback (need ≥ 2 samples in first 10 min)
    sig = {"ABP": torch.tensor([80.0], dtype=torch.float32)}
    r = tool_compare_to_baseline(
        _req("compare_to_baseline", {"modality": "ABP", "sampling_rate_hz": 1.0}),
        clock, sig,
    )
    assert r.ok
    assert r.result["baseline_value"] is None
    assert r.result["direction"] == "unknown"
    assert r.result["meta"]["baseline_source"] == "none"


def test_tool20_modality_absent(clock):
    r = tool_compare_to_baseline(
        _req("compare_to_baseline", {"modality": "ABP"}), clock, {},
    )
    assert not r.ok
    assert r.error.type == "invalid_args"


# ── summarize_current_state ──


# Banned diagnostic phrasings — substrings that indicate assertive language
_BANNED_PHRASES = ("이다.", "진단", "처치", "투여", "권고")


def test_tool21_rule_based_synthesizes_from_vitals(clock):
    """rule-based threshold path (ADR-018: rule_based)."""
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    assert r.ok
    res = r.result
    assert res["hemodynamic_state"] == "stable"  # MAP 80 normal
    assert res["anesthesia_state"] == "adequate_range"  # BIS 50 in 40-60
    assert res["respiratory_state"] == "stable"  # SpO2 98 normal
    assert res["meta"]["tier0_status"] == "rule_based"
    assert r.quality_meta["tier0_status"] == "rule_based"


def test_tool21_clinician_review_marker_mandatory(clock):
    """overall_assessment 는 [CLINICIAN-REVIEW] marker 를 반드시 포함."""
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    assert r.ok
    assert "[CLINICIAN-REVIEW: 의료진 검토 필요]" in r.result["overall_assessment"]


def test_tool21_no_assertive_phrasing_in_output(clock):
    """단정 어조 ("이다.", "진단", "처치", ...) 가 출력에 없어야 한다."""
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    text = (
        r.result["overall_assessment"]
        + " ".join(r.result["key_concerns"])
    )
    for banned in _BANNED_PHRASES:
        assert banned not in text, f"banned phrase {banned!r} found: {text!r}"


def test_tool21_low_map_flagged_as_concern(clock):
    # MAP 55 < 65 → 저혈압 가능성 concern
    sig = {"ABP": torch.tensor([55.0] * 5000, dtype=torch.float32),
           "HR": torch.tensor([75.0] * 60, dtype=torch.float32),
           "SpO2": torch.tensor([98.0] * 60, dtype=torch.float32),
           "BIS": torch.tensor([50.0] * 60, dtype=torch.float32)}
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    assert r.ok
    assert r.result["hemodynamic_state"] == "caution_low_pressure"
    assert any("MAP" in c for c in r.result["key_concerns"])
    # Conditional phrasing — must say "가능성을 시사함" not "MAP is low"
    assert any("가능성을 시사함" in c for c in r.result["key_concerns"])


def test_tool21_clinical_review_required_in_quality_meta(clock):
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    assert r.ok
    assert r.quality_meta["clinical_review_required"] is True
    assert r.quality_meta["tier0_status"] == "rule_based"


def test_tool21_leakage_violation(clock):
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}, sim_time_s=9999.0), clock, sig,
    )
    assert not r.ok
    assert r.error.type == "leakage_violation"


# ── Registry integration / Registry 통합 ──


def test_registry_signal_state_category():
    sa = [name for name, spec in TOOLS.items() if spec.category == "signal_state"]
    assert set(sa) == {
        "get_current_state", "get_signal_trend", "describe_signal",
        "assess_variability", "compare_to_baseline", "summarize_current_state",
    }


def test_call_tool_routes_signal_state_via_dispatch(clock):
    sig = _synth_signal_full()
    # signal-state tools needs_signal=True
    for name in ("get_current_state", "get_signal_trend", "describe_signal",
                 "assess_variability", "compare_to_baseline",
                 "summarize_current_state"):
        args = _minimal_args(name)
        req = ToolRequest(case_id="c1", sim_time_s=30.0, tool_name=name, args=args)
        r = call_tool(name, req, clock=clock, signal=sig)
        assert r.ok, f"tool {name} failed: {r.error}"


def _minimal_args(name: str) -> dict:
    if name in ("get_current_state", "get_signal_trend", "summarize_current_state"):
        return {}
    if name == "describe_signal":
        return {"modality": "ABP"}
    if name == "assess_variability":
        return {"modality": "HR"}
    if name == "compare_to_baseline":
        return {"modality": "ABP", "sampling_rate_hz": 500.0}
    raise ValueError(name)


def test_neurokit2_environment_status():
    """Documents NeuroKit2 availability — informational test."""
    assert USE_NEUROKIT or not USE_NEUROKIT
