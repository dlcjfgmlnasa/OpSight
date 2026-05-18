# Knowledge / Comparative Tools (13–14) — Spec (plan_1.7)

> 2 개 Knowledge tool 의 정식 schema + LLM description + failure mode.
> ⚠️ **Stage 1 prototype 단계에서는 STUB**. Real 구현 (cohort retrieval index, intervention DB) 은 후속 plan.
> Description tone: `prompts/v1_tool_description_style.md` 의 4-line skeleton 준수.

---

## Tool 13 — `find_similar_cases`

### 목적

현재 환자의 state 와 유사한 과거 VitalDB case k 개를 retrieval. Cohort-level 비교 reasoning 에 사용 (brief `[Similar trajectory]` section).

### Input

```json
{
  "required": [],
  "properties": {
    "k":                {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
    "surgery_type":     {"type": "string", "description": "Filter by surgery type"},
    "max_age_diff":     {"type": "integer", "minimum": 0, "default": 10},
    "asa_filter":       {"type": "array", "items": {"type": "integer"}},
    "current_state":    {"type": "object", "description": "Optional summary of current state for similarity scoring"}
  }
}
```

### Output

```json
{
  "properties": {
    "similar_cases": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["case_id", "similarity_score"],
        "properties": {
          "case_id":          {"type": "string"},
          "similarity_score": {"type": "number", "minimum": 0, "maximum": 1},
          "summary":          {"type": "object"},
          "outcome":          {"type": ["object", "null"]}
        }
      }
    },
    "meta": {"type": "object"}
  }
}
```

### LLM Description (KR)

```
용도: 현재 case 와 유사한 과거 코호트 case k 개를 retrieval. 유사도는 (surgery type,
       age, ASA, 최근 risk trajectory) 기준 cosine / euclidean 등.
입력:
  - k: 반환 case 수 (기본 5)
  - surgery_type: 필터링 (예: "general", "thoracic")
  - max_age_diff: 나이 차이 허용 범위 (기본 10년)
  - asa_filter: ASA 등급 필터 list
  - current_state: 현재 환자 state 요약 (선택)
출력:
  - similar_cases: [{case_id, similarity_score, summary, outcome}, ...]
  - meta: cohort_index_version, retrieval_method 등
주의:
  - Stage 1 prototype 에서 STUB — 빈 list 반환 + meta.unimplemented_in_prototype=True
  - Real 구현은 cohort manifest (plan_1.2) + retrieval index 합류 후
  - similarity_score 는 *통계적 유사도*; 임상 진단 동등성 아님
  - similar case 의 outcome 을 *예측* 으로 단정 금지 — "유사 case 의 trajectory" 로만 phrasing
(Leakage guard 적용 — current_state 가 미래 데이터를 포함하면 거부.)
(Quality-aware: meta.cohort_index_version 명시.)
```

### LLM Description (EN)

```
Purpose: Retrieve up to k past cohort cases similar to the current case.
Similarity is computed on (surgery type, age, ASA, recent risk trajectory)
using cosine / euclidean / etc.
Input:
  - k: number of cases to return (default 5)
  - surgery_type: filter (e.g., "general", "thoracic")
  - max_age_diff: age difference tolerance (default 10 years)
  - asa_filter: list of ASA grades to include
  - current_state: optional summary of current case state for scoring
Output:
  - similar_cases: list of {case_id, similarity_score, summary, outcome}
  - meta: cohort_index_version, retrieval_method, etc.
Caveats:
  - STUB in Stage 1 prototype — returns empty list + meta.unimplemented_in_prototype=True
  - Real implementation depends on cohort manifest (plan_1.2) + retrieval index
  - similarity_score is a statistical metric, not clinical equivalence
  - Do not assert outcomes from similar cases — phrase as "trajectory of similar cases"
(Leakage guard: rejects if current_state includes future data.)
(Quality-aware: meta.cohort_index_version exposed.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| Stage 1 prototype 호출 | success, `similar_cases=[]`, `meta.unimplemented_in_prototype=True` |
| Cohort manifest 미존재 (post-plan_1.2) | `error.type = "missing_dependency"` |
| `k` 범위 위반 | `error.type = "invalid_args"` |
| Retrieval index 손상 | `error.type = "tool_internal_error"` |

---

## Tool 14 — `intervention_response_prediction`

### 목적

특정 intervention (vasopressor / fluid / 약물 등) 의 statistical response distribution 예측. **Dose 권고 X**.

ADR-013 의 supervised conditional generation approach 참조 (decision pending).

### Input

```json
{
  "required": ["intervention"],
  "properties": {
    "intervention": {
      "type": "object",
      "required": ["name"],
      "properties": {
        "name":   {"type": "string", "description": "e.g., norepinephrine / fluid_bolus / propofol_adjustment"},
        "amount": {"type": "number"},
        "unit":   {"type": "string"}
      }
    },
    "horizon_min":   {"type": "integer", "minimum": 1, "maximum": 30, "default": 5},
    "current_state": {"type": "object", "description": "Current case state summary"}
  }
}
```

### Output

```json
{
  "properties": {
    "response_distribution": {
      "type": "object",
      "required": ["mean", "p10", "p90"],
      "properties": {
        "mean":   {"type": "array", "items": {"type": "number"}},
        "p10":    {"type": "array", "items": {"type": "number"}},
        "p90":    {"type": "array", "items": {"type": "number"}},
        "metric": {"type": "string", "description": "e.g., MAP_mmHg"}
      }
    },
    "n_reference_cases": {"type": "integer"},
    "meta":              {"type": "object"}
  }
}
```

### LLM Description (KR)

```
용도: 특정 intervention 의 horizon_min 분 시간 동안 통계적 response distribution 예측 — 
       *dose 권고 아님*. 유사 코호트 case 의 historical response 를 합성.
