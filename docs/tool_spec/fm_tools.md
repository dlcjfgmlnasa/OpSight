# FM-based Tools (1–7) — Spec (plan_1.7)

> 7 개 FM tool 의 정식 schema + LLM description + failure mode.
> 의존성: `opsight/fm/interface.py` (BiosignalFMInterface Protocol), `opsight/fm/result_types.py` (7 frozen Result dataclass).
> 본 문서는 `opsight/tools/fm_tools.py` 의 정식 spec.
> Description tone: `prompts/v1_tool_description_style.md` 의 4-line skeleton 준수.

---

## 공통 Input / Output 패턴

| 공통 input field | Type | 의미 |
|------------------|------|------|
| `signal` | `dict[str, torch.Tensor]` | modality → 1-D tensor (sampling rate ~500 Hz) |
| `available_modalities` | `list[str]` | signal 에 포함된 modality 이름 |

| 공통 output field | Type | 의미 |
|-------------------|------|------|
| `meta.mock_tier` | `"stub" \| "rule_based" \| "light_ml" \| "real"` | FM 출처 |
| `meta.*` | various | tier-specific 진단 |

→ Tool wrapper 가 FM Result (dataclass) 를 `dataclasses.asdict()` 로 변환 → `ToolResponse.result` 에 저장.

---

## Tool 1 — `predict_hypotension`

### Input JSON Schema

```json
{
  "title": "predict_hypotension_input",
  "type": "object",
  "required": ["horizon_min"],
  "properties": {
    "horizon_min":          {"type": "integer", "minimum": 1, "maximum": 30, "default": 5},
    "available_modalities": {"type": "array", "items": {"type": "string"}}
  }
}
```

### Output JSON Schema

```json
{
  "title": "predict_hypotension_output",
  "type": "object",
  "required": ["risk", "uncertainty", "horizon_min"],
  "properties": {
    "risk":         {"type": "number", "minimum": 0, "maximum": 1},
    "uncertainty":  {"type": "number", "minimum": 0, "maximum": 1},
    "horizon_min":  {"type": "integer"},
    "meta":         {"type": "object"}
  }
}
```

### Protocol method

`BiosignalFMInterface.predict_hypotension(signal, horizon_min, available_modalities) -> HypotensionResult`

### LLM Description (KR)

```
용도: 최근 신호 window 에서 horizon_min 분 후 저혈압 (MAP < 65 mmHg 가 1 분 이상 지속) 확률 예측.
입력:
  - signal: modality → tensor (~500 Hz)
  - horizon_min: 예측 horizon (분, 기본 5)
  - available_modalities: signal 에 포함된 modality 이름
출력:
  - risk: 0–1, horizon_min 분 안 저혈압 확률
  - uncertainty: 0–1, model 불확실성 (높을수록 신뢰도 낮음)
  - horizon_min: 입력 echo
  - meta: dict (mock_tier, 중간 score 등)
주의:
  - ABP 부재 / flatline 시 fallback (risk≈0.4, uncertainty≈0.7+) 반환
  - mock_tier=="stub" 출력은 random — 임상 추론 사용 금지
  - uncertainty 높을 때 [Risk evaluation] section 에 명시 의무
(Leakage guard: 호출자가 signal 에 미래 sample 포함 금지.)
(Quality-aware: uncertainty 반환 — caller propagate.)
```

### LLM Description (EN)

```
Purpose: Predict probability of hypotension (MAP < 65 mmHg sustained ≥ 1 min)
within `horizon_min` minutes ahead, given a recent biosignal window.
Input:
  - signal: dict of modality -> tensor (1-D, sampling rate ~500 Hz)
  - horizon_min: int, prediction horizon in minutes (typical 5)
  - available_modalities: list of modality names present in `signal`
Output:
  - risk: float in [0, 1] — probability of hypotension within horizon_min
  - uncertainty: float in [0, 1] — model uncertainty; higher = less reliable
  - horizon_min: echoed input
  - meta: dict (mock_tier, intermediate scores for debugging)
Caveats:
  - May return fallback (risk≈0.4, uncertainty≈0.7+) when ABP is absent or flatline
  - mock_tier == "stub" output is random — do not use for clinical reasoning
  - Higher uncertainty → cite explicitly in [Risk evaluation] section
(Leakage guard: caller must not include future samples in `signal`.)
(Quality-aware: returns uncertainty; caller must propagate.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| Future sample 포함 | `error.type = "leakage_violation"` |
| ABP 부재 | success, but `result.risk ≈ 0.4, uncertainty ≈ 0.7+, meta.fallback = "no_abp"` |
| ABP flatline (std < 1e-3) | success, but fallback (low confidence) |
| FM 내부 exception | `error.type = "tool_internal_error"` |

---

## Tool 2 — `predict_cardiac_arrest`

### Schemas

Input — same shape as tool 1 (`horizon_min` + `available_modalities`).
Output — same shape: `{risk, uncertainty, horizon_min, meta}`. Note `risk` 의 범위는 [0, 1] 이지만 baseline (no flag) 시 ~0.02–0.05.

### Protocol method

`predict_cardiac_arrest(signal, horizon_min, available_modalities) -> ArrestResult`

### LLM Description (KR)

```
용도: 최근 신호 window 에서 horizon_min 분 후 심정지 (cardiac arrest) 확률 예측.
입력: tool 1 과 동일.
출력:
  - risk: 0–1, horizon_min 분 안 심정지 확률 (rare event — baseline 0.02–0.05)
  - uncertainty: 0–1
  - meta: dict (mock_tier, flagged criteria — HR_low / HR_high / MAP_low 등)
