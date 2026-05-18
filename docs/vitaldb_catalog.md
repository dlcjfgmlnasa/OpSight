# VitalDB Catalog — Authoritative Lookup (plan_1.1)

> 본 문서는 VitalDB 의 데이터 구조 (waveform / numeric / metadata / API) 에 대한 단일 권위 lookup 이다.
> 모든 후속 stage 가 본 catalog 를 참조한다.
> 의존성: `docs/project_brief.md §4`, `docs/findings/pre_phase3_findings.md`, `docs/notebooks/_cache/{cases,trks}.csv` (2026-05-16 캐시).

**Data snapshot**: 2026-05-16 (cases.csv 6,388 row; trks.csv 486,449 row; 196 unique track).

---

## 0. 한 줄 요약

| 항목 | 값 |
|------|----|
| 총 case 수 | **6,388** |
| Subject 수 | 6,388 (subjectid 1:1 case) |
| Department 수 | 4 (General / Thoracic / Gynecology / Urology) |
| Unique waveform / numeric track 수 | **196** |
| Case-level metadata field 수 | 74 |
| 평가 cohort 후보 (수술 < 30분 제외 후) | ≈ 5,946 (자세한 건 plan_1.2) |
| Modality 가용성 100% | `Solar8000/HR`, `Solar8000/PLETH_HR`, `Solar8000/PLETH_SPO2` |
| Modality 가용성 ≥ 99% | `Primus/CO2`, `Primus/AWP`, `SNUADC/ECG_II`, `Primus/ETCO2` 등 |
| ABP 가용성 (`SNUADC/ART`) | **57.1%** (department 별 큰 편차) |

> 자세한 cohort policy (예: 시기 < 30분 제외) 는 plan_1.2 의 산출물.

---

## 1. API Reference

### ⚠️ 가장 중요한 caveat — `load_clinical_data()` 사용 금지

```
vitaldb.load_clinical_data()  →  0 rows 반환 (2026-05-16 검증)
```

추정 원인: 로그인 / API key 필요. 본 환경 (스크립트 / unit test) 에서는 사용 불가.

### ✅ 운용 가능한 경로 — Public CSV endpoint

```python
import pandas as pd

# Case-level metadata (6,388 row × 74 col)
cases = pd.read_csv("https://api.vitaldb.net/cases")

# Track listing (486,449 row × 3 col: caseid, tname, tid)
trks = pd.read_csv("https://api.vitaldb.net/trks")
```

본 두 endpoint 가 catalog 의 정식 source. 로컬 캐시는 `docs/notebooks/_cache/{cases,trks}.csv`.

자세한 검증 record 는 `docs/findings/pre_phase3_findings.md §1`.

### `vitaldb` Python library — 단일 case load

```python
import vitaldb

# 단일 case 의 모든 track 을 load (DataFrame, time 인덱싱)
vf = vitaldb.VitalFile(caseid=1)
# 또는
df = vitaldb.load_case(caseid=1, track_names=["SNUADC/ART", "Solar8000/HR"], interval=1.0)
```

**Signature 요약** (vitaldb 1.4.x 기준):

| Function | Args | Return |
|----------|------|--------|
| `VitalFile(caseid)` | int caseid | VitalFile object — 단일 case 의 모든 track |
| `VitalFile.to_pandas(track_names, interval=1.0)` | list[str], float (초 단위 resampling) | DataFrame (시간 index + 각 track column) |
| `load_case(caseid, track_names, interval)` | int, list[str], float | DataFrame |
| `load_trks(tids, interval)` | list[str] of tid hashes, float | DataFrame |
| `find_cases(track_names)` | list[str] | list[int] caseid 가 모두 포함하는 case |

⚠️ Version 차이: 일부 release 에서 시간 축이 sample-index, 다른 release 에서 second 인덱싱. `interval=1.0` 인자로 resampling 후 사용 권장.

### Caching 권장 패턴

