# Signal Access Tools (17–21) — Spec (plan_1.3.5)

> 5 deterministic signal-access tool 의 정식 schema + LLM description + failure mode.
> ADR-016 Signal Access 카테고리 (Accepted 2026-05-17).
> Code: `vitalagent/tools/signal_access_tools.py` + `vitalagent/tools/signal_access_types.py`.
> Description tone: `prompts/v1_tool_description_style.md` 4-line skeleton 준수.

---

## 공통 패턴

### Dispatch

- `needs_signal=True`, `needs_fm=False` — `call_tool` 이 `(request, clock, signal)` 3-arg 로 routing
- FM Interface 무관 (ADR-011 swap 영향 없음)

### Leakage guard

- 모든 5 tool 이 `request.sim_time_s > clock.now_s` 시 `error.type="leakage_violation"` 반환

### Quality meta 공통 키

- `category: "signal_access"` — 모든 응답
- `source_tracks` / `baseline_source` / `tier0_status` 등 tool-specific 키 추가

---

## Tool 17 — `get_current_vitals`

### Input

```json
{ "type": "object", "additionalProperties": false, "properties": {} }
```

(`case_id` + `sim_time_s` 은 envelope. 별도 인자 없음.)

### Output

```json
{
  "required": ["map_mmHg", "sbp_mmHg", "dbp_mmHg", "hr_bpm", "rr_per_min",
               "spo2_pct", "etco2_mmHg", "bis", "core_temp_c"],
  "properties": {
    "map_mmHg":      {"type": ["number", "null"]},
    "sbp_mmHg":      {"type": ["number", "null"]},
    "dbp_mmHg":      {"type": ["number", "null"]},
    "hr_bpm":        {"type": ["number", "null"]},
    "rr_per_min":    {"type": ["number", "null"]},
    "spo2_pct":      {"type": ["number", "null"]},
    "etco2_mmHg":    {"type": ["number", "null"]},
    "bis":           {"type": ["number", "null"]},
    "core_temp_c":   {"type": ["number", "null"]},
    "meta":          {"type": "object", "properties": {
      "source_tracks": {"type": "object"},
      "fallback_used": {"type": "array", "items": {"type": "string"}}
    }}
  }
}
```

### LLM Description (KR)

```
용도: 현재 sim_time 기준 활력 징후 (vital signs) 9 field 의 평균값을 반환.
입력: case_id (envelope), sim_time_s (envelope). 별도 인자 없음.
출력:
  - map_mmHg / sbp_mmHg / dbp_mmHg: 혈압 (mmHg)
  - hr_bpm: 심박수 (bpm)
  - rr_per_min: 호흡수 (/min)
  - spo2_pct: 산소포화도 (%)
  - etco2_mmHg: 호기말 이산화탄소 (mmHg)
  - bis: BIS 값 (0–100)
  - core_temp_c: 체온 (°C)
  - meta.source_tracks: 각 field 가 어느 modality alias 에서 왔는지
  - meta.fallback_used: ABP→NIBP 같은 fallback 추적
주의:
  - 부재 field 는 `None` (NaN 아님)
  - ABP 부재 시 NIBP_MBP 로 자동 fallback (meta 표기)
  - Mock environment 에서 sim_time 의 ±5 초 window 평균
(Leakage guard 적용. Quality-aware: meta.source_tracks 가 출처 표기.)
```

### LLM Description (EN)

```
Purpose: Return current vital values dict (9 fields) for the modality window
around sim_time.
Input: case_id and sim_time_s from envelope; no additional args.
Output:
  - map_mmHg / sbp_mmHg / dbp_mmHg: blood pressures (mmHg)
  - hr_bpm: heart rate (bpm)
  - rr_per_min: respiratory rate (/min)
  - spo2_pct: oxygen saturation (%)
  - etco2_mmHg: end-tidal CO2 (mmHg)
  - bis: BIS value (0–100)
  - core_temp_c: core temperature (°C)
  - meta.source_tracks: per-field modality alias source
  - meta.fallback_used: fallbacks like ABP→NIBP tracked
Caveats:
  - Missing fields are `None` (not NaN)
  - ABP absent → falls back to NIBP_MBP (meta records)
  - Mock environment uses ±5 second window mean around sim_time
(Leakage guard. Quality-aware: meta.source_tracks tracks provenance.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| `sim_time_s > clock.now_s` | `error.type = "leakage_violation"` |
| 모든 modality 부재 | success with all fields `None` |
| 일부 modality 부재 | success with partial fields populated |

---

## Tool 18 — `describe_signal`

### Input

```json
{
  "required": ["modality"],
  "properties": {
    "modality":   {"type": "string"},
    "window_min": {"type": "integer", "minimum": 1, "maximum": 30, "default": 5}
  }
}
```

### Output

```json
{
  "required": ["mean", "std", "min", "max", "median", "iqr",
               "missing_ratio", "n_samples"],
  "properties": {
    "mean":          {"type": ["number", "null"]},
    "std":           {"type": ["number", "null"]},
    "min":           {"type": ["number", "null"]},
    "max":           {"type": ["number", "null"]},
    "median":        {"type": ["number", "null"]},
    "iqr":           {"type": ["number", "null"]},
    "missing_ratio": {"type": "number", "minimum": 0, "maximum": 1},
    "n_samples":     {"type": "integer", "minimum": 0},
    "meta":          {"type": "object"}
  }
}
```

### LLM Description (KR)

```
용도: 특정 modality window 의 통계 요약 (mean, std, min, max, median, IQR,
       missing_ratio, n_samples) 반환.
