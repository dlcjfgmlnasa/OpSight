# LangGraph 와 StateGraph

> LLM agent workflow engine. "node 와 edge 로 그린 흐름도" 를 코드로 표현.

## 한 줄

LangChain 팀의 **state-based graph workflow** library. node 는 함수, edge 는 분기 결정. node 사이를 흘러가는 게 우리 `AgentState`.

```
START ──► [shallow] ──► [trigger?] ──► [deep] ──► [shallow] ──► ... ──► END
```

## 왜 LangGraph 인가

| 옵션 | 평가 |
|------|------|
| LangChain Agent Executor | 추상화 과해 tool 호출 흐름이 black-box |
| AutoGen (Microsoft) | 멀티 agent 협업 중심, 단일 case 흐름엔 무거움 |
| 직접 구현 (while loop) | 가능. 하지만 trace / persistence / 재시작 직접 처리 필요 |
| **LangGraph** | state schema + conditional edge + 자동 trace 가 dual-mode 와 잘 맞음 |

## 핵심 개념 3가지

### 1. State

node 사이를 흘러가는 dict 또는 Pydantic model. 우리는 `AgentState` Pydantic.

```python
class AgentState(BaseModel):
    case_id: str
    sim_time_s: float = 0.0
    mode: Literal["shallow", "deep"] = "shallow"
    risk_history: list[RiskSample] = []
    quality_history: list[QualitySample] = []
    brief_history: list[BriefRecord] = []
    # ... etc
```

[[Pydantic_과_typed_state]] + [[30_코드_워크스루/04_state_clock_triggers]].

### 2. Node

`AgentState → AgentState` 함수.

```python
def _shallow_node(state: AgentState) -> AgentState:
    # tool 호출, state 갱신
    return new_state
```

OpSight 의 node:
- `shallow` — 30s tick 마다 quick tool 5개 + narration
- `deep` — full sweep 21 tool + 9-section brief

### 3. Edge

두 종류:

```python
# 무조건
graph.add_edge("deep", "shallow")

# 조건부
graph.add_conditional_edges(
    "shallow",
    _route,                    # state 보고 다음 노드 결정
    {                          # 반환값 → 다음 노드 매핑
        "shallow": "shallow",
        "deep": "deep",
        "end": END,
    },
)
```

`_route` 가 `"shallow" | "deep" | "end"` 반환. **여기에 trigger 7-rule 이 들어간다.**

## 우리 graph

```
START
  │
  ▼
[shallow] ──► _route(state) ──► 결과:
                                  ├── "shallow" → 다시 [shallow]
                                  ├── "deep"    → [deep] ─► [shallow]
                                  └── "end"     → END
```

`max_ticks` (기본 20) 도달 시 `_route` 가 `"end"` 반환.

## graph.invoke() — 실제 실행

```python
fm = create_fm({"fm": {"implementation": "mock_rule_based"}})
clock = SimClock(start_s=0.0)
signal = {"ABP": ..., "ECG_II": ..., "PPG": ..., "HR": ...}

graph = build_graph(
    fm=fm, clock=clock, signal=signal,
    modalities=["ABP", "ECG_II", "PPG", "HR"],
    max_ticks=5,
)

initial = AgentState(case_id="c-001", trace_id="t-001")
final = graph.invoke(initial, {"recursion_limit": 100})
```

## Conditional edge — trigger 가 들어가는 곳

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

[[20_아키텍처/Trigger_7_Rules]] 참조.

## State 변경 — `model_copy(update={...})`

LangGraph 는 새 state 반환을 권장 (functional update).

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

[[Pydantic_과_typed_state]] 참조.

## Recursion limit

기본 25. 무한 conditional loop 방지.

```python
graph.invoke(initial, {"recursion_limit": 100})
```

OpSight 100-case e2e 는 100 으로 설정.

## Trace

LangGraph 자체에 LangSmith trace 지원 (`LANGCHAIN_TRACING_V2=true`). 우리는 별도 JSONL trace 도 작성 ([[30_코드_워크스루/06_nodes_graph]] + `opsight/trace.py`).

Event:
- `tick` / `tool_call` / `tool_result` / `narration` / `trigger` / `brief`

## 한계 / 주의

- **State 직렬화 비용** — 각 node 후 dict 로 직렬화. 우리 state 는 작아 무시 가능.
- **Conditional edge 가독성** — 조건이 복잡하면 흐름이 안 보임. 우리는 `_route` 한 함수에 집중.
- **Multi-graph 합성** — 향후 sub-graph 가능, 현재는 단일 graph.

## 다음 노트

- [[Pydantic_과_typed_state]] — state 정의
- [[20_아키텍처/Trigger_7_Rules]] — conditional edge 결정 규칙
- [[30_코드_워크스루/06_nodes_graph]] — 우리 graph 코드