```python
import os
import pandas as pd
CACHE = "docs/notebooks/_cache"
def _cached(name, url):
    p = f"{CACHE}/{name}"
    if not os.path.exists(p):
        pd.read_csv(url).to_csv(p, index=False)
    return pd.read_csv(p)
cases = _cached("cases.csv", "https://api.vitaldb.net/cases")
trks  = _cached("trks.csv",  "https://api.vitaldb.net/trks")
```

전체 reload 시 ~1 분, 캐시 hit 시 ~3 초.

---

## 2. Waveform Channels (priority)

본 프로젝트가 raw waveform (≥ 100 Hz) 로 소비할 가능성이 있는 channel.

| Channel | sampling_rate_Hz | unit | % cases | description |
|---------|-----------------:|------|--------:|-------------|
| `SNUADC/ART` | 500 | mmHg | 57.1% | Arterial blood pressure waveform — primary hemodynamic input |
| `SNUADC/PLETH` | 500 | (unitless) | 96.4% | Pulse-oximeter plethysmograph waveform |
| `SNUADC/ECG_II` | 500 | mV | 99.5% | ECG lead II waveform |
| `SNUADC/ECG_V5` | 500 | mV | 53.1% | ECG lead V5 waveform |
| `SNUADC/CVP` | 500 | mmHg | 24.8% | Central venous pressure waveform |
| `SNUADC/FEM` | 500 | mmHg | 2.0% | Femoral arterial waveform |
| `BIS/EEG1_WAV` | 128 | μV | 91.9% | BIS EEG channel 1 waveform |
| `BIS/EEG2_WAV` | 128 | μV | 91.9% | BIS EEG channel 2 waveform |
| `Primus/CO2` | 62.5 | mmHg | 99.6% | Capnogram waveform (CO₂) |
| `Primus/AWP` | 62.5 | cmH₂O | 99.6% | Airway pressure waveform |

→ ABP / PPG / ECG-II / EEG / CO₂ / AWP 의 6 가지 waveform 이 분석에 핵심.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] sampling rate 정확치, unit 표기.

---

## 3. Numeric Tracks (priority)

저빈도 (≤ 1 Hz) numeric tracks — Solar8000 / BIS / Orchestra prefix.

### 3.1 Solar8000/* (vital sign monitor — 1 Hz)

| Track | unit | % cases | downstream tool |
|-------|------|--------:|-----------------|
| `Solar8000/HR` | bpm | **100.0%** | tool 1, 2 (arrest risk); FM encode |
| `Solar8000/PLETH_HR` | bpm | 100.0% | tool 3 (quality fallback) |
| `Solar8000/PLETH_SPO2` | % | 100.0% | tool 3 |
| `Solar8000/NIBP_MBP` | mmHg | 90.2% | tool 1 (hypotension fallback when ABP absent) |
| `Solar8000/NIBP_SBP` | mmHg | 90.0% | — |
| `Solar8000/NIBP_DBP` | mmHg | 90.0% | — |
| `Solar8000/ART_MBP` | mmHg | 58.3% | tool 1 (primary MAP if ART exists) |
| `Solar8000/ART_SBP` | mmHg | 58.3% | — |
| `Solar8000/ART_DBP` | mmHg | 58.3% | — |
| `Solar8000/BT` | °C | 92.6% | tool 12 (intraop temp) |
| `Solar8000/ETCO2` | mmHg | 97.7% | tool 3 (signal quality reasoning) |
| `Solar8000/CVP` | mmHg | 25.2% | tool 10 (fluid status proxy) |

### 3.2 BIS/* (depth-of-anesthesia — 1 Hz)

| Track | unit | % cases | downstream tool |
|-------|------|--------:|-----------------|
| `BIS/BIS` | (0–100) | 91.8% | tool 15 (anesthesia depth context) |
| `BIS/SQI` | (0–100) | 91.8% | tool 3 (BIS quality) |
| `BIS/EMG` | dB | 87.3% | tool 3 |
| `BIS/SR` | % | 87.2% | tool 3 (suppression ratio — high = deep anesthesia) |
| `BIS/SEF` | Hz | 87.2% | — |

