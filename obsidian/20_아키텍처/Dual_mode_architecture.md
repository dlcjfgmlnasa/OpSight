# Dual-Mode Architecture — Shallow + Deep

> Agent 가 두 가지 모드로 동작. 평상시 가볍게 (Shallow 30s), 위험 신호 시 깊게 (Deep on-demand).

## 왜 두 모드인가

매 30s 마다 Heavy LLM 으로 9-section brief 를 만들면 세 가지 문제:

1. **느림** — Heavy 70B 호출이 수십 초. 30s 주기 안에 못 끝남
2. **비쌈** — 매 tick GPU 비용 폭발
3. **불필요** — 안정 상태에선 "안정" 한 줄로 충분

해법: 평상시 가볍게, 필요할 때만 깊게. 모드 분기는 **결정론적 rule** 이 정한다 (LLM X).

## 두 모드 비교

| | Shallow | Deep |
|---|---|---|
| 주기 | 30s 마다 (rule) | event 발생 시 (trigger) |
| 호출 tool | 5개 (quick) | **21개 전체** |
| LLM | Light (Llama-3.1-8B, 4-bit) | Heavy (Llama-3.3-70B, 4-bit streaming) |
| 출력 | 1문장 한글 (≤ 50 tokens) | 9-section 한글 brief (500–800 tokens) |
| 목표 latency | < 15s | < 60s |
| GPU | GPU1 (FM + Light) | GPU2 (Heavy) |
| 임상의 review | 위험 band 시 권고 | 항상 |

자세한 brief 구조: [[9_Section_Brief]], 21 tool: [[21_Tool_Suite]].

## Shallow tick 한 번

```
[30s window signal]
         │
         ▼
    [FM forward ≈80ms]
         │
         ├─► predict_hypotension          (≈30ms)
         ├─► predict_cardiac_arrest       (≈30ms)
         ├─► assess_signal_quality        (≈10ms)
         ├─► cross_modal_consistency      (≈20ms)
         └─► anomaly_score                (≈15ms)
                │
                ▼
        5 tool 결과
                │
                ▼
     [Light LLM 한 줄 narration]
                │
                ▼
   "[안정] 저혈압 risk 0.42, 심정지 risk 0.05."
                │
                ▼
     state.risk_history 누적
                │
                ▼
   [7-rule trigger 평가]
                │
        ┌───────┴───────┐
        ▼               ▼
   다시 Shallow      Deep mode
```

[[30_코드_워크스루/06_nodes_graph]] 참조.

## Deep mode 추가 tool

Shallow 5개 위에:

- **FM 추가 2개** — `temporal_trend_analysis`, `forecast_signal`
- **EMR 5개** — anesthesia / vasoactive / fluid / surgery progress / patient baseline
- **Knowledge 2개** — `find_similar_cases`, `intervention_response_prediction` (stub)
- **Auxiliary 2개** — `surgery_context_awareness`, `quality_aware_synthesis`
- **Signal Access 5개** — current vitals, describe, variability, baseline 비교, summarize

총 21개 결과가 Heavy LLM 에 JSON 으로 전달 → 9-section brief 생성.

## Shallow → Deep — Trigger 7-rule

LangGraph conditional edge 가 `should_escalate(state)` 호출. 7 rule + 60s cooldown.

1. Hypotension risk > 0.7
2. Risk 급상승 (Δ > 0.3 in 30s)
3. 신호 품질 하락 (drop > 0.3)
4. Cross-modal 불일치 (consistency < 0.4 & good quality)
5. **Acute event** — arrest risk > 0.5 (cooldown 우회)
6. **Clinician on-demand** (cooldown 우회)
7. Periodic check — 마지막 deep 후 5분

[[Trigger_7_Rules]] 참조.

## 누가 결정하는가 — LLM vs Rule

| | LLM | Rule |
|---|---|---|
| Shallow tick tool 선택 | — | ✅ 5개 모두 |
| Shallow → Deep 분기 | — | ✅ 7-rule |
| Deep tick tool 선택 | — | ✅ 21개 모두 |
| Narration / Brief 자연어 | ✅ | — |

LLM 은 자연어 생성만. Tool 선택 / trigger 는 결정론적 rule. 이유:

- **Safety** — LLM 환각으로 중요 tool 누락 / acute event 놓치면 brief 잘못됨
- **Latency 예측** — 어떤 tool 이 불릴지 미리 알아야 시간 예산 가능
- **검증** — trace 에 deterministic tool sequence, 같은 입력 같은 호출

[[10_기초/Tool_calling_과_Function_calling]] + brief §13.3.

## 100-case e2e 결과 (2026-05-16)

100 synthetic case (MAP 55–95 sweep):
- 100/100 deep brief 발화
- 총 300 deep fires (case 당 평균 3회)
- p95 per-tick **4.8ms** (placeholder LLM, real LLM 시 늘어남)
- Trigger: `hypotension_risk > 0.7` 66회, `cross_modal_inconsistency < 0.4` 234회
- Leakage 0건

`tests/integration/test_e2e_100cases_tier2.py`.

## Real LLM 합류 시 latency 변화

- Light 8B (vLLM 4-bit, GPU): ~3–8s
- Heavy 70B (vLLM 4-bit streaming): ~20–60s

Shallow 15s budget = Light + tool 5개 (각 ~30ms) → *겨우* 맞춤. 최적화 필요 가능성.

## 다음 노트

- [[Mock_FM_3_Tier_전략]] — FM 자체의 진화
- [[Trigger_7_Rules]] — Shallow ↔ Deep 결정 규칙
- [[21_Tool_Suite]] — 21 tool 카탈로그
- [[9_Section_Brief]] — Deep 출력 형식
- [[30_코드_워크스루/06_nodes_graph]] — graph 코드
