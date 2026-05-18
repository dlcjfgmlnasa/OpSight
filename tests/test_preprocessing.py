"""Tests for opsight.preprocessing (Sprint 5 follow-up, real_case findings).
opsight.preprocessing 테스트 (Sprint 5 follow-up, real_case findings).

Coverage:
- SignalConfig registry + alias lookup
- clip_to_physiological — MAP -9 / 344 case (Issue #1)
- fill_short_nan_gaps — boundary preserve, long-gap skip
- detect_sampling_rate / resample_numpy
- preprocess_signal_dict — end-to-end, skipped unknown modality, NaN report
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.preprocessing import (
    SIGNAL_CONFIGS,
    SignalConfig,
    clip_to_physiological,
    config_for_modality,
    detect_sampling_rate,
    fill_short_nan_gaps,
    preprocess_signal_dict,
    resample_numpy,
)


# ── signal_config ──


def test_signal_config_registry_has_priority_modalities():
    for k in ("ABP", "MAP", "HR", "PPG", "ECG_II", "SpO2", "EtCO2", "BIS", "BT"):
        assert k in SIGNAL_CONFIGS, f"missing config: {k}"
        cfg = SIGNAL_CONFIGS[k]
        assert isinstance(cfg, SignalConfig)
        assert cfg.physiological_min < cfg.physiological_max
        assert cfg.clinical_review_required


def test_config_alias_lookup_resolves_to_canonical():
    # SNUADC/ART → ABP
    assert config_for_modality("SNUADC/ART").name == "ABP"
    # Solar8000/ART_MBP → MAP
    assert config_for_modality("Solar8000/ART_MBP").name == "MAP"
    # Solar8000/HR → HR
    assert config_for_modality("Solar8000/HR").name == "HR"
    # BIS/BIS → BIS
    assert config_for_modality("BIS/BIS").name == "BIS"
    # Solar8000/PLETH_SPO2 → SpO2
    assert config_for_modality("Solar8000/PLETH_SPO2").name == "SpO2"


def test_config_alias_unknown_returns_none():
    assert config_for_modality("UnknownTrack") is None
    assert config_for_modality("CardioQ/CO") is None


# ── clip_to_physiological (Issue #1: real_case MAP -9 / 344) ──


def test_clip_masks_below_min():
    arr = np.array([-9.0, 50.0, 60.0, 80.0])
    cleaned, report = clip_to_physiological(arr, min_val=20.0, max_val=250.0)
    assert np.isnan(cleaned[0])  # -9 → NaN
    assert cleaned[1] == 50.0
    assert report["n_below"] == 1
    assert report["n_above"] == 0


def test_clip_masks_above_max():
    arr = np.array([80.0, 90.0, 344.0, 200.0])
    cleaned, report = clip_to_physiological(arr, min_val=20.0, max_val=250.0)
    assert np.isnan(cleaned[2])
    assert report["n_above"] == 1


def test_clip_preserves_pre_existing_nan():
    arr = np.array([80.0, np.nan, 50.0, 90.0])
    cleaned, report = clip_to_physiological(arr, min_val=20.0, max_val=250.0)
    assert np.isnan(cleaned[1])
    # NaN 은 below / above 에 카운트되지 않음 (pre-existing 으로 분리)
    assert report["n_below"] == 0
    assert report["n_above"] == 0
    assert report["pre_existing_nan_ratio"] > 0


def test_clip_real_case_artifact_scenario():
    # case 1 의 raw MAP artifact 시나리오 — std 42.7 → clip 후 정상화 확인
    rng = np.random.default_rng(42)
    base = rng.normal(82.0, 5.0, size=1000)
    # Inject 50 artifacts: 25 below, 25 above
    base[:25] = -9.0
    base[25:50] = 344.0
    cleaned, report = clip_to_physiological(base, min_val=20.0, max_val=250.0)
    # 50 sample 이 NaN 으로 mask
    assert report["n_below"] == 25
    assert report["n_above"] == 25
    # 정상 sample 의 통계가 합리적 — std 큰폭 감소
    valid = cleaned[~np.isnan(cleaned)]
    assert 3.0 < np.std(valid) < 8.0  # 원래 5 근처
    assert 75.0 < np.mean(valid) < 90.0


def test_clip_rejects_non_1d():
    arr2d = np.zeros((10, 10))
    with pytest.raises(ValueError, match="expected 1-D"):
        clip_to_physiological(arr2d, min_val=0, max_val=1)


# ── fill_short_nan_gaps ──


def test_fill_short_gap_interpolated():
    arr = np.array([1.0, 2.0, np.nan, np.nan, 5.0, 6.0])
    out, report = fill_short_nan_gaps(arr, max_gap_samples=3)
    assert report["n_filled"] == 2
    assert report["n_left_nan"] == 0
    # Interpolated values between 2.0 and 5.0
    assert 2.0 < out[2] < 5.0
    assert 2.0 < out[3] < 5.0


def test_fill_long_gap_left_nan():
    arr = np.array([1.0] + [np.nan] * 10 + [5.0])
    out, report = fill_short_nan_gaps(arr, max_gap_samples=3)
    assert report["n_filled"] == 0
    assert report["n_skipped_long_gap"] == 10
    assert np.isnan(out[1:11]).all()


def test_fill_boundary_nan_preserved():
    # Leading NaN — no extrapolation
    arr = np.array([np.nan, np.nan, 3.0, 4.0])
    out, report = fill_short_nan_gaps(arr, max_gap_samples=5)
    assert np.isnan(out[0])
    assert np.isnan(out[1])
    assert report["n_filled"] == 0
    # Trailing NaN — no extrapolation
    arr2 = np.array([1.0, 2.0, np.nan, np.nan])
    out2, _ = fill_short_nan_gaps(arr2, max_gap_samples=5)
    assert np.isnan(out2[2])
    assert np.isnan(out2[3])


def test_fill_no_nan_passthrough():
    arr = np.array([1.0, 2.0, 3.0])
    out, report = fill_short_nan_gaps(arr, max_gap_samples=5)
    assert np.array_equal(out, arr)
    assert report["n_filled"] == 0


# ── sampling ──


def test_detect_sampling_rate_basic():
    # 1000 samples spanning 100 seconds → 10 Hz
    assert detect_sampling_rate(1000, 100.0) == pytest.approx(10.0)


def test_detect_sampling_rate_zero_duration():
    assert detect_sampling_rate(100, 0.0) == 0.0


def test_resample_numpy_upsample():
    arr = np.array([0.0, 10.0, 20.0, 30.0])  # 4 samples, source 1Hz
    out = resample_numpy(arr, source_hz=1.0, target_hz=2.0)
    assert out.size == 8  # 4 sec × 2Hz = 8 samples
    assert out[0] == pytest.approx(0.0)
    assert out[-1] == pytest.approx(30.0)


def test_resample_numpy_downsample():
    arr = np.linspace(0, 100, 1000)  # 1000 samples
    out = resample_numpy(arr, source_hz=100.0, target_hz=10.0)
    assert out.size == 100  # 10s × 10Hz


def test_resample_preserves_nan():
    arr = np.array([1.0, np.nan, 3.0, 4.0])
    out = resample_numpy(arr, source_hz=1.0, target_hz=2.0)
    # any neighbor NaN → result NaN
    assert np.any(np.isnan(out))


def test_resample_same_rate_passthrough():
    arr = np.array([1.0, 2.0, 3.0])
    out = resample_numpy(arr, source_hz=10.0, target_hz=10.0)
    assert np.allclose(out, arr)


# ── pipeline / preprocess_signal_dict ──


def test_pipeline_clips_artifacts_in_signal_dict():
    # MAP 시그널 with artifact
    map_arr = np.full(60, 80.0, dtype=np.float32)
    map_arr[5] = -9.0  # artifact
    map_arr[20] = 344.0  # artifact
    signal = {"MAP": torch.from_numpy(map_arr)}
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=1.0)
    assert "MAP" in cleaned
    cleaned_arr = cleaned["MAP"].numpy()
    # Artifacts → either NaN (if not fillable) or interpolated (if neighbors valid)
    # 본 case: gap 길이 1 → 양 옆 neighbor 80.0 → interpolated to 80.0
    assert report.per_modality["MAP"]["n_below_range"] == 1
    assert report.per_modality["MAP"]["n_above_range"] == 1
    # 1-sample gap 은 max_nan_gap_s=2.0 × 1Hz = 2 samples 미만 → filled
    assert report.per_modality["MAP"]["n_nan_gap_filled"] == 2
    # MAP 은 numeric (not waveform) — resampled=False
    assert report.per_modality["MAP"]["resampled"] is False
    # 정상 sample 영향 없음
    assert cleaned_arr[0] == pytest.approx(80.0)


# ── Waveform 100 Hz resample (BFM standard) ──


def test_pipeline_waveform_resampled_to_100hz():
    """ABP 는 waveform → BFM 표준 100 Hz 로 자동 resample.
    BFM standard: all waveforms resample to uniform 100 Hz target.
    """
    # 500 Hz × 1초 = 500 sample ABP
    sr_native = 500.0
    n = int(sr_native * 1.0)
    abp = (80.0 + np.random.default_rng(0).normal(0, 2, n)).astype(np.float32)
    signal = {"ABP": torch.from_numpy(abp)}
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=sr_native)

    rep = report.per_modality["ABP"]
    assert rep["is_waveform"] is True
    assert rep["resampled"] is True
    assert rep["source_sampling_rate_hz"] == 500.0
    assert rep["output_sampling_rate_hz"] == 100.0
    # 500 Hz → 100 Hz: 500 sample → 100 sample
    assert rep["n_total_output"] == 100
    assert cleaned["ABP"].numel() == 100


def test_pipeline_numeric_not_resampled():
    """HR / BIS / SpO2 같은 numeric 은 native rate 유지.
    Numerics (HR / BIS / SpO2) keep native sampling rate.
    """
    hr_arr = np.full(60, 75.0, dtype=np.float32)  # 60 sample at 1Hz
    signal = {"HR": torch.from_numpy(hr_arr)}
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=1.0)
    rep = report.per_modality["HR"]
    assert rep["is_waveform"] is False
    assert rep["resampled"] is False
    assert rep["source_sampling_rate_hz"] == rep["output_sampling_rate_hz"] == 1.0
    assert cleaned["HR"].numel() == 60


def test_pipeline_resample_can_be_disabled():
    abp = np.full(500, 80.0, dtype=np.float32)
    signal = {"ABP": torch.from_numpy(abp)}
    cleaned, report = preprocess_signal_dict(
        signal, sampling_rate_hz=500.0,
        resample_waveforms_to_target=False,
    )
    rep = report.per_modality["ABP"]
    assert rep["resampled"] is False
    # 500 Hz 유지 — 500 sample 그대로
    assert cleaned["ABP"].numel() == 500


def test_pipeline_eeg_128hz_to_100hz():
    """EEG (BIS/EEG1_WAV) 는 128 Hz → 100 Hz downsample.
    EEG (BIS/EEG1_WAV) at 128 Hz → resample to 100 Hz.
    """
    sr_native = 128.0
    n = int(sr_native * 2.0)  # 2 seconds
    eeg = (np.random.default_rng(1).normal(0, 50, n)).astype(np.float32)
    signal = {"BIS/EEG1_WAV": torch.from_numpy(eeg)}
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=sr_native)
    rep = report.per_modality["BIS/EEG1_WAV"]
    assert rep["is_waveform"] is True
    assert rep["resampled"] is True
    # 128 Hz × 2s → 100 Hz × 2s = 200 samples
    assert rep["n_total_output"] == 200


def test_pipeline_co2_waveform_62_5hz_to_100hz():
    """Primus/CO2 (capnography waveform) 62.5 Hz → 100 Hz upsample.
    """
    sr_native = 62.5
    n = int(sr_native * 4.0)  # 4 seconds = 250 sample
    co2 = np.full(n, 35.0, dtype=np.float32)
    signal = {"Primus/CO2": torch.from_numpy(co2)}
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=sr_native)
    rep = report.per_modality["Primus/CO2"]
    assert rep["is_waveform"] is True
    assert rep["resampled"] is True
    # 62.5 × 4 → 100 × 4 = 400 samples
    assert rep["n_total_output"] == 400


def test_pipeline_skips_unknown_modality():
    signal = {"UnknownTrack": torch.tensor([1.0, 2.0, 3.0])}
    cleaned, report = preprocess_signal_dict(signal)
    assert "UnknownTrack" in cleaned
    assert "UnknownTrack" in report.skipped_modalities
    # untouched
    assert torch.equal(cleaned["UnknownTrack"], torch.tensor([1.0, 2.0, 3.0]))


def test_pipeline_multimodal():
    signal = {
        "MAP": torch.tensor([80.0, -9.0, 82.0, 90.0], dtype=torch.float32),
        "HR":  torch.tensor([75.0, 78.0, 999.0, 80.0], dtype=torch.float32),  # 999 > 250
        "BIS": torch.tensor([45.0, 50.0, 48.0, 52.0], dtype=torch.float32),  # all valid
        "SomeUnknown": torch.tensor([1.0, 2.0], dtype=torch.float32),
    }
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=1.0)
    assert report.n_modalities_in == 4
    assert report.n_modalities_out == 4
    assert "SomeUnknown" in report.skipped_modalities
    assert report.per_modality["MAP"]["n_below_range"] == 1
    assert report.per_modality["HR"]["n_above_range"] == 1
    assert report.per_modality["BIS"]["ratio_clipped"] == 0.0


def test_pipeline_real_case_artifact_volume():
    # case 1 시나리오 시뮬레이션 — 53% NaN + artifact 5%
    rng = np.random.default_rng(0)
    n = 1000
    arr = rng.normal(82.0, 5.0, size=n).astype(np.float32)
    # 53% NaN (sampling gap)
    nan_idx = rng.choice(n, size=int(n * 0.53), replace=False)
    arr[nan_idx] = np.nan
    # 5% artifacts (overlapping ok)
    artifact_idx = rng.choice(n, size=int(n * 0.05), replace=False)
    arr[artifact_idx] = -9.0  # transducer zero
    signal = {"MAP": torch.from_numpy(arr)}
    cleaned, report = preprocess_signal_dict(signal, sampling_rate_hz=1.0)
    rep = report.per_modality["MAP"]
    # artifact 들 (non-NaN 이었던) 이 clip 됨
    assert rep["n_below_range"] > 0
    # 짧은 gap 일부 interpolated
    assert rep["n_nan_gap_filled"] > 0
    # cleaned 의 valid sample 통계 가 합리적
    cleaned_arr = cleaned["MAP"].numpy()
    valid = cleaned_arr[~np.isnan(cleaned_arr)]
    assert 70.0 < np.mean(valid) < 95.0


def test_pipeline_report_dataclass_fields():
    signal = {"MAP": torch.tensor([80.0, 81.0], dtype=torch.float32)}
    _, report = preprocess_signal_dict(signal, sampling_rate_hz=1.0)
    assert hasattr(report, "per_modality")
    assert hasattr(report, "skipped_modalities")
    assert hasattr(report, "n_modalities_in")
    assert hasattr(report, "n_modalities_out")