### 3.3 Orchestra/* (drug effect-site CE — 1 Hz)

| Track | unit | % cases | downstream tool |
|-------|------|--------:|-----------------|
| `Orchestra/RFTN20_CE` | ng/mL | 74.7% | tool 8 (remifentanil concentration) |
| `Orchestra/RFTN20_RATE` | mL/h | 74.7% | tool 8 |
| `Orchestra/PPF20_CE` | μg/mL | 55.0% | tool 8 (propofol concentration) |
| `Orchestra/PPF20_RATE` | mL/h | 55.0% | tool 8 |
| `Orchestra/PHEN_RATE` | mL/h | 2.0% | tool 9 (phenylephrine — vasoactive) |
| `Orchestra/NEPI_RATE` | mL/h | 1.4% | tool 9 (norepinephrine — vasoactive) |
| `Orchestra/EPI_RATE` | mL/h | 0.1% | tool 9 (epinephrine — vasoactive) |
| `Orchestra/DOPA_RATE` | mL/h | 0.5% | tool 9 (dopamine — vasoactive) |
| `Orchestra/ROC_RATE` | mL/h | 4.4% | tool 8 (rocuronium — muscle relaxant) |

### 3.4 Primus/* (anesthesia machine — ~1 Hz)

| Track | unit | % cases | downstream tool |
|-------|------|--------:|-----------------|
| `Primus/EXP_SEVO` | % | 57.7% | tool 8 (sevoflurane expired conc) |
| `Primus/INSP_SEVO` | % | 57.7% | tool 8 |
| `Primus/MAC` | (unitless) | 99.2% | tool 8 (minimum alveolar concentration) |
| `Primus/ETCO2` | mmHg | 99.2% | tool 3 (quality) |
| `Primus/RR_CO2` | /min | 99.1% | tool 3 |
| `Primus/PEEP_MBAR` | mbar | 93.9% | tool 11 (ventilation context) |

자세한 unit / formula 는 VitalDB 공식 docs.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] downstream tool 매핑의 임상적 적절성.

---

## 4. Full Track Listing (196 unique)

본 절은 prefix (device) 별 모든 track 의 전수 catalog. `docs/notebooks/_cache/trks.csv` (2026-05-16) 기반.

### 4.1 Device 별 요약

| Device prefix | # unique tracks | # cases | % cohort |
|---------------|----------------:|--------:|---------:|
| `Solar8000` | 44 | 6,388 | 100.0% |
| `Primus` | 37 | 6,363 | 99.6% |
| `Orchestra` | 51 | 4,919 | 77.0% |
| `BIS` | 8 | 5,871 | 91.9% |
| `SNUADC` | 6 | 6,356 | 99.5% |
| `EV1000` | 9 | 617 | 9.7% |
| `Vigilance` | 14 | 70 | 1.1% |
| `Vigileo` | 5 | 323 | 5.1% |
| `CardioQ` | 13 | 29 | 0.5% |
| `Invos` | 2 | 33 | 0.5% |
| `FMS` | 7 | 15 | 0.2% |
| **합계** | **196** | 6,388 | — |

### 4.2 Solar8000/* (44 tracks)

