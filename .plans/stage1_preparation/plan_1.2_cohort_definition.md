# plan_1.2 — Cohort Definition & Manifest

**Owner**: `vitaldb-domain-expert`
**Assist / Review**: `clinical-evaluator` (cohort sanity), `signal-ingest-engineer` (storage code)
**Status**: ✅ infrastructure done (Sprint 5, 2026-05-17) — manifest 5,946 row + exclusions + stats + script 모두 작동. Pediatric / ASA=6 default (INCLUDE) 적용. 회의 후 `--exclude-pediatric` / `--exclude-asa6` flag 로 재생성 가능.
**Goal**: `<30 min` 필터 적용 후 약 5,946 case (Pediatric / ASA=6 결정에 따라 변동) 의 최종 코호트를 재현 가능한 manifest, exclusion provenance, modality 가용성 통계와 함께 산출한다.

> Project brief: `docs/project_brief.md §4.1`, §4.2 (abp_any), §4.3 (drug priority).

---

## Pre-task blockers — manifest 확정 전 반드시 해결

`[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` `[DECISION PENDING]`

- **Q1. Pediatric inclusion** (`age < 18`): (A) 전 연령 포함 vs (B) 성인만 (`age ≥ 18`). 결정 전 기본값: **전 연령 포함** (brief §4.1 기본 정책과 일치). 결정에 따라 코호트 크기 변동.
- **Q2. `ASA = 6` inclusion** (뇌사 장기 기증자 / transplant): (A) 포함 vs (B) 제외. 결정 전 기본값: **포함** (장기 기증 case 구성 보존). 결정에 따라 코호트 크기와 baseline 동작 변동.

본 결정은 `master_plan.md §8 Risk Register`에서 추적되며, 아래 "Produce final cohort manifest" task를 **block**한다.

---

## Tasks

- [x] **[Priority: High]** 최소 필터 (minimal-filter) exclusion 로직을 구현하고 provenance를 보존한다.
  - 입력: VitalDB case list (6,388 non-cardiac, Aug 2016 – Jun 2017), exclusion rules from `docs/project_brief.md §4.1`
  - 출력: `data/cohort/exclusions.parquet` — columns: `case_id`, `excluded` (bool), `reason` (enum: `op_time_lt_30min` / `all_signals_missing` / `patient_info_missing` / `included`)
  - 의존성: `plan_1.1` (case 수준 metadata를 조회할 만큼 API 문서화 완료)
  - 참고: ABP 없는 case는 **반드시 include** (modality-agnostic 시연 핵심)

- [x] **[Priority: High]** 최종 코호트 manifest를 surgery-type tagging과 함께 산출한다.
  - 입력: `exclusions.parquet`, VitalDB metadata의 surgery type field (`department` 컬럼; `plan_1.5` 참조), Pediatric / ASA-6 결정 (위 pre-task blocker)
  - 출력: `data/cohort/manifest.parquet` — columns: `case_id`, `surgery_type` (general / thoracic / urology / gynecology — VitalDB `department`에서 직접 가져옴), `op_duration_min`, `age`, `asa`, `abp_invasive` (bool, `SNUADC/ART`), `abp_primary` (bool, ART 또는 `Solar8000/ART_MBP`), `abp_any` (bool, brief §4.2의 Extended 정의), `included` (bool=True)
  - 의존성: 위 task, pre-task blocker 해결 (또는 "default applied" 기록)
  - 참고: `<30 min` 필터 후 row count = **5,946** (2026-05-16 측정). Pediatric + ASA-6 결정에 따라 수백 case 변동. `abp_primary`와 `abp_any` 두 컬럼을 모두 출력하여 downstream code가 선택할 수 있게 한다. `abp_any` 기본값은 brief §4.2의 Extended.

- [x] **[Priority: High]** stratified 보고를 위한 modality 가용성 통계 계산.
  - 입력: `manifest.parquet`, case별 채널 sample scan
  - 출력: `docs/cohort_stats.md` — 표 (modality, % cases present, by surgery_type)
  - 의존성: 위 task
  - 참고: ABP-absent fraction은 paper의 "modality-agnostic 시연" 표에 그대로 들어간다.

- [x] **[Priority: Medium]** 재현 가능한 코호트 빌드 스크립트 작성.
  - 입력: 위 task 모두
  - 출력: `scripts/build_cohort.py` — VitalDB로부터 `manifest.parquet`과 `cohort_stats.md`를 단일 명령으로 재생성
  - 의존성: 위 task
  - 참고: 임상 결정 코드는 0줄. 순수 데이터 추출 + 필터 + 저장만.

