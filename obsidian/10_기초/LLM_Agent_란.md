# LLM Agent 란

> LLM에 "도구" 와 "상태" 와 "반복 루프"를 더한 것.

## LLM (Large Language Model) 한 줄

GPT, Claude, Llama 같은 모델. 입력 텍스트를 받아 다음 텍스트를 출력한다. 그게 전부.

```
LLM:  "환자의 MAP이 60이고 떨어지는 추세입니다."
       ↓
       "주의 — 저혈압 가능성이 있으니 임상의 판단 필요."
```

LLM은 **stateless** (이전 대화를 기억하지 못함)다. 우리가 외부에서 context로 매번 끼워 넣어야 한다.

## Agent 는 LLM + 3가지

LLM 자체로는 "글을 만든다"가 끝. **Agent**는 거기에 3가지를 더한다.

### 1. 도구 (tool)

LLM이 "MAP이 얼마야?"라고 *물어볼 수 있는* 함수다.

```
LLM이 출력: "predict_hypotension(case_id='abc', horizon_min=5)"
실행 결과:  risk=0.42, uncertainty=0.18
LLM이 다음 입력으로: "risk가 0.42야. 너의 narration은?"
```

자세한 건 [[Tool_calling_과_Function_calling]].

### 2. 상태 (state)

매 호출 사이에 보존되는 정보. 위 LLM 호출의 *결과*를 기억해서, 다음 호출에 같이 넣어줘야 한다.

```
state = {
    "risk_history": [...],     # 지난 risk 점수들
    "quality_history": [...],  # 지난 신호 품질 점수들
    "brief_history": [...],    # 발화한 brief들
}
```

자세한 건 [[Pydantic_과_typed_state]].

### 3. 루프 (loop)

Agent는 "한 번 호출하고 끝"이 아니다. 무한 또는 정해진 횟수만큼 다음을 반복:

```
while not done:
    1) tool 호출  →  결과 받기
    2) LLM 추론  →  다음 행동 결정
    3) state 갱신
```

루프 안에서 "이번 turn은 Shallow narration만, 다음 turn은 Deep brief"처럼 분기도 한다. 자세한 건 [[LangGraph_와_StateGraph]].

## Tool-using LLM Agent — VitalAgent에서 무슨 뜻인가

**Agent의 LLM은 직접 의학 지식을 가지지 않는다.** 대신 우리가 만든 21개의 tool을 호출해서:

- "지금 환자의 hypotension risk가 얼마야?" → `predict_hypotension` tool
- "ABP 신호 품질이 어때?" → `assess_signal_quality` tool
- "최근 마취제 몇 mg 들어갔어?" → `query_anesthesia_drugs` tool

그 결과를 받아 임상의에게 **한글로** 요약해 준다.

```
[21 tool 결과]
       ↓
[LLM이 종합]
       ↓
"안정 — 저혈압 risk 0.42, 심정지 risk 0.05."  (Shallow, 30초마다)
        또는
"[Surgery context]   복부 수술, maintenance phase, 경과 45분...
 [Signal status]      ABP 품질 양호 (0.92), PPG 품질 양호 (0.88)...
 ... (9 section)"                             (Deep, event 시)
```

## LLM의 한계 — 왜 Tool이 필요한가

LLM 혼자서는:

- **숫자 계산 부정확** — risk 점수 같은 정량은 모델 학습 데이터의 통계 평균에 기반. 실시간 환자에는 적용 불가
- **최신 정보 부재** — 학습 시점 이후의 환자 데이터를 모름
- **출처 불명** — "이 risk는 어디서 나왔나?" 답을 못 줌
- **환각 (hallucination)** — 사실인 듯한 거짓을 만들어 냄

Tool을 끼우면:

- **숫자 계산은 Foundation Model이** 수행 (FM은 신호 → 숫자 매핑 학습됨)
- **데이터는 VitalDB에서** 실시간 조회
- **출처는 tool name + 인자**에 명시
- **환각은 trace에서** 검증 가능 (LLM이 claim한 risk = tool이 반환한 risk인지)

VitalAgent의 21 tool은 [[20_아키텍처/21_Tool_Suite]] 참조.

## 시각화 — VitalAgent 구조 한 그림

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

- LLM: 의학 지식 + 한글 글솜씨 (학습된 모델)
- Tool: 모니터 / 차트 / 약 기록 등 *외부 도구*
- State: 수련의의 메모지 (이번 case에서 관찰한 것들)
- Loop: 30초마다 모니터 확인 + 이상 시 깊이 검토

VitalAgent는 *경험 부족한 똑똑한 수련의*다. 임상 결정은 임상의 (attending)가 한다. 그래서 **임상 사실 단정 금지** 정책이 핵심.

## 다음 노트

- [[Tool_calling_과_Function_calling]] — tool이 어떻게 LLM에서 호출되는지
- [[LangGraph_와_StateGraph]] — 우리가 쓰는 루프 엔진
- [[20_아키텍처/Dual_mode_architecture]] — Shallow + Deep 분기 구조