`Solar8000/HR` 100.0% · `Solar8000/PLETH_HR` 100.0% · `Solar8000/PLETH_SPO2` 100.0% ·
`Solar8000/VENT_MAWP` 98.6% · `Solar8000/ETCO2` 97.7% · `Solar8000/INCO2` 97.7% ·
`Solar8000/FIO2` 97.7% · `Solar8000/FEO2` 97.7% · `Solar8000/RR_CO2` 96.7% ·
`Solar8000/VENT_MV` 93.7% · `Solar8000/VENT_RR` 93.7% · `Solar8000/VENT_TV` 93.6% ·
`Solar8000/ST_II` 93.6% · `Solar8000/VENT_PIP` 93.5% · `Solar8000/VENT_PPLAT` 93.3% ·
`Solar8000/VENT_INSP_TM` 93.0% · `Solar8000/BT` 92.6% · `Solar8000/NIBP_MBP` 90.2% ·
`Solar8000/NIBP_SBP` 90.0% · `Solar8000/NIBP_DBP` 90.0% · `Solar8000/VENT_SET_TV` 66.6% ·
`Solar8000/ART_DBP` 58.3% · `Solar8000/ART_SBP` 58.3% · `Solar8000/ART_MBP` 58.3% ·
`Solar8000/GAS2_EXPIRED` 48.5% · `Solar8000/GAS2_INSPIRED` 48.5% · `Solar8000/ST_III` 47.4% ·
`Solar8000/ST_I` 47.3% · `Solar8000/ST_AVF` 47.0% · `Solar8000/ST_AVL` 47.0% ·
`Solar8000/ST_AVR` 47.0% · `Solar8000/VENT_SET_PCP` 43.0% · `Solar8000/VENT_SET_FIO2` 34.6% ·
`Solar8000/CVP` 25.2% · `Solar8000/RR` 20.3% · `Solar8000/FEM_DBP` 2.2% ·
`Solar8000/FEM_SBP` 2.2% · `Solar8000/FEM_MBP` 2.2% · `Solar8000/VENT_COMPL` 1.8% ·
`Solar8000/VENT_MEAS_PEEP` 1.5% · `Solar8000/PA_SBP` 1.3% · `Solar8000/PA_MBP` 1.3% ·
`Solar8000/PA_DBP` 1.3% · `Solar8000/ST_V5` 0.0%.

### 4.3 Primus/* (37 tracks)

`Primus/CO2` 99.6% · `Primus/SET_AGE` 99.6% · `Primus/PAMB_MBAR` 99.6% ·
`Primus/AWP` 99.6% · `Primus/VENT_LEAK` 99.3% · `Primus/INCO2` 99.2% ·
`Primus/FIN2O` 99.2% · `Primus/ETCO2` 99.2% · `Primus/FEN2O` 99.2% ·
`Primus/MAC` 99.2% · `Primus/MAWP_MBAR` 99.2% · `Primus/FEO2` 99.2% ·
`Primus/FIO2` 99.2% · `Primus/RR_CO2` 99.1% · `Primus/SET_FIO2` 94.7% ·
`Primus/SET_FRESH_FLOW` 94.6% · `Primus/MV` 94.3% · `Primus/TV` 94.2% ·
`Primus/COMPLIANCE` 94.2% · `Primus/PIP_MBAR` 94.0% · `Primus/PEEP_MBAR` 93.9% ·
`Primus/PPLAT_MBAR` 93.9% · `Primus/SET_INSP_TM` 93.6% · `Primus/SET_RR_IPPV` 93.6% ·
`Primus/SET_INTER_PEEP` 93.6% · `Primus/SET_TV_L` 93.4% · `Primus/SET_PIP` 93.4% ·
`Primus/SET_INSP_PAUSE` 93.4% · `Primus/FLOW_N2O` 88.4% · `Primus/FLOW_AIR` 88.4% ·
`Primus/FLOW_O2` 88.3% · `Primus/INSP_SEVO` 57.7% · `Primus/EXP_SEVO` 57.7% ·
`Primus/EXP_DES` 32.0% · `Primus/INSP_DES` 32.0% · `Primus/SET_INSP_PRES` 6.0% ·
`Primus/SET_FLOW_TRIG` 2.4%.

### 4.4 Orchestra/* (51 tracks)

drug infusion 관련. 코호트 인구 차이 큼.

