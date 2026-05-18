# LLM Agent 란

> LLM 에 *도구* 와 *상태* 와 *반복 루프* 를 더한 것.

## LLM (Large Language Model)

GPT, Claude, Llama 같은 모델. 입력 텍스트를 받아 다음 텍스트를 출력한다. 그게 전부.

```
입력:  "환자의 MAP 이 60 이고 떨어지는 추세입니다."
       ↓
출력:  "주의 — 저혈압 가능성, 임상의 판단 필요."
```

LLM 은 **stateless** 다. 이전 대화를 기억 못 한다. 매번 외부에서 context 로 끼워 넣어야 한다.

## Agent = LLM + 3가지

LLM 자체로는 글만 만들고 끝. Agent 는 거기에 세 가지를 더한다.

### 1. 도구 (tool)

LLM 이 "MAP 이 얼마야?" 라고 *물어볼 수 있는* 함수.

```
LLM 출력 (JSON): {"tool_name": "predict_hypotension", "args": {"horizon_min": 5}}
실행 결과:        {risk: 0.42, uncertainty: 0.18}
LLM 입력에 다시:  "risk 가 0.42 야. narration 은?"
```

자세한 건 [[Tool_calling_과_Function_calling]].

### 2. 상태 (state)

호출 사이에 보존되는 정보. 위 흐름의 *결과* 를 기억해서 다음 호출에 같이 넣어줘야 한다.

```python
state = {
    "risk_history": [...],
    "quality_history": [...],
    "brief_history": [...],
}
```

[[Pydantic_과_typed_state]] 참조.

### 3. 루프 (loop)

"한 번 호출하고 끝" 이 아니다. 정해진 횟수만큼 반복:

```
while not done:
    1) tool 호출 → 결과
    2) LLM 추론 → 다음 행동
    3) state 갱신
```

분기도 한다 ("이번 turn 은 Shallow, 다음 turn 은 Deep"). [[LangGraph_와_StateGraph]] 참조.

## OpSight 에서의 "tool-using LLM agent"

LLM 자체는 의학 지식을 가지지 않는다. 21개의 tool 을 호출해서:

- "지금 hypotension risk 는?" → `predict_hypotension`
- "ABP 신호 품질은?" → `assess_signal_quality`
- "최근 마취제는?" → `query_anesthesia_drugs`

결과를 받아 임상의에게 **한글로** 요약.

```
[21 tool 결과]
       ↓
[LLM 종합]
       ↓
"[안정] 저혈압 risk 0.42, 심정지 risk 0.05."         (Shallow, 30s)
                  또는
"[Surgery context] 복부 수술, maintenance, 45분...   (Deep, event)
 [Signal status]   ABP 0.92, PPG 0.88...
 ... (9 section)"
```

## LLM 혼자서는 안 되는 이유

- **숫자 계산 부정확** — 학습 데이터 통계 평균 기반, 실시간 환자에 적용 불가
- **최신 정보 부재** — 학습 시점 이후 데이터 모름
- **출처 불명** — "이 risk 어디서?" 답 X
- **환각 (hallucination)** — 사실인 듯한 거짓

Tool 을 끼우면:
- 숫자는 FM 이 계산
- 데이터는 VitalDB 에서 실시간 조회
- 출처는 tool name + args 에 명시
- 환각은 trace 에서 검증 가능 (LLM claim risk = tool return risk?)

전체 21 tool: [[20_아키텍처/21_Tool_Suite]].

## 한 그림

```
                    ┌───────────────────────────────────────┐
                    │                AGENT                  │
                    │                                       │
   ┌────────┐       │   ┌──────┐    ┌──────────────┐       │
   │VitalDB │──signal──▶│  FM  │───▶│ 21 tools     │       │
   └────────┘       │   └──────┘    └──────┬───────┘       │
                    │                      │ result        │
                    │                      ▼               │
                    │                ┌──────────┐          │
                    │  state ◀──────▶│   LLM    │          │
                    │                └────┬─────┘          │
                    │                     │ text           │
                    │                     ▼                │
                    │   narration / 9-section brief        │
                    │                     │                │
                    └─────────────────────┼────────────────┘
                                          ▼
                                      [clinician]
```

## 비유: LLM agent ≈ 똑똑한 수련의

- LLM = 의학 지식 + 한글 글솜씨
- Tool = 모니터 / 차트 / 약물 기록
- State = 수련의의 메모지
- Loop = 30초마다 모니터 확인 + 이상 시 깊이 검토

OpSight 는 *경험 부족한* 똑똑한 수련의. 임상 결정은 attending 이 한다 → **임상 사실 단정 금지** 정책.

## 다음 노트

- [[Tool_calling_과_Function_calling]] — tool 이 LLM 에서 어떻게 호출되는가
- [[LangGraph_와_StateGraph]] — 루프 엔진
- [[20_아키텍처/Dual_mode_architecture]] — Shallow + Deep 분기
