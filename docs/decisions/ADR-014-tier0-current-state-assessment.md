# ADR-014 — Tier 0 Current State Assessment Capabilities

- **Status**: `[DECISION PENDING]` `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`
- **Date proposed**: 2026-05-16
- **Decision drivers**: project-planner (proposal), signal-ingest-engineer (학습 / hybrid 구현 owner), llm-prompt-engineer (#16 LLM 부분), 이형철 교수님 그룹 (임상 검토)
- **상위 결정 의존성**: 본 ADR은 `ADR-012`가 Accepted로 확정될 경우 함께 발효된다. ADR-012의 13 task suite를 **16 capability**로 확장한다.

> `[DECISION PENDING]` — 회의 후 Accepted / Rejected. 그 전까지 `docs/project_brief.md`와 plan 파일은 수정하지 않는다.

---

## Context (배경)

임상의의 사고 흐름은 일반적으로 다음 순서를 따른다.

> **현재 상태 (state) → 추세 (trend) → 예측 (prediction) → 대응 (response)**

`ADR-012`의 Tier 1–4는 다음을 cover한다.

- Tier 1: Acute Event — *예측*
- Tier 2: Surgery-specific Event — *예측*
- Tier 3: Generative / Forecasting — *추세 + 예측*
- Tier 4: Intervention Response — *대응*

즉 **현재 상태 평가 (current state assessment)**가 빠져 있다. 임상의 평가 시 "현재 상태가 무엇인가"에 대한 명시적 답변이 없으면 브리프 (brief)의 §1 [Surgery context], §2 [Signal status], §3 [Assessment confidence] 항목이 LLM in-context inference에만 의존하게 된다 — supervised guarantee 없음.

본 ADR은 Tier 0을 신설하여 임상 사고 흐름의 시작점을 명시적 capability로 표현한다.

---

## Decision (제안 결정 — 미확정)

`ADR-012`의 task suite를 **13 task → 16 capability**로 확장한다. 신규 3개는 Tier 0에 속한다.

### Tier 0: Current State Assessment (3 capability)

| # | Capability | 구현 전략 | 학습 부담 |
|---|-----------|-----------|-----------|
| **14** | Hemodynamic state classification | **Supervised**, weak label로 시작 | +1 supervised head |
| **15** | Anesthesia state assessment | **Hybrid** — BIS rule-based + supervised | rule + light supervised |
| **16** | Surgical phase recognition | **Hybrid** — rule-based + LLM | 신규 학습 head 없음 |

세 capability 중 **#14만 신규 supervised head**가 추가된다. #15, #16은 hybrid / rule-based로 학습 비용이 거의 0이다 (#16은 LLM in-context로 처리).

### 각 capability 상세 (제안)

#### #14 Hemodynamic state classification (혈역학 상태, hemodynamic state)

- 출력: 4-state classification — 예: `STABLE / CAUTION / WARNING / CRITICAL`
- Weak label 정의 (제안, `[CLINICIAN-REVIEW]`):
  - `STABLE`: MAP 65–110 + HR 50–100 + 추세 stable
  - `CAUTION`: 위 범위 이탈하지만 사건성은 없음
  - `WARNING`: 단일 vital의 사건 임박 (예: MAP < 70 + 하강 추세)
  - `CRITICAL`: 다중 vital 사건 또는 acute event 진행 중
- 학습 데이터: VitalDB 코호트에서 MAP / HR / signal quality로부터 weak label 생성 후 학습. Phase 2에서 임상의 라벨링으로 강화 가능.

#### #15 Anesthesia state assessment (마취 상태, anesthesia state)

- 출력: depth-of-anesthesia 분류 (예: `LIGHT / ADEQUATE / DEEP`) + confidence
- 구현:
  - **Rule-based**: BIS 값 (`BIS/BIS` 채널, 코호트의 91.9%에서 가용) — 표준 threshold 적용
  - **Supervised hybrid**: BIS가 없거나 SQI 낮은 case에서 ECG / ABP / capnography로부터 추정 (light 학습 head 또는 #14의 보조 출력)
- `[CLINICIAN-REVIEW]` — BIS threshold (예: 40–60 = ADEQUATE)의 임상적 적절성

#### #16 Surgical phase recognition (수술 단계, surgical phase)

- 출력: `induction / maintenance / emergence` (이미 `plan_1.5_surgery_context.md`에서 surgery phase 정의됨)
- 구현:
  - **Rule-based**: VitalDB의 `anestart` / `aneend` / `opstart` / `opend` timestamp와 시간 비율 휴리스틱
  - **LLM-assisted**: 휴리스틱 모호 영역 (transitions)을 LLM in-context로 정제
- 신규 supervised head **없음**. `plan_1.5`의 surgery_context.yaml 산출물을 그대로 활용.

### Phase 1 (본 PoC) vs Phase 2 (future)

| 단계 | Tier 0 항목 | 구현 깊이 |
|------|-------------|-----------|
| **Phase 1 (본 PoC, Month 1–10)** | #14 supervised (weak label), #15 hybrid, #16 rule + LLM | 즉시 구현 가능 |
| **Phase 2 (PoC 후속, NRF 도전형 2–3년차)** | #14 강한 supervision (확장 시), #15 fully supervised (필요 시) | 본 PoC 범위 밖 |

---

## Alternatives Considered (검토한 대안)

| Alternative | Why considered / 기각 가능성 |
|-------------|------------------------------|
| **(a) Tier 0 없이 ADR-012만 진행** | 학습 부담 0. 그러나 paper에서 "현재 상태 평가는 LLM in-context로만"이 약점으로 지적될 가능성. 브리프의 §1–§3 supervised guarantee 부재. |
| **(b) Tier 0를 모두 supervised로 학습** | 가장 강한 guarantee. 그러나 학습 비용 과다 (#15, #16에 신규 head). Stage 3 일정 위협. |
| **(c) (제안) Hybrid — #14만 supervised, #15-16은 hybrid/rule** | 학습 부담 +1로 최소. 임상 사고 흐름 완성. Phase 2에서 강화 여지. |

---

## Consequences (예상 결과)

### Positive (긍정적 영향)

- 임상 사고 흐름 (state → trend → prediction → response) 완성 — paper Methods §의 흐름 강화.
- 브리프 §1 [Surgery context], §2 [Signal status], §3 [Assessment confidence]에 supervised 근거 부여.
- Capability 수 13 → 16으로 확장 (paper Tables에 자연스럽게 정리됨).
- 학습 비용 증가는 최소 (#14 하나만 신규 supervised head).

### Negative (부정적 영향)

- 평가 항목 수가 늘어남 (#14는 4-class classification 평가 추가 필요).
- 회의에서 4-state weak label 정의에 대한 합의가 필요 — 합의 실패 시 단순화 (2-state) fallback.

### Risks & mitigations (위험 및 대응책)

| Risk | Mitigation |
|------|------------|
| Weak label 품질이 낮아 #14 학습이 무의미 | Phase 1에서는 weak label로 시작하고 신뢰 구간 (CI)을 함께 보고. Phase 2에서 임상의 라벨링으로 강화 경로 명시. |
| BIS rule threshold 임상 부적절 | `[CLINICIAN-REVIEW]` marker로 회의 결정 |
| Surgical phase 정의가 모호한 transition 구간 | LLM-assisted 정제 (#16) — 휴리스틱 단독 결과 + LLM confidence 함께 보고 |
| 16 capability로 확장 시 Stage 3 일정 잠식 | #14만 신규 학습이므로 영향 작음. #15-16은 rule/LLM이므로 Stage 1 (`plan_1.5`)에서 흡수 가능. |

---

## Open questions (확정 회의 안건)

1. **4-state weak label 정의**: `STABLE / CAUTION / WARNING / CRITICAL` threshold가 임상적으로 합당한가? 단순화 (2-state `STABLE / UNSTABLE`)가 더 안전한가?
2. **BIS rule threshold**: `LIGHT < 40 / ADEQUATE 40–60 / DEEP > 60` 적정성.
3. **Surgical phase**: `induction / maintenance / emergence` 3-state로 충분한가? Subcategory (예: pre-incision, post-incision)가 필요한가?
4. **16-capability 확장 시 Stage 3 일정 영향**: 학습 head 1개 추가는 일정에 수용 가능한가?
5. **Phase 2 (future) commitment 표현 수준**: paper Discussion §에서 어디까지 언급할 것인가?

---

## References (참조)

- `docs/decisions/ADR-012-surgery-specific-downstream-tasks.md` — 상위 결정 (Tier 1–4)
- `docs/decisions/ADR-013-intervention-response-supervised.md` — Tier 4 학습 방법론
- `.plans/stage1_preparation/plan_1.5_surgery_context.md` — Surgical phase 정의 출처
- `docs/project_brief.md §8` — 브리프 9-section template (#1 [Surgery context], #2 [Signal status], #3 [Assessment confidence]이 Tier 0 출력의 소비처)
- `docs/meetings/agenda_vital_group_review.md` — 본 ADR을 회의 안건 7번으로 등록
