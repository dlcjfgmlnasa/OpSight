"""StubBiosignalFM (Mock FM Tier 1, ADR-011) / Tier 1 stub mock.

============================================================================
⚠️ HARD CAVEAT — DO NOT USE STUB OUTPUT FOR ANY OF THE FOLLOWING:
⚠️ 강제 주의 — 본 stub 출력은 아래 용도로 절대 사용하지 않는다:
----------------------------------------------------------------------------
1. Clinical decisions or any patient-facing recommendation.
   임상 결정 또는 환자 대상 권고 일체.
2. Agent-reasoning validation (e.g. brief faithfulness, risk-trend logic).
   Agent reasoning 검증 (예: 브리프 faithfulness, risk-trend 로직).
3. Latency or accuracy benchmarking against the real FM.
   Real FM 대비 latency / accuracy 벤치마킹.

Use Tier 2 (``mock_rule_based.py``) for agent-reasoning validation, and
the real FM (Stage 2+) for accuracy / latency comparison.
Agent reasoning 검증은 Tier 2 (``mock_rule_based.py``), accuracy / latency
비교는 real FM (Stage 2+)을 사용한다.

Every Result this module returns carries ``meta["mock_tier"] == "stub"`` so
downstream agents and trace consumers can detect (and refuse) stub outputs.
본 module이 반환하는 모든 Result는 ``meta["mock_tier"] == "stub"``을 가져
downstream agent / trace consumer가 stub 출력을 감지·거부할 수 있다.

This tier exists ONLY to:
본 tier의 유일한 용도:
  (a) fix the BiosignalFMInterface contract during Stage 1 development.
      Stage 1 개발 동안 BiosignalFMInterface 계약 고정.
  (b) simulate latency for shallow-loop and dual-mode wiring sanity checks.
      Shallow loop / dual-mode wiring sanity check를 위한 latency 시뮬레이션.
============================================================================

Clinical Fact Guard (``docs/project_brief.md §13.1``): no field returned by
this module asserts a clinical state. Any consumer who renders stub output
to a clinician MUST mark it ``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토
필요]`` or refuse to render entirely.
임상 사실 가드 (``docs/project_brief.md §13.1``): 본 module이 반환하는
어떤 field도 임상 상태를 단정하지 않는다. stub 출력을 임상의에게 렌더링하는
consumer는 반드시 ``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]``
marker를 부착하거나 렌더링 자체를 거부해야 한다.

Latency simulation (C2): configurable per-method sleep with optional jitter.
Sync stance — ``time.sleep`` is used (sprint Step 1 decision #1). LangGraph
nodes that call the FM are sync, so blocking sleep is acceptable here. Future
async-style FM backends can wrap the call site with ``asyncio.to_thread`` if
needed.
Latency 시뮬레이션 (C2): method별 sleep + 선택적 jitter. Sync 입장 채택 —
``time.sleep`` 사용 (sprint Step 1 결정 #1). LangGraph node는 sync이므로
blocking sleep 허용. 미래의 async backend는 호출 사이트에서
``asyncio.to_thread``로 wrap 가능.

Spec: ``docs/fm_interface_guide.md §2``, ADR-011 §"3 tiers".
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable, Literal, TypeVar

import numpy as np
import torch

from vitalagent.fm.result_types import (
    AnomalyResult,
    ArrestResult,
    ConsistencyResult,
    ForecastResult,
    HypotensionResult,
    QualityResult,
    TrendResult,
)

T = TypeVar("T")


def _simulate_latency(method: Callable[..., T]) -> Callable[..., T]:
    """Decorator: sleep before invoking the method per stub config.
    데코레이터: stub config에 따른 latency만큼 sleep 후 method 실행.

    Looks up per-method override or falls back to the global ``latency_sim_sec``.
    method별 override → 없으면 전역 ``latency_sim_sec``로 fallback.
    """

    @wraps(method)
    def wrapper(self: "StubBiosignalFM", *args, **kwargs) -> T:
        self._sleep_for(method.__name__)
        return method(self, *args, **kwargs)

    return wrapper


class StubBiosignalFM:
    """Tier 1 Stub Mock — random output within valid shape / range. **NOT for
    clinical decisions or reasoning validation.** See module docstring.
    Tier 1 Stub Mock — 유효 shape / range 내 random 출력. **임상 결정 /
    reasoning 검증용 X.** module docstring 참조.

    All methods return well-formed Result dataclasses with seedable random
    values. Useful for end-to-end agent loop development before the real FM
    arrives, but NOT for reasoning-level validation.
    모든 method는 seedable random 값으로 well-formed Result dataclass를
    반환한다. real FM 도착 전 end-to-end agent loop 개발에는 유용하지만
    reasoning 수준 검증에는 부적합하다.

    Latency simulation is sync (``time.sleep``). See module docstring.
    Latency 시뮬레이션은 sync (``time.sleep``). module docstring 참조.

    Satisfies :class:`vitalagent.fm.interface.BiosignalFMInterface`.
    :class:`vitalagent.fm.interface.BiosignalFMInterface` Protocol을 만족한다.
    """

    def __init__(
        self,
        seed: int = 42,
        latent_dim: int = 128,
        latency_sim_sec: float = 0.0,
        latency_per_method: dict[str, float] | None = None,
        latency_jitter_pct: float = 0.0,
    ) -> None:
        """Initialize with deterministic seed + latency config.
        결정적 seed + latency 설정으로 초기화한다.

        Args:
            seed: random seed for reproducibility.
                재현성을 위한 random seed.
            latent_dim: dimension of ``encode`` output.
                ``encode`` 출력 차원.
            latency_sim_sec: global default sleep in seconds for every method.
                ``0.0`` (default) → no sleep (fast unit-test mode).
                모든 method의 기본 sleep (초). ``0.0`` (기본)은 sleep 없음 →
                unit test에서 빠르게 실행.
            latency_per_method: per-method sleep overrides. Keys are method
                names (e.g. ``"predict_hypotension"``). Methods absent from
                the dict fall back to ``latency_sim_sec``.
                method별 sleep override. key는 method 이름. dict에 없는
                method는 ``latency_sim_sec``로 fallback.
            latency_jitter_pct: random jitter as a fraction of the base sleep.
                ``0.2`` means ±20% jitter applied per call. Always clipped to
                non-negative sleep.
                base sleep 대비 random jitter 비율. ``0.2``는 매 호출 시
                ±20% jitter 적용. 항상 음수 sleep으로 clip되지 않음.
        """
        self._seed = seed
        self._latent_dim = latent_dim
        self._np_rng = np.random.default_rng(seed)
        self._torch_gen = torch.Generator()
        self._torch_gen.manual_seed(seed)
        # Latency config / latency 설정
        self._latency_sim_sec = float(latency_sim_sec)
        self._latency_per_method: dict[str, float] = dict(latency_per_method or {})
        self._latency_jitter_pct = float(latency_jitter_pct)

    # ── Latency helper / latency 헬퍼 ──

    def _sleep_for(self, method_name: str) -> None:
        """Sleep for the configured latency of ``method_name``.
        ``method_name``의 설정된 latency만큼 sleep한다.

        Resolves base latency from per-method override or the global default,
        applies jitter, and calls ``time.sleep`` if positive.
        per-method override → 없으면 전역 default → jitter 적용 → 양수면
        ``time.sleep`` 호출.
        """
        base = self._latency_per_method.get(method_name, self._latency_sim_sec)
        if base <= 0:
            return
        if self._latency_jitter_pct > 0:
            jitter_amplitude = base * self._latency_jitter_pct
            base = base + float(self._np_rng.uniform(-jitter_amplitude, jitter_amplitude))
            base = max(0.0, base)
        if base > 0:
            time.sleep(base)

    # ── 8 Protocol methods / 8 Protocol 메서드 ──

    @_simulate_latency
    def encode(
        self,
        signal: dict[str, torch.Tensor],
        available_modalities: list[str],
    ) -> torch.Tensor:
        """Random latent vector of shape ``(latent_dim,)``.
        Shape ``(latent_dim,)``의 random latent 벡터를 반환한다.
        """
        return torch.randn(self._latent_dim, generator=self._torch_gen)

    @_simulate_latency
    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult:
        """Random risk in [0, 1], uncertainty in [0, 0.5] (tool 1 backend).
        [0, 1] 범위의 random risk, [0, 0.5] 범위의 uncertainty (tool 1 백엔드).
        """
        return HypotensionResult(
            risk=float(self._np_rng.uniform(0.0, 1.0)),
            uncertainty=float(self._np_rng.uniform(0.0, 0.5)),
            horizon_min=horizon_min,
            meta={"mock_tier": "stub", "available_modalities": list(available_modalities)},
        )

    @_simulate_latency
    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult:
        """Random low risk in [0, 0.2] (cardiac arrest is rare) (tool 2 backend).
        [0, 0.2] 범위의 낮은 risk (cardiac arrest는 rare event) (tool 2 백엔드).
        """
        return ArrestResult(
            risk=float(self._np_rng.uniform(0.0, 0.2)),
            uncertainty=float(self._np_rng.uniform(0.0, 0.5)),
            horizon_min=horizon_min,
            meta={"mock_tier": "stub", "available_modalities": list(available_modalities)},
        )

    @_simulate_latency
    def assess_signal_quality(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> QualityResult:
        """Random quality in [0, 1] with ``reason`` if low (tool 3 backend).
        [0, 1] 범위의 random quality. score 낮을 때 ``reason`` 포함 (tool 3 백엔드).
        """
        score = float(self._np_rng.uniform(0.0, 1.0))
        reason = None if score >= 0.5 else "stub-random low quality"
        return QualityResult(
            score=score,
            reason=reason,
            meta={"mock_tier": "stub", "modality": modality},
        )

    @_simulate_latency
    def cross_modal_consistency(
        self,
        signal: dict[str, torch.Tensor],
        modality_pair: tuple[str, str],
    ) -> ConsistencyResult:
        """Random consistency in [0, 1] (tool 4 backend).
        [0, 1] 범위의 random consistency (tool 4 백엔드).
        """
        return ConsistencyResult(
            score=float(self._np_rng.uniform(0.0, 1.0)),
            reason=None,
            meta={"mock_tier": "stub", "modality_pair": list(modality_pair)},
        )

    @_simulate_latency
    def temporal_trend(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        window_min: int,
    ) -> TrendResult:
        """Random slope in [-5, 5]; label derived from slope (tool 5 backend).
        [-5, 5] 범위의 random slope; label은 slope로부터 유도 (tool 5 백엔드).

        Label rule / Label 규칙:
        - ``|slope| < 1``  → ``"stable"``
        - ``slope ≥ 1``    → ``"rising"``
        - ``slope ≤ -1``   → ``"falling"``
        """
        slope = float(self._np_rng.uniform(-5.0, 5.0))
        label: Literal["rising", "falling", "stable"]
        if abs(slope) < 1.0:
            label = "stable"
        elif slope > 0:
            label = "rising"
        else:
            label = "falling"
        return TrendResult(
            slope=slope,
            magnitude=abs(slope),
            label=label,
            meta={"mock_tier": "stub", "modality": modality, "window_min": window_min},
        )

    @_simulate_latency
    def forecast_signal(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        horizon_min: int,
    ) -> ForecastResult:
        """Random forecast trajectory, 1 sample per minute (tool 6 backend).
        분당 1 sample의 random forecast trajectory를 반환한다 (tool 6 백엔드).

        Sample rate is 1 sample/min (stub simplification). ``meta`` records the rate.
        Sample rate는 1 sample/min (stub 단순화). ``meta``에 sample rate 기록.
        Forecast values in [50, 120] (rough physiological range proxy).
        Forecast 값은 [50, 120] 범위 (대략의 생리학적 범위 proxy).
        """
        forecast = self._np_rng.uniform(50.0, 120.0, size=horizon_min).tolist()
        uncertainty = self._np_rng.uniform(2.0, 10.0, size=horizon_min).tolist()
        return ForecastResult(
            forecast=forecast,
            uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={
                "mock_tier": "stub",
                "modality": modality,
                "sampling_rate_hz": 1.0 / 60.0,  # 1 sample / min
            },
        )

    @_simulate_latency
    def anomaly_score(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> AnomalyResult:
        """Random anomaly score in [0, 1] (tool 7 backend).
        [0, 1] 범위의 random anomaly score (tool 7 백엔드).
        """
        return AnomalyResult(
            score=float(self._np_rng.uniform(0.0, 1.0)),
            meta={"mock_tier": "stub", "modality": modality},
        )


__all__ = ["StubBiosignalFM"]
