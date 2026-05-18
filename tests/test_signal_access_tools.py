"""Tests for plan_1.3.5 Signal Access tools (17–21).
plan_1.3.5 Signal Access tool (17–21) 테스트.

Coverage:
- Tool 17 get_current_vitals: 9 vital field 채워짐 / ABP→NIBP fallback / 모든 modality 부재
- Tool 18 describe_signal: NaN-safe / missing_ratio==1.0 경계 / invalid modality
- Tool 19 assess_variability: HRV (HR) / BPV (MAP) / SVV (PPG) / 미지의 modality
- Tool 20 compare_to_baseline: preop 우선 / intraop early fallback / 둘 다 부재
- Tool 21 summarize_current_state: 17–20 합성 / [CLINICIAN-REVIEW] marker / 단정 어조 ban
- Leakage: 모든 5 tool 에서 `sim_time_s > clock.now_s` → leakage_violation
- Registry: 21 entry + signal_access 카테고리 5 / call_tool dispatch
"""
from __future__ import annotations

import re

import numpy as np
import pytest
import torch

from vitalagent.sim_clock import SimClock
from vitalagent.tools.envelope import ToolRequest
from vitalagent.tools.registry import TOOLS, call_tool
from vitalagent.tools.signal_access_tools import (
    USE_NEUROKIT,
    tool_assess_variability,
    tool_compare_to_baseline,
    tool_describe_signal,
    tool_get_current_vitals,
    tool_summarize_current_state,
)


# ── Fixtures / Fixture ──


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)  # now_s = 60.0
    return c


def _synth_signal_full() -> dict[str, torch.Tensor]:
    """Synthetic signal with all 9 modalities for tool 17 happy path.
    Tool 17 happy path 용 9 modality 합성.
    """
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
    return ToolRequest(
        case_id="c-001", sim_time_s=sim_time_s, tool_name=tool, args=args,
    )


# ── Tool 17 — get_current_vitals ──


def test_tool17_happy_all_fields(clock):
    sig = _synth_signal_full()
    r = tool_get_current_vitals(_req("get_current_vitals", {}), clock, sig)
    assert r.ok
    res = r.result
    # All 9 fields populated (not None)
    for k in ("map_mmHg", "sbp_mmHg", "dbp_mmHg", "hr_bpm", "rr_per_min",
              "spo2_pct", "etco2_mmHg", "bis", "core_temp_c"):
        assert res[k] is not None, f"field {k} is None despite synthetic full signal"
    # Map sanity (synthetic mean ≈ 80)
    assert 75 < res["map_mmHg"] < 85
    # source_tracks populated
    assert "map_mmHg" in r.quality_meta["source_tracks"]


def test_tool17_nibp_fallback_when_only_nibp_present(clock):
    sig = {"Solar8000/NIBP_MBP": torch.tensor([90.0] * 60, dtype=torch.float32)}
    r = tool_get_current_vitals(_req("get_current_vitals", {}), clock, sig)
    assert r.ok
    assert r.result["map_mmHg"] == pytest.approx(90.0)
    # fallback tracked in meta
    assert any("map_mmHg" in s for s in r.result["meta"]["fallback_used"])


def test_tool17_all_modalities_absent_yields_all_none(clock):
    r = tool_get_current_vitals(_req("get_current_vitals", {}), clock, {})
    assert r.ok
    for k in ("map_mmHg", "hr_bpm", "spo2_pct", "etco2_mmHg", "bis"):
        assert r.result[k] is None


def test_tool17_leakage_violation(clock):
    # sim_time_s 9999 > clock.now_s 60 → leakage
    sig = _synth_signal_full()
    r = tool_get_current_vitals(
        _req("get_current_vitals", {}, sim_time_s=9999.0), clock, sig,
    )
    assert not r.ok
    assert r.error.type == "leakage_violation"


# ── Tool 18 — describe_signal ──


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


# ── Tool 19 — assess_variability ──


