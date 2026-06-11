"""Per-modality SignalConfig (preprocessing).
Modality 별 SignalConfig (전처리).

Reference / 참조: BFM `data/parser/vitaldb.py::SignalConfig`. 본 module 은
clinical context 에 필요한 *minimum* field 만 포팅 — physiological range,
expected sampling rate, NaN-gap interpolation 정책.

⚠️ 모든 physiological range / 임계 는 lit-standard heuristic 이며 임상의
검토 대상: ``[CLINICIAN-REVIEW: 의료진 검토 필요]``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SignalConfig:
    """Per-modality preprocessing config.
    Modality 별 전처리 config.

    Range 외 sample 은 NaN 으로 mask. ``max_nan_gap_s`` 내 NaN 구간은 선형
    interpolation 으로 fill. Waveform modality 는 `target_sampling_rate_hz` 로
    resample 되어 backend (BFM) 가 *uniform 100 Hz* signal 을 받는다.
    Out-of-range samples → NaN mask. NaN gaps shorter than ``max_nan_gap_s``
    → linear interpolation. Waveform modalities are resampled to
    ``target_sampling_rate_hz`` so the backend (BFM) receives uniform 100 Hz.
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

    is_waveform: bool = False
    """True for waveform modalities (ABP/ECG/PPG/EEG/CO2/AWP). False for numerics
    (HR/SpO2/EtCO2/BIS/BT/MAP). Determines whether resampling to BFM's 100 Hz
    target applies.

    Waveform modality (ABP/ECG/PPG/EEG/CO2/AWP) 는 True. Numeric (HR/SpO2/
    EtCO2/BIS/BT/MAP) 은 False. BFM 의 100 Hz target 으로 resample 할지 결정.
    """

    target_sampling_rate_hz: float = 100.0
    """BFM standard target rate (waveform only).
    BFM 표준 target rate (waveform 만 적용).

    Reference: Biosignal-Foundation-Model `data/parser/vitaldb.py` — "All
    waveforms resampled from native rate (500 Hz SNUADC, 62.5 Hz Primus,
    etc.) to uniform 100 Hz target". Numerics 는 native rate 그대로 사용.
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
# [CLINICIAN-REVIEW: 의료진 검토 필요] — 본 range 들.

SIGNAL_CONFIGS: dict[str, SignalConfig] = {
    # ABP family — all MAP/SBP/DBP fall in similar range
    "ABP": SignalConfig(
        name="ABP",
        physiological_min=20.0,
        physiological_max=250.0,
        typical_sampling_rate_hz=500.0,  # SNUADC native
        is_waveform=True,  # → resample to 100 Hz (BFM target)
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
    # CVP family — central venous pressure (filling pressure proxy).
    # brief §1: 6 pretraining modality 중 하나. VitalDB 가용성 ~25%.
    # [CLINICIAN-REVIEW: 의료진 검토 필요] — physiological_min/max,
    # 호흡 swing 처리 정책.
    "CVP": SignalConfig(
        name="CVP",
        physiological_min=-15.0,
        physiological_max=50.0,  # generous, allows respiratory swing + cough artifact
        typical_sampling_rate_hz=500.0,  # SNUADC native
        is_waveform=True,  # → 100 Hz resample
        unit="mmHg",
        max_nan_gap_s=1.0,
    ),
    "CVP_MEAN": SignalConfig(
        name="CVP_MEAN",
        physiological_min=-5.0,
        physiological_max=30.0,  # normal 0–15; tamponade / cor pulmonale 시 상승
        typical_sampling_rate_hz=1.0,  # Solar8000/CVP, EV1000/CVP
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    # PAP family — pulmonary artery pressure (Swan-Ganz catheter).
    # brief §1: 6 pretraining modality 중 하나. VitalDB 가용성 ~1.3% (수술 종류 제한).
    # [CLINICIAN-REVIEW: 의료진 검토 필요] — pulmonary HTN range.
    "PAP_MBP": SignalConfig(
        name="PAP_MBP",
        physiological_min=5.0,
        physiological_max=60.0,  # normal ~15; severe pulmonary HTN > 40
        typical_sampling_rate_hz=1.0,
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    "PAP_SBP": SignalConfig(
        name="PAP_SBP",
        physiological_min=10.0,
        physiological_max=90.0,  # normal ~25; severe pulm HTN > 60
        typical_sampling_rate_hz=1.0,
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    "PAP_DBP": SignalConfig(
        name="PAP_DBP",
        physiological_min=0.0,
        physiological_max=50.0,
        typical_sampling_rate_hz=1.0,
        unit="mmHg",
        max_nan_gap_s=2.0,
    ),
    # NIBP — wider tolerance + sparser sampling (cuff)
    "NIBP_MBP": SignalConfig(
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
    # PPG (unitless) — waveform
    "PPG": SignalConfig(
        name="PPG",
        physiological_min=-5000.0,  # SNUADC raw ADC range
        physiological_max=5000.0,
        typical_sampling_rate_hz=500.0,
        is_waveform=True,  # → 100 Hz
        unit="adc",
        max_nan_gap_s=0.5,
    ),
    # ECG (mV) — waveform
    "ECG_II": SignalConfig(
        name="ECG_II",
        physiological_min=-5.0,
        physiological_max=5.0,
        typical_sampling_rate_hz=500.0,
        is_waveform=True,  # → 100 Hz
        unit="mV",
        max_nan_gap_s=0.5,
    ),
    # EEG (μV) — BIS/EEG1_WAV native 128 Hz — waveform
    "EEG": SignalConfig(
        name="EEG",
        physiological_min=-500.0,
        physiological_max=500.0,
        typical_sampling_rate_hz=128.0,
        is_waveform=True,  # → 100 Hz
        unit="uV",
        max_nan_gap_s=0.5,
    ),
    # Capnography (CO2 waveform) — Primus/CO2 native 62.5 Hz — waveform
    "CO2_WAV": SignalConfig(
        name="CO2_WAV",
        physiological_min=0.0,
        physiological_max=80.0,
        typical_sampling_rate_hz=62.5,
        is_waveform=True,  # → 100 Hz
        unit="mmHg",
        max_nan_gap_s=1.0,
    ),
    # Airway pressure — Primus/AWP native 62.5 Hz — waveform
    "AWP": SignalConfig(
        name="AWP",
        physiological_min=-10.0,
        physiological_max=80.0,
        typical_sampling_rate_hz=62.5,
        is_waveform=True,  # → 100 Hz
        unit="cmH2O",
        max_nan_gap_s=1.0,
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
    # BIS (1–100)
    # NB: physiological_min = 1.0 (not 0). BIS = 0 in raw VitalDB indicates
    # the sensor was not yet attached (or detached) — it is a sentinel, not a
    # real measurement (BIS 0 in a living patient means deep coma / EEG
    # isoelectric, a perioperative impossibility outside of brain-death exams).
    # Filtering 0 → NaN prevents the live view from showing a fake BIS reading
    # of 0 during sensor-induction phase (see case 13 BIS=0 → 92 jump).
    # BIS=0 은 raw VitalDB 에서 센서 미부착 sentinel. 살아있는 환자에 BIS=0
    # 은 임상적으로 불가능 (뇌사 검사 외). 0 → NaN 처리로 induction phase 의
    # 가짜 0 reading 차단 (case 13 BIS=0 → 92 점프 참조).
    "BIS": SignalConfig(
        name="BIS",
        physiological_min=1.0,
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
# Aliases mirror `opsight/fm/mock_rule_based.py::_*_ALIASES` for consistent lookup.
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
    # CVP family — waveform vs numeric routed to distinct configs.
    "SNUADC/CVP": "CVP",
    "Solar8000/CVP": "CVP_MEAN",
    "EV1000/CVP": "CVP_MEAN",
    # PAP family (Solar8000 only — Swan-Ganz numerics)
    "Solar8000/PA_MBP": "PAP_MBP",
    "Solar8000/PA_SBP": "PAP_SBP",
    "Solar8000/PA_DBP": "PAP_DBP",
    # HR
    "Solar8000/HR": "HR",
    "Solar8000/PLETH_HR": "HR",
    # PPG
    "SNUADC/PLETH": "PPG",
    # ECG
    "ECG_I": "ECG_II",  # close enough range
    "SNUADC/ECG_II": "ECG_II",
    "SNUADC/ECG_V5": "ECG_II",
    # EEG (BIS)
    "BIS/EEG1_WAV": "EEG",
    "BIS/EEG2_WAV": "EEG",
    # CO2 waveform — both short and canonical aliases route to CO2_WAV config.
    # CO2 waveform — 짧은 alias / 정식 이름 모두 CO2_WAV config 로 라우팅.
    "CO2": "CO2_WAV",
    "Primus/CO2": "CO2_WAV",
    # Airway pressure
    "Primus/AWP": "AWP",
    # Live-view aliases (scripts/live_view.py TRACK_TO_ALIAS) that map to
    # canonical configs above. Without these the preprocessing pipeline would
    # skip those modalities entirely (see preprocess_audit.py findings).
    # live_view 의 alias 를 canonical config 로 매핑. 없으면 전처리 skip 됨.
    "ECG": "ECG_II",
    "Solar8000/NIBP_MBP": "NIBP_MBP",
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
