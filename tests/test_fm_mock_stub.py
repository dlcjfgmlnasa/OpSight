"""StubBiosignalFM output shape, range, and latency tests (plan_1.1.5 T4).
StubBiosignalFM output shape / range / latency 테스트 (plan_1.1.5 T4).

These tests verify the *semantic* contract of each method's output (field
presence, value range, derived-label rules, forecast length, etc.) and the
latency simulation behavior. Protocol compliance is covered separately by
``tests/test_fm_protocol_compliance.py``.
본 테스트는 각 method 출력의 *의미* 계약 (field 존재, 값 range, 파생 label
규칙, forecast 길이 등) + latency 시뮬레이션 동작을 검증한다. Protocol
compliance는 ``tests/test_fm_protocol_compliance.py``가 별도로 cover한다.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import asdict, fields

import pytest
import torch

from opsight.fm.mock_stub import StubBiosignalFM
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


@pytest.fixture
def stub() -> StubBiosignalFM:
    """Default-config stub with seed=42 / 기본 설정 stub (seed=42)."""
    return StubBiosignalFM(seed=42)


@pytest.fixture
def signal() -> dict[str, torch.Tensor]:
    """Synthetic multi-modal signal placeholder.
    Synthetic 다중 modality signal placeholder.
    """
    return {"ABP": torch.zeros(1000), "ECG": torch.zeros(1000), "PPG": torch.zeros(1000)}


# ── Per-method output tests / method별 output 테스트 ──


def test_encode_returns_tensor_with_expected_shape(stub, signal) -> None:
    """``encode`` returns a torch.Tensor with shape ``(latent_dim,)``.
    ``encode``는 shape ``(latent_dim,)`` torch.Tensor를 반환한다.
    """
    out = stub.encode(signal, ["ABP", "ECG", "PPG"])
    assert isinstance(out, torch.Tensor)
    assert tuple(out.shape) == (128,)  # default latent_dim
    assert out.dtype == torch.float32


def test_encode_respects_custom_latent_dim(signal) -> None:
    """``latent_dim`` constructor arg flows through to ``encode`` shape.
    생성자 ``latent_dim``가 ``encode`` shape에 반영된다.
    """
    stub = StubBiosignalFM(seed=42, latent_dim=64)
    out = stub.encode(signal, [])
    assert tuple(out.shape) == (64,)


def test_predict_hypotension_fields_and_ranges(stub, signal) -> None:
    """``predict_hypotension`` returns a complete ``HypotensionResult`` in range.
    ``predict_hypotension``은 range 내 완전한 ``HypotensionResult``를 반환.
    """
    r = stub.predict_hypotension(signal, horizon_min=5, available_modalities=["ABP"])
    assert isinstance(r, HypotensionResult)
    field_names = {f.name for f in fields(HypotensionResult)}
    assert field_names == {"risk", "uncertainty", "horizon_min", "meta"}
    assert 0.0 <= r.risk <= 1.0
    assert 0.0 <= r.uncertainty <= 0.5
    assert r.horizon_min == 5
    assert r.meta["mock_tier"] == "stub"
    assert r.meta["available_modalities"] == ["ABP"]


def test_predict_cardiac_arrest_risk_capped_at_low_range(stub, signal) -> None:
    """Stub returns low cardiac-arrest risk (rare event proxy): risk ∈ [0, 0.2].
    Stub은 낮은 cardiac arrest risk를 반환 (rare event proxy): risk ∈ [0, 0.2].
    """
    r = stub.predict_cardiac_arrest(signal, horizon_min=5, available_modalities=[])
    assert isinstance(r, ArrestResult)
    assert 0.0 <= r.risk <= 0.2
    assert 0.0 <= r.uncertainty <= 0.5
    assert r.horizon_min == 5
    assert r.meta["mock_tier"] == "stub"


def test_assess_signal_quality_reason_rule(signal) -> None:
    """``QualityResult.reason`` is ``None`` iff ``score >= 0.5``.
    ``QualityResult.reason``은 ``score >= 0.5``일 때만 ``None``.

    Tested across many seeds to cover both branches.
    여러 seed로 두 분기 모두 cover.
    """
    branches = {"low_with_reason": 0, "high_without_reason": 0}
    for seed in range(200):
        r = StubBiosignalFM(seed=seed).assess_signal_quality(signal, "ABP")
        assert isinstance(r, QualityResult)
        assert 0.0 <= r.score <= 1.0
        if r.score < 0.5:
            assert r.reason == "stub-random low quality"
            branches["low_with_reason"] += 1
        else:
            assert r.reason is None
            branches["high_without_reason"] += 1
    # Both branches must be observed across 200 seeds.
    # 200 seed에 걸쳐 두 분기 모두 관찰되어야 한다.
    assert all(v > 0 for v in branches.values()), branches


def test_cross_modal_consistency_range(stub, signal) -> None:
    """``cross_modal_consistency`` score in [0, 1]; ``reason`` is None.
    ``cross_modal_consistency`` score ∈ [0, 1], ``reason`` = None.
    """
    r = stub.cross_modal_consistency(signal, ("ABP", "PPG"))
    assert isinstance(r, ConsistencyResult)
    assert 0.0 <= r.score <= 1.0
    assert r.reason is None
    assert r.meta["modality_pair"] == ["ABP", "PPG"]


def test_temporal_trend_label_derives_from_slope(signal) -> None:
    """Label rule: ``|slope| < 1`` → stable, slope > 0 → rising, slope < 0 → falling.
    Label 규칙: ``|slope| < 1`` → stable, slope > 0 → rising, slope < 0 → falling.
    """
    observed_labels = set()
    for seed in range(100):
        r = StubBiosignalFM(seed=seed).temporal_trend(signal, "ABP", window_min=5)
        assert isinstance(r, TrendResult)
        assert -5.0 <= r.slope <= 5.0
        assert r.magnitude == pytest.approx(abs(r.slope))
        if abs(r.slope) < 1.0:
            assert r.label == "stable"
        elif r.slope > 0:
            assert r.label == "rising"
        else:
            assert r.label == "falling"
        observed_labels.add(r.label)
    # All three labels must be observed across 100 seeds.
    # 100 seed에 걸쳐 3개 label 모두 관찰.
    assert observed_labels == {"stable", "rising", "falling"}


def test_forecast_signal_length_and_range(stub, signal) -> None:
    """Forecast and uncertainty lists have length ``horizon_min``, values in range.
    Forecast / uncertainty 리스트 길이가 ``horizon_min``, 값은 range 내.
    """
    horizon = 5
    r = stub.forecast_signal(signal, "ABP", horizon_min=horizon)
    assert isinstance(r, ForecastResult)
    assert len(r.forecast) == horizon
    assert len(r.uncertainty) == horizon
    assert all(50.0 <= v <= 120.0 for v in r.forecast)
    assert all(2.0 <= v <= 10.0 for v in r.uncertainty)
    assert r.horizon_min == horizon
    assert r.meta["sampling_rate_hz"] == pytest.approx(1.0 / 60.0)


def test_anomaly_score_range(stub, signal) -> None:
    """``anomaly_score`` returns ``AnomalyResult`` with score in [0, 1].
    ``anomaly_score``는 score ∈ [0, 1]의 ``AnomalyResult`` 반환.
    """
    r = stub.anomaly_score(signal, "ABP")
    assert isinstance(r, AnomalyResult)
    assert 0.0 <= r.score <= 1.0
    assert r.meta["modality"] == "ABP"


# ── Determinism / 결정성 ──


def test_same_seed_yields_same_output() -> None:
    """Two stubs with the same seed produce the same first sample.
    동일 seed의 두 stub은 동일 첫 sample을 생성.
    """
    a = StubBiosignalFM(seed=42).predict_hypotension({}, 5, [])
    b = StubBiosignalFM(seed=42).predict_hypotension({}, 5, [])
    assert a.risk == b.risk
    assert a.uncertainty == b.uncertainty


def test_different_seed_yields_different_output() -> None:
    """Different seeds produce different outputs.
    다른 seed는 다른 출력을 생성한다.
    """
    a = StubBiosignalFM(seed=42).predict_hypotension({}, 5, [])
    b = StubBiosignalFM(seed=123).predict_hypotension({}, 5, [])
    assert a.risk != b.risk


def test_all_results_are_json_serializable(stub, signal) -> None:
    """Every non-tensor Result is JSON-serializable via ``asdict + json``.
    Tensor가 아닌 모든 Result는 ``asdict + json``으로 JSON-serializable.
    """
    import json

    payloads = [
        stub.predict_hypotension(signal, 5, []),
        stub.predict_cardiac_arrest(signal, 5, []),
        stub.assess_signal_quality(signal, "ABP"),
        stub.cross_modal_consistency(signal, ("ABP", "PPG")),
        stub.temporal_trend(signal, "ABP", 5),
        stub.forecast_signal(signal, "ABP", 5),
        stub.anomaly_score(signal, "ABP"),
    ]
    for r in payloads:
        json.dumps(asdict(r))


# ── Latency simulation / latency 시뮬레이션 ──


def test_zero_latency_default_is_fast(signal) -> None:
    """Default (no latency config) returns within a few ms across 8 calls.
    기본 (no latency config)에서 8 호출이 수 ms 안에 완료.
    """
    stub = StubBiosignalFM(seed=42)
    t0 = time.perf_counter()
    for _ in range(8):
        stub.predict_hypotension(signal, 5, [])
    assert (time.perf_counter() - t0) < 0.05


def test_global_latency_applied(signal) -> None:
    """Global ``latency_sim_sec`` is applied to every method.
    전역 ``latency_sim_sec``이 모든 method에 적용.
    """
    stub = StubBiosignalFM(seed=42, latency_sim_sec=0.05)
    t0 = time.perf_counter()
    stub.predict_hypotension(signal, 5, [])
    elapsed = time.perf_counter() - t0
    assert 0.05 <= elapsed < 0.15


def test_per_method_override_takes_precedence(signal) -> None:
    """Per-method override beats the global default; absence falls back to global.
    Per-method override가 전역 default를 이긴다. 부재 시 전역으로 fallback.
    """
    stub = StubBiosignalFM(
        seed=42,
        latency_sim_sec=0.0,
        latency_per_method={"predict_hypotension": 0.03, "encode": 0.10},
    )
    t0 = time.perf_counter()
    stub.predict_hypotension(signal, 5, [])
    hypo = time.perf_counter() - t0

    t0 = time.perf_counter()
    stub.encode(signal, [])
    enc = time.perf_counter() - t0

    t0 = time.perf_counter()
    stub.anomaly_score(signal, "ABP")
    anom = time.perf_counter() - t0

    assert 0.03 <= hypo < 0.10
    assert 0.10 <= enc < 0.20
    assert anom < 0.02


def test_jitter_introduces_variance(signal) -> None:
    """Jitter produces measurable variance around the base latency.
    Jitter가 base latency 주변에 측정 가능한 분산을 만든다.

    Base 50ms ± 50% → range expected in [25ms, 75ms]; std > 1ms.
    Base 50ms ± 50% → range 기대 [25ms, 75ms]; std > 1ms.
    """
    stub = StubBiosignalFM(seed=42, latency_sim_sec=0.05, latency_jitter_pct=0.5)
    durations = []
    for _ in range(10):
        t0 = time.perf_counter()
        stub.predict_hypotension(signal, 5, [])
        durations.append(time.perf_counter() - t0)
    assert 0.020 <= min(durations)
    assert max(durations) <= 0.085  # allow small scheduling slack
    assert statistics.stdev(durations) > 0.001
