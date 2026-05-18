"""RuleBasedBiosignalFM unit tests (plan_1.6.5).
RuleBasedBiosignalFM 단위 테스트 (plan_1.6.5).

Verifies per-rule semantics: response to signal-statistic inputs, output
ranges, threshold behavior, fallback paths, and noise-injection effects.
Rule별 의미 검증: signal 통계 입력에 대한 반응, output range, threshold 동작,
fallback 경로, noise 주입 효과.

Protocol compliance is already covered by ``tests/test_fm_protocol_compliance.py``
(rule-based is now registered there).
Protocol compliance는 ``tests/test_fm_protocol_compliance.py``에서 cover
(rule-based가 등록됨).
"""
from __future__ import annotations

import math
import statistics

import numpy as np
import pytest
import torch

from opsight.fm.mock_rule_based import (
    ARREST_HR_HIGH,
    ARREST_HR_LOW,
    ARREST_MAP_LOW,
    MAP_RISK_FLOOR,
    MAP_TARGET,
    QUALITY_BASE_SCORE,
    QUALITY_DEGRADED_FLATLINE,
    QUALITY_DEGRADED_NAN,
    QUALITY_FLATLINE_STD_EPS,
    QUALITY_NAN_CUTOFF,
    RuleBasedBiosignalFM,
    TREND_STABLE_BAND,
)
from opsight.fm.result_types import (
    AnomalyResult,
    ArrestResult,
    ConsistencyResult,
    ForecastResult,
    HypotensionResult,
    QualityResult,
    TrendResult,
)


# ── Fixtures / 픽스처 ──


def _abp_series(mean: float, slope_mmhg_per_min: float, n_samples: int,
                sampling_rate_hz: float = 500.0) -> torch.Tensor:
    """Generate a synthetic ABP trace with target mean + per-minute slope.
    목표 mean + per-minute slope의 synthetic ABP trace 생성.
    """
    # slope per step = slope_per_min / (rate * 60).
    # step당 slope = slope_per_min / (rate * 60).
    slope_per_step = slope_mmhg_per_min / (sampling_rate_hz * 60.0)
    centered_idx = np.arange(n_samples) - n_samples / 2.0
    arr = mean + slope_per_step * centered_idx
    # Tiny noise so std > flatline epsilon / std가 flatline epsilon 초과하도록 작은 noise.
    arr = arr + np.random.default_rng(0).normal(0, 0.5, size=n_samples)
    return torch.from_numpy(arr.astype(np.float64))


# ── encode ──


def test_encode_returns_torch_tensor_with_latent_dim() -> None:
    fm = RuleBasedBiosignalFM(seed=42, latent_dim=64)
    out = fm.encode({"ABP": torch.zeros(1000) + 80}, ["ABP"])
    assert isinstance(out, torch.Tensor)
    assert tuple(out.shape) == (64,)
    assert out.dtype == torch.float32


def test_encode_features_change_with_signal_stats() -> None:
    """Different signals → different feature vectors.
    다른 signal → 다른 feature vector.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    a = fm.encode({"ABP": _abp_series(80, 0, 5000)}, ["ABP"])
    b = fm.encode({"ABP": _abp_series(50, -3, 5000)}, ["ABP"])
    assert not torch.allclose(a, b)


# ── predict_hypotension ──


def test_hypotension_high_risk_low_map() -> None:
    """MAP at risk floor + falling slope → high risk.
    MAP가 risk floor + falling slope → high risk.
    """
    fm = RuleBasedBiosignalFM(seed=42, sampling_rate_hz=500.0)
    sig = {"ABP": _abp_series(mean=MAP_RISK_FLOOR, slope_mmhg_per_min=-5.0, n_samples=2000)}
    r = fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP"])
    assert isinstance(r, HypotensionResult)
    # Risk should be near saturation (>0.7) when both factors max out.
    # 두 factor 모두 saturate일 때 risk는 0.7 근방.
    assert r.risk > 0.7
    assert r.meta["map_score"] >= 0.9
    assert r.meta["slope_score"] >= 0.9


def test_hypotension_low_risk_stable_normal_map() -> None:
    """MAP at target + flat slope → low risk.
    MAP가 target + flat slope → low risk.
    """
    fm = RuleBasedBiosignalFM(seed=42, sampling_rate_hz=500.0)
    sig = {"ABP": _abp_series(mean=MAP_TARGET, slope_mmhg_per_min=0.0, n_samples=2000)}
    r = fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP"])
    assert r.risk < 0.2


def test_hypotension_fallback_when_no_abp() -> None:
    """No ABP modality → fallback risk ≈ 0.4 with high uncertainty.
    ABP 없음 → fallback risk ≈ 0.4, 높은 uncertainty.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.predict_hypotension({"ECG_II": torch.zeros(100)}, horizon_min=5,
                                available_modalities=["ECG_II"])
    assert r.risk == 0.4
    assert r.uncertainty >= 0.7
    assert r.meta["reason"] == "no_abp_modality"


