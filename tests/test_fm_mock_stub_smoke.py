"""Single-case end-to-end smoke test for StubBiosignalFM (plan_1.1.5 T5).
StubBiosignalFM 단일 case end-to-end smoke 테스트 (plan_1.1.5 T5).

Unlike ``test_fm_mock_stub.py`` (per-method semantic ranges), this module
exercises the *integrated* call path: a single FM instance receives a single
synthetic case payload and is asked to execute every Protocol method in
realistic combinations. Confirms there are no implicit state leaks, no
exceptions, and that the cumulative latency on a representative shallow-loop
profile fits within budget (``docs/project_brief.md §6.1``).
``test_fm_mock_stub.py`` (method별 의미 range 검증)와 달리, 본 module은
*통합* 호출 경로를 점검한다. 단일 FM 인스턴스가 하나의 synthetic case
payload를 받아 8개 Protocol method 전체를 현실적 조합으로 실행한다. 암묵적
state leak / 예외가 없는지, 그리고 대표적인 shallow loop latency profile에서
누적 latency가 예산 (``docs/project_brief.md §6.1``) 내에 들어가는지 확인.

Synthetic signal is used here. When ``plan_1.2`` cohort lands, this fixture
can be swapped for a real case without changing the test logic.
본 테스트는 synthetic signal을 사용한다. ``plan_1.2`` 코호트 도착 시
test logic 변경 없이 본 fixture만 실제 case로 교체 가능.
"""
from __future__ import annotations

import time
from dataclasses import asdict

import pytest
import torch

from vitalagent.fm.interface import BiosignalFMInterface
from vitalagent.fm.mock_stub import StubBiosignalFM
from vitalagent.fm.result_types import (
    AnomalyResult,
    ArrestResult,
    ConsistencyResult,
    ForecastResult,
    HypotensionResult,
    QualityResult,
    TrendResult,
)

# ── Synthetic case payload / synthetic case payload ──
#
# Loosely models a single 30-second window of a few modalities. Values are
# zeros — the stub does not care about content.
# 몇 modality의 약 30초 window를 느슨하게 모사. stub은 내용을 신경 쓰지 않으므로
# zeros로 채움.

_WINDOW_SAMPLES_30S_AT_500HZ = 30 * 500   # 15,000
_WINDOW_SAMPLES_30S_AT_100HZ = 30 * 100   # 3,000


@pytest.fixture
def case_signal() -> dict[str, torch.Tensor]:
    """Synthetic single-case multi-modal signal.
    Synthetic 단일 case 다중 modality 신호.
    """
    return {
        "ABP":     torch.zeros(_WINDOW_SAMPLES_30S_AT_500HZ),   # 500 Hz
        "ECG_II":  torch.zeros(_WINDOW_SAMPLES_30S_AT_500HZ),   # 500 Hz
        "PPG":     torch.zeros(_WINDOW_SAMPLES_30S_AT_500HZ),   # 500 Hz
        "BIS":     torch.zeros(_WINDOW_SAMPLES_30S_AT_100HZ),   # 100 Hz
    }


@pytest.fixture
def case_modalities() -> list[str]:
    """Modalities present in this case / 본 case에 존재하는 modality 목록."""
    return ["ABP", "ECG_II", "PPG", "BIS"]


@pytest.fixture
def shallow_latency_profile() -> dict[str, float]:
    """Realistic shallow-loop latency budget per method (seconds).
    현실적 shallow loop method별 latency 예산 (초).

    Mirrors ``configs/fm/mock_stub.yaml`` defaults.
    ``configs/fm/mock_stub.yaml`` 기본값을 mirror.
    """
    return {
        "encode":                   0.080,
        "predict_hypotension":      0.030,
        "predict_cardiac_arrest":   0.030,
        "assess_signal_quality":    0.010,
        "cross_modal_consistency":  0.020,
        "temporal_trend":           0.015,
        "forecast_signal":          0.050,
        "anomaly_score":            0.015,
    }


# ── Smoke tests / 통합 스모크 테스트 ──


def test_smoke_all_eight_methods_on_single_case(case_signal, case_modalities) -> None:
    """All 8 Protocol methods complete on one synthetic case without exception.
    8개 Protocol method가 단일 synthetic case에서 예외 없이 완료된다.

    Results are checked for type only — semantic ranges are covered in
    ``test_fm_mock_stub.py``.
    결과는 type만 확인 — 의미 range는 ``test_fm_mock_stub.py``가 cover.
    """
    fm = StubBiosignalFM(seed=42)

    # 8 method를 자연스러운 순서로 호출 — Protocol 만족 인스턴스로 보기 위함.
    # Invoke 8 methods in a natural order — treating fm as a Protocol instance.
    fm_typed: BiosignalFMInterface = fm

    enc = fm_typed.encode(case_signal, case_modalities)
    h5 = fm_typed.predict_hypotension(case_signal, 5, case_modalities)
    h15 = fm_typed.predict_hypotension(case_signal, 15, case_modalities)
    arr = fm_typed.predict_cardiac_arrest(case_signal, 5, case_modalities)
    q_abp = fm_typed.assess_signal_quality(case_signal, "ABP")
    q_ecg = fm_typed.assess_signal_quality(case_signal, "ECG_II")
    cons = fm_typed.cross_modal_consistency(case_signal, ("ABP", "PPG"))
    trend = fm_typed.temporal_trend(case_signal, "ABP", window_min=5)
    fcst = fm_typed.forecast_signal(case_signal, "ABP", horizon_min=5)
    anom = fm_typed.anomaly_score(case_signal, "ABP")

    # Well-formed type assertions / well-formed type 검증.
    assert isinstance(enc, torch.Tensor)
    assert isinstance(h5, HypotensionResult) and isinstance(h15, HypotensionResult)
    assert isinstance(arr, ArrestResult)
    assert isinstance(q_abp, QualityResult) and isinstance(q_ecg, QualityResult)
    assert isinstance(cons, ConsistencyResult)
    assert isinstance(trend, TrendResult)
    assert isinstance(fcst, ForecastResult)
    assert isinstance(anom, AnomalyResult)


