"""Mock FM Tier 3 — Light ML (plan_1.7.5).
Mock FM Tier 3 — Light ML (plan_1.7.5).

ADR-011 § "3 tiers" 의 optional Tier 3. plan_1.4 의 baseline (LogReg / LSTM /
Hatib-style; XGBoost 는 xgboost 설치 필요) 을 ``BiosignalFMInterface`` 뒤에서
wrapping 하여 Real-FM proxy 를 제공한다.

ADR-011 §"3 tiers" optional Tier 3. Wraps plan_1.4 baselines (LogReg / LSTM /
Hatib-style; XGBoost requires xgboost install) behind
``BiosignalFMInterface`` as a real-FM proxy.

핵심 설계 / Design:
- ``LightMLBiosignalFM`` 은 ``BaselineFMAdapter`` 의 thin extension —
  config-driven baseline 선택 + 선택적 checkpoint load + latency sim.
- ``BaselineFMAdapter`` 가 이미 8 Protocol method 모두 구현하므로 본
  module 은 *adapter 구성* 만 담당.
- ``mock_tier="light_ml"`` 은 adapter 가 자동 부착.

Method backing / method-to-baseline routing:
- ``predict_hypotension``    → 선택된 baseline (logreg / lstm / hatib_style)
- ``predict_cardiac_arrest`` → adapter 의 rule-based composite (HR/MAP flag)
- ``assess_signal_quality``  → adapter 의 NaN+std heuristic
- ``cross_modal_consistency``→ adapter 의 ``|Pearson r|``
- ``temporal_trend``         → adapter 의 linear slope
- ``forecast_signal``        → adapter 의 linear extrapolation
- ``anomaly_score``          → adapter 의 tail z-score
- ``encode``                  → adapter 의 per-modality (mean, std, slope)

→ 7 method 는 deterministic rule (adapter 내장), 1 method (``predict_hypotension``)
   만 학습된 baseline 사용. 본 분배는 plan_1.4 baseline 의 학습 범위와 일치
   (baseline 은 hypotension 예측 위주).
"""
from __future__ import annotations

import time
from functools import wraps
from typing import TYPE_CHECKING, Any

from opsight.baselines.fm_adapter import BaselineFMAdapter

if TYPE_CHECKING:
    import torch

    from opsight.fm.result_types import (
        AnomalyResult,
        ArrestResult,
        ConsistencyResult,
        ForecastResult,
        HypotensionResult,
        QualityResult,
        TrendResult,
    )


# Baseline registry — config 의 ``primary_baseline`` 이름 → 생성 함수.
# Config 의 ``primary_baseline`` field 가 본 dict 의 key 를 사용.
# XGBoost 는 xgboost 미설치 환경에서 fit/predict 시 NotImplementedError 를
# 발생시키지만 ``BaselineFMAdapter`` 의 unfitted fallback (risk=0.5,
# uncertainty=0.9) 가 동작하므로 LightMLBiosignalFM 의 Protocol 만족은 유지.
_BASELINE_FACTORIES: dict[str, Any] = {}


def _register_baseline_factories() -> None:
    """Lazy register baseline factories — imports happen on first use.
    Lazy registration — 첫 사용 시 import.
    """
    if _BASELINE_FACTORIES:
        return
    from opsight.baselines.hatib_style import HatibStyleBaseline
    from opsight.baselines.logreg_abp import LogRegABPBaseline
    from opsight.baselines.lstm_abp import LSTMABPBaseline
    from opsight.baselines.xgb_multimodal import XGBMultimodalBaseline

    _BASELINE_FACTORIES["logreg_abp"] = LogRegABPBaseline
    _BASELINE_FACTORIES["lstm_abp"] = LSTMABPBaseline
    _BASELINE_FACTORIES["hatib_style"] = HatibStyleBaseline
    _BASELINE_FACTORIES["xgb_multimodal"] = XGBMultimodalBaseline


def _simulate_latency(method: Any) -> Any:
    """Decorator — simulate latency before invoking method.
    호출 전 latency 시뮬레이션 데코레이터.
    """
    @wraps(method)
    def wrapper(self: LightMLBiosignalFM, *args: Any, **kwargs: Any) -> Any:
        self._sleep_for(method.__name__)
        return method(self, *args, **kwargs)
    return wrapper


