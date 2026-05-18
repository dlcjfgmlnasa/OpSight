# 06. Nodes + Graph — node 두 개와 StateGraph wiring 이 agent 의 실행 흐름이다

> LangGraph 에서 "node" 는 state 를 받아 새 state 를 반환하는 함수다. Agent 는 두 개의 node (`shallow`, `deep`) 를 갖고, conditional edge 로 둘 사이를 오간다.

## 파일 구조

```
vitalagent/
├── nodes/
│   ├── __init__.py
│   ├── shallow_loop.py     ← 30초 tick (5 quick tool + light narration)
│   └── deep_brief.py       ← full sweep (21 tool + 9-section brief)
└── graph.py                ← build_graph() — StateGraph wiring
```

두 node 의 구조는 비슷하다. Tool 을 부르고, 결과를 state 의 history 에 누적하고, LLM 으로 자연어를 만들고, 새 state 를 반환. 다만 부르는 tool 의 개수와 LLM 의 무게가 다르다.

## `shallow_loop.py` — `run_shallow_loop(state, ...)`

함수 시그니처부터 보면.

```python
def run_shallow_loop(
    state: AgentState,
    *, fm: BiosignalFMInterface, clock: SimClock,
    signal: dict[str, torch.Tensor], modalities: list[str],
    trace: TraceWriter | None = None,
) -> AgentState:
```

state 를 받아 새 state 를 반환. FM 과 signal 은 *주입* 받는다 (호출자 책임). `trace` 는 디버깅용 JSONL writer, 선택사항.

### 단계별 풀어 쓰기

```
1. SHALLOW_TOOL_NAMES (5개) 순회
   ├── ToolRequest 생성
   ├── trace.event("tool_call", ...)
   ├── call_tool(name, req, fm, clock, signal) → ToolResponse
   └── trace.event("tool_result", ...)

2. tool_results 에서 risk / quality sample 추출 → state.risk_history / quality_history 에 append

3. Light LLM (지금은 placeholder template) 호출 → 한 문장 narration

4. trace.event("narration", {"text": ...})

5. 새 state 반환 (model_copy with update)
```

### Tool 호출 부분

```python
tool_results: list[ToolResponse] = []
for tool_name in SHALLOW_TOOL_NAMES:
    args = _shallow_tool_args(tool_name, modalities)
    req = ToolRequest(
        case_id=state.case_id,
        sim_time_s=state.sim_time_s,
        tool_name=tool_name,
        args=args,
    )
    if trace is not None:
        trace.event("tool_call", {"tool": tool_name, "args": args}, sim_time_s=state.sim_time_s)
    resp = call_tool(tool_name, req, fm=fm, clock=clock, signal=signal)
    tool_results.append(resp)
    if trace is not None:
        trace.event(
            "tool_result",
            {"tool": tool_name, "ok": resp.ok, "latency_ms": resp.latency_ms, ...},
            sim_time_s=state.sim_time_s,
        )
```

trace event 가 호출 전후로 두 번 찍힌다. "어떤 tool 을 어떤 args 로 불렀고, 결과가 어땠는지" 가 JSONL 에 모두 남는다.

### Risk / quality sample 누적

Tool 결과는 *그대로* state 에 들어가지 않고, 의미 있는 sample 로 정제된 후 들어간다.

```python
new_risk = list(state.risk_history)
new_quality = list(state.quality_history)
for r in tool_results:
    if not r.ok or r.result is None:
        continue
    if r.tool_name == "predict_hypotension":
        new_risk.append(RiskSample(
            sim_time_s=state.sim_time_s,
            risk_type=f"hypotension_h{r.result.get('horizon_min', 5)}",
            risk=float(r.result.get("risk", 0.0)),
            uncertainty=float(r.result.get("uncertainty", 0.0)),
        ))
    elif r.tool_name == "predict_cardiac_arrest":
        new_risk.append(RiskSample(...))
    elif r.tool_name == "assess_signal_quality":
        new_quality.append(QualitySample(...))
```