주의:
  - 본 tool 의 fire (risk > 0.5) 는 trigger rule 5 의 acute event → deep mode + cooldown 우회
  - HR / ABP 모두 부재 시 fallback (risk≈0.05, uncertainty≈0.8)
  - mock_tier=="stub" 출력은 random
(Leakage guard 적용. Quality-aware uncertainty propagate.)
```

### LLM Description (EN)

```
Purpose: Predict probability of cardiac arrest within `horizon_min` minutes.
Input: same as tool 1.
Output:
  - risk: float in [0, 1] (rare event — baseline ~0.02–0.05)
  - uncertainty: float in [0, 1]
  - meta: includes mock_tier and flagged criteria (e.g., HR_low / HR_high / MAP_low)
Caveats:
  - risk > 0.5 fires trigger rule #5 (acute event) — bypasses cooldown
  - HR and ABP both absent → fallback (risk ≈ 0.05, uncertainty ≈ 0.8)
  - mock_tier == "stub" output is random
(Leakage guard. Quality-aware uncertainty propagate.)
```

### Failure modes — same as tool 1

---

## Tool 3 — `assess_signal_quality`

### Input

```json
{
  "required": ["modality"],
  "properties": {
    "modality": {"type": "string", "enum-hint": ["ABP", "ECG_II", "PPG", "HR", "BIS"]}
  }
}
```

### Output

```json
{
  "required": ["score"],
  "properties": {
    "score":  {"type": "number", "minimum": 0, "maximum": 1},
    "reason": {"type": ["string", "null"]},
    "meta":   {"type": "object"}
  }
}
```

### Protocol method

`assess_signal_quality(signal, modality) -> QualityResult`

### LLM Description (KR)

```
용도: 단일 modality window 의 신호 품질을 [0, 1] 로 점수화 (1=깨끗, 0=사용불가).
입력: signal, modality 이름.
출력:
  - score: 0–1
  - reason: 낮은 점수의 이유 ("flatline", "high_nan_ratio", "modality_absent")
  - meta: dict (mock_tier, NaN ratio, std 등)
주의:
  - score < 0.5 → [Limitations] 에 명시 + Assessment confidence 하향
  - score < 0.3 → Assessment confidence = UNRELIABLE 권장
  - 부재 modality → score = 0.0, reason = "modality_absent"
(Leakage guard. Quality-aware: 본 tool 자체가 quality signal.)
```

### LLM Description (EN)

```
Purpose: Score the quality of a single modality's signal window in [0, 1],
where 1 is clean and 0 is unusable (flatline / saturated NaN).
Input: signal, modality name.
Output:
  - score: float in [0, 1]
  - reason: optional string explaining low scores ("flatline", "high_nan_ratio", "modality_absent")
  - meta: dict (mock_tier, diagnostics)
Caveats:
  - score < 0.5 → cite in [Limitations] + lower Assessment confidence
  - score < 0.3 → consider Assessment confidence = UNRELIABLE
  - Absent modality returns score = 0.0 with reason = "modality_absent"