**Main anesthetics**: `Orchestra/RFTN20_VOL` 74.7% · `Orchestra/RFTN20_RATE` 74.7% ·
`Orchestra/RFTN20_CE` 74.7% · `Orchestra/RFTN20_CP` 74.7% · `Orchestra/RFTN20_CT` 74.7% ·
`Orchestra/PPF20_VOL` 55.0% · `Orchestra/PPF20_RATE` 55.0% · `Orchestra/PPF20_CT` 55.0% ·
`Orchestra/PPF20_CP` 55.0% · `Orchestra/PPF20_CE` 55.0%.

**Muscle relaxants**: `Orchestra/ROC_VOL` 4.4% · `Orchestra/ROC_RATE` 4.4% ·
`Orchestra/VEC_RATE` 0.0% · `Orchestra/VEC_VOL` 0.0%.

**Vasoactives**: `Orchestra/PHEN_VOL` 2.0% · `Orchestra/PHEN_RATE` 2.0% ·
`Orchestra/NEPI_RATE` 1.4% · `Orchestra/NEPI_VOL` 1.4% · `Orchestra/DOPA_VOL` 0.5% ·
`Orchestra/DOPA_RATE` 0.5% · `Orchestra/EPI_RATE` 0.1% · `Orchestra/EPI_VOL` 0.1% ·
`Orchestra/DOBU_VOL` 0.0% · `Orchestra/DOBU_RATE` 0.0% · `Orchestra/VASO_RATE` 0.0% ·
`Orchestra/VASO_VOL` 0.0%.

**Other infusions**: `Orchestra/RFTN50_*` 1.1% (5 tracks) ·
`Orchestra/NTG_VOL` 0.5% · `Orchestra/NTG_RATE` 0.5% · `Orchestra/FUT_VOL` 1.5% ·
`Orchestra/FUT_RATE` 1.5% · `Orchestra/PGE1_VOL` 1.4% · `Orchestra/PGE1_RATE` 1.4% ·
`Orchestra/DEX2_*` (2 tracks) · `Orchestra/DEX4_*` (2 tracks) ·
`Orchestra/MRN_*` (2 tracks) · `Orchestra/OXY_*` (2 tracks) · `Orchestra/DTZ_*` (2 tracks) ·
`Orchestra/AMD_*` (2 tracks) · `Orchestra/NPS_*` (2 tracks).

### 4.5 BIS/* (8 tracks)

`BIS/EEG1_WAV` 91.9% · `BIS/EEG2_WAV` 91.9% · `BIS/BIS` 91.8% · `BIS/SQI` 91.8% ·
`BIS/EMG` 87.3% · `BIS/SEF` 87.2% · `BIS/SR` 87.2% · `BIS/TOTPOW` 86.9%.

### 4.6 SNUADC/* (6 tracks — high-rate waveform)

`SNUADC/ECG_II` 99.5% · `SNUADC/PLETH` 96.4% · `SNUADC/ART` 57.1% ·
`SNUADC/ECG_V5` 53.1% · `SNUADC/CVP` 24.8% · `SNUADC/FEM` 2.0%.

### 4.7 EV1000/* (9 tracks — `[CAVEAT]` 9.7% cohort)

`EV1000/CI` 9.7% · `EV1000/SVV` 9.7% · `EV1000/CO` 9.7% · `EV1000/SV` 9.7% ·
`EV1000/SVI` 9.7% · `EV1000/ART_MBP` 9.3% · `EV1000/SVR` 4.0% · `EV1000/SVRI` 4.0% ·
`EV1000/CVP` 3.7%.

### 4.8 기타 minority devices

본 devices 는 코호트 대다수에서 부재. modality-agnostic agent 는 *가용 시* 활용, 부재 시 [Limitations] 명시.

| Device | # tracks | % cohort |
|--------|---------:|---------:|
| `Vigilance/*` | 14 | 1.1% |
| `Vigileo/*` | 5 | 5.1% |
| `CardioQ/*` | 13 | 0.5% |
| `Invos/*` | 2 | 0.5% |
| `FMS/*` | 7 | 0.2% |

