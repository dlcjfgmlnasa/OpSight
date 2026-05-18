# Auxiliary Tools (15–16) — Spec (plan_1.7)

> 2 개 Auxiliary tool 의 정식 schema + LLM description + failure mode.
> ⚠️ Stage 1 prototype 단계에서는 STUB (또는 minimal). Real 구현은 후속 plan 의존.
> Description tone: `prompts/v1_tool_description_style.md` 의 4-line skeleton 준수.

---

## Tool 15 — `surgery_context_awareness`

### 목적

수술 유형 / phase 에 따른 reasoning hint 제공. plan_1.5 의 `docs/surgery_context.yaml` 을 기반으로 LLM 에 "이 phase 에서 어떤 hemodynamic event 가 일반적인지" 정보 전달.

### Input

```json
{
  "required": ["surgery_type"],
  "properties": {
    "surgery_type": {"type": "string", "description": "general / thoracic / urologic / gynecologic / etc."},
    "phase":        {"type": "string", "enum": ["induction", "maintenance", "emergence", "unknown"]}
  }
}
```

### Output

```json
{
  "properties": {
    "common_events":      {"type": "array", "items": {"type": "string"}},
    "phase_hint":         {"type": "string"},
    "reasoning_priors":   {"type": "object", "description": "Per-event prior probabilities (informative, not deterministic)"},
    "meta":               {"type": "object"}
  }
}
```

### LLM Description (KR)

```
용도: 수술 유형 + phase 에 따른 reasoning hint 제공. brief [Surgery context] 와 
       [Evidence] section 의 추론 priors 로 사용.
입력:
  - surgery_type: "general" / "thoracic" / "urologic" / "gynecologic" / etc.
  - phase: "induction" / "maintenance" / "emergence" / "unknown"
출력:
  - common_events: 본 phase 에서 흔한 event list (예: "induction hypotension", "emergence delirium")
  - phase_hint: phase-specific 추론 hint 한 문장
  - reasoning_priors: event 별 prior probability (informative — 결정론적 아님)
  - meta: source = "surgery_context.yaml", version
주의:
  - 본 tool 은 *priors* 제공이며 진단 아님 — LLM 이 [Risk evaluation] 에서 단정 금지
  - Stage 1 prototype 에서는 `surgery_context.yaml` (plan_1.5) 미존재 → STUB minimal 출력
  - Real 합류 후에도 임상의 검토 필수 [CLINICIAN-REVIEW]
(Quality-aware: meta.source / version 표기.)
```

### LLM Description (EN)

```
Purpose: Provide reasoning hints based on surgery type + phase. Consumed as
priors in brief [Surgery context] and [Evidence] sections.
Input:
  - surgery_type: "general" / "thoracic" / "urologic" / "gynecologic" / etc.
  - phase: "induction" / "maintenance" / "emergence" / "unknown"
Output:
  - common_events: list of events common in this phase (e.g., "induction hypotension")
  - phase_hint: single-sentence phase-specific reasoning hint
  - reasoning_priors: per-event prior probability (informative, not deterministic)
  - meta: source = "surgery_context.yaml", version
Caveats:
  - This tool provides PRIORS, not diagnoses — LLM must not assert in [Risk evaluation]
  - STUB in Stage 1 prototype (surgery_context.yaml from plan_1.5 not yet available)
  - Even after real integration, clinician review remains required [CLINICIAN-REVIEW]
(Quality-aware: meta.source / version exposed.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| Stage 1 prototype 호출 | success, minimal hardcoded priors + `meta.unimplemented_in_prototype=True` |
| 미지의 surgery_type | success with `common_events=[], phase_hint="unknown surgery type"` |
| plan_1.5 yaml load 실패 | `error.type = "missing_dependency"` |

---

## Tool 16 — `quality_aware_synthesis`

### 목적

여러 prediction 을 quality-weighted 로 결합. **Deterministic — LLM 호출 없음**. 본 tool 은 *합성 (fusion)* 함수이며 reasoning 함수 아님.

### Input

```json
{
  "required": ["predictions"],
  "properties": {
    "predictions": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["value", "quality"],
        "properties": {
          "value":    {"type": "number"},
          "quality":  {"type": "number", "minimum": 0, "maximum": 1},
          "source":   {"type": "string"}
        }
      }
    },
    "method": {"type": "string", "enum": ["weighted_mean", "max_quality", "min_uncertainty"], "default": "weighted_mean"}
  }
}
```

### Output

```json
{
  "properties": {
    "fused_value":      {"type": "number"},
    "effective_quality": {"type": "number", "minimum": 0, "maximum": 1},
    "contributors":     {"type": "array", "items": {"type": "string"}},
    "meta":             {"type": "object"}
  }
}
```

### LLM Description (KR)

```
용도: 여러 prediction (각각 quality score 포함) 을 quality-weighted 로 결합하여 
       단일 fused_value 출력. 본 tool 은 *deterministic 함수* 이며 LLM 호출 없음.
