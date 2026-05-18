# Tool Calling 과 Function Calling

> "LLM이 함수를 호출한다"는 표현의 실체.

## LLM은 진짜로 함수를 *호출*하지 않는다

LLM은 텍스트를 만드는 모델이다. 함수를 실행하지 못한다. 우리가 흔히 말하는 "tool calling"은 정확히는 다음 흐름이다.

```
1. 사용자가 LLM에 "사용 가능한 tool 명세"를 같이 준다.
   - 예: predict_hypotension(case_id: str, horizon_min: int) -> {risk, uncertainty}

2. LLM은 다음 텍스트를 출력한다 (보통 JSON 형식):
   {
     "tool_name": "predict_hypotension",
     "args": {"case_id": "case-001", "horizon_min": 5}
   }

3. 우리 코드 (agent framework)가 그 JSON을 파싱.
4. 우리 코드가 실제 Python 함수 predict_hypotension(case_id="case-001", horizon_min=5)을 실행.
5. 결과 {risk: 0.42, uncertainty: 0.18}을 LLM에 다음 입력으로 다시 넣어준다.
6. LLM은 결과를 보고 narration / brief를 작성.
```

LLM은 "어떤 tool을 어떤 인자로 부를지 *결정만*" 한다. 실제 호출은 우리 코드가 한다.

## Function calling = OpenAI 용어, Tool use = Anthropic 용어

같은 메커니즘. 본 문서는 **tool call**로 통일.

## VitalAgent의 21 tool — schema 한 줄씩

| # | Tool | 카테고리 | 입력 | 출력 |
|---|------|----------|------|------|
| 1 | `predict_hypotension` | FM | (case_id, horizon_min) | {risk, uncertainty, ...} |
| 2 | `predict_cardiac_arrest` | FM | (case_id, horizon_min) | {risk, uncertainty, ...} |
| 3 | `assess_signal_quality` | FM | (case_id, modality) | {score, reason, ...} |
| 4 | `cross_modal_consistency` | FM | (case_id, modality_pair) | {score, reason, ...} |
| 5 | `temporal_trend_analysis` | FM | (case_id, modality, window) | {slope, magnitude, label} |
| 6 | `forecast_signal` | FM | (case_id, modality, horizon) | {forecast: [...], uncertainty: [...]} |
| 7 | `anomaly_score` | FM | (case_id, modality, window) | {score} |
| 8 | `query_anesthesia_drugs` | EMR | (case_id, time_window) | {drugs: [...]} |
| 9 | `query_vasoactive_drugs` | EMR | (case_id, time_window) | {drugs: [...]} |
| 10 | `query_fluid_blood` | EMR | (case_id) | {intake_cumulative, ebl, urine, ...} |
| 11 | `query_surgery_progress` | EMR | (case_id, current_time) | {phase, elapsed_min, ...} |
| 12 | `query_patient_baseline` | EMR | (case_id) | {age, sex, asa, ...} |
| 13 | `find_similar_cases` 🟡 stub | Knowledge | (current_state, surgery_type, k) | [...] |
| 14 | `intervention_response_prediction` 🟡 stub | Knowledge | (intervention, dose) | {...} |
| 15 | `surgery_context_awareness` ✅ yaml-backed | Auxiliary | (surgery_type, phase) | {...} |
| 16 | `quality_aware_synthesis` ✅ full | Auxiliary | (predictions, qualities) | {fused_value, ...} |
| **17** | **`get_current_vitals`** ★ ADR-016 | **Signal Access** | (case_id, time) | {map, sbp, dbp, hr, rr, spo2, etco2, bis, temp} |
| **18** | **`describe_signal`** ★ | **Signal Access** | (case_id, modality, window_min) | {mean, std, min, max, median, iqr, missing_ratio, n_samples} |
| **19** | **`assess_variability`** ★ | **Signal Access** | (case_id, modality) | HRV / BPV / SVV metric dict |
| **20** | **`compare_to_baseline`** ★ | **Signal Access** | (case_id, modality, preop_baseline?) | {baseline, current, change, direction} |
| **21** | **`summarize_current_state`** ★ 🟡 stub | **Signal Access** | (case_id, time) | {hemodynamic_state, anesthesia_state, respiratory_state, key_concerns, overall_assessment} |