→ 총 41 tracks 가 < 6% 코호트만 보유. agent 가 의존하면 안 됨.

---

## 5. Modality Availability by Department (`[CLINICIAN-REVIEW]`)

Brief §11.0 의 mandatory department-stratified 보고용 empirical 근거.

```
                 All     General   Gynecology  Thoracic    Urology
                       (n=4,930)   (n=230)    (n=1,111)   (n=117)
                       
ABP family     58%       48%      82%         97%        71%
PPG            96%       97%      96%         96%        79% [CAVEAT]
ECG-II         99%      100%      98%         99%        99%
BIS            92%       92%      96%         92%        79% [CAVEAT]
EEG (BIS wav)  92%       92%      96%         92%        79% [CAVEAT]
SEVO (vol)     58%       59%      78%         51%        17% [CAVEAT]
RFTN (TIVA)    76%       74%      48% [CAVEAT] 90%        74%
PPF (TIVA)     55%       51%       2% [CAVEAT] 90%         6% [CAVEAT]
NIBP           90%       93%      90%         77%        91%
CO2 (Primus)  100%      100%      98%         99%       100%
```

`[CAVEAT]` mark = 가용성 < 50% 또는 본 department 에서 일반 표준과 큰 괴리.

### 5.1 해석 hint (brief §10 modality-agnostic 정책)

| Department | ABP 가용 | TIVA / VOL 비율 | Comment |
|------------|----------|-----------------|---------|
| **General surgery** | 48% (낮음) | RFTN 74% · PPF 51% (TIVA dominant) | 코호트 다수 — ABP 미보유 case 가 더 많음 → modality-agnostic 정책 필수 |
| **Thoracic surgery** | 97% (높음) | RFTN 90% · PPF 90% (TIVA dominant) | ABP 가용성 거의 모든 case — high-fidelity 분석 가능 |
| **Gynecology** | 82% | SEVO 78% (volatile dominant) | PPF 거의 부재 (2%) — TIVA 가정 안 됨 |
| **Urology** | 71% | SEVO 17% / RFTN 74% / PPF 6% | 코호트 작음 (n=117) — 통계 안정성 caveat |

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — department 별 anesthetic protocol 의 비율이 임상적으로 합리적인지 검증.

---

## 6. Case Metadata (74 fields)

`cases.csv` 의 74 컬럼 — agent / tool / cohort filter / EMR tool 이 소비.

### 6.1 Identity / Timestamps (10 fields, 100% available)

| Field | type | 의미 / downstream |
|-------|------|---------------------|
| `caseid` | int | case unique ID |
| `subjectid` | int | subject ID (case 와 1:1, 따라서 dedup 불필요) |
| `casestart`, `caseend` | int (sec) | record window 시작 / 끝 |
| `anestart`, `aneend` | int (sec) | anesthesia 시작 / 끝 |
| `opstart`, `opend` | int (sec) | surgical incision 시작 / 끝 |
| `adm`, `dis` | int (UTC?) | hospital admission / discharge — tool 12 |

### 6.2 Outcome (2 fields)

| Field | type | downstream tool |
|-------|------|-----------------|
| `icu_days` | int | tool 12 (postop outcome) |
| `death_inhosp` | int (0/1) | evaluation only |

### 6.3 Demographics (7 fields, 100% available except asa)

| Field | type | downstream |
|-------|------|------------|
| `age` | float (year) | tool 12 (baseline) |
| `sex` | str (M/F) | tool 12 |
| `height` | float (cm) | tool 12 |
| `weight` | float (kg) | tool 12 |
| `bmi` | float | tool 12 |
| `asa` | float (1–5, 97.9% available) | tool 12 (risk stratification) |
| `emop` | int (0/1) | emergency op flag |

