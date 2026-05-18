# ADR-013 — Intervention Response as Supervised Conditional Generation

- **Status**: `[DECISION PENDING]` `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`
- **Date proposed**: 2026-05-16
- **Decision drivers**: project-planner (proposal), signal-ingest-engineer (학습 페어 추출 owner), 이형철 교수님 그룹 (임상 confounding 검토)
- **상위 결정 의존성**: 본 ADR은 `ADR-012`가 Accepted로 확정될 경우에만 발효된다.

> `[DECISION PENDING]` — 회의 후 Accepted 또는 Rejected. 그 전까지 `docs/project_brief.md`와 plan 파일은 수정하지 않는다.

---

## Context (배경)

`ADR-012`는 VitalAgent task suite의 Tier 4 (Intervention Response, 3 tasks)를 제안한다. 본 ADR은 Tier 4를 *어떻게 학습할지*에 대한 별도 결정이다.

Tier 4의 3 task (T4.1 Vasopressor, T4.2 Fluid, T4.3 Anesthetic change)는 모두 공통 형식을 갖는다.

```
Input:  pre_signal (intervention 시작 직전 5분 window) + intervention spec (약물 / dose)
Output: post_signal (intervention 후 5분 trajectory) + uncertainty
```

이는 FM의 일반 forecasting 기능과 구조적으로 유사하지만, **intervention 조건 (conditioning)**이 추가되어야 한다.

---

## Decision (제안 결정 — 미확정)

옵션 **(B) Conditional Generation**을 채택한다.

- Forecasting head + intervention conditioning (cross-attention 또는 token concatenation)
- Input: `pre_signal: dict[str, Tensor]` + `intervention: InterventionSpec`
- Output: `post_signal: dict[str, Tensor]` + `uncertainty: Tensor`

### InterventionSpec (대략의 형태 — 정식 dataclass는 plan 단계에서 확정)

```python
@dataclass
class InterventionSpec:
    kind: Literal["vasopressor", "fluid", "anesthetic_change"]
    drug_or_agent: str          # e.g., "phenylephrine", "crystalloid", "sevoflurane"
    dose_amount: float
    dose_unit: str              # e.g., "ug", "mL", "MAC"
    start_time_s: float
    end_time_s: float | None    # bolus는 None, infusion은 종료 시점
```

### 학습 페어 추출 (Pair extraction) — high-level 방법론

| 단계 | 내용 |
|------|------|
| 1 | VitalDB EMR (`Orchestra/*`, `intraop_*` 컬럼)에서 intervention 시점 / dose 추출 |
| 2 | 각 intervention에 대해 pre 5분 + post 5분 signal window 구성 |
| 3 | Confounding filter 적용 (아래 *Confounding 처리 원칙* 참조) |
| 4 | Surgery type, baseline state 통계 첨부 |
| 5 | Train / val / test split (case-level — leakage 방지) |

### Confounding 처리 원칙

| 원칙 | 적용 |
|------|------|
| **단일 intervention window** | pre 5분 + post 5분 동안 동종 intervention 외 추가 intervention이 없는 window만 선별 |
| **Baseline state 매칭** | pre-intervention MAP / HR 분포를 학습 / 평가 split 간 매칭 |
| **Surgery phase 명시** | induction / maintenance / emergence를 conditioning 일부로 포함 — `plan_1.5_surgery_context.md`의 surgery context 활용 |
| **Concurrent EMR event 표기** | 동시에 진행 중인 다른 약물·수액은 InterventionSpec에 보조 field로 첨부 (학습 input에 포함) |

위 원칙은 가설이며, 회의에서 임상의 검토를 받는다 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`.

---

## Alternatives Considered (검토한 대안)

| Alternative | Why considered / 기각 가능성 |
|-------------|------------------------------|
| **(a) Zero-shot (FM 일반 forecasting 재활용)** | 학습 비용 0. 그러나 intervention 정보가 신호에 implicit하므로 정확도 낮음. paper 차별점 약함. |
| **(b) (제안) Supervised conditional generation** | 명확한 차별점, intervention 정보가 explicit conditioning으로 들어감. 학습 페어 추출 비용 존재. |
| **(c) Counterfactual / causal inference (twins)** | 학문적 매력 있음. 그러나 VitalDB 단일 dataset에서 causal claim의 외부 타당성 (external validity)이 약함. PoC 범위 초과. |

---

## Consequences (예상 결과)

### Positive (긍정적 영향)

- VitalAgent의 가장 인상적 차별점 — "intervention을 알면 trajectory가 달라지는가"에 대한 정량 답변 가능.
- Stage 4 임상의 평가에서 시나리오성이 가장 강한 산출물.
- Forecasting baseline (Tier 3 T3.1)과의 비교가 자연스럽게 ablation 결과가 됨.

### Negative (부정적 영향)

- 학습 페어 추출 파이프라인 별도 구현 필요 — `plan_1.4` baseline과 별도 작업.
- Confounding 처리 logic의 미세 결정이 학습 신호 품질을 크게 좌우.

### Risks & mitigations (위험 및 대응책)

| Risk | Mitigation |
|------|------------|
| Tier 4 학습 페어가 ≥ 1,000 case 확보되지 않음 | 사전 분석: `Orchestra/PHEN_*` (phenylephrine) 등 각 약물 채널의 case-level 가용성 표 작성 (회의 자료) |
| Confounding 처리가 부적절하여 학습 신호 노이즈 | 회의에서 confounding 처리 원칙을 명시적으로 검토받는다. 학습 후 `assess_signal_quality` 기반 회고 검토. |
| Intervention 시점 추출 정확도가 EMR 신뢰도에 묶임 | VitalDB EMR은 timestamp가 정확한 편이지만, 일부 약물은 manual entry — `plan_1.3_emr_tools.md` Tool 9 / 10 구현 시 동일 logic을 활용 |
| Counterfactual claim으로 오해될 위험 | paper에서 "supervised observational prediction of intervention-conditioned trajectory"로 정확히 표기 — causal claim 아님 |

---

## Open questions (확정 회의 안건)

1. **Pre / post window 길이**: 5분 / 5분이 적절한지. 약물 종류별 차등 (vasopressor 단시간 vs sevoflurane 장시간)?
2. **Confounding 처리 원칙 4개 적정성**: 단일 intervention window 정의, baseline 매칭 기준, surgery phase conditioning, concurrent EMR 처리.
3. **Tier 4 학습 페어 ≥ 1,000 case 달성 가능성**: 사전 분석 결과로 회의에서 검토.
4. **Conditioning 구조**: cross-attention vs token concat — 본 결정은 implementation 단계 (`plan_2.x`)로 위임 가능.

---

## References (참조)

- `docs/decisions/ADR-012-surgery-specific-downstream-tasks.md` — 상위 결정 (Tier 4 도입)
- `docs/project_brief.md §3` — FM 일반 downstream 9번 (cross-modal reconstruction + intra-modal forecasting) — 본 결정과 구조적으로 가까움
- `docs/project_brief.md §4.3` — Anesthesia drug priority (RFTN20 first-class) — Tier 4 학습 페어 추출의 채널 가용성 근거
- `.plans/stage1_preparation/plan_1.3_emr_tools.md` — EMR tool 8 / 9 / 10 (intervention 추출 로직)
- `docs/meetings/agenda_vital_group_review.md` — 본 ADR을 회의 안건 2번 / 3번으로 등록