이 누적된 history 를 다음 turn 에 trigger engine 이 검사한다. 자세한 건 [[04_state_clock_triggers]].

### Narration

```python
narration = render_shallow_narration(tool_results)
if trace is not None:
    trace.event("narration", {"text": narration}, sim_time_s=state.sim_time_s)
```

지금은 template 이지만, 진짜 LLM 합류 후엔 같은 위치에서 LLM 호출. 자세한 건 [[07_llm_placeholder_와_plan_1_6]].

### State 갱신은 functional update

```python
new_state = state.model_copy(
    update={
        "mode": "shallow",
        "last_tool_results": tool_results,
        "risk_history": new_risk,
        "quality_history": new_quality,
    }
)
new_state.scratch["narration"] = narration
return new_state
```

`model_copy(update={...})` 는 *새 instance* 를 반환한다. 원본 state 는 그대로. LangGraph 의 expectation 에 맞춘 functional update. 자세한 건 [[10_기초/Pydantic_과_typed_state]].

## `deep_brief.py` — `run_deep_brief(state, ...)`

Shallow 와 같은 패턴이지만 몇 가지 차이가 있다.

- **21개 tool 전체** 를 호출한다 (FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2 + Signal Access 5)
- **Heavy LLM** (지금은 placeholder) → 9 섹션짜리 brief 생성
- `BriefRecord` 를 만들어 `state.brief_history` 에 append
- `state.last_deep_trigger_time_s = state.sim_time_s` 로 cooldown 의 기준 시각 갱신
- `state.scratch["clinician_on_demand"] = False` 로 on-demand flag 자동 해제

### 모든 카테고리를 순회하며 호출

```python
for tool_name, spec in TOOLS.items():
    try:
        args = _deep_args(tool_name, state, modalities)
    except ValueError:
        # 미구현 tool 의 args 가 부족할 때 skip
        continue
    req = ToolRequest(...)
    resp = call_tool(tool_name, req, fm=fm, clock=clock, signal=signal)
    tool_results.append(resp)
```

미구현 tool 의 args 가 부족하면 `_deep_args` 가 `ValueError` 를 던지고, 그 tool 은 그냥 skip 된다. graph 가 멈추지 않는다.

### Surgery context 를 brief 용으로 추출

```python
surgery_phase = "maintenance"
elapsed_min = state.sim_time_s / 60.0
for r in tool_results:
    if r.tool_name == "query_surgery_progress" and r.ok and r.result is not None:
        surgery_phase = str(r.result.get("phase", surgery_phase))
        elapsed_min = float(r.result.get("elapsed_min", elapsed_min))
        break
```

`query_surgery_progress` 의 결과를 꺼내서 brief 의 `[Surgery context]` 섹션에 쓸 phase 와 elapsed_min 을 구한다.

### Brief 생성

```python
sections = render_deep_brief(
    tool_results,
    surgery_type="general",
    surgery_phase=surgery_phase,
    elapsed_min=elapsed_min,
)
latency_ms = (time.perf_counter() - t0) * 1000.0
record = BriefRecord(
    sim_time_s=state.sim_time_s,
    trigger_reason=trigger_reason,
    sections=sections,
    latency_ms=latency_ms,
)

if trace is not None:
    trace.event("brief", {"trigger_reason": trigger_reason, "latency_ms": latency_ms, "sections": sections},
                sim_time_s=state.sim_time_s)
```

`BriefRecord` 가 frozen 이라 한번 만들어지면 변경 불가. trace 에도 어떤 trigger 가 이 brief 를 부른건지 함께 기록된다. 자세한 brief 구조는 [[20_아키텍처/9_Section_Brief]].

## `graph.py` — LangGraph StateGraph wiring

