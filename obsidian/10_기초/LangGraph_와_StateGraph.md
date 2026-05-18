# LangGraph 와 StateGraph

> 우리가 쓰는 LLM agent 워크플로우 엔진. "node와 edge로 그린 흐름도"를 코드로 표현.

## LangGraph 한 줄

LangChain 팀이 만든 **state-based 그래프 워크플로우** library. 각 node는 함수, edge는 분기 결정. Node 사이를 흘러가는 게 우리의 `AgentState`.

```
START ──► [shallow] ──► [trigger?] ──► [deep] ──► [shallow] ──► ... ──► END
```

## 왜 LangGraph 인가 (다른 옵션 대비)

| 옵션 | 장단점 |
|------|--------|
| LangChain (Agent Executor) | 너무 추상화. tool 호출 흐름이 black-box. |
| AutoGen (Microsoft) | 멀티 agent 협업 중심. 단일 case 흐름은 무겁다. |
| 직접 구현 (while loop) | 가능. 하지만 trace / persistence / 재시작이 직접 처리 필요. |
| **LangGraph** | state schema + conditional edge + 자동 trace. 우리 dual-mode (shallow ↔ deep)와 잘 맞음. |

## StateGraph 핵심 개념 — 3가지만

### 1. State (상태)

모든 node 사이를 흘러가는 dict 또는 Pydantic model. 우리는 `AgentState` Pydantic model 사용. 자세한 건 [[Pydantic_과_typed_state]] + [[30_코드_워크스루/04_state_clock_triggers]].

```python
class AgentState(BaseModel):
    case_id: str
    sim_time_s: float = 0.0
    mode: Literal["shallow", "deep"] = "shallow"
    risk_history: list[RiskSample] = []
    quality_history: list[QualitySample] = []
    brief_history: list[BriefRecord] = []
    # ... 등
```

### 2. Node (노드)

`AgentState → AgentState` 함수다. 받은 state를 갱신해서 반환.

```python
def _shallow_node(state: AgentState) -> AgentState:
    # tool 호출
    # state 갱신
    return new_state
```

VitalAgent의 node:
- `shallow` — 30초 tick마다 quick tool 5개 + narration
- `deep` — full sweep 21 tool + 9-section brief

### 3. Edge (엣지)

Node 사이의 연결. 두 종류:

```python
# 무조건 다음 node로
graph.add_edge("deep", "shallow")

# 조건부 분기
graph.add_conditional_edges(
    "shallow",
    _route,                    # 함수 — state 보고 다음 노드 결정
    {                          # 함수 반환값 → 다음 노드 매핑
        "shallow": "shallow",
        "deep": "deep",
        "end": END,
    },
)
```

`_route` 함수는 state를 받아 `"shallow" | "deep" | "end"`를 반환. **이게 우리 trigger 7-rule이 들어가는 곳**.

## 우리 graph의 전체 그림 (`vitalagent/graph.py`)

```
START
  │
  ▼
[shallow] ──► _route(state) ──► 결과에 따라:
                                  ├── "shallow" → 다시 [shallow]
                                  ├── "deep"    → [deep] ─► [shallow]
                                  └── "end"     → END
```

`max_ticks` (기본 20) 만큼 shallow tick을 돌면 `_route`가 `"end"`를 반환 → 종료.

## graph.invoke() — 실제 실행

```python
fm = create_fm({"fm": {"implementation": "mock_rule_based"}})
clock = SimClock(start_s=0.0)
signal = {"ABP": ..., "ECG_II": ..., "PPG": ..., "HR": ...}

graph = build_graph(
    fm=fm,
    clock=clock,
    signal=signal,
    modalities=["ABP", "ECG_II", "PPG", "HR"],
    max_ticks=5,
)

initial = AgentState(case_id="c-001", trace_id="t-001")
final = graph.invoke(initial, {"recursion_limit": 100})
```

`invoke`가 START에서 END까지 자동으로 흘려보낸다. `final`이 마지막 state.

## Conditional edge — trigger 7-rule이 들어가는 곳

```python
def _route(state: AgentState) -> str:
    tick_count = state.scratch.get("tick_count", 0)
    if tick_count >= max_ticks:
        return "end"
    fire, _reason = should_escalate(state)   # ← trigger 7 rule
    if fire:
        return "deep"
    return "shallow"
```

`should_escalate`는 [[20_아키텍처/Trigger_7_Rules]] 참조.

## State 변경 방법 — Pydantic `model_copy`

LangGraph는 node가 새 state를 *반환* 하도록 권장. in-place 변경도 작동하지만 functional update가 더 명료:

```python
new_state = state.model_copy(
    update={
        "sim_time_s": new_time,
        "mode": "shallow",
        "risk_history": [*state.risk_history, new_sample],
    }
)
return new_state
```

자세한 Pydantic 사용은 [[Pydantic_과_typed_state]].

## Recursion limit — 무한 루프 방지

LangGraph는 `recursion_limit` (기본 25)을 두어 node 호출 횟수를 제한. 무한 conditional loop를 자동 stop.

```python
graph.invoke(initial, {"recursion_limit": 100})
```

VitalAgent의 100-case e2e test에서는 100으로 설정 (5 tick × 최대 2 node + buffer).

## Trace — 자동 + 수동

LangGraph 자체적으로 LangSmith trace 지원 (LANGCHAIN_TRACING_V2=true). 우리는 **별도 JSONL trace**를 작성: [[30_코드_워크스루/06_nodes_graph]] + `vitalagent/trace.py`.

Trace event:
- `tick`: shallow tick 발생
- `tool_call`: tool 요청
- `tool_result`: tool 응답
- `narration`: shallow LLM narration
- `trigger`: deep escalation 발화
- `brief`: deep brief 생성

## 한계 / 주의 사항

- **상태 직렬화 비용**: 각 node 후 state를 dict로 직렬화하는 비용 발생. 우리 state는 작아서 무시 가능.
- **conditional edge의 가독성**: 조건이 복잡해지면 흐름이 안 보임. 우리는 `_route` 한 함수로 분기 집중.
- **multi-graph 합성**: 향후 sub-graph (예: per-modality 처리)를 만들 수 있지만 현재는 단일 graph.

## 다음 노트

- [[Pydantic_과_typed_state]] — state 정의 방법
- [[20_아키텍처/Trigger_7_Rules]] — conditional edge의 결정 규칙
- [[30_코드_워크스루/06_nodes_graph]] — 우리 graph 코드 한 줄씩