(Leakage guard. Quality-aware: this IS the quality signal — caller propagates.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| 미지의 modality | success, `score=0.0, reason="modality_absent"` |
| Future sample 포함 | `error.type = "leakage_violation"` |
| FM 내부 exception | `error.type = "tool_internal_error"` |

---

## Tool 4 — `cross_modal_consistency`

### Input

```json
{
  "required": ["modality_pair"],
  "properties": {
    "modality_pair": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2}
  }
}
```

### Output

```json
{
  "properties": {
    "score":  {"type": "number", "minimum": 0, "maximum": 1},
    "reason": {"type": ["string", "null"]},
    "meta":   {"type": "object"}
  }
}
```

### Protocol method

`cross_modal_consistency(signal, modality_pair) -> ConsistencyResult`

### LLM Description (KR)

```
용도: 두 modality 사이 시간 정렬 일관성 score (0–1). 1=일관, 0=비일관. 
       Rule-based 구현은 quality-filtered window 에서 |Pearson r|.
입력: signal, modality_pair (예: ["ABP", "PPG"]).
출력: score, reason, meta.
주의:
  - score < 0.4 (consistency 임계) + 두 modality quality ≥ 0.7 → trigger rule 4 fire
  - 한쪽 modality 부재 / flatline → score 가 의미 없음 (meta 에 표시)
  - 본 score 는 *correlation*, 인과 관계 아님 — LLM 이 해석 시 conditional phrasing 사용
(Leakage guard. Quality-aware propagate.)
```

### LLM Description (EN)

```
Purpose: Cross-modal consistency score in [0, 1] between two modalities.
1 = consistent, 0 = inconsistent. Rule-based implementation uses |Pearson r|
on a quality-filtered window.
Input: signal, modality_pair (e.g., ["ABP", "PPG"]).
Output: score, reason, meta.
Caveats:
  - score < 0.4 AND both modality qualities ≥ 0.7 fires trigger rule #4
  - One modality absent / flatline → score is meaningless (meta records this)
  - This is a correlation metric, not causal — LLM must use conditional phrasing
(Leakage guard. Quality-aware propagate.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| modality_pair 크기 ≠ 2 | `error.type = "invalid_args"` |
| 한쪽 modality 부재 | success, `score=0.0, reason="modality_absent"` |

---

## Tool 5 — `temporal_trend_analysis`

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
  "properties": {
    "slope":     {"type": "number"},
    "magnitude": {"type": "number", "minimum": 0},
    "label":     {"type": "string", "enum": ["rising", "falling", "stable"]},
    "meta":      {"type": "object"}
  }
}
```

### Protocol method

`temporal_trend(signal, modality, window_min) -> TrendResult`

### LLM Description (KR)

```
용도: 특정 modality 의 window_min 분 동안 시간 추세 (slope) 분석.
입력: signal, modality, window_min (기본 5).
출력:
  - slope: 추세 기울기 (단위는 modality 별; ABP 라면 mmHg/min)
  - magnitude: |slope * window| (변화 폭)
  - label: "rising" / "falling" / "stable" (|slope|<1 → stable)
  - meta: mock_tier, intermediate stats
주의:
  - 신호 품질 낮으면 slope 가 noise 일 수 있음 — quality_meta 확인 후 phrasing
  - Δrisk (trigger rule 2) 와 별개 metric — modality 신호 자체의 trend
(Leakage guard. Quality-aware propagate.)
```

### LLM Description (EN)

```
Purpose: Temporal trend (slope) of a modality over the past `window_min` minutes.
Input: signal, modality, window_min (default 5).
Output:
  - slope: trend slope in modality-specific units (e.g., mmHg/min for ABP)
  - magnitude: |slope * window| (change amplitude)
  - label: "rising" / "falling" / "stable" (|slope|<1 → stable)
  - meta: mock_tier, intermediate stats
Caveats:
  - Low signal quality → slope may be noise; check quality_meta before phrasing
  - Distinct from Δrisk (trigger rule #2); this is a signal-level trend
(Leakage guard. Quality-aware propagate.)
```

### Failure modes

| Failure | 표현 |
|---------|------|
| modality 부재 | success with `label="stable", slope=0, meta.modality_absent=True` |
| FM 내부 exception | `error.type = "tool_internal_error"` |

---

## Tool 6 — `forecast_signal`

### Input

```json
{
  "required": ["modality", "horizon_min"],
  "properties": {
    "modality":    {"type": "string"},
    "horizon_min": {"type": "integer", "minimum": 1, "maximum": 30}
  }
}
```

### Output

```json
{
  "properties": {
    "forecast":    {"type": "array", "items": {"type": "number"}},
    "uncertainty": {"type": "array", "items": {"type": "number", "minimum": 0}},
    "meta":        {"type": "object"}
  }
}
```

### Protocol method

`forecast_signal(signal, modality, horizon_min) -> ForecastResult`

### LLM Description (KR)

```
용도: 특정 modality 의 horizon_min 분 미래 trajectory 예측.
입력: signal, modality, horizon_min.
출력:
  - forecast: length = horizon_min (분 단위 예측값)
  - uncertainty: length = horizon_min, 시간이 갈수록 증가
  - meta: mock_tier, residual_std 등
주의:
  - 본 출력은 *예측* 이며 미래의 실측이 아님 → "예측" 으로 LLM 이 phrasing
  - rule-based 구현은 linear extrapolation; real FM 도착 후 출력 분포가 달라짐
(Leakage guard. Quality-aware propagate.)
```

### LLM Description (EN)

```
Purpose: Forecast a modality's trajectory `horizon_min` minutes into the future.
Input: signal, modality, horizon_min.
Output:
  - forecast: list of length horizon_min (per-minute predictions)
  - uncertainty: list of length horizon_min, increasing with horizon
  - meta: mock_tier, residual_std, etc.
Caveats:
  - This is a PREDICTION, not a future measurement → LLM must phrase as such
  - Rule-based implementation uses linear extrapolation; real FM will differ
(Leakage guard. Quality-aware propagate.)
```

### Failure modes — same pattern

---

## Tool 7 — `anomaly_score`

### Input

```json
{
  "required": ["modality"],
  "properties": {
    "modality": {"type": "string"}
  }
}
```

### Output

```json
{
  "properties": {
    "score": {"type": "number", "minimum": 0, "maximum": 1},
    "meta":  {"type": "object"}
  }
}
```

### Protocol method

`anomaly_score(signal, modality) -> AnomalyResult`

### LLM Description (KR)

```
용도: 특정 modality window 의 이상치 (anomaly) score (0–1). 1=강한 anomaly.
입력: signal, modality.
출력: score, meta.
주의:
  - score > 0.5 는 *비정상 신호 패턴* 일 가능성; 임상 진단 아님
  - Flatline → score ≈ 0 (signal 자체가 없음)
  - score 단독으로 [Risk evaluation] section 의 risk claim 만들기 금지 — supporting evidence 로만 사용
(Leakage guard. Quality-aware propagate.)
```

### LLM Description (EN)

```
Purpose: Anomaly score in [0, 1] for a modality window. 1 = strong anomaly.
Input: signal, modality.
Output: score, meta.
Caveats:
  - score > 0.5 suggests an abnormal signal pattern; not a diagnosis
  - Flatline → score ≈ 0 (no signal)
  - Do not use score alone to make a [Risk evaluation] claim — supporting evidence only
(Leakage guard. Quality-aware propagate.)
```

---

## Cross-cutting alignment table — FM Tool ↔ Protocol Method ↔ Result Dataclass

| Tool # | Tool name | Protocol method | Result dataclass | Result fields |
|--------|-----------|-----------------|------------------|---------------|
| 1 | `predict_hypotension` | `predict_hypotension` | `HypotensionResult` | risk, uncertainty, horizon_min, meta |
| 2 | `predict_cardiac_arrest` | `predict_cardiac_arrest` | `ArrestResult` | risk, uncertainty, horizon_min, meta |
| 3 | `assess_signal_quality` | `assess_signal_quality` | `QualityResult` | score, reason, meta |
| 4 | `cross_modal_consistency` | `cross_modal_consistency` | `ConsistencyResult` | score, reason, meta |
| 5 | `temporal_trend_analysis` | `temporal_trend` | `TrendResult` | slope, magnitude, label, meta |
| 6 | `forecast_signal` | `forecast_signal` | `ForecastResult` | forecast, uncertainty, meta |
| 7 | `anomaly_score` | `anomaly_score` | `AnomalyResult` | score, meta |

Protocol method `encode` 은 tool 로 노출되지 않음 (내부 latent representation).

## Mock vs Real FM — description 의 보편성 (audit)

본 7 tool description 은 다음 조건을 만족해야 한다 (`v1_tool_description_style.md` audit):

1. ✅ "stub" / "rule_based" / "real" 어느 mock_tier 가 와도 description 이 그대로 적용된다
2. ✅ "mock_tier == 'stub'" 한계는 description 에서 *언급* 만 — 별도 mock-전용 phrasing 강제 안 함
3. ✅ uncertainty 가 7 tool 중 6 개에 *명시적으로* 기술됨 (예외: `anomaly_score`, `temporal_trend_analysis` 는 magnitude/label 로 대체)
4. ✅ failure mode 모두 fallback 동작 명시

자세한 audit 결과는 `.plans/stage1_preparation/plan_1.7_tool_spec.md` 의 audit note 섹션.