```python
def build_graph(
    *, fm: BiosignalFMInterface, clock: SimClock,
    signal: dict[str, torch.Tensor], modalities: list[str],
    max_ticks: int = 20, tick_sim_advance_s: float = 30.0,
    trace: TraceWriter | None = None,
):
    def _shallow_node(state: AgentState) -> AgentState:
        # 1. clock tick — sim_time 이 30초 전진
        clock.tick(tick_sim_advance_s)
        state = state.model_copy(update={
            "sim_time_s": clock.now_s,
            "scratch": {**state.scratch, "tick_count": state.scratch.get("tick_count", 0) + 1},
        })
        # 2. trace tick event
        if trace is not None:
            trace.event("tick", {"tick_count": state.scratch["tick_count"]}, sim_time_s=state.sim_time_s)
        # 3. shallow loop 실행
        return run_shallow_loop(state, fm=fm, clock=clock, signal=signal, modalities=modalities, trace=trace)

    def _deep_node(state: AgentState) -> AgentState:
        _fire, reason = should_escalate(state)
        assert reason is not None      # route 에서 fire 일 때만 호출됨
        if trace is not None:
            trace.event("trigger", {"reason": reason}, sim_time_s=state.sim_time_s)
        return run_deep_brief(state, fm=fm, clock=clock, signal=signal, modalities=modalities,
                              trigger_reason=reason, trace=trace)

    def _route(state: AgentState) -> str:
        tick_count = state.scratch.get("tick_count", 0)
        if tick_count >= max_ticks:
            return "end"
        fire, _reason = should_escalate(state)
        if fire:
            return "deep"
        return "shallow"

    graph = StateGraph(AgentState)
    graph.add_node("shallow", _shallow_node)
    graph.add_node("deep", _deep_node)
    graph.add_edge(START, "shallow")
    graph.add_conditional_edges("shallow", _route,
        {"shallow": "shallow", "deep": "deep", "end": END})
    graph.add_edge("deep", "shallow")   # deep 후엔 shallow 로 복귀
    return graph.compile()
```

자세한 LangGraph 개념은 [[10_기초/LangGraph_와_StateGraph]].

### 그림으로 보면

```
START
  │
  ▼
[shallow] ─► _route(state) ──► "shallow" / "deep" / "end"
   ▲                              │              │       │
   │                              ▼              ▼       ▼
   │                          [shallow]      [deep]    END
   │                                            │
   └────────────────────────────────────────────┘
```

`shallow` → `_route` → 셋 중 하나 (`shallow` / `deep` / `end`). Deep 이 끝나면 다시 shallow 로 돌아온다. `max_ticks` 에 도달하면 `_route` 가 `"end"` 를 반환해서 graph 가 종료된다.

## 자동 검증 — node 와 graph 어디서도 concrete FM 을 import 하지 못함

```python
# tests/integration/test_smoke_single_case.py

def test_no_concrete_fm_import_in_node_or_graph_module():
    forbidden = ("StubBiosignalFM", "RuleBasedBiosignalFM",
                 "LightMLBiosignalFM", "RealBiosignalFM")
    targets = [
        Path("vitalagent/nodes/__init__.py"),
        Path("vitalagent/nodes/shallow_loop.py"),
        Path("vitalagent/nodes/deep_brief.py"),
        Path("vitalagent/graph.py"),
    ]
    for rel in targets:
        text = (root / rel).read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in text
```

ADR-011 의 swap mechanism 을 자동으로 지킨다. node 나 graph 코드에서 누가 실수로 `from vitalagent.fm.mock_stub import StubBiosignalFM` 같은 라인을 추가하면 이 test 가 즉시 실패한다.

## 다음 노트

- [[07_llm_placeholder_와_plan_1_6]] — node 가 호출하는 LLM (지금은 placeholder, 곧 vLLM 으로 교체)
- [[04_state_clock_triggers]] — state / clock / trigger 가 node 안에서 어떻게 동작하는가
- [[10_기초/LangGraph_와_StateGraph]] — LangGraph 의 StateGraph 개념
