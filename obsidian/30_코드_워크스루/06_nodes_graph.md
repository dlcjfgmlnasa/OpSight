# 06. Nodes + Graph — `shallow_loop.py` + `deep_brief.py` + `graph.py`

> LangGraph node 2개 + StateGraph wiring.

## 파일 구조

```
opsight/
├── nodes/
│   ├── __init__.py
│   ├── shallow_loop.py     ← 30s tick (5 quick tool + light narration)
│   └── deep_brief.py       ← full sweep (21 tool + 9-section brief)
└── graph.py                ← build_graph() — StateGraph wiring
```

## `shallow_loop.py` — `run_shallow_loop(state, ...)`

```python
def run_shallow_loop(
    state: AgentState,
    *, fm: BiosignalFMInterface, clock: SimClock,
    signal: dict[str, torch.Tensor], modalities: list[str],
    trace: TraceWriter | None = None,
) -> AgentState:
```

### 단계

```
1. SHALLOW_TOOL_NAMES (5개) 순회
   ├── ToolRequest 생성
   ├── trace.event("tool_call", ...)
   ├── call_tool(name, req, fm, clock, signal) → ToolResponse
   └── trace.event("tool_result", ...)

2. tool_results 에서 risk / quality sample 추출 → state.risk_history / quality_history 에 append

3. Light LLM (placeholder template) 호출 → 1문장 narration

4. trace.event("narration", {"text": ...})

5. new state 반환 (model_copy with update)
```

### Tool 호출

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

### Risk / quality sample 누적

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

다음 turn 에 trigger engine ([[04_state_clock_triggers]]) 이 history 검사.

### Narration

```python
narration = render_shallow_narration(tool_results)
if trace is not None:
    trace.event("narration", {"text": narration}, sim_time_s=state.sim_time_s)
```

Placeholder LLM: [[07_llm_placeholder_와_plan_1_6]].

### State 갱신 (functional update)

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

`model_copy(update={...})` 가 새 instance 반환. [[10_기초/Pydantic_과_typed_state]].

## `deep_brief.py` — `run_deep_brief(state, ...)`

Shallow 와 비슷한 패턴, 차이:
- **21 tool 호출** (FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2 + Signal Access 5)
- **Heavy LLM** (placeholder) → 9-section brief
- `BriefRecord` → `state.brief_history` 에 append
- `state.last_deep_trigger_time_s = state.sim_time_s` (cooldown 기준 갱신)
- `state.scratch["clinician_on_demand"] = False` (flag 해제)

### Tool sweep — 모든 카테고리

```python
for tool_name, spec in TOOLS.items():
    try:
        args = _deep_args(tool_name, state, modalities)
    except ValueError:
        # 미구현 tool args 부족 — skip
        continue
    req = ToolRequest(...)
    resp = call_tool(tool_name, req, fm=fm, clock=clock, signal=signal)
    tool_results.append(resp)
```

### Surgery context 추출

```python
surgery_phase = "maintenance"
elapsed_min = state.sim_time_s / 60.0
for r in tool_results:
    if r.tool_name == "query_surgery_progress" and r.ok and r.result is not None:
        surgery_phase = str(r.result.get("phase", surgery_phase))
        elapsed_min = float(r.result.get("elapsed_min", elapsed_min))
        break
```

Brief 의 `[Surgery context]` 에 사용.

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

Brief 구조: [[20_아키텍처/9_Section_Brief]].

## `graph.py` — `build_graph(...)`

```python
def build_graph(
    *, fm: BiosignalFMInterface, clock: SimClock,
    signal: dict[str, torch.Tensor], modalities: list[str],
    max_ticks: int = 20, tick_sim_advance_s: float = 30.0,
    trace: TraceWriter | None = None,
):
    def _shallow_node(state: AgentState) -> AgentState:
        clock.tick(tick_sim_advance_s)
        state = state.model_copy(update={
            "sim_time_s": clock.now_s,
            "scratch": {**state.scratch, "tick_count": state.scratch.get("tick_count", 0) + 1},
        })
        if trace is not None:
            trace.event("tick", {"tick_count": state.scratch["tick_count"]}, sim_time_s=state.sim_time_s)
        return run_shallow_loop(state, fm=fm, clock=clock, signal=signal, modalities=modalities, trace=trace)

    def _deep_node(state: AgentState) -> AgentState:
        _fire, reason = should_escalate(state)
        assert reason is not None      # route 에서 fire 일 때만 호출
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
    graph.add_edge("deep", "shallow")   # deep 후 shallow 로 복귀
    return graph.compile()
```

LangGraph 개념: [[10_기초/LangGraph_와_StateGraph]].

### 흐름도

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

`max_ticks` 도달 시 `_route` 가 `"end"` 반환 → graph 종료.

## 정적 검증 — concrete FM import 금지

```python
# tests/integration/test_smoke_single_case.py

def test_no_concrete_fm_import_in_node_or_graph_module():
    forbidden = ("StubBiosignalFM", "RuleBasedBiosignalFM",
                 "LightMLBiosignalFM", "RealBiosignalFM")
    targets = [
        Path("opsight/nodes/__init__.py"),
        Path("opsight/nodes/shallow_loop.py"),
        Path("opsight/nodes/deep_brief.py"),
        Path("opsight/graph.py"),
    ]
    for rel in targets:
        text = (root / rel).read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in text
```

ADR-011 swap mechanism 을 자동 검증 — node / graph 에서 concrete FM class import 금지.

## 다음 노트

- [[07_llm_placeholder_와_plan_1_6]] — node 가 호출하는 LLM
- [[04_state_clock_triggers]] — state / clock / trigger
- [[10_기초/LangGraph_와_StateGraph]] — LangGraph 개념
