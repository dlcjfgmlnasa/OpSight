# Cohort Stats — plan_1.2 산출물

> 자동 생성: `python scripts/build_cohort.py`. 매번 갱신.
> Source: `data/cohort/manifest.parquet` + `data/cohort/exclusions.parquet`.

## 0. 빌드 정책 (Build policy)

| 항목 | 값 |
|------|----|
| 데이터 source | `docs/notebooks/_cache/cases.csv` + `trks.csv` (2026-05-16 snapshot) |
| 최소 수술시간 | ≥ 30 분 |
| Pediatric (`age < 18`) | INCLUDED (default) |
| `ASA = 6` | INCLUDED (default) |

`[DECISION PENDING]` `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` —
Pediatric / ASA=6 inclusion 은 회의 후 결정. 본 manifest 는 *default (둘 다 INCLUDE)* 기반.

## 1. Cohort 규모

| Stratum | n |
|---------|---|
| Raw (cases.csv) | 6388 |
| Excluded — op_time_lt_30min | 442 |
| **Included (manifest.parquet)** | **5946** |

### Surgery type 분포

| surgery_type | n | % of included |
|--------------|---|---------------|
| general | 4576 | 77.0% |
| thoracic | 1055 | 17.7% |
| urology | 94 | 1.6% |
| gynecology | 221 | 3.7% |

## 2. Department-stratified modality 가용성

| modality | All (n=5946) | general (n=4576) | thoracic (n=1055) | urology (n=94) | gynecology (n=221) |
|----------|---|---|---|---|---|
| `ABP_any (Extended)` | 61.5% | 51.3% | 98.6% | 87.2% | 83.3% |
| `SNUADC/ART (invasive)` | 59.7% | 50.0% | 96.9% | 66.0% | 79.2% |
| `Solar8000/NIBP_MBP (NIBP)` | 89.7% | 92.7% | 76.5% | 89.4% | 89.6% |
| `SNUADC/PLETH (PPG)` | 96.1% | 96.6% | 96.2% | 73.4% | 96.4% |
| `SNUADC/ECG_II` | 99.5% | 99.6% | 99.3% | 98.9% | 98.6% |
| `BIS/BIS` | 92.8% | 92.9% | 91.8% | 86.2% | 96.4% |
| `BIS/EEG1_WAV (EEG)` | 92.8% | 93.0% | 91.8% | 86.2% | 96.4% |
| `Primus/EXP_SEVO (Sevo)` | 58.2% | 59.7% | 50.9% | 19.1% [CAVEAT] | 78.7% |
| `Orchestra/RFTN20_CE (Remi)` | 77.0% | 75.4% | 88.8% | 84.0% | 48.9% [CAVEAT] |
| `Orchestra/PPF20_CE (Prop)` | 56.1% | 52.1% | 89.6% | 3.2% [CAVEAT] | 2.3% [CAVEAT] |
| `Solar8000/HR` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| `Primus/CO2 (Capno)` | 99.6% | 99.7% | 99.3% | 100.0% | 98.2% |

`[CAVEAT]` mark = 가용성 < 50% (department 안).

## 3. Manifest schema

```
case_id: int
surgery_type: enum {general, thoracic, urology, gynecology, other}
op_duration_min: float
age: float
asa: int | null
abp_invasive: bool      # SNUADC/ART present
abp_primary: bool       # ART OR Solar8000/ART_MBP (brief §4.2 Primary)
abp_any: bool           # Primary OR EV1000/ART_MBP OR Solar8000/FEM_MBP (brief §4.2 Extended, default)
included: bool          # always True in manifest.parquet
```

## 4. Clinical-evaluator review note (자동)

아래는 *자동 sanity check* 결과. 실제 임상 검토는 `[CLINICIAN-REVIEW]` marker.

- ABP 가용성 department 별 편차 — General: 51.3%, Thoracic: 98.6%. brief §1 의 modality-agnostic 정책의 empirical 근거.
- Pediatric / ASA=6 default 적용 — 회의 결정 후 본 stats 재생성 필요 시 `--exclude-pediatric` / `--exclude-asa6` flag 사용.
- `surgery_type == 'other'` 비율 — VitalDB `department` 가 4 표준 외 값을 가지면 발생. 본 dataset (2026-05-16 snapshot) 은 4 department 만.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — surgery_type 분포의 임상적 타당성, ABP 가용성 편차 해석.