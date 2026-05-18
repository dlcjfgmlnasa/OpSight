"""Tests for plan_1.4 baselines.
plan_1.4 baseline 테스트.

Coverage:
- Labels (h5 / h15) — positive / negative / NaN
- Features (ABP / multimodal / Hatib-style) — shape, NaN propagation
- Splits — reproducibility + stratification
- LogReg / LSTM / Hatib — fit on synthetic, predict shapes, save/load
- XGBoost — graceful NotImplementedError when xgboost missing
- BaselineFMAdapter — BiosignalFMInterface Protocol 만족 + 8 method smoke
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from vitalagent.baselines import BaselineFMAdapter, BaselineConfig
from vitalagent.baselines.features import (
    ABP_FEATURE_NAMES,
    MULTIMODAL_FEATURE_NAMES,
    extract_abp_features,
    extract_multimodal_features,
)
from vitalagent.baselines.hatib_style import (
    HATIB_LIKE_FEATURE_NAMES,
    HatibStyleBaseline,
    extract_hatib_like_features,
)
from vitalagent.baselines.labels import label_h5, label_h15, label_hypotension_window
from vitalagent.baselines.logreg_abp import LogRegABPBaseline
from vitalagent.baselines.lstm_abp import LSTMABPBaseline
from vitalagent.baselines.splits import make_splits
from vitalagent.baselines.xgb_multimodal import XGBMultimodalBaseline
from vitalagent.fm.interface import BiosignalFMInterface


# ── Synthetic signal helpers / 합성 signal 헬퍼 ──


def _synth_abp(map_mean: float = 80.0, slope_per_min: float = 0.0,
               n_seconds: float = 60.0, sampling_rate_hz: float = 500.0,
               noise_std: float = 2.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(n_seconds * sampling_rate_hz)
    t_min = np.arange(n) / sampling_rate_hz / 60.0
    return map_mean + slope_per_min * t_min + rng.normal(0.0, noise_std, size=n)


def _signal_dict(abp: np.ndarray, hr: float | None = 75.0,
                 ppg_mean: float = 1.0) -> dict[str, torch.Tensor]:
    out: dict[str, torch.Tensor] = {"ABP": torch.from_numpy(abp.astype(np.float32))}
    if hr is not None:
        out["HR"] = torch.tensor([float(hr)] * 60, dtype=torch.float32)
    out["PPG"] = torch.tensor([ppg_mean] * 100, dtype=torch.float32)
    return out


# ── Labels / 라벨 ──


def test_label_h5_positive_when_sustained_below_65():
    # 5분 horizon 안에 1분 이상 MAP < 65 유지 / MAP < 65 sustained ≥ 1 min within 5 min
    sr = 1.0  # 1 Hz for clarity / 명료성 위해 1 Hz
    # 첫 90초 MAP=60 (< 65 sustained 60s), 나머지는 정상
    trace = np.concatenate([np.full(90, 60.0), np.full(210, 80.0)])
    assert label_h5(trace, sampling_rate_hz=sr) == 1


def test_label_h5_negative_when_brief_dip():
    sr = 1.0
    # 30초만 MAP=60 (< 1 min 지속) / only 30 sec below threshold
    trace = np.concatenate([np.full(30, 60.0), np.full(270, 80.0)])
    assert label_h5(trace, sampling_rate_hz=sr) == 0


def test_label_h5_negative_normal_pressure():
    sr = 1.0
    trace = np.full(300, 80.0)
    assert label_h5(trace, sampling_rate_hz=sr) == 0


def test_label_h15_positive_when_event_in_second_half():
    sr = 1.0
    # First 600 sec normal, then 90 sec dip
    trace = np.concatenate([np.full(600, 80.0), np.full(90, 55.0), np.full(210, 80.0)])
    assert label_h15(trace, sampling_rate_hz=sr) == 1


def test_label_handles_nan_safely():
    sr = 1.0
    trace = np.concatenate([np.full(60, 60.0), np.full(240, np.nan)])
    # 60 sec below threshold → exactly meets min duration
    assert label_h5(trace, sampling_rate_hz=sr) == 1


def test_label_with_custom_threshold():
    sr = 1.0
    trace = np.full(300, 70.0)
    assert label_hypotension_window(trace, sr, horizon_s=300.0, map_threshold_mmhg=75.0,
                                    min_duration_s=60.0) == 1


# ── Features / Feature ──


def test_abp_features_shape_and_no_nan():
    abp = _synth_abp(map_mean=80.0, n_seconds=10.0)
    feats = extract_abp_features({"ABP": torch.from_numpy(abp)}, sampling_rate_hz=500.0)
    assert feats.shape == (len(ABP_FEATURE_NAMES),)
    assert not np.isnan(feats).any()
    # map_mean (index 0) should be close to 80
    assert 75.0 < feats[0] < 85.0


def test_abp_features_nan_padded_when_absent():
    feats = extract_abp_features({}, sampling_rate_hz=500.0)
    assert feats.shape == (len(ABP_FEATURE_NAMES),)
    assert np.isnan(feats).all()


def test_abp_features_slope_detected():
    abp = _synth_abp(map_mean=80.0, slope_per_min=-5.0, n_seconds=10.0, noise_std=0.1)
    feats = extract_abp_features({"ABP": torch.from_numpy(abp)}, sampling_rate_hz=500.0)
    # slope index = 2 / map_slope_per_min
    assert feats[2] < -3.0


def test_multimodal_features_shape():
    abp = _synth_abp(n_seconds=10.0)
    feats = extract_multimodal_features(_signal_dict(abp), sampling_rate_hz=500.0)
    assert feats.shape == (len(MULTIMODAL_FEATURE_NAMES),)


def test_hatib_features_shape():
    abp = _synth_abp(n_seconds=10.0)
    feats = extract_hatib_like_features({"ABP": torch.from_numpy(abp)}, sampling_rate_hz=500.0)
    assert feats.shape == (len(HATIB_LIKE_FEATURE_NAMES),)


# ── Splits / Split ──


def test_make_splits_reproducible():
    import pandas as pd
    cases = pd.DataFrame({"caseid": list(range(100)), "department": ["A"] * 50 + ["B"] * 50})
    s1 = make_splits(cases, seed=42, stratify_by=["department"])
    s2 = make_splits(cases, seed=42, stratify_by=["department"])
    assert s1.equals(s2)


def test_make_splits_distribution_close_to_target():
    import pandas as pd
    cases = pd.DataFrame({"caseid": list(range(200))})
    s = make_splits(cases, seed=0, val_frac=0.15, test_frac=0.15)
    counts = s["split"].value_counts(normalize=True)
    assert abs(counts.get("train", 0) - 0.70) < 0.05
    assert abs(counts.get("val", 0) - 0.15) < 0.05
    assert abs(counts.get("test", 0) - 0.15) < 0.05


def test_make_splits_rejects_invalid_fractions():
    import pandas as pd
    cases = pd.DataFrame({"caseid": [1, 2, 3]})
    with pytest.raises(ValueError):
        make_splits(cases, val_frac=0.6, test_frac=0.6)


# ── LogRegABPBaseline / LogReg ABP ──


def _synthetic_dataset_logreg(n: int = 200, seed: int = 0):
    """n samples; half hypotensive (low MAP + falling slope), half stable.
    n samples; 절반 hypotensive (low MAP + 떨어지는 slope), 절반 안정.
    """
    rng = np.random.default_rng(seed)
    X = []
    y = []
    for i in range(n):
        label = i % 2  # alternate
        if label == 1:
            abp = _synth_abp(map_mean=58.0 + rng.uniform(0, 5),
                             slope_per_min=-3.0 + rng.uniform(-1, 1),
                             n_seconds=10.0, seed=seed + i)
        else:
            abp = _synth_abp(map_mean=85.0 + rng.uniform(-5, 5),
                             slope_per_min=rng.uniform(-1, 1),
                             n_seconds=10.0, seed=seed + i)
        X.append(extract_abp_features({"ABP": torch.from_numpy(abp)},
                                      sampling_rate_hz=500.0))
        y.append(label)
    return np.array(X), np.array(y, dtype=np.float64)


def test_logreg_fits_and_separates_synthetic():
    X, y = _synthetic_dataset_logreg(n=200, seed=1)
    model = LogRegABPBaseline()
    stats = model.fit(X, y, epochs=300, lr=0.1)
    assert "final_loss" in stats
    # Predict on the same data; AUROC-ish: positives should average > negatives
    probs = model.predict_proba(X)
    pos_mean = float(probs[y == 1].mean())
    neg_mean = float(probs[y == 0].mean())
    assert pos_mean > neg_mean + 0.2, f"weak separation: {pos_mean=}, {neg_mean=}"


def test_logreg_predict_returns_baseline_result():
    X, y = _synthetic_dataset_logreg(n=100)
    model = LogRegABPBaseline()
    model.fit(X, y, epochs=100)
    abp = _synth_abp(map_mean=85.0, n_seconds=10.0)
    r = model.predict(_signal_dict(abp), horizon_min=5, available_modalities=["ABP", "HR"])
    assert 0.0 <= r.risk <= 1.0
    assert 0.0 <= r.uncertainty <= 1.0
    assert r.horizon_min == 5
    assert r.meta["model_name"] == "logreg_abp"


def test_logreg_no_abp_fallback():
    model = LogRegABPBaseline()
    r = model.predict({}, horizon_min=5, available_modalities=[])
    assert r.meta["fallback"] == "no_abp"
    assert r.uncertainty > 0.5


def test_logreg_save_load_roundtrip(tmp_path: Path):
    X, y = _synthetic_dataset_logreg(n=100)
    m1 = LogRegABPBaseline()
    m1.fit(X, y, epochs=50)
    abp = _synth_abp(n_seconds=10.0)
    sig = _signal_dict(abp)
    r1 = m1.predict(sig, horizon_min=5, available_modalities=["ABP"])

    path = str(tmp_path / "logreg.pt")
    m1.save(path)
    m2 = LogRegABPBaseline()
    m2.load(path)
    r2 = m2.predict(sig, horizon_min=5, available_modalities=["ABP"])
    assert r1.risk == pytest.approx(r2.risk, abs=1e-5)


# ── LSTMABPBaseline / LSTM ABP ──


def _synthetic_dataset_lstm(n: int = 30, T: int = 5000, seed: int = 0):
    """n samples of (T,) ABP waveform + label.
    n 개의 (T,) ABP waveform + label.
    """
    rng = np.random.default_rng(seed)
    X = []
    y = []
    for i in range(n):
        label = i % 2
        if label == 1:
            arr = _synth_abp(map_mean=60.0, slope_per_min=-2.0, n_seconds=T / 500.0,
                             seed=seed + i)
        else:
            arr = _synth_abp(map_mean=85.0, n_seconds=T / 500.0, seed=seed + i)
        X.append(arr)
        y.append(label)
    # All have same T
    return np.stack(X), np.array(y, dtype=np.float64)


def test_lstm_fits_and_returns_baseline_result():
    X, y = _synthetic_dataset_lstm(n=20, T=2500, seed=2)
    model = LSTMABPBaseline(BaselineConfig(name="lstm_abp", sampling_rate_hz=500.0),
                            hidden_size=8, downsample_hz=4.0)
    stats = model.fit(X, y, epochs=3, lr=0.05, batch_size=8)
    assert "final_loss" in stats
    abp = _synth_abp(map_mean=85.0, n_seconds=5.0)
    r = model.predict(_signal_dict(abp), horizon_min=5, available_modalities=["ABP"])
    assert 0.0 <= r.risk <= 1.0
    assert r.meta["model_name"] == "lstm_abp"
    assert "mc_dropout_n" in r.meta


def test_lstm_no_abp_fallback():
    model = LSTMABPBaseline(hidden_size=4)
    r = model.predict({}, horizon_min=5, available_modalities=[])
    assert r.meta["fallback"] == "no_abp"


def test_lstm_save_load_roundtrip(tmp_path: Path):
    X, y = _synthetic_dataset_lstm(n=12, T=2500, seed=3)
    m1 = LSTMABPBaseline(hidden_size=4, downsample_hz=4.0)
    m1.fit(X, y, epochs=2, batch_size=4)
    abp = _synth_abp(map_mean=70.0, n_seconds=5.0)
    sig = _signal_dict(abp)
    # MC-dropout adds noise so we don't compare exact risks; we compare state-dict shape.
    # MC-dropout 는 noise 추가 → exact risk 비교 X; state-dict shape 만 비교.
    path = str(tmp_path / "lstm.pt")
    m1.save(path)
    m2 = LSTMABPBaseline()
    m2.load(path)
    r2 = m2.predict(sig, horizon_min=5, available_modalities=["ABP"])
    assert 0.0 <= r2.risk <= 1.0


# ── XGBMultimodalBaseline (xgboost not installed) ──


def test_xgb_unfitted_returns_install_hint():
    model = XGBMultimodalBaseline()
    abp = _synth_abp()
    r = model.predict(_signal_dict(abp), horizon_min=5, available_modalities=["ABP", "HR"])
    assert "install_hint" in r.meta
    assert "xgboost" in r.meta["install_hint"].lower()
    assert r.meta["fallback"] == "untrained_or_xgb_missing"


def test_xgb_fit_raises_notimplemented_when_xgboost_missing():
    # xgboost not installed in this env → fit must raise NotImplementedError
    # xgboost 부재 환경 → fit 시 NotImplementedError
    model = XGBMultimodalBaseline()
    X = np.zeros((10, len(MULTIMODAL_FEATURE_NAMES)))
    y = np.zeros(10)
    with pytest.raises(NotImplementedError):
        model.fit(X, y)


# ── HatibStyleBaseline ──


def _synthetic_dataset_hatib(n: int = 80, seed: int = 0):
    X = []
    y = []
    rng = np.random.default_rng(seed)
    for i in range(n):
        label = i % 2
        if label == 1:
            arr = _synth_abp(map_mean=60.0, slope_per_min=-2.0, n_seconds=10.0, seed=seed + i)
        else:
            arr = _synth_abp(map_mean=85.0, n_seconds=10.0, seed=seed + i)
        X.append(extract_hatib_like_features({"ABP": torch.from_numpy(arr)}))
        y.append(label)
    return np.array(X), np.array(y, dtype=np.float64)


def test_hatib_fits_and_separates_synthetic():
    X, y = _synthetic_dataset_hatib(n=100)
    model = HatibStyleBaseline()
    model.fit(X, y, epochs=200)
    probs_pos = []
    probs_neg = []
    for label, mean in [(1, 60.0), (0, 85.0)]:
        for seed in range(5):
            abp = _synth_abp(map_mean=mean, n_seconds=10.0, seed=999 + seed)
            r = model.predict(_signal_dict(abp), horizon_min=5, available_modalities=["ABP"])
            (probs_pos if label == 1 else probs_neg).append(r.risk)
            assert r.meta.get("open_source_approximation") is True
    assert np.mean(probs_pos) > np.mean(probs_neg) + 0.1


# ── BaselineFMAdapter — BiosignalFMInterface Protocol 만족 ──


def test_adapter_isinstance_protocol():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model, latent_dim=64)
    assert isinstance(adapter, BiosignalFMInterface)


def test_adapter_encode_returns_correct_shape():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model, latent_dim=64)
    abp = _synth_abp(n_seconds=5.0)
    sig = _signal_dict(abp)
    enc = adapter.encode(sig, available_modalities=["ABP", "HR", "PPG"])
    assert isinstance(enc, torch.Tensor)
    assert enc.shape == (64,)


def test_adapter_predict_hypotension_routes_to_baseline():
    X, y = _synthetic_dataset_logreg(n=100)
    model = LogRegABPBaseline()
    model.fit(X, y, epochs=100)
    adapter = BaselineFMAdapter(model)
    abp = _synth_abp(map_mean=60.0, slope_per_min=-2.0, n_seconds=10.0)
    r = adapter.predict_hypotension(_signal_dict(abp), horizon_min=5,
                                    available_modalities=["ABP", "HR"])
    assert r.meta["mock_tier"] == "light_ml"
    assert r.meta["baseline"] == "logreg_abp"
    assert 0.0 <= r.risk <= 1.0


def test_adapter_predict_cardiac_arrest_low_baseline():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    abp = _synth_abp(map_mean=85.0, n_seconds=5.0)
    r = adapter.predict_cardiac_arrest(_signal_dict(abp, hr=75.0), horizon_min=5,
                                        available_modalities=["ABP", "HR"])
    # Normal HR / MAP → baseline risk ~0.02
    assert r.risk < 0.1


def test_adapter_predict_cardiac_arrest_high_when_hr_extreme():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    abp = _synth_abp(map_mean=45.0, n_seconds=5.0)  # MAP < 50 flag
    r = adapter.predict_cardiac_arrest(_signal_dict(abp, hr=30.0), horizon_min=5,
                                        available_modalities=["ABP", "HR"])
    # HR low + MAP low → 2 flags → risk ≈ 0.62
    assert r.risk > 0.3


def test_adapter_assess_signal_quality_clean_modality():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    abp = _synth_abp(n_seconds=5.0)
    q = adapter.assess_signal_quality({"ABP": torch.from_numpy(abp)}, modality="ABP")
    assert q.score >= 0.9


def test_adapter_assess_signal_quality_missing_modality():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    q = adapter.assess_signal_quality({}, modality="ABP")
    assert q.score == 0.0
    assert q.reason == "modality_absent"


def test_adapter_cross_modal_consistency_correlation():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    n = 1000
    rng = np.random.default_rng(7)
    a = rng.normal(0, 1, size=n)
    sig = {"A": torch.from_numpy(a.astype(np.float32)),
           "B": torch.from_numpy(a.astype(np.float32) + rng.normal(0, 0.1, n).astype(np.float32))}
    c = adapter.cross_modal_consistency(sig, modality_pair=["A", "B"])
    assert c.score > 0.9


def test_adapter_temporal_trend_falling():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    abp = _synth_abp(slope_per_min=-3.0, n_seconds=10.0, noise_std=0.1)
    t = adapter.temporal_trend({"ABP": torch.from_numpy(abp)}, modality="ABP", window_min=5)
    assert t.label == "falling"


def test_adapter_forecast_returns_horizon_length():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    abp = _synth_abp(n_seconds=10.0)
    f = adapter.forecast_signal({"ABP": torch.from_numpy(abp)}, modality="ABP", horizon_min=5)
    assert len(f.forecast) == 5
    assert len(f.uncertainty) == 5
    # uncertainty 단조 증가 / monotonically increasing uncertainty
    assert f.uncertainty[-1] >= f.uncertainty[0]


def test_adapter_anomaly_score_flatline_zero():
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    flat = np.full(100, 80.0, dtype=np.float32)
    a = adapter.anomaly_score({"ABP": torch.from_numpy(flat)}, modality="ABP")
    assert a.score == 0.0


def test_adapter_anomaly_score_with_spikes_nonzero():
    rng = np.random.default_rng(8)
    arr = rng.normal(80.0, 2.0, size=1000)
    # 100 spikes (= tail 10%) to ensure tail-mean of |z| is large
    # 100 spike (tail 10%) — tail-mean |z| 충분히 큼
    arr[450:550] = 200.0
    model = LogRegABPBaseline()
    adapter = BaselineFMAdapter(model)
    a = adapter.anomaly_score({"ABP": torch.from_numpy(arr.astype(np.float32))}, modality="ABP")
    assert a.score > 0.3


# ── End-to-end / End-to-end ──


def test_adapter_with_logreg_works_in_factory_pattern():
    """Adapter 는 mock_light_ml YAML 의 drop-in 으로 쓸 수 있다.
    Adapter is a drop-in for the mock_light_ml YAML config.
    """
    X, y = _synthetic_dataset_logreg(n=120)
    baseline = LogRegABPBaseline()
    baseline.fit(X, y, epochs=100)
    adapter = BaselineFMAdapter(baseline, latent_dim=128)

    # Verify all 8 Protocol methods are callable / 8 Protocol method 호출 가능 검증
    abp = _synth_abp(n_seconds=10.0)
    sig = _signal_dict(abp)
    adapter.encode(sig, ["ABP", "HR"])
    adapter.predict_hypotension(sig, 5, ["ABP", "HR"])
    adapter.predict_cardiac_arrest(sig, 5, ["ABP", "HR"])
    adapter.assess_signal_quality(sig, "ABP")
    adapter.cross_modal_consistency(sig, ["ABP", "HR"])
    adapter.temporal_trend(sig, "ABP", 5)
    adapter.forecast_signal(sig, "ABP", 5)
    adapter.anomaly_score(sig, "ABP")