### 6.4 Surgery context (6 fields)

| Field | type | downstream |
|-------|------|------------|
| `department` | str (4 values) | tool 15 (surgery context priors) |
| `optype` | str (10+ values) | tool 15 |
| `dx` | str | tool 15 |
| `opname` | str | tool 15 |
| `approach` | str | tool 15 |
| `position` | str (97.0% available) | tool 15 |
| `ane_type` | str (General / Spinal / Sedationalgesia) | tool 8 |

### 6.5 Preop comorbidity + ECG + PFT (4 fields)

| Field | type | downstream |
|-------|------|------------|
| `preop_htn` | int (0/1) | tool 12 |
| `preop_dm` | int (0/1) | tool 12 |
| `preop_ecg` | str (free text) | tool 12 `[CLINICIAN-REVIEW]` |
| `preop_pft` | str (free text) | tool 12 `[CLINICIAN-REVIEW]` |

### 6.6 Preop labs (16 fields, varying availability)

| Field | unit | % available | downstream |
|-------|------|------------:|------------|
| `preop_hb` | g/dL | 94.7% | tool 12 |
| `preop_plt` | 10³/μL | 94.7% | tool 12 |
| `preop_pt` | (INR) | 93.9% | tool 12 |
| `preop_aptt` | sec | 93.7% | tool 12 |
| `preop_na`, `preop_k` | mEq/L | ~90% | tool 12 |
| `preop_gluc` | mg/dL | 94.1% | tool 12 |
| `preop_alb` | g/dL | 94.2% | tool 12 |
| `preop_ast`, `preop_alt`, `preop_bun`, `preop_cr` | various | ~94% | tool 12 |
| `preop_ph`, `preop_hco3`, `preop_be`, `preop_pao2`, `preop_paco2`, `preop_sao2` | ABG | 8.3–8.5% | tool 12 `[CAVEAT]` 가용성 낮음 |

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — 어떤 lab value 가 어떤 risk 의 indicator 인지 매핑.

### 6.7 Airway / Lines (8 fields)

| Field | type | 의미 |
|-------|------|------|
| `cormack` | str (86.9%) | Cormack-Lehane grade |
| `airway` | str (93.5%) | airway device |
| `tubesize` | float (77.0%) | endotracheal tube size |
| `dltubesize` | str (14.6%) | double-lumen tube size |
| `lmasize` | float (1.6%) | LMA size |
| `iv1`, `iv2` | str | IV line locations |
| `aline1`, `aline2` | str | arterial line locations |
| `cline1`, `cline2` | str | central line locations |

### 6.8 Intraop fluids / drugs / blood (15 fields, 100% available)

`intraop_*` prefix. Tool 8 / 9 / 10 의 reality-check ground truth.

| Field | unit | downstream tool |
|-------|------|-----------------|
| `intraop_ebl` | mL (62.4%) | tool 10 (blood loss) |
| `intraop_uo` | mL (58.0%) | tool 10 (urine output) |
| `intraop_rbc` | unit | tool 10 |
| `intraop_ffp` | unit | tool 10 |
| `intraop_crystalloid` | mL (93.6%) | tool 10 |
| `intraop_colloid` | mL | tool 10 |
| `intraop_ppf` | mL | tool 8 (propofol bolus) |
| `intraop_mdz` | mg | tool 8 (midazolam) |
| `intraop_ftn` | μg | tool 8 (fentanyl) |
| `intraop_rocu` | mg | tool 8 (rocuronium) |
| `intraop_vecu` | mg | tool 8 (vecuronium) |
| `intraop_eph` | mg | tool 9 (ephedrine — vasoactive) |
| `intraop_phe` | mg | tool 9 (phenylephrine) |
| `intraop_epi` | mg | tool 9 (epinephrine) |
| `intraop_ca` | mg | tool 9 (calcium) |

→ Real EMR tool (plan_1.3) 합류 시 본 17 field 가 tool 8 / 9 / 10 의 ground truth.

