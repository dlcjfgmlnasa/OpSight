# plan_1.1 — VitalDB Exploration & Catalog

**Owner**: `vitaldb-domain-expert`
**Assist**: `signal-ingest-engineer`
**Status**: ✅ done (Sprint 4 continuation, 2026-05-17) — `docs/vitaldb_catalog.md` v1 작성
**Goal**: VitalDB의 데이터 구조 (channel, numeric, metadata, API)에 대한 완전하고 reference-quality 카탈로그를 생성한다. 모든 후속 stage가 단일 권위 lookup을 갖도록 한다.

> Project brief: `docs/project_brief.md §4`. 본 plan은 §4의 12-channel modality 목록 TODO marker를 해결한다.

---

## Tasks

- [x] **[Priority: High]** 코호트가 사용하는 모든 waveform channel을 enumerate한다. 각 채널의 sampling rate, unit, 일반 가용성을 포함한다.
  - 입력: `vitaldb` Python library, VitalDB online schema
  - 출력: `docs/vitaldb_catalog.md`의 "Waveform channels" 섹션 — 표 (channel name, sampling_rate_Hz, unit, description, % cases present)
  - 의존성: 없음
  - 참고: 최소 §4 본문에 언급된 6개 (`SNUADC/ART`, `SNUADC/PLETH`, `SNUADC/ECG_II`, `BIS/EEG1_WAV`, `Primus/CO2`, `Primus/AWP`) + 누락 6개 식별

