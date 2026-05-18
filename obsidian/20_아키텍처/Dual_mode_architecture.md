# Dual-Mode Architecture — 가볍게 보다가 필요할 때 깊게

> Agent 가 두 가지 모드로 동작한다. 평상시엔 30초마다 짧게 (Shallow), 위험 신호가 잡힐 때만 깊게 (Deep).

## 왜 두 모드로 나누었나

수술실 모니터는 빠르게 반응해야 한다. 우리 시뮬레이션 기준으로 agent 는 **30초마다 한 번** 환자 상태를 확인한다. 그런데 매번 **9-section 짜리 한글 brief** 를 LLM 에게 작성시키면 세 가지가 문제다.

1. **느리다.** Heavy LLM (Llama-3.3-70B) 호출은 수십 초가 걸린다. 30초 주기 안에 못 끝낸다.
2. **비싸다.** 매 tick 마다 70B 모델을 부르면 GPU 비용이 폭발한다.
3. **불필요하다.** 환자가 안정 상태면 "안정" 한 줄이면 충분하다. 매번 9-section 을 받아봐야 의미 없다.

해법은 자연스럽다 — **평상시엔 가볍게, 필요할 때만 깊게**. 두 모드를 한 graph 안에 두고, 어떤 모드로 갈지는 **결정론적인 규칙 (rule)** 이 정한다 (LLM 이 정하지 않는다, 이유는 아래).

## 두 모드는 무엇이 다른가

**Shallow mode (평상시 30초 주기)**
- 5개의 빠른 tool 만 부른다 — hypotension risk, cardiac arrest risk, signal quality, cross-modal consistency, anomaly score
- 가벼운 LLM (Llama-3.1-8B, 4-bit 양자화) 이 받아서 **한 줄 한글 narration** 생성 (50 token 이하)
- 예: `"[안정] 저혈압 risk 0.15, 심정지 risk 0.03."`
- 목표 latency: **15초 이내** (Light LLM + tool 5개)
- 임상의 review 는 "위험 band" 일 때만 권고

**Deep mode (위험 신호 발생 시 on-demand)**
- 21개 tool 모두 부른다 — FM 7개 + EMR 5개 + Knowledge 2개 + Auxiliary 2개 + Signal Access 5개
- 무거운 LLM (Llama-3.3-70B, 4-bit streaming) 이 받아서 **9-section 한글 brief** 생성 (500–800 token)
- 목표 latency: **60초 이내**
- 임상의 review 가 항상 권고됨

자세한 brief 구조는 [[9_Section_Brief]], 21개 tool 의 spec 은 [[21_Tool_Suite]].

## Shallow tick 한 번이 흘러가는 모습

```
[VitalDB 신호 30초 window]
         │
         ▼
    [FM forward, 약 80ms]
         │
         ├─► predict_hypotension          (≈30ms)
         ├─► predict_cardiac_arrest       (≈30ms)
         ├─► assess_signal_quality        (≈10ms)
         ├─► cross_modal_consistency      (≈20ms)
         └─► anomaly_score                (≈15ms)
                │
                ▼
        5개 tool 결과 묶음
                │
                ▼
     [Light LLM 이 한 줄 narration 생성]
                │
                ▼
   "[안정] 저혈압 risk 0.42, 심정지 risk 0.05."
                │
                ▼
     state.risk_history 에 누적
                │
                ▼
   [7-rule trigger 평가 — rule-based]
                │
        ┌───────┴───────┐
        ▼               ▼
   다시 Shallow      Deep mode
```

코드 흐름은 [[30_코드_워크스루/06_nodes_graph]] 에 한 줄씩 풀어 두었다.

## Deep mode 는 무엇을 추가로 부르나

Shallow 의 5개 tool 위에 다음이 추가된다.

- **FM 의 나머지 2개** — `temporal_trend_analysis` (추세 분석), `forecast_signal` (앞으로의 예상)
- **EMR 5개** — 마취제, 혈관활성제, 수액·수혈, 수술 진행 단계, 환자 baseline
- **Knowledge 2개** — 유사 case 검색, intervention response 예측 (현재 stub)
- **Auxiliary 2개** — 수술 맥락 hint, quality-weighted fusion
- **Signal Access 5개** — 현재 vitals, 신호 통계 기술, variability (HRV 등), baseline 대비 변화, 종합 요약

이 모든 결과가 Heavy LLM 에게 JSON 으로 묶여 전달되고, LLM 은 정해진 9-section 형식으로 brief 를 작성한다.

