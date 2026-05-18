"""Per-modality SignalConfig (preprocessing).
Modality 별 SignalConfig (전처리).

Reference / 참조: BFM `data/parser/vitaldb.py::SignalConfig`. 본 module 은
clinical context 에 필요한 *minimum* field 만 포팅 — physiological range,
expected sampling rate, NaN-gap interpolation 정책.

⚠️ 모든 physiological range / 임계 는 lit-standard heuristic 이며 임상의
검토 대상: ``[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SignalConfig:
    """Per-modality preprocessing config.
    Modality 별 전처리 config.

    Range 외 sample 은 NaN 으로 mask. ``max_nan_gap_s`` 내 NaN 구간은 선형
    interpolation 으로 fill.
    Out-of-range samples are masked to NaN. NaN gaps shorter than
    ``max_nan_gap_s`` are filled by linear interpolation.
    """

    name: str
    """Display name (e.g. "ABP") / 표시명."""

    physiological_min: float
    """Plausible minimum (below → artifact, mask NaN)."""

    physiological_max: float
    """Plausible maximum (above → artifact, mask NaN)."""

    typical_sampling_rate_hz: float
    """Native sampling rate as documented in `docs/vitaldb_catalog.md`.
    `docs/vitaldb_catalog.md` 의 native rate.
    """

    unit: str = ""
    """Unit string (e.g. "mmHg", "bpm")."""

    max_nan_gap_s: float = 1.0
    """Maximum NaN-gap to linearly interpolate (longer → keep as NaN).
    선형 interpolation 으로 채울 최대 NaN-gap (초). 더 긴 gap 은 NaN 유지.
    """

    flatline_std_threshold: float = 1e-3
    """Std below this within a window → considered flatline.
    Window 안 std 가 본 임계 미만 → flatline 판정.
    """

    clinical_review_required: bool = True
    """All clinical range thresholds require clinician review.
    모든 임상 range 임계는 임상의 검토 필요.
    """

    extra: dict[str, Any] = field(default_factory=dict)


# ── Per-modality registry / Modality 별 registry ──
# Reference: BFM SignalConfig (vitaldb.py) + brief §4, docs/vitaldb_catalog.md §3.
# [CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — 본 range 들.

SIGNAL_CONFIGS: dict[str, SignalConfig] = {
    # ABP family — all MAP/SBP/DBP fall in similar range
    "ABP": SignalConfig(
        name="ABP",
        physiological_min=20.0,
        physiological_max=250.0,
        typical_sampling_rate_hz=500.0,  # SNUADC native
        unit="mmHg",
        max_nan_gap_s=1.0,
    ),
    "MAP": SignalConfig(
        name="MAP",
        physiological_min=20.0,
        physiological_max=200.0,
        typical_sampling_rate_hz=1.0,  # Solar8000/ART_MBP native
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    "SBP": SignalConfig(
        name="SBP",
        physiological_min=40.0,
        physiological_max=250.0,
        typical_sampling_rate_hz=1.0,
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    "DBP": SignalConfig(
        name="DBP",
        physiological_min=20.0,
        physiological_max=150.0,
        typical_sampling_rate_hz=1.0,
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    # NIBP — wider tolerance + sparser sampling (cuff)
    "Solar8000/NIBP_MBP": SignalConfig(
        name="NIBP_MBP",
        physiological_min=30.0,
        physiological_max=220.0,
        typical_sampling_rate_hz=1.0,  # native; effective ~1/5 min cuff
        unit="mmHg",
        max_nan_gap_s=600.0,  # cuff measurement gaps are normal
    ),
    # HR family
    "HR": SignalConfig(
        name="HR",
        physiological_min=20.0,
        physiological_max=250.0,
        typical_sampling_rate_hz=1.0,  # Solar8000/HR
        unit="bpm",
        max_nan_gap_s=2.0,
    ),
    # PPG (unitless)
    "PPG": SignalConfig(
        name="PPG",
        physiological_min=-5000.0,  # SNUADC raw ADC range
        physiological_max=5000.0,
        typical_sampling_rate_hz=500.0,
        unit="adc",
        max_nan_gap_s=0.5,
    ),
    # ECG (mV)
    "ECG_II": SignalConfig(
        name="ECG_II",
        physiological_min=-5.0,
        physiological_max=5.0,
        typical_sampling_rate_hz=500.0,
        unit="mV",
        max_nan_gap_s=0.5,
    ),
    # SpO2 (%)
    "SpO2": SignalConfig(
        name="SpO2",
        physiological_min=50.0,
        physiological_max=100.0,
        typical_sampling_rate_hz=1.0,
        unit="%",
        max_nan_gap_s=2.0,
    ),
    # EtCO2 (mmHg)
    "EtCO2": SignalConfig(
        name="EtCO2",
        physiological_min=0.0,
        physiological_max=80.0,
        typical_sampling_rate_hz=1.0,
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    # BIS (0–100)
    "BIS": SignalConfig(
        name="BIS",
        physiological_min=0.0,
        physiological_max=100.0,
        typical_sampling_rate_hz=1.0,
        unit="",
        max_nan_gap_s=5.0,
    ),
    # Core temperature
    "BT": SignalConfig(
        name="BT",
        physiological_min=30.0,
        physiological_max=42.0,
        typical_sampling_rate_hz=1.0,
        unit="°C",
        max_nan_gap_s=30.0,
    ),
}


# Modality alias → canonical config key
# Aliases mirror `vitalagent/fm/mock_rule_based.py::_*_ALIASES` for consistent lookup.
_ALIAS_MAP: dict[str, str] = {
    # ABP family
    "SNUADC/ART": "ABP",
    "Solar8000/ART_MBP": "MAP",
    "EV1000/ART_MBP": "MAP",
    "Solar8000/FEM_MBP": "MAP",
    "Solar8000/ART_SBP": "SBP",
    "Solar8000/NIBP_SBP": "SBP",
    "Solar8000/ART_DBP": "DBP",
    "Solar8000/NIBP_DBP": "DBP",
    # HR
    "Solar8000/HR": "HR",
    "Solar8000/PLETH_HR": "HR",
    # PPG
    "SNUADC/PLETH": "PPG",
    # ECG
    "ECG": "ECG_II",
    "SNUADC/ECG_II": "ECG_II",
    # SpO2
    "SPO2": "SpO2",
    "Solar8000/PLETH_SPO2": "SpO2",
    # EtCO2
    "ETCO2": "EtCO2",
    "Solar8000/ETCO2": "EtCO2",
    "Primus/ETCO2": "EtCO2",
    # BIS
    "BIS/BIS": "BIS",
    # Temperature
    "Solar8000/BT": "BT",
    "core_temp": "BT",
    "TEMP": "BT",
}


def config_for_modality(modality_name: str) -> SignalConfig | None:
    """Look up SignalConfig by modality alias.
    Modality alias 로 SignalConfig 조회.

    Returns ``None`` for unknown modalities (preprocessing pipeline 은
    이 경우 해당 modality 를 *건드리지 않음* — skip).
    Returns ``None`` for unknown modalities (pipeline skips them).
    """
    if modality_name in SIGNAL_CONFIGS:
        return SIGNAL_CONFIGS[modality_name]
    canonical = _ALIAS_MAP.get(modality_name)
    if canonical is not None:
        return SIGNAL_CONFIGS[canonical]
    return None


__all__ = ["SignalConfig", "SIGNAL_CONFIGS", "config_for_modality"]