- [x] **[Priority: High]** 후속 stage에서 활용되는 주요 numeric track (Solar8000/*, BIS/*, Orchestra/* drug effect-site)을 enumerate한다.
  - 입력: cohort sample (`vitaldb.load_case`로 5–10 case 로드)
  - 출력: `docs/vitaldb_catalog.md`의 "Numeric tracks" 섹션 — 표 (track name, sampling_rate_Hz, unit, downstream tool consumer)
  - 의존성: 위 task 부분 진행
  - 참고: 73 perioperative + 34 lab parameter는 다음 task에서 분리 정리

- [x] **[Priority: High]** 본 프로젝트가 사용할 `vitaldb` Python API surface를 문서화한다.
  - 입력: `vitaldb` package source / docstrings, operable CSV endpoint (참고 참조)
  - 출력: `docs/vitaldb_catalog.md`의 "API reference" 섹션 — `find_cases`, `load_case`, `load_trks`의 signature, args, return shape, 예제
  - 의존성: 없음
  - 참고: `vitaldb.load_clinical_data()`는 본 환경에서 **0 rows**를 반환했다 (로그인 필요로 추정). **운용 가능한 경로는 public CSV endpoint** `pd.read_csv("https://api.vitaldb.net/cases")`와 `https://api.vitaldb.net/trks`이다 (2026-05-16 검증; `docs/findings/pre_phase3_findings.md §1` 참조). 본 사실을 두드러지게 문서화한다. version 차이 (예: 시간 인덱싱 second vs sample)도 명시한다.

- [x] **[Priority: High]** `trks.csv`로부터 **196개 unique track 전수**를 enumerate하고 분류한다.
  - 입력: `docs/notebooks/_cache/trks.csv` (2026-05-16 캐시) 또는 `https://api.vitaldb.net/trks`에서 재조회
  - 출력: `docs/vitaldb_catalog.md`의 "Full track listing" 섹션 — 196 track 전체를 device prefix (`SNUADC/*`, `Solar8000/*`, `Primus/*`, `BIS/*`, `Orchestra/*`, `EV1000/*` 등)로 그룹화한 표. 컬럼: track별 n_cases, % of cohort, downstream consumer (있는 경우)
  - 의존성: 위 API reference task
  - 참고: 본 task는 `docs/project_brief.md §4`의 12-channel TODO를 해결한다. brief의 "12"는 placeholder였다 — 실제 코호트는 **196 unique track**과 닿으며, priority subset은 §4에서 enumerate되어 있다.

- [x] **[Priority: High]** Department별 stratified modality 가용성 표.
  - 입력: 코호트 manifest (또는 pre-filter case list), case별 track set
  - 출력: `docs/vitaldb_catalog.md`의 "Modality availability by department" 섹션 — priority modality (ABP family, PPG, ECG II, BIS, Sevo, RFTN, PPF, NIBP) 각각에 대해 department별 (General / Thoracic / Urology / Gynecology) + aggregate % 가용성을 보고. 가용성 < 50%인 cell은 `[CAVEAT]`로 표시.
  - 의존성: `plan_1.2` 부분 진행 cohort, 위 full track listing
  - 참고: 본 표는 `docs/project_brief.md §11.0` (mandatory department-stratified 보고)의 empirical 근거다. `docs/findings/pre_phase3_findings.md §5`가 2026-05-16 시점 스냅샷을 제공한다. 본 task는 그것을 카탈로그로 정식화한다.

- [x] **[Priority: Medium]** Case 수준 metadata 필드 (73 perioperative + 34 lab)를 downstream 용도와 매핑한다.
  - 입력: VitalDB case 수준 metadata sample
  - 출력: `docs/vitaldb_catalog.md`의 "Case metadata" 섹션 — 표 (field name, type, used by tool#)
  - 의존성: tool spec 진행 상황 (plan_1.7 부분 진행 시 정확도 향상)
  - 참고: 모든 임상 해석 (예: "이 lab value가 risk를 의미한다")은 `[CLINICIAN-REVIEW]` marker로 표기

- [x] **[Priority: Medium]** 재현성 (reproducibility)에 영향을 주는 version / format 차이를 문서화한다.
  - 입력: VitalDB release notes, `vitaldb` changelog
  - 출력: `docs/vitaldb_catalog.md`의 "Version notes" 섹션 — 단락 + version 고정된 package pin
  - 의존성: 없음
  - 참고: 향후 외부 검증 (MOVER, INSPIRE) 합류 가능성 염두

- [x] **[Priority: Low]** Project brief §4와 cross-check하여 필요한 수정 사항을 제안한다.
  - 입력: `docs/project_brief.md §4`
  - 출력: 본 plan 파일 내 PR-style markdown comment block에 필요한 업데이트 기록
  - 의존성: 위 task 전체
  - 참고: 본 plan은 `docs/project_brief.md`보다 늦게 작성되었다 — 충돌 시 catalog가 더 정확할 수 있다.

---

## Definition of done

- `docs/vitaldb_catalog.md`가 존재하며 다음을 모두 다룬다: waveform channels, numeric tracks, API, case metadata, version notes.
- 모든 임상 해석에 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` marker가 부착되어 있다.
- `docs/project_brief.md §4`의 TODO marker가 해결됨 (12-channel 목록 완료).

## Data contracts established here

- Waveform / numeric track naming convention (`plan_1.7_tool_spec.md`와 `plan_1.8_dual_mode_infra.md`에서 downstream으로 사용됨).

---

## Sprint 4 산출물 요약 (2026-05-17)

### Catalog 9 섹션 작성 — `docs/vitaldb_catalog.md`

1. **한 줄 요약** — 6,388 case · 196 track · 4 department
2. **API reference** — `load_clinical_data()` 0 row 검증 + CSV endpoint 우회 패턴
3. **Waveform channels (priority)** — 10 channel (ABP / PPG / ECG-II / EEG / CO₂ / AWP family)
4. **Numeric tracks (priority)** — Solar8000 / BIS / Orchestra / Primus subset 매핑
5. **Full 196-track listing** — Device prefix 별 11 group 전수
6. **Modality availability by department** — 10 modality × 5 column (All + 4 dept) 매트릭스
7. **Case metadata (74 fields)** — Identity / Outcome / Demographics / Surgery context / Preop labs / Airway / Intraop drugs+fluids
8. **Version notes** — `vitaldb 1.4.x`, `interval=1.0` 통일, 2026-05-16 snapshot
9. **Brief §4 cross-check** — TODO marker 해결 권고 3 항목

### 핵심 발견 (catalog 의 quote 가능한 사실)

- 총 case 6,388, subject 1:1, department 4 (General 4,930 / Thoracic 1,111 / Gynecology 230 / Urology 117)
- **196 unique track** (project_brief §4 의 "12-channel" placeholder 해결)
- ABP family 평균 가용성 58% — **department 별 큰 편차 (General 48% ~ Thoracic 97%)** → modality-agnostic 정책의 empirical 기반
- TIVA vs Volatile 비율 department 별 큰 차이 (Gynecology 의 PPF 2% 부재, Urology 의 SEVO 17% 부재)
- 100% 가용 track: `Solar8000/HR`, `Solar8000/PLETH_HR`, `Solar8000/PLETH_SPO2`
- `[CAVEAT]` mark = 가용성 < 50% modality / 부서 cell

### Brief §4 cross-check 권고 (paper-writer 협의 항목)

1. brief §4 의 "12 channel" placeholder → "10 priority channel + 186 long-tail track (196 total)" 로 갱신
2. brief §4 의 modality list 에 `Solar8000/HR` 명시적 추가 (현재 누락)
3. brief §10 modality-agnostic 정책에 department 별 ABP 가용성 편차 (48% ~ 97%) 강조

### 다음 plan 의 unblock

- **plan_1.2 (Cohort definition)** — modality availability table 이 cohort 진입 기준 입력
- **plan_1.3 (EMR tools)** — case metadata 74 field 의 downstream mapping 이 real EMR tool 의 schema source
- **plan_1.4 (Baselines)** — priority modality list 가 feature engineering 입력
- **plan_1.5 (Surgery context)** — department × optype 의 코호트 분포가 surgery_context priors 의 기초

### Schema contract 확정

- Track 이름 (예: `SNUADC/ART`) — 정식 source 는 본 catalog. 모든 downstream 코드 / 문서가 그대로 사용.
- Modality alias (예: ABP → ART / ART_MBP / EV1000_ART_MBP) — `vitalagent/fm/mock_rule_based.py::_ABP_ALIASES` 와 1:1 일치 (이미 정합)
- Case metadata field 이름 — 본 catalog §6 가 정식 source (plan_1.3 의 real EMR tool 의 schema)

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — §3 unit 정확성, §5 modality 가용성 해석, §6 downstream tool mapping, §8 brief §4 cross-check 권고