def test_hypotension_fallback_on_flatline() -> None:
    """ABP flatline (zeros) → low-quality fallback.
    ABP flatline (zeros) → low-quality fallback.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.predict_hypotension({"ABP": torch.zeros(1000)}, horizon_min=5,
                                available_modalities=["ABP"])
    assert r.meta["reason"] == "low_quality_abp"
    assert r.uncertainty >= 0.7


# ── predict_cardiac_arrest ──


def test_arrest_low_baseline_when_no_flags() -> None:
    """Normal HR + MAP → baseline low risk.
    정상 HR + MAP → baseline low risk.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {
        "HR":  torch.full((500,), 75.0),
        "ABP": _abp_series(mean=80, slope_mmhg_per_min=0, n_samples=2000),
    }
    r = fm.predict_cardiac_arrest(sig, horizon_min=5, available_modalities=["HR", "ABP"])
    assert isinstance(r, ArrestResult)
    assert r.risk < 0.10
    assert r.meta["flags"] == []


def test_arrest_high_when_two_flags() -> None:
    """HR > threshold + MAP < threshold → ≥ 2 flags → high risk.
    HR > threshold + MAP < threshold → flag ≥ 2 → high risk.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {
        "HR":  torch.full((500,), ARREST_HR_HIGH + 5),
        "ABP": _abp_series(mean=ARREST_MAP_LOW - 5, slope_mmhg_per_min=0, n_samples=2000),
    }
    r = fm.predict_cardiac_arrest(sig, horizon_min=5, available_modalities=["HR", "ABP"])
    assert r.risk > 0.5
    assert len(r.meta["flags"]) >= 2


def test_arrest_fallback_when_no_hr_or_abp() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.predict_cardiac_arrest({"PPG": torch.zeros(100)}, horizon_min=5,
                                   available_modalities=["PPG"])
    assert r.risk == 0.05
    assert r.uncertainty >= 0.7
    assert r.meta["reason"] == "no_hr_or_abp"


# ── assess_signal_quality ──


def test_quality_clean_signal() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {"ABP": _abp_series(80, 0, 2000)}
    r = fm.assess_signal_quality(sig, "ABP")
    assert isinstance(r, QualityResult)
    assert r.score == pytest.approx(QUALITY_BASE_SCORE)
    assert r.reason is None


def test_quality_flatline() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.assess_signal_quality({"ABP": torch.zeros(1000)}, "ABP")
    assert r.score == pytest.approx(QUALITY_DEGRADED_FLATLINE)
    assert r.reason == "flatline_detected"


def test_quality_high_nan_ratio() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    arr = np.full(1000, 80.0)
    arr[: int(0.5 * 1000)] = np.nan  # 50% NaN
    r = fm.assess_signal_quality({"ABP": torch.from_numpy(arr)}, "ABP")
    assert r.score == pytest.approx(QUALITY_DEGRADED_NAN)
    assert r.reason is not None and r.reason.startswith("nan_ratio")


def test_quality_modality_absent() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.assess_signal_quality({}, "ABP")
    assert r.score == 0.0 and r.reason == "modality_absent"


# ── cross_modal_consistency ──


def test_consistency_perfect_correlation() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    a = _abp_series(80, 0, 2000)
    sig = {"ABP": a, "PPG": a.clone()}  # identical → r = 1
    r = fm.cross_modal_consistency(sig, ("ABP", "PPG"))
    assert r.score > 0.99


def test_consistency_anticorrelation_magnitude() -> None:
    """|r| = 1 even when r is negative.
    r이 음수여도 |r| = 1.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    a = _abp_series(80, 0, 2000)
    sig = {"ABP": a, "PPG": -a}
    r = fm.cross_modal_consistency(sig, ("ABP", "PPG"))
    assert r.score > 0.99
    assert r.meta["pearson_r"] < 0


