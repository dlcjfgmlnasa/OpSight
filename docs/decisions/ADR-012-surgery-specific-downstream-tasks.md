# ADR-012 — Surgery-Specific Downstream Tasks for OpSight

- **Status**: `[DECISION PENDING]` `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`
- **Date proposed**: 2026-05-16
- **Decision drivers**: project-planner (proposal), 이형철 교수님 그룹 (임상 검토 owner), signal-ingest-engineer (학습 가능성 검토), langgraph-engineer (tool 통합 검토)

> 본 ADR은 아직 확정되지 않았다. 회의 후 Accepted 또는 Rejected로 전환된다. 그 전까지 본 문서는 *기록*과 *논의 기반*의 역할만 한다. `docs/project_brief.md`는 수정하지 않는다.

---

## Context (배경)

본 논문의 Foundation Model (BFM)은 K-MIMIC ICU pretrained로, 13개 general downstream task에 대해 학습 중이다 (`docs/project_brief.md §3`). 이 task suite는 ICU monitoring 전반에 대한 일반성을 목표로 한다.

OpSight는 OR (수술실, operating room) 환경에서 동작한다. OR은 ICU와 다음과 같이 distribution과 임상 question이 다르다.

- 마취 (anesthesia) 상태 — 약물 효과로 인한 신호 dynamics 변화
- 명시적 시점 이벤트 (induction, incision, emergence) 존재
- 임상의의 능동적 개입 (intervention) 빈도가 ICU보다 높음
- 환자 baseline이 비교적 안정적 (vs ICU의 다중 합병증)

일반 13 task만으로 OR-specific 평가를 수행하면 OpSight의 핵심 가치인 **surgery-aware**가 희석된다. 또한 paper의 contribution이 "FM downstream 활용 사례"에 머무를 위험이 있다.

---

## Decision (제안 결정 — 미확정)

FM downstream task suite와 OpSight task suite를 **분리**한다.

| 구분 | task suite | 데이터 | 개수 |
|------|-----------|--------|------|
| 본 논문 FM (별도 프로젝트) | general ICU downstream | K-MIMIC ICU | 13 |
| OpSight (본 PoC) | **OR-specific downstream** | VitalDB | **13** (4-tier) |

### OpSight task suite — 13 tasks, 4 tier

#### Tier 1: Acute Event (5)

| # | Task | Horizon | Label 정의 |
|---|------|---------|-----------|
| T1.1 | Hypotension (저혈압) | 5 min | MAP < 65 mmHg ≥ 1 min (brief §5와 동일) |
| T1.2 | Hypotension (저혈압) | 15 min | 동일 정의, 15분 horizon |
| T1.3 | Hypotension severe | 5 min | MAP < 55 mmHg ≥ 1 min |
| T1.4 | Hypertension event (고혈압) | 5 min | `[CLINICIAN-REVIEW]` — threshold 결정 필요 (예: MAP > 110) |
| T1.5 | Cardiac arrest (심정지) | 5 min | brief §3 downstream task 4와 동일 정의 |

#### Tier 2: Surgery-specific Event (3)

| # | Task | Horizon | Label 정의 |
|---|------|---------|-----------|
| T2.1 | Bradycardia / Tachycardia event | 5 min | HR < 50 또는 > 120 ≥ 1 min `[CLINICIAN-REVIEW]` — threshold |
| T2.2 | Hypoxemia (저산소증, hypoxemia) | 5 min | SpO2 < 90% ≥ 1 min |
| T2.3 | Bleeding suspicion (출혈 의심) | 5 min | Composite label — `[CLINICIAN-REVIEW]` (예: MAP 급강하 + HR 급증 + 수혈 시작) |

#### Tier 3: Generative / Forecasting (2)

| # | Task | Output |
|---|------|--------|
| T3.1 | ABP forecasting | next 5 min ABP trajectory + uncertainty |
| T3.2 | Cross-modal reconstruction | 누락된 modality를 다른 modality로부터 재구성 (brief §3 downstream task 9와 동일) |