def test_tool19_hr_returns_hrv_metrics(clock):
    sig = _synth_signal_full()
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "HR"}), clock, sig,
    )
    assert r.ok
    assert "SDNN_ms" in r.result["metrics"]
    assert "RMSSD_ms" in r.result["metrics"]
    # LF/HF is None on short series even with NeuroKit
    # 짧은 series 에서는 LF/HF None
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
    r = tool_assess_variability(
        _req("assess_variability", {"modality": "PA_MBP"}), clock, {},
    )
    assert not r.ok
    assert r.error.type == "invalid_args"


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


# ── Tool 20 — compare_to_baseline ──


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
    # signal 이 너무 짧음 (intraop fallback 위해 first 10 min ≥ 2 sample 필요)
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


# ── Tool 21 — summarize_current_state ──


# Banned diagnostic phrasings — substrings that indicate assertive language
# 단정 어조 ban — phrase substring 목록
_BANNED_PHRASES = ("이다.", "진단", "처치", "투여", "권고")


def test_tool21_stub_synthesizes_from_vitals(clock):
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    assert r.ok
    res = r.result
    assert res["hemodynamic_state"] == "stable"  # MAP 80 normal
    assert res["anesthesia_state"] == "adequate_range"  # BIS 50 in 40-60
    assert res["respiratory_state"] == "stable"  # SpO2 98 normal
    assert res["meta"]["tier0_status"] == "stub"


def test_tool21_clinician_review_marker_mandatory(clock):
    """Tool 21 의 overall_assessment 는 [CLINICIAN-REVIEW] marker 를 반드시 포함.
    """
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}), clock, sig,
    )
    assert r.ok
    assert "[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]" in r.result["overall_assessment"]


def test_tool21_no_assertive_phrasing_in_output(clock):
    """단정 어조 ("이다.", "진단", "처치", ...) 가 출력에 없어야 한다.
    """
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
    assert r.quality_meta["tier0_status"] == "stub"


def test_tool21_leakage_violation(clock):
    sig = _synth_signal_full()
    r = tool_summarize_current_state(
        _req("summarize_current_state", {}, sim_time_s=9999.0), clock, sig,
    )
    assert not r.ok
    assert r.error.type == "leakage_violation"


# ── Registry integration / Registry 통합 ──


def test_registry_now_has_21_tools():
    assert len(TOOLS) == 21


def test_registry_signal_access_category_has_5():
    sa = [name for name, spec in TOOLS.items() if spec.category == "signal_access"]
    assert len(sa) == 5
    assert set(sa) == {
        "get_current_vitals", "describe_signal", "assess_variability",
        "compare_to_baseline", "summarize_current_state",
    }


def test_call_tool_routes_signal_access_via_dispatch(clock):
    sig = _synth_signal_full()
    # signal access tools needs_signal=True, needs_fm=False
    for name in ("get_current_vitals", "describe_signal", "assess_variability",
                 "compare_to_baseline", "summarize_current_state"):
        args = _minimal_args(name)
        req = ToolRequest(case_id="c1", sim_time_s=30.0, tool_name=name, args=args)
        r = call_tool(name, req, clock=clock, signal=sig)
        assert r.ok, f"tool {name} failed: {r.error}"


def _minimal_args(name: str) -> dict:
    if name in ("get_current_vitals", "summarize_current_state"):
        return {}
    if name == "describe_signal":
        return {"modality": "ABP"}
    if name == "assess_variability":
        return {"modality": "HR"}
    if name == "compare_to_baseline":
        return {"modality": "ABP", "sampling_rate_hz": 500.0}
    raise ValueError(name)


def test_neurokit2_environment_status():
    """Documents NeuroKit2 availability — informational test.
    NeuroKit2 가용 상태 문서화 (informational).
    """
    if USE_NEUROKIT:
        # PRIMARY path active
        assert True
    else:
        # FALLBACK path — would be skipped if NeuroKit2 ever uninstalled
        # FALLBACK path — NeuroKit2 미설치 시
        assert True
