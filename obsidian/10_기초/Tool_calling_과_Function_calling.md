# Tool Calling 과 Function Calling

> "LLM 이 함수를 호출한다" 의 실체.

## LLM 은 진짜로 함수를 *호출* 하지 않는다

LLM 은 텍스트 모델이다. 함수를 실행하지 못한다. "tool calling" 의 정확한 흐름:

```
1. 사용자가 LLM 에 "사용 가능한 tool 명세" 를 같이 준다
   - 예: predict_hypotension(case_id: str, horizon_min: int) -> {risk, uncertainty}

2. LLM 이 텍스트 (보통 JSON) 출력:
   {"tool_name": "predict_hypotension", "args": {"case_id": "case-001", "horizon_min": 5}}

3. Agent framework 가 JSON 파싱
4. 실제 Python 함수 predict_hypotension(case_id="case-001", horizon_min=5) 실행
5. 결과 {risk: 0.42, uncertainty: 0.18} 를 LLM 다음 입력에 끼움
6. LLM 이 결과 보고 narration / brief 작성
```

LLM 은 *"어떤 tool 을 어떤 인자로 부를지" 만* 결정. 실제 호출은 agent 코드.

## Function calling = Tool use

OpenAI 용어 vs Anthropic 용어. 같은 mechanism. 본 문서는 **tool call** 통일.

## OpSight 21 tool

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
| 15 | `surgery_context_awareness` ✅ yaml | Auxiliary | (surgery_type, phase) | {...} |
| 16 | `quality_aware_synthesis` ✅ full | Auxiliary | (predictions, qualities) | {fused_value, ...} |
| **17** | **`get_current_vitals`** ★ | Signal Access | (case_id, time) | {map, sbp, dbp, hr, rr, spo2, etco2, bis, temp} |
| **18** | **`describe_signal`** ★ | Signal Access | (case_id, modality, window_min) | {mean, std, min, max, median, iqr, missing_ratio, n_samples} |
| **19** | **`assess_variability`** ★ | Signal Access | (case_id, modality) | HRV / BPV / SVV dict |
| **20** | **`compare_to_baseline`** ★ | Signal Access | (case_id, modality, preop_baseline?) | {baseline, current, change, direction} |
| **21** | **`summarize_current_state`** ★ 🟡 stub | Signal Access | (case_id, time) | {hemodynamic_state, anesthesia_state, ...} |

자세한 schema: [[20_아키텍처/21_Tool_Suite]]. ★ = ADR-016 신규 (Sprint 5).

## Tool 정의 — `registry.py`

```python
TOOLS: Final[dict[str, ToolSpec]] = {
    "predict_hypotension": ToolSpec(
        name="predict_hypotension",
        category="fm",
        description="Predict hypotension risk within horizon_min.",
        fn=tool_predict_hypotension,
        needs_fm=True,
        needs_signal=True,
    ),
    # ... 20개 더
}
```

- `name` — LLM 에 노출되는 이름
- `description` — LLM 이 "언제 부르는지" 이해하는 자연어
- `fn` — 실제 Python 함수
- `needs_fm` / `needs_signal` — dispatch 분기 기준

[[30_코드_워크스루/05_tools_layer]] 참조.

## Tool description 의 품질이 LLM 정확도를 좌우

나쁜 예
```
description: "Get risk"        ← 어떤 risk? horizon 은? 언제 부르나?
```

좋은 예
```
description: "Predict probability of hypotension (MAP < 65 mmHg sustained for ≥1 min)
within horizon_min minutes ahead. Use when current MAP is borderline or
declining. Returns risk in [0, 1] with uncertainty."
```

OpSight tone guide: `prompts/v1_tool_description_style.md`.

## OpSight — tool calling 은 LLM 이 결정하지 않는다

| 단계 | 결정자 | 무엇을 |
|------|--------|--------|
| Shallow 5 quick tool | **rule (코드)** | 매 30s tick 시 5개 모두. LLM 선택 X |
| Deep 21 tool | **rule (코드)** | Deep 진입 시 21개 모두 |
| Trigger (Shallow → Deep) | **rule (코드)** | 7 rule + 60s cooldown. LLM 사용 절대 금지 |
| Narration / Brief 자연어 | **LLM** | tool 결과를 한글 문장으로 |

→ **OpSight 는 LLM 의 tool 선택 능력에 의존하지 않는다.** Safety + deterministic latency. [[20_아키텍처/Trigger_7_Rules]] + brief §13.3.

## 왜 rule-based trigger

- **Safety** — LLM 환각으로 "이번엔 deep 안 가도 돼" 면 환자 안전 위협
- **Latency 예측** — rule 은 결정적, LLM 은 매번 random 1–10s. 30s tick budget 불가
- **검증 가능** — rule 은 unit test, LLM 은 stochastic

OpSight trigger 19 unit test 통과 (`tests/test_triggers.py`).

## 다음 노트

- [[LangGraph_와_StateGraph]] — tool 결과를 어떻게 다음 LLM 호출에 흘려보내는가
- [[20_아키텍처/21_Tool_Suite]] — 21 tool 상세 schema
- [[30_코드_워크스루/05_tools_layer]] — tool layer 워크스루
- [[20_아키텍처/Trigger_7_Rules]] — rule-based trigger 7 규칙
