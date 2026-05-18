"""Tests for Mock FM Tier 3 — LightMLBiosignalFM (plan_1.7.5).
Mock FM Tier 3 LightMLBiosignalFM 테스트 (plan_1.7.5).

Coverage:
- Construction with each supported primary_baseline (logreg / lstm / hatib / xgb)
- Protocol compliance (isinstance + 8 method smoke)
- mock_tier == "light_ml" marker propagation
- Optional checkpoint load (file not found)
- Latency simulation
- Factory integration (create_fm with mock_light_ml.yaml)
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
import torch

from vitalagent.fm.factory import create_fm
from vitalagent.fm.interface import BiosignalFMInterface
from vitalagent.fm.mock_light_ml import LightMLBiosignalFM


# ── Synthetic signal fixture / 합성 signal fixture ──


def _synth_signal(seed: int = 0) -> dict[str, torch.Tensor]:
    rng = np.random.default_rng(seed)
    n = 5000  # ~10 sec at 500 Hz
    abp = 80.0 + rng.normal(0, 2.0, size=n)
    hr = 75.0 + rng.normal(0, 3.0, size=60)
    ppg = rng.normal(1.0, 0.3, size=n)
    return {
        "ABP": torch.from_numpy(abp.astype(np.float32)),
        "HR": torch.from_numpy(hr.astype(np.float32)),
        "PPG": torch.from_numpy(ppg.astype(np.float32)),
    }


# ── Construction with each baseline / baseline 별 생성 ──


@pytest.mark.parametrize(
    "baseline_name",
    ["logreg_abp", "lstm_abp", "hatib_style", "xgb_multimodal"],
)
def test_construct_with_each_baseline(baseline_name: str) -> None:
    fm = LightMLBiosignalFM(primary_baseline=baseline_name, seed=42)
    assert fm.primary_baseline_name == baseline_name
    assert baseline_name in fm.name


def test_construct_unknown_baseline_raises() -> None:
    with pytest.raises(ValueError, match="unknown primary_baseline"):
        LightMLBiosignalFM(primary_baseline="random_forest_v99")


# ── Protocol compliance / Protocol 만족 ──


def test_isinstance_protocol() -> None:
    fm = LightMLBiosignalFM(primary_baseline="logreg_abp")
    assert isinstance(fm, BiosignalFMInterface)


# ── 8 method smoke / 8 method smoke ──


def test_all_8_methods_callable() -> None:
    fm = LightMLBiosignalFM(primary_baseline="logreg_abp")
    sig = _synth_signal()

    enc = fm.encode(sig, available_modalities=["ABP", "HR", "PPG"])
    assert isinstance(enc, torch.Tensor)

    h = fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP", "HR"])
    assert 0.0 <= h.risk <= 1.0

    a = fm.predict_cardiac_arrest(sig, horizon_min=5, available_modalities=["ABP", "HR"])
    assert 0.0 <= a.risk <= 1.0

    q = fm.assess_signal_quality(sig, modality="ABP")
    assert 0.0 <= q.score <= 1.0

    c = fm.cross_modal_consistency(sig, modality_pair=("ABP", "PPG"))
    assert 0.0 <= c.score <= 1.0

    t = fm.temporal_trend(sig, modality="ABP", window_min=5)
    assert t.label in ("rising", "falling", "stable")

    f = fm.forecast_signal(sig, modality="ABP", horizon_min=5)
    assert len(f.forecast) == 5
    assert len(f.uncertainty) == 5

    n = fm.anomaly_score(sig, modality="ABP")
    assert 0.0 <= n.score <= 1.0


# ── mock_tier propagation / mock_tier 전파 ──


def test_mock_tier_marker_in_all_results() -> None:
    fm = LightMLBiosignalFM(primary_baseline="logreg_abp")
    sig = _synth_signal()

    results = [
        fm.predict_hypotension(sig, 5, ["ABP"]),
        fm.predict_cardiac_arrest(sig, 5, ["ABP", "HR"]),
        fm.assess_signal_quality(sig, "ABP"),
        fm.cross_modal_consistency(sig, ("ABP", "PPG")),
        fm.temporal_trend(sig, "ABP", 5),
        fm.forecast_signal(sig, "ABP", 5),
        fm.anomaly_score(sig, "ABP"),
    ]
    for r in results:
        assert r.meta.get("mock_tier") == "light_ml", (
            f"Result {type(r).__name__} missing mock_tier=light_ml: {r.meta}"
        )
        assert r.meta.get("baseline") == "logreg_abp", (
            f"Result {type(r).__name__} missing baseline=logreg_abp: {r.meta}"
        )


# ── Checkpoint optional load / Checkpoint 선택 load ──


def test_checkpoint_path_not_found_raises() -> None:
    with pytest.raises(FileNotFoundError, match="checkpoint not found"):
        LightMLBiosignalFM(
            primary_baseline="logreg_abp",
            checkpoint_path="/nonexistent/path/to/baseline.pt",
        )


def test_checkpoint_roundtrip_via_logreg(tmp_path: Path) -> None:
    # Train a logreg baseline, save, then load via LightMLBiosignalFM.
    # logreg baseline 학습 + 저장 후 LightMLBiosignalFM 으로 load.
    from vitalagent.baselines.features import (
        ABP_FEATURE_NAMES,
        extract_abp_features,
    )
    from vitalagent.baselines.logreg_abp import LogRegABPBaseline

    # Synthetic dataset
    rng = np.random.default_rng(0)
    X, y = [], []
    for i in range(80):
        label = i % 2
        mean = 60.0 if label == 1 else 85.0
        abp = mean + rng.normal(0, 2.0, size=5000)
        X.append(extract_abp_features({"ABP": torch.from_numpy(abp)}))
        y.append(label)
    X = np.array(X)
    y = np.array(y, dtype=np.float64)

    trained = LogRegABPBaseline()
    trained.fit(X, y, epochs=80)
    ckpt = str(tmp_path / "logreg.pt")
    trained.save(ckpt)

    # Construct LightMLBiosignalFM with loaded checkpoint
    fm = LightMLBiosignalFM(primary_baseline="logreg_abp", checkpoint_path=ckpt)
    assert isinstance(fm, BiosignalFMInterface)

    sig = _synth_signal(seed=42)
    h = fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP"])
    assert 0.0 <= h.risk <= 1.0
    # Trained model meta should not signal "untrained" fallback
    # 학습된 모델은 untrained fallback 출력하지 않아야 함
    assert h.meta.get("fallback") != "untrained"


# ── Latency simulation / Latency 시뮬레이션 ──


def test_latency_per_method_applied() -> None:
    fm = LightMLBiosignalFM(
        primary_baseline="logreg_abp",
        latency_per_method={"predict_hypotension": 0.05},  # 50 ms
    )
    sig = _synth_signal()
    t0 = time.perf_counter()
    fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP"])
    elapsed = time.perf_counter() - t0
    # Expect at least 40 ms (latency 50 ms minus jitter slack)
    assert elapsed >= 0.04, f"latency too low: {elapsed * 1000:.1f}ms"


def test_latency_default_zero_does_not_sleep() -> None:
    fm = LightMLBiosignalFM(primary_baseline="logreg_abp", latency_sim_sec=0.0)
    sig = _synth_signal()
    t0 = time.perf_counter()
    fm.encode(sig, available_modalities=["ABP"])
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.05, f"unexpected latency: {elapsed * 1000:.1f}ms"


# ── Factory integration / Factory 통합 ──


def test_factory_create_fm_with_mock_light_ml() -> None:
    fm = create_fm({
        "fm": {
            "implementation": "mock_light_ml",
            "config": {"primary_baseline": "logreg_abp", "seed": 42},
        }
    })
    assert isinstance(fm, BiosignalFMInterface)
    assert isinstance(fm, LightMLBiosignalFM)
    assert fm.primary_baseline_name == "logreg_abp"


def test_factory_create_fm_with_yaml_config() -> None:
    import yaml
    with open("configs/fm/mock_light_ml.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    fm = create_fm(cfg)
    assert isinstance(fm, LightMLBiosignalFM)
    # yaml default = logreg_abp
    assert fm.primary_baseline_name == "logreg_abp"


# ── Negative — XGBoost (unfitted) does not crash, returns fallback ──


def test_xgb_unfitted_predict_falls_back_gracefully() -> None:
    # XGBoost 미설치 → BaselineFMAdapter 가 routes to baseline.predict
    # → XGBMultimodalBaseline.predict 가 untrained_or_xgb_missing fallback 반환
    # XGBoost not installed → adapter routes to baseline.predict
    # → XGBMultimodalBaseline.predict returns untrained_or_xgb_missing fallback
    fm = LightMLBiosignalFM(primary_baseline="xgb_multimodal")
    sig = _synth_signal()
    h = fm.predict_hypotension(sig, horizon_min=5, available_modalities=["ABP"])
    assert 0.0 <= h.risk <= 1.0
    # The adapter wraps the result; baseline meta is merged into HypotensionResult.meta
    # adapter 가 result wrap; baseline meta 가 HypotensionResult.meta 에 merge
    assert h.meta.get("mock_tier") == "light_ml"
    assert h.meta.get("baseline") == "xgb_multimodal"