입력:
  - modality: 통계를 낼 modality 이름 (예: "ABP", "HR")
  - window_min: window 크기 (기본 5 분)
출력: 위 8 field + meta
주의:
  - NaN-safe — NaN sample 은 통계 계산에서 제외, missing_ratio 에 반영
  - `missing_ratio == 1.0` 시 모든 통계 field 는 `None`
  - 본 tool 은 *deterministic 통계* — 임상 결정 아님
(Leakage guard. Quality-aware: missing_ratio 가 신뢰도 hint.)
```

### LLM Description (EN)

```
Purpose: Statistical summary of a modality window (mean, std, min, max, median,
IQR, missing_ratio, n_samples).
Input:
  - modality: modality name (e.g. "ABP", "HR")
  - window_min: window size in minutes (default 5)
Output: 8 fields above + meta
Caveats:
  - NaN-safe — NaN samples excluded from stats; reflected in missing_ratio
  - When missing_ratio == 1.0, all stat fields are `None`
  - Deterministic statistics — not a clinical decision
(Leakage guard. Quality-aware: missing_ratio hints reliability.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| `modality` 미지정 또는 비-string | `error.type = "invalid_args"` |
| `modality` 가 signal dict 에 없음 | `error.type = "invalid_args"` |
| Leakage | `error.type = "leakage_violation"` |

---

## Tool 19 — `assess_variability`

### Input

```json
{
  "required": ["modality"],
  "properties": {
    "modality":   {"type": "string"},
    "window_min": {"type": "integer", "minimum": 1, "maximum": 30, "default": 5}
  }
}
```

### Output

```json
{
  "required": ["metrics"],
  "properties": {
    "metrics": {
      "type": "object",
      "description": "Modality-class-specific metric dict (see below)"
    },
    "meta": {
      "type": "object",
      "properties": {
        "modality":       {"type": "string"},
        "modality_class": {"type": "string", "enum": ["HR", "MAP", "PPG"]},
        "implementation": {"type": "string", "enum": ["neurokit", "numpy_fallback", "numpy"]},
        "unavailable_metrics": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

### Metric dict shape

| Modality class | metrics keys |
|----------------|--------------|
| HR (`HR`, `Solar8000/HR`, `Solar8000/PLETH_HR`) | `SDNN_ms`, `RMSSD_ms`, `LF_HF_ratio` |
| MAP / ABP family | `SD_mmHg`, `ARV_mmHg` |
| PPG (`PPG`, `SNUADC/PLETH`) | `amplitude_var`, `SVV_pct` |

### LLM Description (KR)

```
용도: Modality 별 변동성 metric 계산.
       - HR → 심박변이도 (HRV): SDNN, RMSSD, LF/HF 비
       - MAP/ABP → 혈압 변동성 (BPV): SD, ARV (평균 실측 변동)
       - PPG → 진폭 변동 + SVV (Stroke Volume Variation) 근사
입력: modality, window_min
출력: metrics dict (위 표 참조) + meta (implementation, unavailable_metrics)
주의:
  - NeuroKit2 설치 시 LF/HF 사용 가능; 미설치 시 `meta.implementation="numpy_fallback"`
    + `LF_HF_ratio=None` + `meta.unavailable_metrics=["LF_HF_ratio"]`
  - 짧은 window (R-R interval < 32 sample) 에서는 LF/HF None
  - `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토]` — metric 선택의 임상 적절성
(Leakage guard. Quality-aware: meta.implementation 이 출처 표기.)
```

### LLM Description (EN)

```
Purpose: Per-modality variability metrics.
       - HR → HRV: SDNN, RMSSD, LF/HF ratio
       - MAP/ABP → BPV: SD, ARV (average real variability)
       - PPG → amplitude variation + SVV (stroke volume variation) approximation
Input: modality, window_min
Output: metrics dict (see above table) + meta (implementation, unavailable_metrics)
Caveats:
  - NeuroKit2 installed → LF/HF available; else
    `meta.implementation="numpy_fallback"` + `LF_HF_ratio=None`
  - Short windows (<32 R-R intervals) yield LF/HF = None
  - `[CLINICIAN-REVIEW]` for metric selection appropriateness
(Leakage guard. Quality-aware: meta.implementation tracks provenance.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| `modality` 미지정 | `error.type = "invalid_args"` |
| `modality` 가 HR / MAP / PPG family 아님 | `error.type = "invalid_args"` |
| `modality` 가 signal dict 에 부재 | `error.type = "invalid_args"` |
| Leakage | `error.type = "leakage_violation"` |

---

## Tool 20 — `compare_to_baseline`

### Input

```json
{
  "required": ["modality"],
  "properties": {
    "modality":         {"type": "string"},
    "preop_baseline":   {"type": ["number", "null"]},
    "sampling_rate_hz": {"type": "number", "default": 500.0}
  }
}
```

### Output

```json
{
  "required": ["baseline_value", "current_value", "direction"],
  "properties": {
    "baseline_value":  {"type": ["number", "null"]},
    "current_value":   {"type": "number"},
    "absolute_change": {"type": ["number", "null"]},
    "percent_change":  {"type": ["number", "null"]},
    "direction":       {"type": "string", "enum": ["up", "down", "stable", "unknown"]},
    "meta": {
      "type": "object",
      "properties": {
        "baseline_source": {"type": "string",
                            "enum": ["preop", "intraop_early_10min", "none"]},
        "modality":        {"type": "string"}
      }
    }
  }
}
```

### LLM Description (KR)

```
용도: 현재 modality 값을 기저값 (baseline) 과 비교.
       Baseline 우선순위: (1) preop_baseline 인자 (예: query_patient_baseline.baseline_bp)
                       (2) intraop 초기 10 분 평균 fallback
                       (3) 둘 다 부재 시 None
입력:
  - modality: 비교할 modality (예: "ABP")
  - preop_baseline: 선택, preop 값 (없으면 intraop fallback)
  - sampling_rate_hz: fallback 계산용 (기본 500.0)
출력:
  - baseline_value, current_value, absolute_change, percent_change, direction
  - meta.baseline_source 가 어느 source 사용했는지 표기
주의:
  - direction == "unknown" 는 baseline 없음을 시사 — `[Limitations]` 에 명시
  - `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토]` — baseline 정의 우선순위
(Leakage guard. Quality-aware: meta.baseline_source 가 신뢰도 hint.)
```

### LLM Description (EN)

```
Purpose: Compare current modality mean to baseline.
       Baseline priority: (1) `preop_baseline` arg (e.g. query_patient_baseline.baseline_bp)
                         (2) intraop early 10-min mean fallback
                         (3) None if neither available
Input:
  - modality: target modality (e.g. "ABP")
  - preop_baseline: optional preop value
  - sampling_rate_hz: for fallback computation (default 500.0)
Output:
  - baseline_value, current_value, absolute_change, percent_change, direction
  - meta.baseline_source records which source was used
Caveats:
  - direction == "unknown" indicates no baseline available — note in [Limitations]
  - `[CLINICIAN-REVIEW]` — baseline definition priority
(Leakage guard. Quality-aware: meta.baseline_source hints reliability.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| `modality` 미지정 | `error.type = "invalid_args"` |
| `modality` 가 signal dict 에 부재 | `error.type = "invalid_args"` |
| `modality` 에 valid sample 없음 (모두 NaN) | `error.type = "invalid_args"` |
| Baseline 모두 부재 | success with `baseline_value=None, direction="unknown"` |
| Leakage | `error.type = "leakage_violation"` |

---

## Tool 21 — `summarize_current_state`

> ⚠️ **STUB (Stage 1 prototype)**. ADR-014 의 Tier 0 #14–16 (hemodynamic state classifier / anesthesia state / surgical phase) 합류 시 wrap 으로 교체.

### Input

```json
{ "type": "object", "additionalProperties": false, "properties": {} }
```

### Output

```json
{
  "required": ["hemodynamic_state", "anesthesia_state", "respiratory_state",
               "key_concerns", "overall_assessment"],
  "properties": {
    "hemodynamic_state": {"type": "string",
                          "enum": ["stable", "caution_low_pressure",
                                   "caution_high_pressure", "unknown"]},
    "anesthesia_state":  {"type": "string",
                          "enum": ["adequate_range", "possibly_light",
                                   "possibly_deep", "unknown"]},
    "respiratory_state": {"type": "string",
                          "enum": ["stable", "caution_low_spo2", "unknown"]},
    "key_concerns":      {"type": "array", "items": {"type": "string"}},
    "overall_assessment":{"type": "string",
                          "description": "MUST contain '[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]' marker"},
    "meta": {
      "type": "object",
      "properties": {
        "tier0_status":      {"type": "string", "enum": ["stub", "tier0_supervised"]},
        "stub_rule":         {"type": "string"},
        "vitals_source":     {"type": "object"}
      }
    }
  }
}
```

### LLM Description (KR)

```
용도: 통합 현재 상태 평가 — tool 17–20 출력을 합성한 (현재 STUB) rule-based 결과.
       Tier 0 supervised head (ADR-014, DECISION PENDING) 합류 시 본격 wrap.
입력: 없음 (envelope 의 case_id + sim_time_s 사용).
출력:
  - hemodynamic_state / anesthesia_state / respiratory_state (enum)
  - key_concerns: threshold 위반 항목 list
  - overall_assessment: conditional phrasing + [CLINICIAN-REVIEW] marker
  - meta.tier0_status: "stub" (현재) 또는 "tier0_supervised" (ADR-014 후)
주의:
  - **Phrasing 정책** (brief §13.1, ADR-016): conditional phrasing 만,
    단정형 금지, dose 권고 절대 금지, `[CLINICIAN-REVIEW]` marker MANDATORY
  - 본 출력은 *측정값 합성* 일 뿐 임상 결정 아님
  - Stub 단계에서는 lit-standard threshold (MAP 65–110, HR 50–100, SpO2 ≥ 92, BIS 40–60)
    기반 휴리스틱
(Leakage guard. Quality-aware: meta.tier0_status="stub", clinical_review_required=True.)
```

### LLM Description (EN)

```
Purpose: Integrated current state assessment — STUB synthesizing tools 17–20.
       Replaced by Tier 0 supervised wrap once ADR-014 is Accepted.
Input: none (uses envelope case_id + sim_time_s).
Output:
  - hemodynamic_state / anesthesia_state / respiratory_state (enum)
  - key_concerns: list of threshold violations
  - overall_assessment: conditional phrasing + [CLINICIAN-REVIEW] marker
  - meta.tier0_status: "stub" (current) or "tier0_supervised" (post ADR-014)
Caveats:
  - **Phrasing policy** (brief §13.1, ADR-016): conditional phrasing only,
    NO assertions, NO dose recommendations, `[CLINICIAN-REVIEW]` marker MANDATORY
  - Output is a synthesis of measurements — NOT a clinical decision
  - STUB uses lit-standard thresholds (MAP 65–110, HR 50–100, SpO2 ≥ 92, BIS 40–60)
(Leakage guard. Quality-aware: meta.tier0_status="stub", clinical_review_required=True.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| Leakage | `error.type = "leakage_violation"` |
| Tool 17 내부 실패 (이론상 불가) | `error.type = "tool_internal_error"` |

---

## Cross-cutting

### Brief §[Signal status] / §[Surgery context] / §[Evidence] source mapping

ADR-016 §"브리프 §[Signal status] / §[Surgery context] 의 tool source 명시" 표 참조. 본 5 tool 이 brief 의 정량 claim 의 explicit source.

### Mock-vs-real universality

본 5 tool 은 deterministic — mock_tier 개념 무관. 동일 description 이 prototype synthetic signal 과 real VitalDB load 양쪽에 적용.

### Description style audit (`v1_tool_description_style.md` 준수)

| 항목 | Tool 17 | 18 | 19 | 20 | 21 |
|------|---------|----|----|----|-----|
| Purpose 1 문장 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Input 인자 + 의미 + 단위 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Output 키 + 범위 + 단위 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Caveats (failure mode + 신뢰도) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Leakage guard 메모 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Quality-aware 메모 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 한·영 병기 | ✅ | ✅ | ✅ | ✅ | ✅ |

### Failure mode coverage

| Tool | Leakage | Invalid args | Missing modality | Internal exc | Fallback success |
|------|---------|--------------|------------------|--------------|------------------|
| 17 | ✅ | ✅ (envelope 만) | ✅ (`None` field) | N/A | ✅ (NIBP fallback) |
| 18 | ✅ | ✅ (missing modality / invalid) | ✅ | N/A | ✅ (all-NaN → `None`) |
| 19 | ✅ | ✅ (unsupported class / missing) | ✅ | N/A | ✅ (LF/HF None fallback) |
| 20 | ✅ | ✅ (missing modality) | ✅ | N/A | ✅ (no-baseline `unknown` direction) |
| 21 | ✅ | N/A (no args) | N/A (uses 17 output) | ✅ | ✅ (vitals 부재 → "unknown" states) |

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — Tool 19 의 HRV/BPV/SVV metric 선택, Tool 20 의 baseline 정의 우선순위, Tool 21 의 threshold (MAP 65–110, HR 50–100, SpO2 ≥ 92, BIS 40–60), Tool 21 의 phrasing rule.