## Shallow → Deep 으로 언제 넘어가는가

LangGraph 의 conditional edge 가 `should_escalate(state)` 함수를 호출하고, 이 함수가 7개 규칙을 평가한다. 어느 하나라도 발화하면 Deep 으로 간다.

7개 규칙의 골격:

1. 저혈압 risk 가 0.7 을 넘으면 발화
2. Risk 가 30초 안에 0.3 이상 급상승하면 발화
3. 신호 품질이 0.3 이상 떨어지면 발화
4. Cross-modal 불일치 (consistency < 0.4) 가 잡히면 발화
5. **Acute event** — cardiac arrest risk > 0.5 면 즉시 발화 (cooldown 우회)
6. **Clinician on-demand** — 사용자가 명시적으로 요청하면 즉시 발화 (cooldown 우회)
7. **Periodic check** — 마지막 deep 후 5분이 경과하면 발화

연속 Deep 발화를 막기 위해 **60초 cooldown** 이 걸려 있고, 5번과 6번만 이를 우회한다 (환자 안전 / 명시적 요청 우선). 자세한 건 [[Trigger_7_Rules]].

## 누가 어떤 결정을 하는가 — LLM vs Rule

이 시스템에서 가장 자주 헷갈리는 부분이라 명확히 한다.

| 결정 | LLM | Rule |
|---|---|---|
| Shallow tick 에서 어떤 tool 부를지 | — | ✅ 5개 모두 |
| Shallow → Deep 분기 | — | ✅ 7-rule |
| Deep tick 에서 어떤 tool 부를지 | — | ✅ 21개 모두 |
| Shallow narration / Deep brief 의 *자연어* 생성 | ✅ | — |

LLM 은 **자연어 생성만** 한다. tool 선택과 trigger 결정은 결정론적 rule 이다. 이유는 세 가지:

- **안전** — LLM 이 "이번엔 vasoactive 조회 안 해도 돼" 라고 환각해서 빠뜨리면, 그 brief 는 잘못된다. Rule 이라면 그런 누락은 없다.
- **Latency 예측 가능** — 어떤 tool 이 불릴지 미리 알 수 있으니 시간 예산을 짤 수 있다.
- **검증 가능** — trace 에 tool 호출 sequence 가 deterministic 으로 찍히니, 같은 입력은 같은 출력 (LLM 자연어 생성은 결과만 비결정적, 호출 sequence 는 결정적).

자세한 정책 배경은 [[10_기초/Tool_calling_과_Function_calling]] 와 project brief §13.3.

## 실측 — 100 case end-to-end 결과

100개의 synthetic case (MAP baseline 55–95, slope -6 ~ +4 sweep) 를 돌려본 결과 (2026-05-16):

- 100/100 case 에서 deep brief 가 한 번 이상 발화함
- 총 300 회 deep 발화 (case 당 평균 3회)
- p95 per-tick latency: **4.8ms** — Shallow 의 15초 budget 의 0.03%. 단, 이건 placeholder LLM 기준이라 진짜 LLM 합류 시 늘어남
- Trigger 별 분포: hypotension_risk > 0.7 → 66회, cross_modal_inconsistency < 0.4 → 234회
- 데이터 누수 0건

테스트는 `tests/integration/test_e2e_100cases_tier2.py`.

## 진짜 LLM 이 합류하면 시간이 어떻게 바뀌나

지금은 placeholder template 이라 매 tick 이 수 ms 로 끝난다. 진짜 LLM 이 합류하면 다음으로 늘어난다.

- **Light 8B (vLLM 4-bit, GPU)**: tick 당 3–8초
- **Heavy 70B (vLLM 4-bit streaming, GPU)**: brief 당 20–60초

Shallow 의 15초 예산은 Light LLM + tool 5개 (각 30ms 안팎) 를 합산하면 *겨우* 맞는다. 합류 후 실측해서 최적화가 필요할 가능성이 있다.

## 다음 노트

- [[Trigger_7_Rules]] — 7개 trigger 규칙을 한 줄씩
- [[Mock_FM_3_Tier_전략]] — FM 자리에 무엇을 끼우고 있는가
- [[21_Tool_Suite]] — 21개 tool 의 카탈로그
- [[9_Section_Brief]] — Deep mode 의 출력 형식
- [[30_코드_워크스루/06_nodes_graph]] — graph 코드 한 줄씩
