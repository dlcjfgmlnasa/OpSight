"""Tests for assess_signal_quality — rule-based per-modality SQI.
assess_signal_quality 테스트 — 규칙 기반 모달리티별 SQI.

- 깨끗한 파형 → 높은 SQI / flatline 파형 → 낮은 SQI
- 상수 수치 vital(HR 75 고정) → flatline 오판 안 함 (높은 SQI)
- 생리범위 이탈 → SQI 하락 / 결측 → SQI 하락 / 전부 NaN → 0
- overall = 평균, worst = 최솟값 / leakage guard

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_assess_signal_quality.py -v
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.envelope import ToolRequest
from opsight.sim_clock import SimClock
from opsight.tools.signal_state_tools.extractors.assess_signal_quality import (
    tool_assess_signal_quality,
)


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(60.0)
    return c


def _req(args: dict, sim_time_s: float = 30.0) -> ToolRequest:
    return ToolRequest(case_id="c1", sim_time_s=sim_time_s,
                       tool_name="assess_signal_quality", args=args)


def _clean_abp() -> torch.Tensor:
    rng = np.random.default_rng(0)
    return torch.from_numpy((80.0 + rng.normal(0, 10.0, 5000)).astype(np.float32))


# ── Clean vs flatline (waveform) ──


def test_clean_waveform_high_sqi(clock) -> None:
    sig = {"ABP": _clean_abp()}
    r = tool_assess_signal_quality(_req({"sampling_rate_hz": 500.0}), clock, sig)
    assert r.ok
    assert r.result["scores"]["ABP"] > 0.9
    assert r.result["details"]["ABP"]["flatline"] is False


def test_flatline_waveform_low_sqi(clock) -> None:
    sig = {"ABP": torch.zeros(5000)}  # transducer flat → artifact
    r = tool_assess_signal_quality(_req({"sampling_rate_hz": 500.0}), clock, sig)
    assert r.ok
    assert r.result["details"]["ABP"]["flatline"] is True
    assert r.result["scores"]["ABP"] <= 0.2


def test_constant_numeric_vital_not_flatlined(clock) -> None:
    """A stable HR=75 is GOOD quality — must NOT be penalized as flatline."""
    sig = {"HR": torch.full((60,), 75.0)}
    r = tool_assess_signal_quality(_req({}), clock, sig)
    assert r.ok
    assert r.result["details"]["HR"]["flatline"] is False
    assert r.result["scores"]["HR"] == 1.0


# ── Range / missing ──


def test_out_of_range_lowers_sqi(clock) -> None:
    # constant impossible HR (>300) → full range violation, no sudden jump → SQI 0
    sig = {"HR": torch.from_numpy(np.full(60, 350.0, dtype=np.float32))}
    r = tool_assess_signal_quality(_req({"window_s": 60}), clock, sig)
    assert r.ok
    assert r.result["details"]["HR"]["range_violation_ratio"] == pytest.approx(1.0)
    assert r.result["scores"]["HR"] == pytest.approx(0.0)


def test_sudden_jump_flagged_as_artifact(clock) -> None:
    # numeric MAP with an implausible 80→20 step (line flush) → artifact → low SQI.
    arr = np.full(20, 80.0, dtype=np.float32)
    arr[10] = 20.0  # single-sample dip = sudden jump (Δ60 > 25)
    r = tool_assess_signal_quality(_req({"window_s": 60}), clock, {"ABP": torch.from_numpy(arr)})
    assert r.ok
    assert r.result["details"]["ABP"]["sudden_jump"] is True
    assert r.result["scores"]["ABP"] <= 0.2


def test_gradual_change_not_flagged(clock) -> None:
    # a gradual MAP drift (no implausible step) is NOT an artifact.
    arr = np.linspace(80.0, 60.0, 60).astype(np.float32)
    r = tool_assess_signal_quality(_req({"window_s": 60}), clock, {"ABP": torch.from_numpy(arr)})
    assert r.ok
    assert r.result["details"]["ABP"]["sudden_jump"] is False
    assert r.result["scores"]["ABP"] > 0.9


def test_sparse_sampling_tolerated(clock) -> None:
    # 50% NaN is normal sparse numeric sampling (Solar8000 ~2 s @ 1 Hz) → SQI 1.0.
    arr = np.array([75.0] * 30 + [np.nan] * 30, dtype=np.float32)
    r = tool_assess_signal_quality(_req({"window_s": 60}), clock, {"HR": torch.from_numpy(arr)})
    assert r.ok
    assert r.result["details"]["HR"]["missing_ratio"] == pytest.approx(0.5)
    assert r.result["scores"]["HR"] == pytest.approx(1.0)  # tolerated


def test_heavy_missing_lowers_sqi(clock) -> None:
    # 75% missing exceeds tolerance → real gap → SQI drops.
    arr = np.array([75.0] * 15 + [np.nan] * 45, dtype=np.float32)
    r = tool_assess_signal_quality(_req({"window_s": 60}), clock, {"HR": torch.from_numpy(arr)})
    assert r.ok
    assert r.result["details"]["HR"]["missing_ratio"] == pytest.approx(0.75)
    assert r.result["scores"]["HR"] == pytest.approx(0.5)  # (0.75-0.5)/0.5 penalty


def test_all_nan_absent_not_zero(clock) -> None:
    # A fully-absent channel is None (excluded), NOT sqi 0 — it must not gate alarms.
    sig = {"HR": torch.from_numpy(np.full(60, np.nan, dtype=np.float32))}
    r = tool_assess_signal_quality(_req({}), clock, sig)
    assert r.ok
    assert r.result["scores"]["HR"] is None
    assert r.result["overall"] is None and r.result["primary_worst"] is None


# ── Aggregation ──


def test_overall_and_worst(clock) -> None:
    sig = {"ABP": _clean_abp(), "ECG_II": torch.zeros(5000)}  # one clean, one flat
    r = tool_assess_signal_quality(_req({"sampling_rate_hz": 500.0}), clock, sig)
    assert r.ok
    scores = r.result["scores"]
    assert r.result["worst"] == min(scores.values())
    assert r.result["overall"] == pytest.approx(sum(scores.values()) / len(scores), abs=1e-3)


def test_specific_modality(clock) -> None:
    sig = {"ABP": _clean_abp(), "HR": torch.full((60,), 75.0)}
    r = tool_assess_signal_quality(_req({"modality": "HR"}), clock, sig)
    assert r.ok
    assert set(r.result["scores"]) == {"HR"}


def test_unknown_modality_invalid_args(clock) -> None:
    r = tool_assess_signal_quality(_req({"modality": "NOPE"}), clock, {"HR": torch.zeros(10)})
    assert not r.ok and r.error.type == "invalid_args"


def test_leakage_violation(clock) -> None:
    r = tool_assess_signal_quality(_req({}, sim_time_s=9999.0), clock, {"HR": torch.zeros(10)})
    assert not r.ok and r.error.type == "leakage_violation"


def test_quality_meta_category(clock) -> None:
    r = tool_assess_signal_quality(_req({}), clock, {"HR": torch.full((60,), 75.0)})
    assert r.quality_meta["category"] == "signal_state"
    assert r.quality_meta["method"] == "rule_based_sqi"
