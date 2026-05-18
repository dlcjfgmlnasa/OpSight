# v1 — Tool Description Style Guide

> 16 개 tool 의 `description` 필드를 *어떻게 작성할지* 의 guide.
> 본 guide 는 `plan_1.7` (`langgraph-engineer` 가 owner) 가 16 tool spec 을 작성할 때 따른다.
> 동시에 `vitalagent/tools/registry.py` 의 inline description 도 본 guide 를 따른다.

---

## 왜 description 이 중요한가

VitalAgent 의 LLM 은 *tool 을 직접 선택*하지 않는다 (rule-based 호출, brief §13.3). 그러나 LLM 은 *tool 결과를 해석* 할 때 description 을 읽는다. Description 이 모호하면:

- LLM 이 risk 값의 *단위 / 의미*를 오해
- `[Evidence]` 또는 `[Limitations]` section 에서 부정확 / 환각
- Quality-aware 특성 약화 (LLM 이 uncertainty 의 의미를 모름)

→ 매 description 은 LLM 가 *처음 보는 임상 도구* 라고 가정하고 작성한다.

## Format — 4-line skeleton

```
1. Purpose: <한 문장, 무엇을 측정 / 예측 / 조회 하는가>
2. Input: <인자 이름 + 의미 + 단위>
3. Output: <키 이름 + 범위 + 단위 + uncertainty 의미>
4. Caveats: <failure mode + 신뢰도 한계 + leakage guard 참고>
```

- 영문이 default (LLM 학습 데이터 분포). 단 한국 임상 용어가 적합하면 병기.
- 70 – 200 tokens / tool. 짧게.
- 모든 description 끝에 `(Leakage guard: query_window_end_s ≤ clock.now_s)` 한 줄.
- 모든 description 끝에 `(Quality-aware: returns uncertainty; caller must propagate.)`

## Example — `predict_hypotension`

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
  - Mock_tier == "stub" output is random — do not use for clinical reasoning
  - Higher uncertainty → cite explicitly in [Risk evaluation] section
(Leakage guard: caller must not include future samples in `signal`.)
(Quality-aware: returns uncertainty; caller must propagate.)
```

## Example — `assess_signal_quality`

```
Purpose: Score the quality of a single modality's signal window in [0, 1],
where 1 is clean and 0 is unusable (flatline / saturated NaN).
Input:
  - signal: dict of modality -> tensor
  - modality: target modality name (e.g., "ABP", "ECG_II", "PPG")
Output:
  - score: float in [0, 1] — overall quality
  - reason: optional string explaining low scores ("flatline", "high_nan_ratio", ...)
  - meta: dict (mock_tier, intermediate diagnostics)
Caveats:
  - Score < 0.5 → cite in [Limitations] section + lower Assessment confidence
  - Score < 0.3 → consider Assessment confidence = UNRELIABLE
  - Absent modality returns score = 0.0 with reason = "modality_absent"
(Leakage guard: caller must not include future samples.)
(Quality-aware: this IS the quality signal — caller propagates downstream.)
```

## Example — `query_anesthesia_drugs` (EMR stub)

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
  - `query_window_end_s` (= time_window.end_s) must not exceed clock.now_s
(Leakage guard: query_window_end_s ≤ clock.now_s enforced.)
(Quality-aware: meta.clinical_review_required signals stub provenance.)
```

## Anti-patterns — 다음과 같이 작성하지 말 것

❌ 너무 짧음 (의미 부족):
```
description: "Get risk."
```

❌ 단정적 임상 어조:
```
description: "Diagnoses hypotension within 5 minutes. Used by clinicians."
```

❌ 단위 / 범위 누락:
```
description: "Returns the risk for hypotension."
```
→ "risk" 의 단위, 범위, uncertainty 가 명시되지 않으면 LLM 이 0.5 의 의미를 오해할 수 있다.

❌ Leakage guard / quality 정책 무시:
```
# 끝에 leakage / quality 메모 없음 → LLM 이 미래 데이터 사용 가능성 인지 못함
```

## Tool 16 개 description 필요 항목 (체크리스트)

| # | Tool | Status |
|---|------|--------|
| 1 | `predict_hypotension` | ✅ 본 doc 예시 |
| 2 | `predict_cardiac_arrest` | (plan_1.7 작성 예정) |
| 3 | `assess_signal_quality` | ✅ 본 doc 예시 |
| 4 | `cross_modal_consistency` | (plan_1.7) |
| 5 | `temporal_trend_analysis` | (plan_1.7) |
| 6 | `forecast_signal` | (plan_1.7) |
| 7 | `anomaly_score` | (plan_1.7) |
| 8 | `query_anesthesia_drugs` | ✅ 본 doc 예시 |
| 9 | `query_vasoactive_drugs` | (plan_1.7) |
| 10 | `query_fluid_blood` | (plan_1.7) |
| 11 | `query_surgery_progress` | (plan_1.7) |
| 12 | `query_patient_baseline` | (plan_1.7) |
| 13 | `find_similar_cases` | TBD (after plan_1.7 spec) |
| 14 | `intervention_response_prediction` | TBD (ADR-013 pending) |
| 15 | `surgery_context_awareness` | TBD (plan_1.5 dependency) |
| 16 | `quality_aware_synthesis` | TBD (plan_1.7) |

## Versioning

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-05-17 | Initial — plan_1.6 |

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] (description tone + clinical phrasing 정합성 검토)
