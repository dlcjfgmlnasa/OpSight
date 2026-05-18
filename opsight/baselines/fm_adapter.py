"""Baseline → ``BiosignalFMInterface`` adapter (plan_1.4 task 8).
Baseline → ``BiosignalFMInterface`` adapter (plan_1.4 task 8).

본 adapter 는 *어떤* ``BaselinePredictor`` 라도 ``BiosignalFMInterface``
Protocol 을 만족하는 mock FM 으로 wrap 한다. 본 wrap 결과는 그대로
plan_1.7.5 의 Tier 3 (Light ML) Mock FM 으로 사용 가능 — ADR-011 의
swap mechanism 을 지킨다 (호출자는 ``BiosignalFMInterface`` 만 안다).

This adapter wraps any ``BaselinePredictor`` as a mock FM that satisfies
``BiosignalFMInterface``. The wrap result is directly usable as plan_1.7.5
Tier 3 (Light ML) Mock FM, preserving ADR-011 swap mechanism (callers only
know ``BiosignalFMInterface``).

Protocol method coverage / Protocol method 커버리지:

| Method                       | Implementation                              |
|------------------------------|---------------------------------------------|
| ``encode``                   | feature-vector → torch.Tensor (latent dim)  |
| ``predict_hypotension``      | baseline.predict — main path                |
| ``predict_cardiac_arrest``   | rule-based fallback (rare event proxy)      |
| ``assess_signal_quality``    | heuristic from signal NaN ratio + std       |
| ``cross_modal_consistency``  | |Pearson r| on quality-filtered windows     |
| ``temporal_trend``           | linear slope on requested modality          |
| ``forecast_signal``          | linear extrapolation                         |
| ``anomaly_score``            | tail z-score / 6                            |
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import torch

from opsight.baselines.features import _to_numpy
from opsight.baselines.types import BaselinePredictor
from opsight.fm.result_types import (
    AnomalyResult,
    ArrestResult,
    ConsistencyResult,
    ForecastResult,
    HypotensionResult,
    QualityResult,
    TrendResult,
)

if TYPE_CHECKING:
    pass


class BaselineFMAdapter:
    """Wrap a ``BaselinePredictor`` as ``BiosignalFMInterface``-compatible.
    ``BaselinePredictor`` 를 ``BiosignalFMInterface`` 호환으로 wrap.

    The wrapped object passes ``isinstance(x, BiosignalFMInterface)`` and is
    a drop-in for ``configs/fm/mock_light_ml.yaml`` once plan_1.7.5 lands.
    Wrap 결과는 ``isinstance(x, BiosignalFMInterface)`` 통과; plan_1.7.5
    합류 시 ``configs/fm/mock_light_ml.yaml`` 의 drop-in 으로 사용 가능.
    """

    def __init__(self, baseline: BaselinePredictor, *, latent_dim: int = 128) -> None:
        self._baseline = baseline
        self._latent_dim = int(latent_dim)
        # mock_tier marker propagated through every Result.meta
        # mock_tier marker 가 모든 Result.meta 에 전파됨
        self._tier = "light_ml"

    @property
    def name(self) -> str:
        return f"baseline_fm_adapter[{self._baseline.name}]"

    # ── BiosignalFMInterface method 8 가지 / 8 BiosignalFMInterface methods ──

    def encode(
        self, signal: dict[str, torch.Tensor], available_modalities: list[str]
    ) -> torch.Tensor:
        """Encode by aggregating per-modality (mean, std, slope) into latent_dim.
        modality 별 (mean, std, slope) 를 latent_dim 으로 집계.
        """
        feats: list[float] = [float(len(available_modalities))]
        for k in available_modalities:
            if k not in signal:
                continue
            arr = _to_numpy(signal[k])
            if len(arr) == 0:
                feats.extend([0.0, 0.0, 0.0])
                continue
            mean = float(np.nanmean(arr)) if not np.isnan(arr).all() else 0.0
            std = float(np.nanstd(arr)) if not np.isnan(arr).all() else 0.0
            if len(arr) >= 2:
                mask = ~np.isnan(arr)
                if mask.sum() >= 2:
                    x = np.arange(len(arr), dtype=np.float64)
                    try:
                        slope, _ = np.polyfit(x[mask], arr[mask], 1)
                    except (np.linalg.LinAlgError, ValueError):
                        slope = 0.0
                else:
                    slope = 0.0
            else:
                slope = 0.0
            feats.extend([mean, std, float(slope)])
        out = np.zeros(self._latent_dim, dtype=np.float32)
        n = min(len(feats), self._latent_dim)
        out[:n] = feats[:n]
        return torch.from_numpy(out)

    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult:
        """Route to baseline.predict / baseline.predict 로 routing."""
        result = self._baseline.predict(signal, horizon_min, available_modalities)
        return HypotensionResult(
            risk=result.risk,
            uncertainty=result.uncertainty,
            horizon_min=result.horizon_min,
            meta={
                "mock_tier": self._tier,
                "baseline": self._baseline.name,
                **result.meta,
            },
        )

    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult:
        """Rule-based composite flag (HR + MAP extremes).
        Rule-based composite flag (HR + MAP 극값).
        """
        from opsight.fm.mock_rule_based import (
            ARREST_HR_HIGH,
            ARREST_HR_LOW,
            ARREST_MAP_LOW,
        )

        flags: list[str] = []
        score = 0.0
        present = 0
        hr = None
        for k in ("HR", "Solar8000/HR", "Solar8000/PLETH_HR"):
            if k in signal:
                hr = _to_numpy(signal[k])
                break
        if hr is not None and len(hr) and not np.isnan(hr).all():
            hr_mean = float(np.nanmean(hr))
            if hr_mean < ARREST_HR_LOW:
                score += 0.5
                flags.append("hr_low")
            elif hr_mean > ARREST_HR_HIGH:
                score += 0.5
                flags.append("hr_high")
            present += 1
        abp = None
        for k in ("ABP", "SNUADC/ART", "Solar8000/ART_MBP", "EV1000/ART_MBP"):
            if k in signal:
                abp = _to_numpy(signal[k])
                break
        if abp is not None and len(abp) and not np.isnan(abp).all():
            abp_mean = float(np.nanmean(abp))
            if abp_mean < ARREST_MAP_LOW:
                score += 0.5
                flags.append("map_low")
            present += 1
        if present == 0:
            return ArrestResult(
                risk=0.05, uncertainty=0.8, horizon_min=horizon_min,
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "fallback": "no_hr_or_abp"},
            )
        risk_raw = min(1.0, score)
        risk = 0.02 + 0.6 * risk_raw
        return ArrestResult(
            risk=risk,
            uncertainty=0.3 if flags else 0.5,
            horizon_min=horizon_min,
            meta={"mock_tier": self._tier, "baseline": self._baseline.name, "flags": flags},
        )

    def assess_signal_quality(
        self, signal: dict[str, torch.Tensor], modality: str
    ) -> QualityResult:
        if modality not in signal:
            return QualityResult(
                score=0.0, reason="modality_absent",
                meta={"mock_tier": self._tier, "baseline": self._baseline.name},
            )
        arr = _to_numpy(signal[modality])
        if len(arr) == 0:
            return QualityResult(
                score=0.0, reason="empty",
                meta={"mock_tier": self._tier, "baseline": self._baseline.name},
            )
        nan_ratio = float(np.mean(np.isnan(arr)))
        valid = arr[~np.isnan(arr)]
        std = float(np.std(valid)) if len(valid) else 0.0
        if nan_ratio > 0.5:
            return QualityResult(score=0.3, reason="high_nan_ratio",
                                 meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                                       "nan_ratio": nan_ratio})
        if std < 1e-3:
            return QualityResult(score=0.2, reason="flatline",
                                 meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                                       "std": std})
        return QualityResult(score=0.95, reason=None,
                             meta={"mock_tier": self._tier, "baseline": self._baseline.name})

    def cross_modal_consistency(
        self, signal: dict[str, torch.Tensor], modality_pair: list[str]
    ) -> ConsistencyResult:
        if len(modality_pair) != 2:
            return ConsistencyResult(
                score=0.0, reason="invalid_pair",
                meta={"mock_tier": self._tier, "baseline": self._baseline.name},
            )
        a_name, b_name = modality_pair
        if a_name not in signal or b_name not in signal:
            return ConsistencyResult(
                score=0.0, reason="modality_absent",
                meta={"mock_tier": self._tier, "baseline": self._baseline.name},
            )
        a = _to_numpy(signal[a_name])
        b = _to_numpy(signal[b_name])
        n = min(len(a), len(b))
        if n < 2:
            return ConsistencyResult(score=0.0, reason="insufficient_samples",
                                     meta={"mock_tier": self._tier, "baseline": self._baseline.name})
        a, b = a[:n], b[:n]
        mask = ~(np.isnan(a) | np.isnan(b))
        if mask.sum() < 2 or np.std(a[mask]) < 1e-6 or np.std(b[mask]) < 1e-6:
            return ConsistencyResult(score=0.0, reason="flatline_or_nan",
                                     meta={"mock_tier": self._tier, "baseline": self._baseline.name})
        r = float(np.corrcoef(a[mask], b[mask])[0, 1])
        score = float(abs(r))
        return ConsistencyResult(
            score=score, reason=f"modality_pair: {a_name}-{b_name}",
            meta={"mock_tier": self._tier, "baseline": self._baseline.name, "pearson_r": r},
        )

    def temporal_trend(
        self, signal: dict[str, torch.Tensor], modality: str, window_min: int
    ) -> TrendResult:
        if modality not in signal:
            return TrendResult(
                slope=0.0, magnitude=0.0, label="stable",
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "modality_absent": True},
            )
        arr = _to_numpy(signal[modality])
        mask = ~np.isnan(arr)
        if mask.sum() < 2:
            return TrendResult(
                slope=0.0, magnitude=0.0, label="stable",
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "insufficient_samples": True},
            )
        x = np.arange(len(arr), dtype=np.float64)
        try:
            slope, _ = np.polyfit(x[mask], arr[mask], 1)
        except (np.linalg.LinAlgError, ValueError):
            slope = 0.0
        # convert to per-minute / 분당 단위 변환
        slope_per_min = float(slope * self._baseline.config.sampling_rate_hz * 60.0)
        magnitude = float(abs(slope_per_min) * window_min)
        if abs(slope_per_min) < 1.0:
            label = "stable"
        elif slope_per_min > 0:
            label = "rising"
        else:
            label = "falling"
        return TrendResult(
            slope=slope_per_min, magnitude=magnitude, label=label,
            meta={"mock_tier": self._tier, "baseline": self._baseline.name},
        )

    def forecast_signal(
        self, signal: dict[str, torch.Tensor], modality: str, horizon_min: int
    ) -> ForecastResult:
        if modality not in signal:
            return ForecastResult(
                forecast=[0.0] * horizon_min, uncertainty=[1.0] * horizon_min,
                horizon_min=horizon_min,
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "modality_absent": True},
            )
        arr = _to_numpy(signal[modality])
        mask = ~np.isnan(arr)
        if mask.sum() < 2:
            mean_val = float(np.nanmean(arr)) if mask.any() else 0.0
            return ForecastResult(
                forecast=[mean_val] * horizon_min, uncertainty=[1.0] * horizon_min,
                horizon_min=horizon_min,
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "insufficient_samples": True},
            )
        x = np.arange(len(arr), dtype=np.float64)
        try:
            slope, intercept = np.polyfit(x[mask], arr[mask], 1)
        except (np.linalg.LinAlgError, ValueError):
            slope, intercept = 0.0, float(np.mean(arr[mask]))
        residual = arr[mask] - (slope * x[mask] + intercept)
        residual_std = float(np.std(residual))
        last_x = float(x[mask].max())
        # 1-minute steps in sample-index space / 분 단위 step
        step_samples = self._baseline.config.sampling_rate_hz * 60.0
        forecast = [float(slope * (last_x + (i + 1) * step_samples) + intercept) for i in range(horizon_min)]
        uncertainty = [float(residual_std * np.sqrt(i + 1)) for i in range(horizon_min)]
        return ForecastResult(
            forecast=forecast, uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                  "residual_std": residual_std},
        )

    def anomaly_score(
        self, signal: dict[str, torch.Tensor], modality: str
    ) -> AnomalyResult:
        if modality not in signal:
            return AnomalyResult(
                score=0.0,
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "modality_absent": True},
            )
        arr = _to_numpy(signal[modality])
        mask = ~np.isnan(arr)
        if mask.sum() < 10:
            return AnomalyResult(
                score=0.0,
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "insufficient_samples": True},
            )
        valid = arr[mask]
        m = float(np.mean(valid))
        s = float(np.std(valid))
        if s < 1e-3:
            return AnomalyResult(
                score=0.0,
                meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                      "flatline": True},
            )
        z = np.abs((valid - m) / s)
        # tail 10% worst-z / tail 10% worst-z
        tail = max(1, int(len(z) * 0.1))
        worst_z = float(np.partition(z, -tail)[-tail:].mean())
        raw = min(1.0, worst_z / 6.0)
        return AnomalyResult(
            score=raw,
            meta={"mock_tier": self._tier, "baseline": self._baseline.name,
                  "worst_z": worst_z},
        )


__all__ = ["BaselineFMAdapter"]