class LightMLBiosignalFM:
    """Tier 3 Mock FM — wraps a baseline as ``BiosignalFMInterface``.
    Tier 3 Mock FM — baseline 을 ``BiosignalFMInterface`` 로 wrap.

    Example / 사용 예::

        fm = LightMLBiosignalFM(
            primary_baseline="logreg_abp",
            baseline_config={"sampling_rate_hz": 500.0},
        )
        # 이후 일반 BiosignalFMInterface 처럼 사용
        # Use like any BiosignalFMInterface
    """

    def __init__(
        self,
        primary_baseline: str = "logreg_abp",
        baseline_config: dict[str, Any] | None = None,
        checkpoint_path: str | None = None,
        latent_dim: int = 128,
        seed: int = 42,
        latency_sim_sec: float = 0.0,
        latency_per_method: dict[str, float] | None = None,
        latency_jitter_pct: float = 0.0,
    ) -> None:
        _register_baseline_factories()
        if primary_baseline not in _BASELINE_FACTORIES:
            raise ValueError(
                f"unknown primary_baseline: {primary_baseline!r}. "
                f"Known: {sorted(_BASELINE_FACTORIES)}"
            )

        # Build baseline (untrained — caller may load_state via checkpoint_path).
        # Baseline 생성 (untrained — checkpoint_path 로 load 가능).
        baseline_cls = _BASELINE_FACTORIES[primary_baseline]
        self._baseline = baseline_cls(**(baseline_config or {}))
        self._primary_baseline_name = primary_baseline

        # Optional checkpoint load / 선택적 checkpoint load
        if checkpoint_path is not None:
            try:
                self._baseline.load(checkpoint_path)
            except FileNotFoundError as exc:
                raise FileNotFoundError(
                    f"checkpoint not found: {checkpoint_path}. "
                    f"Train + save the baseline first (plan_1.4)."
                ) from exc

        # Adapter — already satisfies BiosignalFMInterface
        # Adapter 가 이미 BiosignalFMInterface 만족
        self._adapter = BaselineFMAdapter(self._baseline, latent_dim=latent_dim)

        # Latency simulation config
        # numpy RNG for jitter — independent of baseline RNG.
        # numpy RNG (jitter 용) — baseline RNG 와 독립.
        import numpy as np
        self._np_rng = np.random.default_rng(seed)
        self._latency_sim_sec = float(latency_sim_sec)
        self._latency_per_method = dict(latency_per_method or {})
        self._latency_jitter_pct = float(latency_jitter_pct)

    # ── Properties / 속성 ──

    @property
    def name(self) -> str:
        return f"LightMLBiosignalFM[{self._primary_baseline_name}]"

    @property
    def primary_baseline_name(self) -> str:
        """The baseline backing ``predict_hypotension``.
        ``predict_hypotension`` 을 backing 하는 baseline 이름.
        """
        return self._primary_baseline_name

    # ── Latency helper / Latency 헬퍼 ──

    def _sleep_for(self, method_name: str) -> None:
        """Sleep to simulate inference latency.
        추론 latency 시뮬레이션 sleep.
        """
        base = self._latency_per_method.get(method_name, self._latency_sim_sec)
        if base <= 0:
            return
        if self._latency_jitter_pct > 0:
            jitter = base * self._latency_jitter_pct
            base = base + float(self._np_rng.uniform(-jitter, jitter))
            base = max(0.0, base)
        if base > 0:
            time.sleep(base)

    # ── BiosignalFMInterface 8 method (adapter 위임 + latency sim) ──

    @_simulate_latency
    def encode(
        self,
        signal: dict[str, torch.Tensor],
        available_modalities: list[str],
    ) -> torch.Tensor:
        return self._adapter.encode(signal, available_modalities)

    @_simulate_latency
    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult:
        return self._adapter.predict_hypotension(signal, horizon_min, available_modalities)

    @_simulate_latency
    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult:
        return self._adapter.predict_cardiac_arrest(signal, horizon_min, available_modalities)

    @_simulate_latency
    def assess_signal_quality(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> QualityResult:
        return self._adapter.assess_signal_quality(signal, modality)

    @_simulate_latency
    def cross_modal_consistency(
        self,
        signal: dict[str, torch.Tensor],
        modality_pair: tuple[str, str],
    ) -> ConsistencyResult:
        # adapter expects list — convert tuple for consistency
        # adapter 는 list 를 기대 — tuple → list 변환
        return self._adapter.cross_modal_consistency(signal, list(modality_pair))

    @_simulate_latency
    def temporal_trend(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        window_min: int,
    ) -> TrendResult:
        return self._adapter.temporal_trend(signal, modality, window_min)

    @_simulate_latency
    def forecast_signal(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        horizon_min: int,
    ) -> ForecastResult:
        return self._adapter.forecast_signal(signal, modality, horizon_min)

    @_simulate_latency
    def anomaly_score(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> AnomalyResult:
        return self._adapter.anomaly_score(signal, modality)


__all__ = ["LightMLBiosignalFM"]