입력:
  - predictions: [{value, quality, source}, ...] (최소 1개)
  - method: "weighted_mean" (기본) / "max_quality" / "min_uncertainty"
출력:
  - fused_value: 결합된 단일 값
  - effective_quality: 합성 후 effective quality
  - contributors: 결합에 기여한 source 들
  - meta: method, formula 등
주의:
  - 본 tool 은 *수학적 결합* — 임상 추론 아님. LLM 은 fused_value 를 그대로 사용 + source 출처 명시
  - 모든 quality 가 0 이면 fused_value 는 의미 없음 → effective_quality=0 명시
  - method 별 공식:
    * weighted_mean: Σ(v_i * q_i) / Σ(q_i)
    * max_quality: argmax_q(v_i)
    * min_uncertainty: argmin_u(v_i) — uncertainty = 1 - quality
(Leakage guard 적용 X — input 자체가 이미 fetched.)
(Quality-aware: meta.deterministic=True, effective_quality 반환.)
```

### LLM Description (EN)

```
Purpose: Fuse multiple predictions (each with a quality score) into a single
fused_value using a quality-weighted combination. This tool is a
**deterministic function**; no LLM call inside.
Input:
  - predictions: list of {value, quality, source} (minimum 1)
  - method: "weighted_mean" (default) / "max_quality" / "min_uncertainty"
Output:
  - fused_value: single combined value
  - effective_quality: effective quality post-fusion
  - contributors: list of source names that contributed
  - meta: method, formula, etc.
Caveats:
  - This is a MATHEMATICAL fusion, not clinical reasoning. LLM uses
    fused_value as-is and cites source provenance.
  - If all qualities are 0, fused_value is meaningless → effective_quality=0
  - Formulas per method:
    * weighted_mean: Σ(v_i * q_i) / Σ(q_i)
    * max_quality:   v_i where q_i is max
    * min_uncertainty: v_i where (1 - q_i) is min
(No leakage guard — inputs are already fetched.)
(Quality-aware: meta.deterministic=True, effective_quality reported.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| `predictions=[]` | `error.type = "invalid_args"` |
| 미지의 method | `error.type = "invalid_args"` |
| 모든 quality=0 | success, `fused_value=NaN or fallback, effective_quality=0` |

### Why deterministic?

본 tool 은 LLM 호출이 없는 *순수 함수*. 이유:
- **Reproducibility**: 같은 input → 같은 output (LLM 의 stochastic 특성 제거)
- **Latency**: 수학적 합성 < 1ms (LLM 호출 수십 초 vs)
- **검증 가능**: unit test 로 모든 method 의 수학적 공식 검증

LLM 은 `fused_value` 를 *받아서* brief 본문에 인용만 한다.

---

## Cross-cutting

### Stage 1 prototype 상태

| Tool | Stage 1 STUB | Real 구현 의존 |
|------|-------------|----------------|
| 15 `surgery_context_awareness` | minimal hardcoded priors | `plan_1.5` 의 `surgery_context.yaml` |
| 16 `quality_aware_synthesis` | full implementation 가능 (deterministic 함수) | 의존 없음 — 즉시 구현 가능 |

→ Tool 16 은 deterministic 이라 Stage 1 prototype 에서도 **real 구현 가능**. Stub 불필요.

### Description audit

본 2 tool description 의 `v1_tool_description_style.md` 준수 audit 는 `.plans/stage1_preparation/plan_1.7_tool_spec.md` 의 audit note 섹션 참조.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] (surgery_context priors / phrasing rule 검토)
