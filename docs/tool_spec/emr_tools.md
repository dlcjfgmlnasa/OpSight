# EMR-based Tools (8–12) — Spec (plan_1.7)

> 5 개 EMR tool 의 정식 schema + LLM description + failure mode.
> ⚠️ 현재 구현 (`vitalagent/tools/emr_tools_stub.py`) 은 **STUB**. fake data 반환.
> 실 EMR query 는 `plan_1.3` 에서 교체. 본 spec 의 schema 는 real 합류 후 그대로 적용.
> Description tone: `prompts/v1_tool_description_style.md` 의 4-line skeleton 준수.

---

## 공통 패턴

### 공통 input

| Field | Type | 의미 |
|-------|------|------|
| `case_id` | `str` | request envelope 의 case_id (echo, 별도 지정 불필요) |
| `time_window` (선택) | `[start_s, end_s]` | 조회 시간 윈도. End 가 `clock.now_s` 초과 시 leakage error |

### 공통 output

`result` 외에 `quality_meta` 가 다음을 포함:
- `emr_stub: True` (STUB 동안)
- `clinical_review_required: True` (모든 EMR 응답)

→ Brief LLM 의 `[Intraoperative context]` + `[Limitations]` section 작성 의무.

---

## Tool 8 — `query_anesthesia_drugs`

### Input

```json
{
  "required": [],
  "properties": {
    "time_window": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
  }
}
```

### Output

```json
{
  "properties": {
    "drugs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "amount", "unit", "timestamp_s"],
        "properties": {
          "name":         {"type": "string"},
          "amount":       {"type": "number"},
          "unit":         {"type": "string"},
          "timestamp_s":  {"type": "number"},
          "channel":      {"type": "string"}
        }
      }
    }
  }
}
```

### LLM Description (KR)

```
용도: time_window 동안 EMR 에서 마취제 (induction, maintenance, opioid 등) 투여 기록 조회.
입력:
  - case_id: str
  - time_window: (start_s, end_s)
출력:
  - drugs: list of {name, amount, unit, timestamp_s, channel}
  - meta: clinical_review_required (stub 단계)
주의:
  - 현재 STUB — 고정 fake data 반환. 특정 약물명/용량을 임상 추론에 사용 금지
  - end_s > clock.now_s 시 leakage_violation 에러
  - 실 EMR 합류 후 channel 명은 Orchestra/RFTN20_CE 등 VitalDB track 이름
(Leakage guard 적용. Quality-aware: meta.clinical_review_required 표기.)
```

### LLM Description (EN)

```
Purpose: Retrieve anesthesia drug administration records (induction agents,
maintenance agents, opioids) within `time_window` from the EMR.
Input:
  - case_id: str
  - time_window: tuple (start_s, end_s) in seconds since case start
Output:
  - drugs: list of {name, amount, unit, timestamp_s, channel}
  - meta: includes "clinical_review_required": True when stub data
Caveats:
  - Current implementation is a STUB returning fixed fake data — do not rely
    on specific drug names / doses for clinical inference
  - `time_window.end_s` must not exceed clock.now_s
(Leakage guard: query_window_end_s ≤ clock.now_s enforced.)
(Quality-aware: meta.clinical_review_required signals stub provenance.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| `time_window.end > clock.now_s` | `error.type = "leakage_violation"` |
| `time_window` 누락 | success, default `(now - 300, now)` (최근 5분) |
| 실 EMR 부재 (Stage 1) | success with fake drugs |

---

## Tool 9 — `query_vasoactive_drugs`

Schema / description: tool 8 과 동일 구조. `drugs` 항목은 norepinephrine / phenylephrine / dopamine / dobutamine / vasopressin / ephedrine 등.

### LLM Description (KR)

```
용도: time_window 동안 vasoactive drug (norepinephrine, phenylephrine, dopamine 등) 투여 기록 조회.
입력 / 출력: tool 8 과 동일.
주의:
  - drugs == [] (빈 list) 는 *기록 없음* 을 의미; 임상의 monitor 확인 권장
  - STUB 단계에서는 모든 case 가 같은 fake 출력
(Leakage guard. Quality-aware propagate.)
```

### LLM Description (EN)

```
Purpose: Retrieve vasoactive drug (norepinephrine, phenylephrine, dopamine, etc.)
administration records within `time_window`.
Input / Output: same shape as tool 8.
Caveats:
  - drugs == [] means "no record found" — clinician monitor verification advised
  - In STUB mode, all cases return the same fake output
(Leakage guard. Quality-aware propagate.)
```

---

## Tool 10 — `query_fluid_blood`

### Output

```json
{
  "properties": {
    "fluids":         {"type": "array", "items": {"type": "object"}},
    "blood_products": {"type": "array", "items": {"type": "object"}}
  }
}
```

Each item: `{name, volume_ml, timestamp_s, channel}`.

### LLM Description (KR)

```
용도: time_window 동안 수액 (crystalloid, colloid) 및 혈액 제제 (RBC, FFP, platelet) 투여 기록 조회.
입력 / 출력 패턴: tool 8 과 유사.
주의:
  - 누적 volume 계산은 caller (LLM 또는 후속 tool) 책임
  - STUB 단계에서 fake 수액 / 혈액 = 0