---

## 7. Version Notes (재현성)

| Component | 권장 / 검증 version | 비고 |
|-----------|---------------------|------|
| `vitaldb` (Python lib) | `1.4.x` | 시간 인덱스 second/sample 차이 — `interval=1.0` 으로 통일 |
| `pandas` | `>= 2.0` | CSV endpoint 직접 read 호환 |
| `numpy` | `>= 1.24` | torch interop |
| API endpoint | `https://api.vitaldb.net/{cases,trks}` | 2026-05-16 검증, 추후 변경 가능성 |
| Cache snapshot | 2026-05-16 | `docs/notebooks/_cache/{cases,trks}.csv` |

### Version diff 주의

- VitalDB release notes 갱신 시 track 수 / 컬럼 schema 변경 가능. 본 catalog 는 2026-05-16 snapshot.
- `load_clinical_data()` 동작은 향후 인증 변경 시 다시 시도해볼 가치 있음.
- 외부 검증 dataset (MOVER, INSPIRE) 합류 시 schema mapping table 추가 필요.

---

## 8. Brief §4 Cross-Check Notes

본 catalog 작성 후 `docs/project_brief.md §4` 와의 정합성 review:

```diff
- §4 의 "12 channel modality" 는 placeholder TODO 였다.
+ 실제 데이터: 196 unique track, priority subset 10 (waveform 6 + numeric 4).
+ TODO marker 제거 가능 — 본 catalog §2 (waveform) + §3 (numeric) 가 spec 이다.

- §4 본문에 언급된 6 waveform channel:
+ `SNUADC/ART`, `SNUADC/PLETH`, `SNUADC/ECG_II`, `BIS/EEG1_WAV`, `Primus/CO2`, `Primus/AWP`
+ → 모두 본 catalog §2 에서 확인 + sampling rate / unit 명시.

- 누락 / 추가 modality 후보:
+ `Solar8000/HR` (100% 가용성, downstream tool 1/2 의 fallback) — brief §4 에 명시되어 있지 않으나 핵심
+ `SNUADC/ECG_V5` (53% 가용성) — multi-lead ECG 분석 시 추가 input 가능
+ BIS sub-tracks (`BIS/SQI`, `BIS/EMG`, `BIS/SR`) — anesthesia depth context tool 15 의 추가 feature
```

후속 조치 (`biomedical-ai-paper-writer` 협의 필요):
1. brief §4 의 "12 channel" placeholder 를 "10 priority channel + 186 long-tail track (196 total)" 로 갱신
2. brief §4 의 modality list 에 `Solar8000/HR` 명시적 추가
3. brief §10 의 "modality-agnostic" 정책에 department-별 ABP 가용성 큰 편차 (48% – 97%) 강조

---

## 9. Schema for downstream

본 catalog 에서 정의된 모든 track / metadata field 의 *naming convention* 은 후속 plan 의 contract.

| 약속 (contract) | 위치 |
|----------------|------|
| Track 이름 (예: `SNUADC/ART`) | plan_1.3 (EMR tool), plan_1.4 (baselines), plan_1.5 (surgery context), plan_1.7 (tool spec) 의 직접 input |
| Modality alias (예: `ABP` → `SNUADC/ART` / `Solar8000/ART_MBP` / `EV1000/ART_MBP`) | `vitalagent/fm/mock_rule_based.py::_ABP_ALIASES` 와 일치 |
| Case metadata field 이름 | plan_1.3 (real EMR tool) 의 정식 schema |

→ Track 이름 / metadata field 이름은 **본 catalog 가 정식 source**. 모든 코드 / 문서 가 본 이름을 그대로 사용.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — 본 catalog 의 임상 해석 부분 (§5 modality availability, §6 metadata 의 downstream tool mapping, §3 의 unit 정확성).

---

## Versioning

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-05-17 | Initial — plan_1.1 산출물 |
