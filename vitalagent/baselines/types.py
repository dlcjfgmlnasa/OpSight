"""Baseline interface types (plan_1.4 task 8).
Baseline 인터페이스 type (plan_1.4 task 8).

공통 ``BaselinePredictor`` Protocol 을 통해 4 baseline 이 같은 surface 를
제공하도록 강제한다. 본 surface 는 ``BaselineFMAdapter`` 에 의해
``BiosignalFMInterface`` 로 wrap 되어 plan_1.7.5 Tier 3 Mock FM 으로 사용된다.

Shared ``BaselinePredictor`` Protocol forces all 4 baselines to expose the
same surface, which ``BaselineFMAdapter`` then wraps as
``BiosignalFMInterface`` (plan_1.7.5 Tier 3 Mock FM).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    import torch


@dataclass(frozen=True)
class BaselineResult:
    """Single prediction output / 단일 예측 출력.

    Shared by all baselines to maintain a stable wrap surface.
    모든 baseline 이 공유하여 wrap surface 를 안정 유지.
    """

    risk: float
    """Hypotension probability in [0, 1] / 저혈압 확률 (0–1)."""

    uncertainty: float
    """Prediction uncertainty in [0, 1] / 예측 불확실성 (0–1).

    For models that don't natively output uncertainty (logreg / xgb), this is
    approximated via calibration distance from 0.5 or via MC-dropout (LSTM).
    Native uncertainty 가 없는 모델 (logreg / xgb) 은 0.5 기준 거리 또는
    MC-dropout (LSTM) 로 근사.
    """

    horizon_min: int
    """Prediction horizon in minutes / 예측 horizon (분)."""

    meta: dict[str, Any] = field(default_factory=dict)
    """Per-baseline diagnostic info (model_name, n_features, etc.).
    Baseline 별 진단 정보 (model_name, n_features 등).
    """


@dataclass(frozen=True)
class BaselineConfig:
    """Training-time + inference-time config / 학습/추론 공통 config.

    Concrete baselines may subclass via composition, but this base provides
    the fields used by the FM adapter.
    Concrete baseline 은 composition 으로 확장 가능; 본 base 는 FM adapter
    가 사용하는 field 만 정의.
    """

    name: str
    """Baseline name (e.g., 'logreg_abp') / Baseline 이름."""

    horizon_min: int = 5
    """Prediction horizon in minutes / 예측 horizon (분)."""

    feature_window_min: int = 5
    """Input feature window in minutes / 입력 feature window (분)."""

    sampling_rate_hz: float = 500.0
    """Waveform sampling rate / Waveform sampling rate."""

    label_threshold_mmhg: float = 65.0
    """Hypotension threshold (MAP < this) / 저혈압 임계 (MAP < this)."""

    label_min_duration_s: float = 60.0
    """Sustained duration to count as event / event 인정 지속 시간."""

    checkpoint_path: str | None = None
    """Optional saved-model path / 선택적 저장 모델 경로."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Baseline-specific overrides / Baseline 별 override."""


@runtime_checkable
class BaselinePredictor(Protocol):
    """Common predictor surface across the 4 baselines.
    4 baseline 공통 predictor surface.

    The 3 required methods:
    필수 method 3 가지:
    - ``fit(X, y)``  — train on features + labels
    - ``predict(signal_dict, horizon_min, available_modalities)`` —
      single-sample inference returning a ``BaselineResult``
    - ``save(path)`` / ``load(path)`` — checkpoint persistence
    """

    name: str
    """Baseline name accessible without calling / 호출 없이 접근 가능."""

    config: BaselineConfig

    def fit(self, X: Any, y: Any) -> None:
        """Train on (features, labels). Shape varies per baseline.
        (feature, label) 로 학습. shape 는 baseline 별 상이.
        """
        ...

    def predict(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> BaselineResult:
        """Single-case inference returning a ``BaselineResult``.
        단일 case 추론, ``BaselineResult`` 반환.

        Same call signature as ``BiosignalFMInterface.predict_hypotension`` so
        the FM adapter can route directly.
        ``BiosignalFMInterface.predict_hypotension`` 과 동일 signature —
        FM adapter 가 그대로 routing.
        """
        ...

    def save(self, path: str) -> None:
        """Save trained model to ``path`` / 학습된 모델을 ``path`` 에 저장."""
        ...

    def load(self, path: str) -> None:
        """Load saved model from ``path`` / 저장된 모델을 ``path`` 에서 load."""
        ...


# ── Status taxonomy / 상태 분류 ──

BaselineStatus = Literal["untrained", "trained", "loaded"]


__all__ = [
    "BaselineResult",
    "BaselineConfig",
    "BaselinePredictor",
    "BaselineStatus",
]