입력:
  - intervention: {name, amount, unit}
  - horizon_min: 예측 horizon (기본 5)
  - current_state: 현재 환자 state 요약
출력:
  - response_distribution: {mean, p10, p90, metric} — 각 array 의 길이 = horizon_min
  - n_reference_cases: 합성에 사용된 reference case 수
  - meta: cohort_index_version, model_version, clinical_review_required=True
주의:
  - **Dose 권고가 아니다** — historical statistical response 만 보고
  - LLM 은 brief [Recommendations] 에서 본 출력을 *고려사항* 으로만 사용 + [CLINICIAN-REVIEW] 의무
  - Stage 1 prototype 에서 STUB — empty distribution + meta.unimplemented_in_prototype=True
  - ADR-013 decision pending — output schema 는 향후 변경 가능
(Leakage guard 적용. Quality-aware: meta.clinical_review_required=True 항상.)
```

### LLM Description (EN)

```
Purpose: Predict statistical response distribution for an intervention over the
next `horizon_min` minutes — **not a dose recommendation**. Synthesized from
historical responses of similar cohort cases.
Input:
  - intervention: {name, amount, unit}
  - horizon_min: prediction horizon (default 5)
  - current_state: current case state summary
Output:
  - response_distribution: {mean, p10, p90, metric}, each array length = horizon_min
  - n_reference_cases: number of reference cases synthesized
  - meta: cohort_index_version, model_version, clinical_review_required=True
Caveats:
  - **NOT a dose recommendation** — reports historical statistical response only
  - LLM must treat this as a "consideration" in [Recommendations]
    section + mandatory [CLINICIAN-REVIEW] marker
  - STUB in Stage 1 prototype — empty distribution + meta.unimplemented_in_prototype=True
  - ADR-013 decision pending — output schema may change
(Leakage guard. Quality-aware: meta.clinical_review_required=True always.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| Stage 1 prototype 호출 | success, empty `response_distribution`, `meta.unimplemented_in_prototype=True` |
| Intervention name 미지의 | `error.type = "invalid_args"` |
| Cohort index / model 부재 | `error.type = "missing_dependency"` |
| FM/model 내부 exception | `error.type = "tool_internal_error"` |

### Clinical phrasing rules (강제)

LLM 이 본 tool 출력을 brief 에 인용할 때:

✅ "유사 코호트 case 의 historical response 에 따르면, MAP 의 기대 trajectory 는 ..."
✅ "Intervention X 의 통계적 response 는 mean MAP ... 이며, 임상의 판단이 필요할 수 있다. [CLINICIAN-REVIEW]"

❌ "Norepinephrine X mcg/kg/min 시작 권고."
❌ "MAP 이 ... 까지 상승할 것이다."
❌ "본 intervention 이 효과적이다."

---

## Cross-cutting

### Why STUB in Stage 1?

본 2 tool 은 다음을 의존:
- **Cohort manifest** (plan_1.2) — 어떤 case 가 cohort 에 포함되는지
- **Retrieval index** (post-plan_1.2 + plan_1.4 baselines) — embedding / feature index
- **Intervention response model** (ADR-013 결정 후) — supervised conditional generation 등

Stage 1 prototype 시연 시 임상의 그룹에 *interface 만 보여주고* "이 tool 은 후속 plan 에서 구현됩니다" 안내. brief 는 `[Similar trajectory]` section 에 "TBD" 명시.

### Leakage guard 적용 표

| Tool | `query_window_end_s` 원천 | Guard 적용 |
|------|--------------------------|-----------|
| 13 `find_similar_cases` | `current_state.sim_time_s` (또는 request.sim_time_s) | ✅ |
| 14 `intervention_response_prediction` | `current_state.sim_time_s` | ✅ |

### Description audit

본 2 tool description 의 `v1_tool_description_style.md` 준수 audit 는 `.plans/stage1_preparation/plan_1.7_tool_spec.md` 의 audit note 섹션 참조.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] (intervention response 의 schema / phrasing rule 검토)
