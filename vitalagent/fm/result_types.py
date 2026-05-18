"""FM Result dataclasses (ADR-011) / FM Result 데이터클래스.

Field semantics: ``docs/fm_interface_guide.md §1``.
Field 의미는 가이드 §1 참조.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class HypotensionResult:
    """Tool 1 ``predict_hypotension`` output / Tool 1 출력."""

    risk: float
    uncertainty: float
    horizon_min: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArrestResult:
    """Tool 2 ``predict_cardiac_arrest`` output / Tool 2 출력."""

    risk: float
    uncertainty: float
    horizon_min: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityResult:
    """Tool 3 ``assess_signal_quality`` output / Tool 3 출력."""

    score: float
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsistencyResult:
    """Tool 4 ``cross_modal_consistency`` output / Tool 4 출력."""

    score: float
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrendResult:
    """Tool 5 ``temporal_trend_analysis`` output / Tool 5 출력."""

    slope: float
    magnitude: float
    label: Literal["rising", "falling", "stable"]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ForecastResult:
    """Tool 6 ``forecast_signal`` output / Tool 6 출력."""

    forecast: list[float]
    uncertainty: list[float]
    horizon_min: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnomalyResult:
    """Tool 7 ``anomaly_score`` output / Tool 7 출력."""

    score: float
    meta: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "HypotensionResult",
    "ArrestResult",
    "QualityResult",
    "ConsistencyResult",
    "TrendResult",
    "ForecastResult",
    "AnomalyResult",
]
