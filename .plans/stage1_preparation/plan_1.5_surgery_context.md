# plan_1.5 — Surgery-aware Context Taxonomy

**Owner**: `vitaldb-domain-expert`
**Assist**: `llm-prompt-engineer` (prompt embedding 시점)
**Status**: ✅ done (Sprint 5, 2026-05-17) — `surgery_context.yaml` v1 (4 type × 3 phase = 12 cell + 11 optype reference) + tool 15 yaml-backed 교체 + 2 신규 test.
**Goal**: agent가 `docs/project_brief.md §1` Core Characteristic #4의 "surgery-aware"를 충족할 수 있도록 surgery-type + surgery-phase taxonomy와 그에 대응하는 *reasoning hint* (임상 단정 아님)를 정의한다.

---

## Tasks

- [x] **[Priority: High]** 기존 VitalDB `department` 4-bucket을 본 프로젝트 surgery-type taxonomy로 **confirm 및 freeze** (재매핑 불필요).
  - 입력: `docs/findings/pre_phase3_findings.md §2`, VitalDB `department` field
  - 출력: `docs/surgery_context.yaml`의 `surgery_types` section — enum + 카테고리별 짧은 설명. 4 bucket은 **VitalDB의 `department` 값 그대로**: `General surgery`, `Thoracic surgery`, `Gynecology`, `Urology`. 코호트 분포 (2026-05-16): 77.2% / 17.4% / 3.6% / 1.8%.
  - 의존성: `plan_1.2`
  - 참고: 본 task는 원래 "taxonomy 정의"로 framing되었으나, pre-Phase 3 empirical 검증 결과 VitalDB가 이미 정확히 본 4-bucket axis를 publish하고 있음이 확인되었다. 따라서 작업은 **import + freeze**이며 설계 없음. 더 세밀한 `optype` axis (11 bucket — `Colorectal`, `Biliary/Pancreas`, `Stomach`, `Breast`, `Transplantation` 등)는 **mid-granularity 옵션**으로 동일 YAML의 `optype_subcategories`에 reference로 기록한다. 본 프로젝트의 surgery-type axis는 `department`로 유지된다.

- [x] **[Priority: High]** Surgery-phase taxonomy 정의.
  - 입력: anesthesia 문헌의 phase 정의; VitalDB phase marker (존재 시)
  - 출력: `docs/surgery_context.yaml`의 `phases` section — enum (induction / maintenance / emergence) + 휴리스틱 경계 정의
  - 의존성: 없음
  - 참고: phase 경계는 시간 비율 기반 휴리스틱 (예: 첫 15분 = induction, 마지막 10분 = emergence). `[CLINICIAN-REVIEW]` marker.

- [x] **[Priority: High]** (surgery_type × phase) → reasoning hint 매핑.
  - 입력: 위 두 task
  - 출력: `docs/surgery_context.yaml`의 `hints` section — 각 cell은 짧은 한글 reasoning hint를 담는다 (예: "thoracic / induction → 흉강 진입 시 일과성 저혈압 빈도 알려져 있음")
  - 의존성: 위 두 task
  - 참고: **모든 hint는 통계적 / 일반적 경향**을 표현하며 진단·치료 권고가 아니다. cell별로 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` 명시.

- [x] **[Priority: Medium]** Sanity check: 코호트 surgery-type 분포 vs taxonomy 커버리지.
  - 입력: manifest 분포, taxonomy
  - 출력: `docs/surgery_context_coverage.md` — named category가 cover하는 코호트 비율; "other" bucket 크기
  - 의존성: 위 task
  - 참고: "other" 비율이 너무 크면 분류 재설계 필요.

- [x] **[Priority: Medium]** `plan_1.6_system_prompt` 및 `plan_1.7_tool_spec` (tool 15 `surgery_context_awareness`)으로의 handoff note.
  - 입력: 위 task 모두
  - 출력: 본 plan 파일에 "Consumers" section 추가 — `surgery_context.yaml`의 어떤 key가 어디서 사용되는지 매핑
  - 의존성: 없음
  - 참고: downstream 단위 변경 시 회귀 방지.

---

## Definition of done

- `docs/surgery_context.yaml`이 존재하며 `surgery_types`, `phases`, `hints` section 보유.
- 모든 임상 hint가 `[CLINICIAN-REVIEW]` marker로 wrap됨.
- Coverage report가 named category로 코호트의 ≥ 80% cover.

## Data contracts established here

- **`surgery_context.yaml` schema** (`plan_1.7` tool 15와 `plan_1.6` system prompt에서 소비됨)

---

## Sprint 5 산출물 (2026-05-17)

### 산출물

- `docs/surgery_context.yaml` v1 — 4 surgery_types (`department` frozen) + 11 optype_subcategories + 3 phases (induction/maintenance/emergence) + 12 hint cell (4×3) + consumers map
- `docs/surgery_context_coverage.md` — 100% named category coverage (DoD ≥ 80% 충족)
- `opsight/tools/auxiliary_tools.py` — Tool 15 STUB → yaml-backed 교체 (graceful fallback 유지)
- 2 신규 test (yaml load 검증 + 4×3 cell 전수 검증)

### 핵심 정책

- `surgery_types` 는 VitalDB `department` 4-bucket frozen — 재매핑 없음 (pre-phase 3 finding)
- `phases` 는 시간 비율 기반 휴리스틱 (induction = 시작~opstart, emergence = opend~aneend)
- 12 hint cell 모두 `[CLINICIAN-REVIEW]` marker 부착
- Hint phrasing 은 통계적/일반적 경향만 — 진단/처방 권고 X

### Consumers map (downstream 회귀 방지)

- `opsight/tools/auxiliary_tools.py::tool_surgery_context_awareness` — Tool 15 (현재 활성)
- `prompts/v1_heavy_deep_brief.md` (v2 follow-up) — §[Surgery context] section
- `opsight/baselines/labels.py + features.py` — phase boundary 휴리스틱 활용 가능

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — 12 hint cell 의 임상적 적절성 + phase boundary 휴리스틱 + optype subcategory 매핑.