#### Tier 4: Intervention Response (3) ★ 핵심 차별점

| # | Task | Output |
|---|------|--------|
| T4.1 | Vasopressor response (혈관수축제, vasopressor) | phenylephrine / ephedrine / norepinephrine 투여 후 5분 signal trajectory |
| T4.2 | Fluid response (수액 반응) | crystalloid (정질액) / colloid (교질액) / transfusion (수혈) 후 5분 trajectory |
| T4.3 | Anesthetic change response | sevoflurane (세보플루레인) / propofol (프로포폴) 농도 변경 후 5분 trajectory |

Tier 4 학습 방법론은 별도 ADR-013에서 결정된다.

---

## Alternatives Considered (검토한 대안)

| Alternative | Why considered / 기각 가능성 |
|-------------|------------------------------|
| **(a) FM 13 task suite 그대로 reuse** | 단순함, 학습 비용 0. 그러나 OR specificity 손실. surgery-aware 차별점이 paper에 드러나지 않음. |
| **(b) VitalDB에 1–2개 task만 추가** | 학습 비용 최소. 그러나 Tier 4 (intervention response) 차별점 부재. paper contribution 약화. |
| **(c) (제안) FM general + OpSight OR-specific 13 task 분리** | 최대 차별점 + paper-worthy contribution. 학습 + 평가 비용 약 2배. |

---

## Consequences (예상 결과)

### Positive (긍정적 영향)

- **Surgery-aware** 핵심 가치를 평가 단계에서 명확히 표현 가능.
- Paper의 contribution이 "FM 활용"이 아닌 "OR-specific agent + intervention reasoning"으로 격상.
- Tier 4 intervention response는 임상의 평가 (Stage 4)에서 가장 인상적인 시연이 될 가능성이 높음.
- VitalDB의 OR-specific 데이터 자산을 fully 활용.

### Negative (부정적 영향)

- 학습 시간 + GPU 비용 증가. Stage 2/3의 critical path에 영향 가능.
- Baseline 비교 부담 증가 (13 task 각각에 대해 baseline 측정).
- `master_plan.md §8 Risk Register`에 신규 risk 등재 필요.

### Risks & mitigations (위험 및 대응책)

| Risk | Mitigation |
|------|------------|
| Tier 4 학습 페어 추출 비용이 비현실적 | ADR-013에서 별도 결정. 학습 페어 ≥ 1,000 cases 확보 가능성을 사전 검증. |
| Tier 2 threshold 임상적 부적절 | `[CLINICIAN-REVIEW]` marker로 회의에서 확정 |
| 13 task 학습 시간이 Stage 3을 잠식 | Mock FM Tier 3 (`plan_1.7.5`)에서 task별 baseline을 우선 구현하여 risk hedge |

---

## Open questions (확정 회의 안건)

1. **Tier 1 hypertension threshold**: MAP > 110 vs > 120 vs surgery type별 차등.
2. **Tier 2 bradycardia/tachycardia threshold**: HR < 50 / > 120 vs age-adjusted.
3. **Tier 2 bleeding suspicion composite 정의**: MAP 강하 + HR 급증 + 수혈 시작 외 추가 criteria.
4. **Tier 4 학습 가능성**: 학습 페어 충분히 추출되는지 (예비 분석은 ADR-013 channel availability 표 활용).
5. **13개로 고정 vs 더 적게 (10개)**: Stage 3 일정과 학습 비용 트레이드오프.

---

## References (참조)

- `docs/project_brief.md §3` — FM 13 general downstream
- `docs/project_brief.md §5` — Hypotension event 정의
- `docs/project_brief.md §11.2` — baselines
- `docs/decisions/ADR-013-intervention-response-supervised.md` — Tier 4 학습 방법론
- `docs/meetings/agenda_vital_group_review.md` — 본 ADR을 회의 안건 1번으로 등록
