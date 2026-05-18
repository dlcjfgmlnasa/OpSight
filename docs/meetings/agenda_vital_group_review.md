# 회의 안건 — Vital Group Review

> 이형철 교수님 그룹 검토 회의용 누적 안건 (rolling agenda).
> 항목별 결정 결과는 회의 후 본 파일에 기록되고, 관련 ADR / brief / plan 파일이 일괄 갱신된다.
> 그 전까지 항목은 `[DECISION PENDING]` 상태로 유지된다.

마지막 갱신: 2026-05-16.
다음 회의: TBD (`[DECISION PENDING]` 항목 N건 누적 시 일정 조율).

---

## 안건 — 미결 항목 (Open)

### 1. 수술실 (OR) Specialist Downstream Tasks 채택 여부

- 관련 ADR: `docs/decisions/ADR-012-surgery-specific-downstream-tasks.md` `[DECISION PENDING]`
- 핵심 질문:
  - FM downstream 13 task suite (general)와 OpSight task suite (OR-specific)를 분리하는 것이 적절한가?
  - 제안한 Tier 1–4 구성 (5+3+2+3=13)이 임상적으로 적절한가?
- 검토 자료: ADR-012 §Decision의 4-tier 표
- Open question 5건은 ADR-012 §"Open questions" 참조

### 2. Intervention Response 학습 방법론

- 관련 ADR: `docs/decisions/ADR-013-intervention-response-supervised.md` `[DECISION PENDING]`
- 핵심 질문:
  - Tier 4 (Vasopressor / Fluid / Anesthetic change response) 학습을 supervised conditional generation (옵션 B)으로 수행하는 것이 적절한가?
  - 대안 (zero-shot, counterfactual) 대비 이득이 비용을 정당화하는가?
- 검토 자료: ADR-013 §Decision의 학습 페어 추출 + Confounding 처리 4 원칙

### 3. Tier 4 학습 페어 추출 방법론 (상세)

- 관련 ADR: `docs/decisions/ADR-013-intervention-response-supervised.md`
- 핵심 질문:
  - First-class intervention 목록 확정 (phenylephrine / ephedrine / norepinephrine / crystalloid / colloid / transfusion / sevoflurane / propofol)
  - 최소 sample size (≥ 1,000 case) 달성 가능성 — 사전 분석 결과 검토
  - Surgery type별 분리 학습 vs unified 학습
- 검토 자료: VitalDB intervention 채널 가용성 사전 분석 (회의 직전 작성, 미정)

### 4. Pediatric / ASA = 6 inclusion 결정

- 관련 위치: `docs/project_brief.md §4.1`, `.plans/stage1_preparation/plan_1.2_cohort_definition.md` Pre-task blocker, `master_plan.md §8 Risk Register`
- 핵심 질문:
  - Q1. Pediatric (`age < 18`) inclusion: (A) 전체 포함 vs (B) 성인만 (`age ≥ 18`)
  - Q2. `ASA = 6` (뇌사 장기 기증자, brain-dead organ donor) inclusion: (A) 포함 vs (B) 제외
- 결정 영향: 최종 코호트 크기 변동 (현재 5,946 cases 기준)

### 5. 임상의 평가 (Clinician evaluation) commitment

- 관련 위치: `docs/project_brief.md §11.1`, `master_plan.md §8 Risk Register`
- 핵심 질문:
  - 평가자 정확한 N 확정 (5 vs 7)
  - 평가 가능 시점 (Stage 4 = Month 7–8)
  - 200–300 브리프 평가 분량 commitment
  - Blinded comparison 운영 방식 (UI / spreadsheet / 일정)

### 6. FM 학습 진행 상황 + 변경 가능성 공유

- 관련 위치: `docs/project_brief.md §3` (FM context, 학습 약 2개월 후 완료 예정)
- 핵심 질문:
  - 학습 진행 timeline 확인 — Stage 2 시작 시점 (Month 3)에 도착 가능한가?
  - 학습 도중 architecture / objective 변경 가능성 — OpSight 측에서 대응 가능한가?
  - 13 downstream task 중 미확정 4건 (T10–T13) 확정 가능성

### 7. Tier 0 (Current State Assessment) capability 채택 여부

- 관련 ADR: `docs/decisions/ADR-014-tier0-current-state-assessment.md` `[DECISION PENDING]`
- 상위 의존: 본 안건은 안건 1번 (ADR-012)이 Accepted로 결정될 경우에만 발효된다. 함께 검토.
- 핵심 질문:
  - 임상 사고 흐름 (state → trend → prediction → response)에서 빠진 "현재 상태 평가 (Tier 0)"를 capability로 추가하는 것이 적절한가?
  - 제안한 3 capability (#14 Hemodynamic state classification, #15 Anesthesia state assessment, #16 Surgical phase recognition) 구성이 적절한가?
  - Hybrid 전략 (#14만 supervised, #15 hybrid, #16 rule + LLM)이 학습 부담 trade-off로 합리적인가?
- 검토 자료: ADR-014 §"각 capability 상세" + §"Phase 1 vs Phase 2"
- Open question 5건은 ADR-014 §"Open questions" 참조

---

## 안건 — 결정 완료 (Closed)

(현재 없음. 회의 후 결정된 항목은 본 섹션으로 이동하고 결과를 한 줄 요약한다.)

---

## 본 안건 운영 규칙

1. 새 `[DECISION PENDING]` 항목 발생 시 본 파일에 즉시 등록된다 (담당: project-planner).
2. 회의 후 각 항목은 다음 중 하나로 전환된다:
   - **Accepted** — 관련 ADR을 `Accepted` 상태로 갱신하고 `docs/project_brief.md` / plan 파일에 일괄 반영
   - **Rejected** — 관련 ADR을 `Rejected` 상태로 갱신하고 본 안건은 Closed로 이동
   - **Deferred** — 다음 회의로 미룬다. Open 상태 유지.
3. 본 파일은 회의 외 일상 작업의 SoT가 아니다 — 결정 확정된 사항은 ADR / brief / plan을 보아야 한다.