자세한 schema는 [[20_아키텍처/21_Tool_Suite]] 참조. 🟡 stub = full 은 회의 / Tier 0 wrap 후. ★ = ADR-016 신규 (Sprint 5).

## 우리 코드에서 tool은 어떻게 정의되는가

```python
# vitalagent/tools/registry.py 일부 발췌

TOOLS: Final[dict[str, ToolSpec]] = {
    "predict_hypotension": ToolSpec(
        name="predict_hypotension",
        category="fm",
        description="Predict hypotension risk within horizon_min.",
        fn=tool_predict_hypotension,
        needs_fm=True,
        needs_signal=True,
    ),
    # ... 11개 더 ...
}
```

- `name`: LLM에 노출되는 tool 이름
- `description`: LLM이 "언제 이 tool을 쓰는가"를 이해하는 자연어 설명
- `fn`: 실제 호출되는 Python 함수
- `needs_fm`: FM을 인자로 받는지
- `needs_signal`: signal dict를 인자로 받는지

자세한 구조는 [[30_코드_워크스루/05_tools_layer]].

## "Tool description의 품질" 이 LLM 정확도를 좌우한다

LLM이 어떤 tool을 부를지 결정하는 기준은 `description` 문자열. 잘 쓰여 있어야 LLM이 적절히 부른다.

나쁜 예:
```
description: "Get risk"        ← 어떤 risk? horizon은? 언제 부르나?
```

좋은 예:
```
description: "Predict probability of hypotension (MAP < 65 mmHg sustained for ≥1 min) 
within horizon_min minutes ahead. Use when current MAP is borderline or
declining. Returns risk in [0, 1] with uncertainty."
```

VitalAgent의 description tone guide는 **plan_1.6**의 산출물 (`prompts/v1_tool_description_style.md`). 작성 중.

## VitalAgent에서 tool calling은 누가 결정하는가

| 단계 | 결정자 | 무엇을 결정하나 |
|------|--------|-----------------|
| Shallow loop의 5개 quick tool | **rule-based (코드)** | 매 30초 tick 시 5개 tool을 *모두* 부른다. LLM이 선택하지 않는다. |
| Deep brief의 21 tool | rule-based (코드) | Deep mode 진입 시 21 tool을 *모두* 부른다. |
| Trigger (Shallow → Deep) | **rule-based (코드)** | 7개 규칙 (brief §6.3) + 60초 cooldown. LLM 사용 절대 금지. |
| Narration / Brief 생성 | **LLM** | tool 결과를 받아 한글 문장으로 변환. |

→ **VitalAgent는 LLM의 tool 선택 능력에 의존하지 않는다.** 안전성과 deterministic latency를 위해. 자세한 결정은 [[20_아키텍처/Trigger_7_Rules]] + brief §13.3.

## "Trigger는 rule-based, LLM-driven 아니다" 이유

- **Safety**: LLM이 환각으로 "이번엔 deep mode 안 가도 돼"라고 결정하면 환자 안전 위협
- **Latency 예측**: rule은 결정적, LLM은 매 호출이 random 1–10s. 30초 tick budget 안 맞음
- **검증 가능**: rule은 unit test로 검증, LLM 동작은 stochastic하여 어려움

VitalAgent의 trigger 19 unit test 통과 (`tests/test_triggers.py`).

## 다음 노트

- [[LangGraph_와_StateGraph]] — Tool 호출 결과를 어떻게 다음 LLM 호출에 흘려보내는가
- [[20_아키텍처/21_Tool_Suite]] — 21 tool의 상세 schema
- [[30_코드_워크스루/05_tools_layer]] — 코드 워크스루
