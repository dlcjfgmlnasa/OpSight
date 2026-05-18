"""Signal Access tool Result dataclasses (plan_1.3.5).
Signal Access tool 의 Result dataclass (plan_1.3.5).

5 frozen dataclass — ADR-016 Signal Access 카테고리 (tool 17–21).
`vitalagent/fm/result_types.py` 와 분리: FM Interface 무관함을 코드 layout 으로
명시 (ADR-011 swap mechanism 영향 없음).

5 frozen dataclasses — ADR-016 Signal Access category (tools 17–21).
Separate from ``vitalagent/fm/result_types.py`` to make their FM-Interface
independence explicit in code layout (ADR-011 swap mechanism preserved).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class CurrentVitalsResult:
    """Tool 17 ``get_current_vitals`` output / Tool 17 출력.

    9 vital fields; absent values are ``None`` (not NaN).
    9 vital field; 부재 시 ``None`` (NaN 아님).
    """

    map_mmHg: float | None
    sbp_mmHg: float | None
    dbp_mmHg: float | None
    hr_bpm: float | None
    rr_per_min: float | None
    spo2_pct: float | None
    etco2_mmHg: float | None
    bis: float | None
    core_temp_c: float | None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalDescription:
    """Tool 18 ``describe_signal`` output / Tool 18 출력.

    NaN-safe statistics. If ``missing_ratio == 1.0`` all stats are ``None``.
    NaN-safe 통계. ``missing_ratio == 1.0`` 시 모든 통계는 ``None``.
    """

    mean: float | None
    std: float | None
    min: float | None
    max: float | None
    median: float | None
    iqr: float | None
    missing_ratio: float
    n_samples: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VariabilityResult:
    """Tool 19 ``assess_variability`` output / Tool 19 출력.

    Metrics dict shape depends on modality:
    - HR: ``{"SDNN_ms", "RMSSD_ms", "LF_HF_ratio"}``
    - MAP/ABP: ``{"SD_mmHg", "ARV_mmHg"}``
    - PPG: ``{"amplitude_var", "SVV_pct"}``

    metric dict shape 는 modality 별 상이.
    """

    metrics: dict[str, float | None]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BaselineComparison:
    """Tool 20 ``compare_to_baseline`` output / Tool 20 출력.

    ``baseline_value`` 부재 시 (preop + intraop early 둘 다 없음) ``None``;
    이 경우 ``meta.baseline_source == "none"``.
    When ``baseline_value`` is absent (no preop / no intraop early) it is
    ``None``; ``meta.baseline_source == "none"`` is also set.
    """

    baseline_value: float | None
    current_value: float
    absolute_change: float | None
    percent_change: float | None
    direction: Literal["up", "down", "stable", "unknown"]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StateSynthesis:
    """Tool 21 ``summarize_current_state`` output / Tool 21 출력.

    ⚠️ **Phrasing 강제 정책** (ADR-016 § "Clinical Fact Guard"):
    - ``overall_assessment`` 는 conditional phrasing 만 ("X 가능성을 시사함")
    - 단정형 금지 ("X 이다")
    - Dose 권고 절대 금지
    - ``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`` marker 끝에 *반드시* 부착

    ⚠️ Phrasing enforcement (ADR-016 §Clinical Fact Guard):
    - ``overall_assessment`` uses conditional phrasing only
    - No diagnostic assertions, no dose recommendations
    - ``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`` marker MANDATORY at end
    """

    hemodynamic_state: str
    anesthesia_state: str
    respiratory_state: str
    key_concerns: list[str]
    overall_assessment: str
    meta: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "CurrentVitalsResult",
    "SignalDescription",
    "VariabilityResult",
    "BaselineComparison",
    "StateSynthesis",
]
