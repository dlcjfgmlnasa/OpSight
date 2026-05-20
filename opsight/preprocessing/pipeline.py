"""End-to-end preprocessing pipeline for a signal dict.
Signal dict 의 end-to-end 전처리 pipeline.

Composes :mod:`signal_config` + :mod:`artifact` into a single entry point
that takes the same ``signal: dict[str, torch.Tensor]`` format the graph
uses, and returns a cleaned version + per-modality report.

Reference: BFM `vitaldb.py` 의 per-signal pipeline 패턴 *minimum* 포팅.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch

from opsight.preprocessing.artifact import (
    clip_to_physiological,
    fill_short_nan_gaps,
)
from opsight.preprocessing.sampling import resample_numpy
from opsight.preprocessing.signal_config import config_for_modality


# Minimum source sampling rate above which upsampling to ``target_sampling_rate_hz``
# is allowed. Below this, the signal is treated as too sparse to be a true
# waveform and is kept at its source rate.
#
# Rationale: VitalDB raw waveforms (SNUADC 500 Hz, Primus 62.5 Hz, BIS 128 Hz)
# are all well above this floor. But live_view loads via ``interval=1.0`` →
# 1 Hz, which is *not* a waveform sampling rate. Upsampling that to 100 Hz via
# linear interpolation propagates NaN aggressively (one source NaN poisons
# ~target_hz/source_hz output samples) and cannot recover the bandwidth that
# was lost at load time. See `scripts/preprocess_audit.py` audit (Bug #1).
# VitalDB raw waveform 의 native rate 는 모두 본 threshold 보다 위. live_view
# 의 1Hz load 는 waveform rate 가 아니므로 100Hz upsample 시 NaN propagation
# 으로 신호 손상. 위 threshold 미만이면 source rate 유지.
MIN_UPSAMPLE_SOURCE_HZ: float = 10.0


@dataclass(frozen=True)
class PreprocessReport:
    """Aggregate diagnostics after preprocessing a signal dict.
    Signal dict 전처리 후 진단 정보.

    Per-modality keys hold dicts with ``n_clipped`` / ``ratio_clipped`` /
    ``n_filled`` / ``n_left_nan`` / ``config_used`` (None when no config).
    """

    per_modality: dict[str, dict[str, Any]]
    """Per-modality report dict (see above keys)."""

    skipped_modalities: list[str]
    """Modalities with no SignalConfig (kept as-is in output).
    SignalConfig 없는 modality (출력에 그대로 유지).
    """

    n_modalities_in: int
    n_modalities_out: int


def preprocess_signal_dict(
    signal: dict[str, torch.Tensor],
    *,
    sampling_rate_hz: float | None = None,
    resample_waveforms_to_target: bool = True,
) -> tuple[dict[str, torch.Tensor], PreprocessReport]:
    """Apply per-modality preprocessing — clip artifacts + fill NaN gaps + (waveform) resample.
    Modality 별 전처리 — artifact clip + NaN-gap fill + (waveform) resample.

    Per-modality lookup:
        1. ``opsight.preprocessing.signal_config.config_for_modality(name)``
        2. If None → modality 가 그대로 통과 (skipped 에 기록).
        3. If found:
           - ``clip_to_physiological`` (Issue #1)
           - ``fill_short_nan_gaps`` (Issue #4)
           - if ``cfg.is_waveform and resample_waveforms_to_target``:
             resample to ``cfg.target_sampling_rate_hz`` (BFM 표준 100 Hz)

    Args:
        signal: dict mapping modality name → 1-D tensor.
        sampling_rate_hz: if provided, used to convert ``max_nan_gap_s`` →
            samples. If None, ``typical_sampling_rate_hz`` of the modality
            config is used. *Note*: when waveform resample applies, the input
            sampling rate is per-modality (cfg.typical_sampling_rate_hz),
            output is uniform 100 Hz.
        resample_waveforms_to_target: if True (default), waveform modalities
            (`cfg.is_waveform=True`) are resampled to ``cfg.target_sampling_rate_hz``.
            Set False to keep native rate (e.g. for tests).

    Returns:
        (cleaned_signal, report). per_modality dict records
        ``source_sampling_rate_hz`` + ``output_sampling_rate_hz`` + ``resampled``.
    """
    out_signal: dict[str, torch.Tensor] = {}
    per_mod: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []

    for name, tensor in signal.items():
        cfg = config_for_modality(name)
        if cfg is None:
            out_signal[name] = tensor  # untouched
            skipped.append(name)
            continue

        arr = tensor.detach().cpu().numpy().astype(np.float64).ravel()
        # Step 1: physiological clipping (Issue #1)
        clipped, clip_report = clip_to_physiological(
            arr, min_val=cfg.physiological_min, max_val=cfg.physiological_max,
        )
        # Step 2: short NaN-gap fill (Issue #4)
        # gap-budget 은 *native* sampling rate 기준 (resample 전).
        sr_hz = sampling_rate_hz if sampling_rate_hz is not None else cfg.typical_sampling_rate_hz
        max_gap_samples = max(1, int(round(cfg.max_nan_gap_s * sr_hz)))
        filled, fill_report = fill_short_nan_gaps(
            clipped, max_gap_samples=max_gap_samples,
        )

        # Step 3: waveform → BFM target rate resample (100 Hz default)
        # Numeric (HR/SpO2/BIS 등) 은 native rate 유지 — agent layer 의 통계 계산이
        # 이미 numerics-tolerant. Waveform 만 backend (BFM) 의 100 Hz target 정렬.
        # NB: Only DOWNSAMPLE (source > target). Upsampling 1Hz → 100Hz on a
        # waveform that was loaded sparsely (e.g., interval=1.0 via vitaldb)
        # corrupts the signal — linear interpolation propagates NaN aggressively
        # (one source NaN poisons ~target_hz/source_hz output samples) and
        # cannot recover the bandwidth that was lost at load time. Keep the
        # signal at source rate in that case; the agent layer (Tier 2 / Mock
        # FM) is already rate-tolerant and Bio-FM (Stage 2) will receive raw
        # native-rate signals via a different load path.
        # NB: 다운샘플만 수행 (source > target). 1Hz 로 load 된 waveform 을 100Hz
        # 로 upsample 하면 linear interpolation 의 NaN 전파로 신호가 손상되며
        # (source NaN 1개가 ~target_hz/source_hz 개의 출력 NaN 으로), load 시점에
        # 잃어버린 대역폭은 복구되지 않음. 이 경우 source rate 유지.
        resampled = False
        out_sr_hz = sr_hz
        if cfg.is_waveform and resample_waveforms_to_target and sr_hz != cfg.target_sampling_rate_hz:
            upsampling = sr_hz < cfg.target_sampling_rate_hz
            if upsampling and sr_hz < MIN_UPSAMPLE_SOURCE_HZ:
                # Source too sparse to upsample — keep at source rate.
                # Source rate 가 너무 낮아 upsample 불가 — source rate 유지.
                pass
            else:
                filled = resample_numpy(
                    filled, source_hz=sr_hz, target_hz=cfg.target_sampling_rate_hz,
                )
                resampled = True
                out_sr_hz = cfg.target_sampling_rate_hz

        out_signal[name] = torch.from_numpy(filled.astype(np.float32))
        per_mod[name] = {
            "config_used": cfg.name,
            "is_waveform": cfg.is_waveform,
            "n_total_input": clip_report["n_total"],
            "n_total_output": int(filled.size),
            "n_below_range": clip_report["n_below"],
            "n_above_range": clip_report["n_above"],
            "ratio_clipped": clip_report["ratio_clipped"],
            "pre_existing_nan_ratio": clip_report["pre_existing_nan_ratio"],
            "n_nan_gap_filled": fill_report["n_filled"],
            "n_nan_left": fill_report["n_left_nan"],
            "n_long_gap_skipped": fill_report["n_skipped_long_gap"],
            "max_gap_samples": max_gap_samples,
            "source_sampling_rate_hz": sr_hz,
            "output_sampling_rate_hz": out_sr_hz,
            "resampled": resampled,
        }

    report = PreprocessReport(
        per_modality=per_mod,
        skipped_modalities=skipped,
        n_modalities_in=len(signal),
        n_modalities_out=len(out_signal),
    )
    return out_signal, report


__all__ = ["preprocess_signal_dict", "PreprocessReport"]
