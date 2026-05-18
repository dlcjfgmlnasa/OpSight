"""BiosignalFMInterface Protocol (ADR-011) / BiosignalFMInterface 프로토콜.

This Protocol defines the 8-method contract that all FM tiers (Tier 1 stub,
Tier 2 rule-based, Tier 3 light ML, real FM adapter) MUST satisfy.
본 Protocol은 모든 FM tier (Tier 1 stub / Tier 2 rule-based / Tier 3 light
ML / real FM adapter)가 반드시 구현해야 하는 8-method 계약을 정의한다.

Agent and tool layers depend ONLY on this Protocol, never on concrete
classes. Changes to this Protocol require ADR-011 amendment.
Agent / tool layer는 본 Protocol에만 의존하며 concrete class에 의존하지
않는다. 본 Protocol 변경은 ADR-011 개정을 필요로 한다.

Spec: ``docs/fm_interface_guide.md §2``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    # ``torch`` is only needed at type-check time. ``from __future__ import
    # annotations`` makes every annotation a string, so importing torch at
    # runtime is unnecessary for the Protocol itself; concrete FM implementations
    # import it directly.
    # ``torch``는 type-check 시점에만 필요하다. ``from __future__ import
    # annotations``가 모든 annotation을 string으로 만들기 때문에 Protocol 자체는
    # runtime에 torch를 import할 필요가 없다. concrete FM 구현체는 각자 torch를
    # 직접 import한다.
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


@runtime_checkable
class BiosignalFMInterface(Protocol):
    """Foundation Model backend contract / Foundation Model 백엔드 계약.

    Implementations are selected via :func:`vitalagent.fm.factory.create_fm`
    based on a configuration string (``mock_stub`` / ``mock_rule_based`` /
    ``mock_light_ml`` / ``real``). Swap is a config change, not a code change.
    구현체는 ``mock_stub`` / ``mock_rule_based`` / ``mock_light_ml`` / ``real``
    중 하나를 가리키는 config 문자열로 :func:`vitalagent.fm.factory.create_fm`
    에서 선택된다. Swap은 코드 변경이 아닌 config 변경이다.
    """

    def encode(
        self,
        signal: dict[str, torch.Tensor],
        available_modalities: list[str],
    ) -> torch.Tensor:
        """Encode multi-modal signal into a latent representation.
        다중 modality 신호를 latent representation으로 인코딩한다.

        Returns a raw ``torch.Tensor`` (NOT wrapped in a Result dataclass —
        per ADR-011).
        Raw ``torch.Tensor``를 반환한다 (ADR-011에 따라 Result dataclass로
        wrap하지 않는다).
        """
        ...

    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult:
        """Predict hypotension risk within ``horizon_min`` minutes (tool 1).
        ``horizon_min``분 이내 저혈압 (hypotension) 위험도를 예측한다 (tool 1).

        Backend for tool 1 ``predict_hypotension``. Output shape: see guide §1.2.
        Tool 1 ``predict_hypotension``의 백엔드. 출력 구조: 가이드 §1.2 참조.
        """
        ...

    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult:
        """Predict cardiac arrest risk within ``horizon_min`` minutes (tool 2).
        ``horizon_min``분 이내 심정지 (cardiac arrest) 위험도를 예측한다 (tool 2).
        """
        ...

    def assess_signal_quality(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> QualityResult:
        """Assess signal quality for a single modality (tool 3).
        단일 modality의 신호 품질을 평가한다 (tool 3).
        """
        ...

    def cross_modal_consistency(
        self,
        signal: dict[str, torch.Tensor],
        modality_pair: tuple[str, str],
    ) -> ConsistencyResult:
        """Score cross-modal consistency for a modality pair (tool 4).
        Modality 쌍 간 cross-modal 일관성 score를 계산한다 (tool 4).
        """
        ...

    def temporal_trend(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        window_min: int,
    ) -> TrendResult:
        """Compute temporal trend over a ``window_min``-minute window (tool 5).
        ``window_min``분 window에서 시간적 trend를 산출한다 (tool 5).
        """
        ...

    def forecast_signal(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        horizon_min: int,
    ) -> ForecastResult:
        """Forecast modality trajectory ``horizon_min`` minutes ahead (tool 6).
        ``horizon_min``분 후까지의 modality 신호 trajectory를 예측한다 (tool 6).
        """
        ...

    def anomaly_score(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> AnomalyResult:
        """Compute anomaly score for a modality window (tool 7).
        Modality window에 대한 anomaly score를 계산한다 (tool 7).
        """
        ...


__all__ = ["BiosignalFMInterface"]