def test_consistency_modality_missing_fallback() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.cross_modal_consistency({"ABP": torch.zeros(100)}, ("ABP", "PPG"))
    assert r.score == 0.5 and r.reason == "modality_missing"


def test_consistency_flatline_fallback() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.cross_modal_consistency(
        {"ABP": torch.zeros(2000), "PPG": _abp_series(80, 0, 2000)},
        ("ABP", "PPG"),
    )
    assert r.reason == "flatline_modality"


# ── temporal_trend ──


def test_trend_rising_label_when_positive_slope() -> None:
    fm = RuleBasedBiosignalFM(seed=42, sampling_rate_hz=500.0)
    sig = {"ABP": _abp_series(80, slope_mmhg_per_min=3.0, n_samples=2000)}
    r = fm.temporal_trend(sig, "ABP", window_min=5)
    assert isinstance(r, TrendResult)
    assert r.label == "rising"
    assert r.slope > TREND_STABLE_BAND


def test_trend_falling_label_when_negative_slope() -> None:
    fm = RuleBasedBiosignalFM(seed=42, sampling_rate_hz=500.0)
    sig = {"ABP": _abp_series(80, slope_mmhg_per_min=-3.0, n_samples=2000)}
    r = fm.temporal_trend(sig, "ABP", window_min=5)
    assert r.label == "falling"
    assert r.slope < -TREND_STABLE_BAND


def test_trend_stable_when_flat() -> None:
    fm = RuleBasedBiosignalFM(seed=42, sampling_rate_hz=500.0)
    sig = {"ABP": _abp_series(80, slope_mmhg_per_min=0.0, n_samples=2000)}
    r = fm.temporal_trend(sig, "ABP", window_min=5)
    assert r.label == "stable"
    assert abs(r.slope) < TREND_STABLE_BAND


# ── forecast_signal ──


def test_forecast_length_matches_horizon() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {"ABP": _abp_series(80, 0, 2000)}
    r = fm.forecast_signal(sig, "ABP", horizon_min=5)
    assert isinstance(r, ForecastResult)
    assert len(r.forecast) == 5 and len(r.uncertainty) == 5
    assert all(math.isfinite(v) for v in r.forecast)