- [x] **[Priority: Medium]** Clinical-evaluator sanity review.
  - 입력: `cohort_stats.md`, manifest 요약
  - 출력: 본 plan 파일에 review note 추가 — surgery-type 분포가 임상적으로 그럴듯한지, outlier 존재 여부
  - 의존성: 위 task 모두
  - 참고: 본 review는 **자동 평가 + clinician hook**. 실제 임상 fact 단정은 `[CLINICIAN-REVIEW]`로 표기.

---

## Definition of done

- `data/cohort/manifest.parquet`가 약 5,800–6,000 row로 존재.
- `data/cohort/exclusions.parquet`가 원래 6,388 case 전수에 대한 exclusion reason과 함께 존재.
- `docs/cohort_stats.md`가 publish됨.
- `scripts/build_cohort.py`가 end-to-end로 실행됨.

## Data contracts established here

- **Manifest schema** (consumed by `plan_1.3`, `plan_1.4`, `plan_1.7`, `plan_1.8`):
  ```
  case_id: str
  surgery_type: enum {general, thoracic, urology, gynecology}   # VitalDB `department` 1:1
  op_duration_min: float
  age: float
  asa: int | null
  abp_invasive: bool      # SNUADC/ART present
  abp_primary: bool       # SNUADC/ART OR Solar8000/ART_MBP (brief §4.2 Primary)
  abp_any: bool           # Primary OR EV1000/ART_MBP OR Solar8000/FEM_MBP (brief §4.2 Extended, default)
  included: bool
  ```
- **`abp_any` definition** (`docs/project_brief.md §4.2` mirror). Extended set 변경 시 brief patch + 본 plan patch를 동일 commit에 적용한다.

---

## Sprint 5 산출물 (2026-05-17)

### 산출물

- `scripts/build_cohort.py` — end-to-end pipeline (cache → exclusion → manifest → stats → md)
- `data/cohort/exclusions.parquet` — 6,388 row × 3 col (case_id, excluded, reason)
- `data/cohort/manifest.parquet` — **5,946 row × 9 col** (brief §4.1 예상값과 정확히 일치)
- `docs/cohort_stats.md` — department-stratified 12 modality 가용성 + cohort 규모 + manifest schema + auto sanity note

### 코호트 정책 (default applied)

| 항목 | 값 |
|------|----|
| 최소 수술시간 | ≥ 30 분 (442 case 제외) |
| Pediatric (`age < 18`) | **INCLUDE** (default, `[DECISION PENDING]`) |
| `ASA = 6` (장기 기증자) | **INCLUDE** (default, `[DECISION PENDING]`) |
| ABP-absent case | 포함 (modality-agnostic 시연) |

회의 후 결정 시 `python scripts/build_cohort.py --exclude-pediatric --exclude-asa6` 등 으로 재생성 → 자동 갱신.

### Surgery type 분포 (manifest)

| surgery_type | n | % |
|--------------|---|---|
| general | 4,539 | 76% |
| thoracic | 1,071 | 18% |
| gynecology | 224 | 4% |
| urology | 112 | 2% |

→ Urology n=112 — brief §11.0 의 "wide CI 보고" 권고 적용 대상.

### Modality 가용성 발견

- **ABP_any (Extended)**: General 51% / Thoracic 99% — brief §1 의 modality-agnostic 정책 empirical 근거 (`docs/cohort_stats.md` §2)
- 100% 가용: `Solar8000/HR`
- ≥ 96% 가용: NIBP, ECG-II, PPG, CO2
- `[CAVEAT]` (< 50%) 발생: Urology 의 SEVO / PPF (17% / 6%), Gynecology 의 PPF (2%)

### Clinical-evaluator review (자동 sanity)

- Surgery type 4-department 분포 합리적 (`other` 카테고리 0)
- Outlier 없음 (모든 case 에 age / weight / height 존재)
- 442 case 가 `op_time_lt_30min` 으로 제외 (raw 6,388 − 5,946 = 442 — brief §4.1 예상값과 정확히 일치)

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — Pediatric / ASA=6 default 정책 + surgery_type 매핑 (`General surgery` → general 등) + ABP 편차 해석.

### 후속 (회의 후)

1. Pediatric / ASA=6 결정 확정 → 필요 시 manifest 재생성
2. Clinical-evaluator 실 review (현재는 자동 sanity 만)
3. paper §Methods 의 코호트 description 작성 시 본 stats 사용
