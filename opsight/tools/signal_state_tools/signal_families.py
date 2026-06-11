"""Signal-type registry — vital → track aliases and variability families.
신호 종류 registry — vital→track alias 와 변동성 family 정의.

This is the single "signal taxonomy" source for the signal-state tools. Modality
is a *data* axis (resolved through these alias maps), not a code-module axis —
the tools stay modality-agnostic and route through this registry. Keeping the
taxonomy in one visible module (separate from the numpy / envelope helpers in
``_common``) makes the signal-type knowledge easy to find and extend.
signal-state tool 의 단일 "신호 분류" source. modality 는 코드 모듈 축이 아니라
*데이터* 축이며 이 alias 맵으로 라우팅된다. taxonomy 를 numpy/envelope 헬퍼와
분리된 한 모듈에 두어 신호 종류 지식을 찾고 확장하기 쉽게 한다.
"""
from __future__ import annotations


# ── Vital → track-alias map (synthetic keys + real VitalDB track names) ──
# Field order is the canonical output order. First matching alias wins.
# field 순서가 출력 순서. 첫 매칭 alias 채택.

_VITAL_ALIASES: dict[str, tuple[str, ...]] = {
    "map_mmHg": ("ABP", "MAP", "Solar8000/ART_MBP", "Solar8000/NIBP_MBP",
                 "SNUADC/ART", "EV1000/ART_MBP", "Solar8000/FEM_MBP"),
    "sbp_mmHg": ("SBP", "Solar8000/ART_SBP", "Solar8000/NIBP_SBP"),
    "dbp_mmHg": ("DBP", "Solar8000/ART_DBP", "Solar8000/NIBP_DBP"),
    "hr_bpm": ("HR", "Solar8000/HR", "Solar8000/PLETH_HR"),
    "spo2_pct": ("SpO2", "SPO2", "Solar8000/PLETH_SPO2"),
    "etco2_mmHg": ("EtCO2", "ETCO2", "Solar8000/ETCO2", "Primus/ETCO2"),
    "rr_per_min": ("RR", "Solar8000/RR", "Solar8000/VENT_RR", "Solar8000/RR_CO2"),
    "bis": ("BIS", "BIS/BIS"),
    "core_temp_c": ("BT", "Solar8000/BT", "TEMP", "core_temp"),
}

# Family aliases for variability routing. Numeric-vital families are derived from
# the canonical map; waveform-only families (no numeric vital field) stand alone.
# 변동성 routing 용 family alias — 수치 vital 은 canonical map 에서 파생,
# waveform 전용(PPG/CVP/PAP)은 별도 정의.
_HR_ALIASES: tuple[str, ...] = _VITAL_ALIASES["hr_bpm"]
_ABP_ALIASES: tuple[str, ...] = _VITAL_ALIASES["map_mmHg"]
_PPG_ALIASES = ("PPG", "SNUADC/PLETH")
_CVP_ALIASES = ("CVP", "CVP_MEAN", "SNUADC/CVP", "Solar8000/CVP", "EV1000/CVP")
_PAP_ALIASES = (
    "PAP_MBP", "PAP_SBP", "PAP_DBP",
    "Solar8000/PA_MBP", "Solar8000/PA_SBP", "Solar8000/PA_DBP",
)


__all__ = [
    "_VITAL_ALIASES",
    "_HR_ALIASES",
    "_ABP_ALIASES",
    "_PPG_ALIASES",
    "_CVP_ALIASES",
    "_PAP_ALIASES",
]