def test_forecast_uncertainty_grows_with_horizon() -> None:
    """Uncertainty should be non-decreasing across the forecast horizon.
    Forecast horizon에 걸쳐 uncertainty가 non-decreasing.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {"ABP": _abp_series(80, 0, 2000)}
    r = fm.forecast_signal(sig, "ABP", horizon_min=10)
    assert r.uncertainty == sorted(r.uncertainty)


def test_forecast_extrapolates_linearly() -> None:
    """Linear input → linear forecast (intercept + slope).
    선형 입력 → 선형 forecast (intercept + slope).
    """
    fm = RuleBasedBiosignalFM(seed=42, sampling_rate_hz=500.0)
    arr = 50 + 0.001 * np.arange(2000)
    r = fm.forecast_signal({"ABP": torch.from_numpy(arr)}, "ABP", horizon_min=5)
    # Successive forecast steps should be increasing (positive slope).
    # 연속한 forecast step은 증가 (positive slope).
    assert r.forecast == sorted(r.forecast)


# ── anomaly_score ──


def test_anomaly_low_when_stationary() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    arr = np.random.default_rng(0).normal(80, 5, 2000)
    r = fm.anomaly_score({"ABP": torch.from_numpy(arr)}, "ABP")
    assert r.score < 0.5


def test_anomaly_high_when_tail_spike() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    arr = np.full(2000, 80.0)
    arr[-50:] = 200.0  # large positive spike at the tail
    r = fm.anomaly_score({"ABP": torch.from_numpy(arr)}, "ABP")
    assert r.score > 0.5


def test_anomaly_flatline_low() -> None:
    fm = RuleBasedBiosignalFM(seed=42)
    r = fm.anomaly_score({"ABP": torch.zeros(2000)}, "ABP")
    assert r.score == pytest.approx(0.05)
    assert r.meta["reason"] == "flatline"


# ── Noise injection ──


def test_noise_injection_varies_output() -> None:
    """Global noise_pct introduces variance across instances.
    전역 noise_pct가 인스턴스에 분산을 도입.
    """
    sig = {"ABP": _abp_series(60, -2.0, 2000)}  # mid-range risk

    risks = []
    for seed in range(20):
        fm = RuleBasedBiosignalFM(seed=42, noise_pct=0.3, noise_seed=seed)
        r = fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP"])
        risks.append(r.risk)
    assert statistics.stdev(risks) > 0.005


def test_noise_disabled_is_deterministic() -> None:
    """noise_pct=0 → deterministic given same signal.
    noise_pct=0 → 동일 signal에 대해 결정적.
    """
    sig = {"ABP": _abp_series(60, -2.0, 2000)}
    a = RuleBasedBiosignalFM(seed=42).predict_hypotension(sig, 5, ["ABP"])
    b = RuleBasedBiosignalFM(seed=42).predict_hypotension(sig, 5, ["ABP"])
    assert a.risk == b.risk


def test_noise_per_method_override() -> None:
    """Per-method override beats the global default.
    Method별 override가 전역 default를 이긴다.
    """
    sig = {"ABP": _abp_series(60, -2.0, 2000)}
    fm_quiet_global = RuleBasedBiosignalFM(
        seed=42, noise_pct=0.0,
        noise_per_method={"predict_hypotension": 0.5}, noise_seed=1,
    )
    fm_clean = RuleBasedBiosignalFM(seed=42, noise_pct=0.0)
    r_noisy = fm_quiet_global.predict_hypotension(sig, 5, ["ABP"])
    r_clean = fm_clean.predict_hypotension(sig, 5, ["ABP"])
    # Override path produces a different number from the deterministic clean run.
    # Override 경로는 결정적 clean run과 다른 값 산출.
    assert r_noisy.risk != r_clean.risk


# ── Smoke / integration / 통합 ──


def test_smoke_all_eight_methods_on_synthetic_case() -> None:
    """8 methods all callable on a single synthetic case without exception.
    단일 synthetic case에서 8 method가 모두 예외 없이 callable.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {
        "ABP":    _abp_series(80, slope_mmhg_per_min=-1.0, n_samples=2000),
        "ECG_II": torch.zeros(2000),
        "PPG":    _abp_series(80, slope_mmhg_per_min=-1.0, n_samples=2000),
        "BIS":    torch.zeros(500),
        "HR":     torch.full((500,), 80.0),
    }
    mods = list(sig)
    assert isinstance(fm.encode(sig, mods), torch.Tensor)
    assert isinstance(fm.predict_hypotension(sig, 5, mods), HypotensionResult)
    assert isinstance(fm.predict_cardiac_arrest(sig, 5, mods), ArrestResult)
    assert isinstance(fm.assess_signal_quality(sig, "ABP"), QualityResult)
    assert isinstance(fm.cross_modal_consistency(sig, ("ABP", "PPG")), ConsistencyResult)
    assert isinstance(fm.temporal_trend(sig, "ABP", 5), TrendResult)
    assert isinstance(fm.forecast_signal(sig, "ABP", 5), ForecastResult)
    assert isinstance(fm.anomaly_score(sig, "ABP"), AnomalyResult)


def test_smoke_meta_carries_mock_tier_marker() -> None:
    """Every Result includes ``meta["mock_tier"] == "rule_based"``.
    모든 Result가 ``meta["mock_tier"] == "rule_based"``를 포함.
    """
    fm = RuleBasedBiosignalFM(seed=42)
    sig = {"ABP": _abp_series(80, 0, 2000)}
    results = [
        fm.predict_hypotension(sig, 5, ["ABP"]),
        fm.predict_cardiac_arrest(sig, 5, ["ABP"]),
        fm.assess_signal_quality(sig, "ABP"),
        fm.cross_modal_consistency(sig, ("ABP", "ABP")),
        fm.temporal_trend(sig, "ABP", 5),
        fm.forecast_signal(sig, "ABP", 5),
        fm.anomaly_score(sig, "ABP"),
    ]
    for r in results:
        assert r.meta.get("mock_tier") == "rule_based", f"missing marker on {type(r).__name__}"