(Leakage guard. Quality-aware propagate.)
```

### LLM Description (EN)

```
Purpose: Retrieve fluid (crystalloid, colloid) and blood product (RBC, FFP,
platelets) administration records within `time_window`.
Input / Output: similar shape to tool 8.
Caveats:
  - Cumulative volume aggregation is caller's responsibility
  - STUB returns zero fluids / blood products
(Leakage guard. Quality-aware propagate.)
```

---

## Tool 11 — `query_surgery_progress`

### Input

```json
{
  "properties": {
    "current_time": {"type": "number", "description": "Defaults to clock.now_s"}
  }
}
```

### Output

```json
{
  "required": ["phase", "elapsed_min"],
  "properties": {
    "phase":                  {"type": "string", "enum": ["induction", "maintenance", "emergence", "unknown"]},
    "elapsed_min":            {"type": "number"},
    "estimated_remaining_min": {"type": ["number", "null"]}
  }
}
```

### LLM Description (KR)

```
용도: 현재 sim_time 기준 surgery phase (induction / maintenance / emergence) 및 경과 / 잔여 분 추정.
입력: current_time (선택, 기본 clock.now_s).
출력: phase, elapsed_min, estimated_remaining_min.
주의:
  - STUB 단계는 시간 비율 기반 heuristic (자세한 phase 정의는 plan_1.5)
  - "unknown" 은 phase classifier 불확실 — [Surgery context] 에 명시
(Leakage guard. Quality-aware: heuristic 출처 표기.)
```

### LLM Description (EN)

```
Purpose: Estimate current surgery phase (induction / maintenance / emergence)
and elapsed / remaining minutes given current sim_time.
Input: current_time (optional, defaults to clock.now_s).
Output: phase, elapsed_min, estimated_remaining_min.
Caveats:
  - STUB uses a time-ratio heuristic (phase definition lives in plan_1.5)
  - "unknown" phase signals classifier uncertainty — note in [Surgery context]
(Leakage guard. Quality-aware: heuristic provenance flagged.)
```

---

## Tool 12 — `query_patient_baseline`

### Input

case_id only.

### Output

```json
{
  "properties": {
    "age":           {"type": ["integer", "null"]},
    "sex":           {"type": ["string", "null"], "enum-hint": ["M", "F", null]},
    "asa":           {"type": ["integer", "null"]},
    "comorbidities": {"type": "array", "items": {"type": "string"}},
    "baseline_bp":   {"type": ["string", "null"], "description": "e.g. '130/80'"},
    "labs":          {"type": "object"}
  }
}
```

### LLM Description (KR)

```
용도: case-level 환자 baseline metadata 조회 (수술 시작 전 정적 정보).
입력: case_id (request envelope 의 값 사용).
출력: age, sex, asa, comorbidities, baseline_bp, labs.
주의:
  - 본 정보는 case 시작 *전* 정적 정보로 누수 risk 없음
  - STUB 단계는 모든 case 가 동일 fake 환자 (62세 남성, ASA 2)
  - 임상 의사결정 시 실 EMR 합류 후 (plan_1.3) 사용
(Quality-aware: meta.emr_stub 표기.)
```

### LLM Description (EN)

```
Purpose: Retrieve case-level patient baseline metadata (static, pre-surgery info).
Input: case_id (taken from request envelope).
Output: age, sex, asa, comorbidities, baseline_bp, labs.
Caveats:
  - This info is static and pre-case, so leakage risk does not apply
  - STUB returns the same fake patient (62-year-old male, ASA 2) for every case
  - For clinical decisions, wait for real EMR integration (plan_1.3)
(Quality-aware: meta.emr_stub flagged.)
```

---

## Cross-cutting

### Leakage guard 적용 표

| Tool | `query_window_end_s` 원천 | Guard 적용 |
|------|--------------------------|-----------|
| 8 `query_anesthesia_drugs` | `time_window.end_s` | ✅ |
| 9 `query_vasoactive_drugs` | `time_window.end_s` | ✅ |
| 10 `query_fluid_blood` | `time_window.end_s` | ✅ |
| 11 `query_surgery_progress` | `current_time` | ✅ |
| 12 `query_patient_baseline` | — (static info) | ⛔ N/A |

### Plan_1.3 합류 시 변경 항목

- `quality_meta.emr_stub` 제거 → `quality_meta.emr_source: "vitaldb_clinical_table"` 등으로 교체
- `clinical_review_required` 는 *유지* (실 EMR 데이터도 임상의 검토 의무)
- Schema 자체는 *불변* — 본 문서가 contract

### Description audit

본 5 tool description 의 `v1_tool_description_style.md` 준수 audit 는 `.plans/stage1_preparation/plan_1.7_tool_spec.md` 의 audit note 섹션 참조.