def test_smoke_modality_subset_only(case_signal) -> None:
    """Stub accepts a strict subset of modalities (no exception).
    Stub은 modality 부분 집합을 수용해야 한다 (예외 없음).
    """
    fm = StubBiosignalFM(seed=42)
    # ABP-only case (Thoracic-like) / ABP만 있는 case (Thoracic 유사).
    fm.predict_hypotension(case_signal, 5, ["ABP"])
    fm.cross_modal_consistency(case_signal, ("ABP", "ABP"))
    fm.assess_signal_quality(case_signal, "ABP")


def test_smoke_no_modalities(case_signal) -> None:
    """Stub returns valid results even with an empty modality list.
    Stub은 modality 리스트가 비어 있어도 유효한 결과를 반환.

    Realistic edge case for the ABP-absent + PPG-absent extreme of the
    modality-agnostic claim.
    Modality-agnostic claim의 ABP-absent + PPG-absent 극단 케이스.
    """
    fm = StubBiosignalFM(seed=42)
    r = fm.predict_hypotension(case_signal, 5, [])
    assert isinstance(r, HypotensionResult)
    assert r.meta["available_modalities"] == []


def test_smoke_all_results_serialize(case_signal, case_modalities) -> None:
    """Every Result from a full sweep is JSON-serializable.
    전체 sweep 결과 Result 모두 JSON-serializable.

    encode() returns a tensor — excluded from this check; serialized by
    upstream node code when needed.
    encode()는 tensor 반환 — 본 체크에서 제외. 필요 시 upstream node가 직렬화.
    """
    import json

    fm = StubBiosignalFM(seed=42)
    results = [
        fm.predict_hypotension(case_signal, 5, case_modalities),
        fm.predict_cardiac_arrest(case_signal, 5, case_modalities),
        fm.assess_signal_quality(case_signal, "ABP"),
        fm.cross_modal_consistency(case_signal, ("ABP", "PPG")),
        fm.temporal_trend(case_signal, "ABP", 5),
        fm.forecast_signal(case_signal, "ABP", 5),
        fm.anomaly_score(case_signal, "ABP"),
    ]
    for r in results:
        json.dumps(asdict(r))


def test_smoke_shallow_loop_latency_within_budget(
    case_signal, case_modalities, shallow_latency_profile
) -> None:
    """Realistic shallow-loop sweep stays within the 15-second budget (§6.1).
    현실적 shallow loop sweep이 15초 예산 안에 머문다 (§6.1).

    Sweep covers the "5–6 quick tools in parallel" but sequentialized here —
    so the wall-clock budget for the SUM is a coarse upper bound, not an
    expectation of parallel execution.
    Sweep은 "5–6 quick tool 병렬"을 sequentialize한 것 — 합산 budget은
    coarse upper bound이며 병렬 실행을 가정하지 않는다.
    """
    fm = StubBiosignalFM(
        seed=42,
        latency_per_method=shallow_latency_profile,
        latency_jitter_pct=0.15,
    )
    t0 = time.perf_counter()
    fm.encode(case_signal, case_modalities)
    fm.predict_hypotension(case_signal, 5, case_modalities)
    fm.predict_hypotension(case_signal, 15, case_modalities)
    fm.assess_signal_quality(case_signal, "ABP")
    fm.cross_modal_consistency(case_signal, ("ABP", "PPG"))
    fm.temporal_trend(case_signal, "ABP", 5)
    fm.forecast_signal(case_signal, "ABP", 5)
    fm.anomaly_score(case_signal, "ABP")
    elapsed = time.perf_counter() - t0
    # Sum of base latencies = 80+30+30+10+20+15+50+15 = 250 ms.
    # +15% jitter best case → ~213 ms; worst case → ~287 ms; well under 15 sec budget.
    # base 합 = 250ms; jitter ±15% → [213, 287]ms; 15초 예산 안에 충분.
    assert elapsed < 1.0, f"sequential shallow sweep too slow: {elapsed*1000:.1f}ms"


def test_smoke_idempotent_state_across_repeated_calls(case_signal, case_modalities) -> None:
    """Repeated calls on one instance do not raise or leak (state evolves only
    via the seeded RNG, not via external IO).
    한 인스턴스에 반복 호출해도 예외 / leak 없음 (state는 seed RNG로만 진화).
    """
    fm = StubBiosignalFM(seed=42)
    for _ in range(20):
        fm.encode(case_signal, case_modalities)
        fm.predict_hypotension(case_signal, 5, case_modalities)
        fm.assess_signal_quality(case_signal, "ABP")
