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

from vitalagent.preprocessing.artifact import (
    clip_to_physiological,
    fill_short_nan_gaps,
)
from vitalagent.preprocessing.signal_config import config_for_modality


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
) -> tuple[dict[str, torch.Tensor], PreprocessReport]:
    """Apply per-modality preprocessing — clip artifacts + fill short NaN gaps.
    Modality 별 전처리 — artifact clip + 짧은 NaN-gap fill.

    Per-modality lookup:
        1. ``vitalagent.preprocessing.signal_config.config_for_modality(name)``
        2. If None → modality 가 그대로 통과 (skipped 에 기록).
        3. If found → ``clip_to_physiological`` (Issue #1) + ``fill_short_nan_gaps`` (Issue #4).

    Args:
        signal: dict mapping modality name → 1-D tensor.
        sampling_rate_hz: if provided, used to convert ``max_nan_gap_s`` →
            samples. If None, ``typical_sampling_rate_hz`` of the modality config
            is used.

    Returns:
        (cleaned_signal, report).
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
        sr_hz = sampling_rate_hz if sampling_rate_hz is not None else cfg.typical_sampling_rate_hz
        max_gap_samples = max(1, int(round(cfg.max_nan_gap_s * sr_hz)))
        filled, fill_report = fill_short_nan_gaps(
            clipped, max_gap_samples=max_gap_samples,
        )

        out_signal[name] = torch.from_numpy(filled.astype(np.float32))
        per_mod[name] = {
            "config_used": cfg.name,
            "n_total": clip_report["n_total"],
            "n_below_range": clip_report["n_below"],
            "n_above_range": clip_report["n_above"],
            "ratio_clipped": clip_report["ratio_clipped"],
            "pre_existing_nan_ratio": clip_report["pre_existing_nan_ratio"],
            "n_nan_gap_filled": fill_report["n_filled"],
            "n_nan_left": fill_report["n_left_nan"],
            "n_long_gap_skipped": fill_report["n_skipped_long_gap"],
            "max_gap_samples": max_gap_samples,
            "sampling_rate_hz_used": sr_hz,
        }

    report = PreprocessReport(
        per_modality=per_mod,
        skipped_modalities=skipped,
        n_modalities_in=len(signal),
        n_modalities_out=len(out_signal),
    )
    return out_signal, report


__all__ = ["preprocess_signal_dict", "PreprocessReport"]
