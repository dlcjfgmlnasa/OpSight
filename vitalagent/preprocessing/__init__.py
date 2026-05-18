"""Signal preprocessing module (Sprint 5 follow-up, real_case_run_findings Issue 1/4/8).
신호 전처리 module (Sprint 5 follow-up, real_case_run_findings Issue 1/4/8).

Real VitalDB 데이터로 dual-mode graph 를 돌릴 때 발견된 한계 (sensor artifact,
NaN ratio, modality fallback) 를 다룬다.

Reference / 참조:
    Biosignal-Foundation-Model `data/parser/{_common.py,_quality_checks.py,vitaldb.py}`.
    https://github.com/dlcjfgmlnasa/Biosignal-Foundation-Model
    본 module 은 BFM 의 `SignalConfig` + artifact-removal pipeline 패턴 *최소 subset*
    포팅. Filter / notch / peak detection 등 heavy 부분은 제외 — agent 단계의
    prototype 목적상 *physiological clipping + NaN-aware* 만 필요.

Reference: BFM preprocessing pipeline (SignalConfig, range clipping, NaN-gap
interpolation). VitalAgent ports the *minimum subset* that addresses real_case
findings; filtering / peak detection are out of scope (covered by FM tools).
"""
from __future__ import annotations

from vitalagent.preprocessing.artifact import (
    clip_to_physiological,
    fill_short_nan_gaps,
)
from vitalagent.preprocessing.pipeline import (
    PreprocessReport,
    preprocess_signal_dict,
)
from vitalagent.preprocessing.sampling import (
    detect_sampling_rate,
    resample_numpy,
)
from vitalagent.preprocessing.signal_config import (
    SIGNAL_CONFIGS,
    SignalConfig,
    config_for_modality,
)

__all__ = [
    # signal_config
    "SignalConfig",
    "SIGNAL_CONFIGS",
    "config_for_modality",
    # artifact
    "clip_to_physiological",
    "fill_short_nan_gaps",
    # sampling
    "detect_sampling_rate",
    "resample_numpy",
    # pipeline
    "preprocess_signal_dict",
    "PreprocessReport",
]
