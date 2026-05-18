# 04. State + SimClock + Triggers

> Agent 의 *기억* (state), *시간 인식* (sim_clock), *분기 결정* (triggers). 세 파일이 한 묶음.

## `opsight/state.py` — `AgentState`

LangGraph node 사이를 흘러가는 상태. Pydantic BaseModel.

```python
class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown field 거부

    # 식별
    case_id: str
    trace_id: str

    # 시계
    sim_time_s: float = 0.0

    # 모드
    mode: Literal["shallow", "deep"] = "shallow"

    # 히스토리 buffer
    last_tool_results: list[ToolResponse] = Field(default_factory=list)
    risk_history: list[RiskSample] = Field(default_factory=list)
    quality_history: list[QualitySample] = Field(default_factory=list)
    brief_history: list[BriefRecord] = Field(default_factory=list)

    # Trigger 추적
    last_deep_trigger_time_s: float | None = None

    # 자유 형식 scratch
    scratch: dict[str, Any] = Field(default_factory=dict)
```

### Sub-type 들 (frozen)

```python
class RiskSample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sim_time_s: float
    risk_type: str       # "hypotension_h5", "arrest_h5"
    risk: float
    uncertainty: float

class QualitySample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sim_time_s: float
    modality: str
    score: float

class BriefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sim_time_s: float
    trigger_reason: str
    sections: dict[str, str]   # 9-section dict
    latency_ms: float = 0.0
```

History buffer 항목은 모두 frozen — 기록 후 변경 불가.

### `scratch` — 자유 형식 dict

특정 schema 강제 X. node 가 메모처럼 사용:
- `tick_count`: shallow tick 누적
- `narration`: 최근 shallow narration
- `clinician_on_demand`: True 면 trigger 6 발화

새 use case 시 schema 안 건드리고 key 추가 가능. [[10_기초/Pydantic_과_typed_state]] 참조.

## `opsight/sim_clock.py` — `SimClock`

```python
class SimClock:
    def __init__(self, start_s: float = 0.0):
        self._now_s = float(start_s)
        self._tick_history: list[TickMeasurement] = []

    @property
    def now_s(self) -> float:
        return self._now_s

    def tick(self, sim_advance_s: float = 30.0) -> TickMeasurement:
        wall_start = time.perf_counter()
        before = self._now_s
        self._now_s = before + float(sim_advance_s)
        wall_end = time.perf_counter()
        m = TickMeasurement(...)
        self._tick_history.append(m)
        return m

    def assert_le(self, query_window_end_s: float) -> None:
        """누수 가드 — query_end > now 면 raise."""
```

자세한 누수 정책: [[20_아키텍처/데이터_누수_방지]].

### `TickMeasurement`

```python
@dataclass
class TickMeasurement:
    sim_time_before_s: float
    sim_time_after_s: float
    wall_start: float
    wall_end: float
```

매 tick 의 sim 진행 + wall 실측 동시 기록. Shallow latency budget 검증용.

## `opsight/triggers.py` — `should_escalate(state)`

7 trigger + 60초 cooldown. `(fire: bool, reason: str | None)` 반환.

```python
def should_escalate(state: AgentState) -> tuple[bool, str | None]:
    # 1. Clinician on-demand — 항상 적용
    reason = _check_clinician_on_demand(state)
    if reason is not None:
        return True, reason

    # 2. Acute event — cooldown 우회
    reason = _check_arrest(state)
    if reason is not None:
        return True, reason

    # 3. Cooldown gate
    if _within_cooldown(state):
        return False, None

    # 4. Remaining triggers
    for check in (
        _check_hypotension,
        _check_rapid_increase,
        _check_quality_drop,
        _check_cross_modal_inconsistency,
        _check_periodic,
    ):
        reason = check(state)
        if reason is not None:
            return True, reason
    return False, None
```

순서: clinician on-demand → acute → cooldown gate → 나머지. 7 rule 의미는 [[20_아키텍처/Trigger_7_Rules]].

### `_check_hypotension` 예시

```python
def _check_hypotension(state):
    for sample in reversed(state.risk_history):
        if sample.risk_type.startswith("hypotension"):
            if sample.risk > HYPOTENSION_RISK_THRESHOLD:
                return f"hypotension_risk_gt_{HYPOTENSION_RISK_THRESHOLD} (risk={sample.risk:.2f})"
            return None
    return None
```

최근 hypotension sample 을 찾아 threshold 비교. reason 문자열에 risk 값 포함 (trace 디버깅용).

### Thresholds (`brief §6.3` 정확 일치)

```python
HYPOTENSION_RISK_THRESHOLD: float = 0.7
RISK_DELTA_WINDOW_S: float = 30.0
RISK_DELTA_THRESHOLD: float = 0.3
QUALITY_DROP_THRESHOLD: float = 0.3
CONSISTENCY_THRESHOLD: float = 0.4
CONSISTENCY_GOOD_QUALITY_GATE: float = 0.7
ARREST_RISK_THRESHOLD: float = 0.5
PERIODIC_CHECK_INTERVAL_S: float = 300.0     # 5분
DEEP_COOLDOWN_S: float = 60.0
```

## 셋이 협력하는 cycle

```
Shallow node:
  1. clock.tick(30.0)                      ← sim_time + 30
  2. state.sim_time_s = clock.now_s
  3. tool 호출 → result
  4. state.risk_history.append(RiskSample(...))
  5. 새 state 반환

[conditional edge] _route(state):
  6. fire, reason = should_escalate(state)
  7. if fire: route to deep node
     else:    route back to shallow

Deep node (if fire):
  8. 21 tool 호출 + brief 생성
  9. state.brief_history.append(BriefRecord(...))
  10. state.last_deep_trigger_time_s = state.sim_time_s
  11. 새 state 반환

→ next iteration
```

[[06_nodes_graph]] 에 graph wiring.

## Tests

`tests/test_triggers.py`: **19 test**.

| 그룹 | 개수 |
|------|------|
| Per-trigger positive + negative | 14 (7 × 2) |
| Cooldown semantics | 3 (block / bypass / expire) |
| On-demand bypass | 1 |
| No-data baseline | 1 |

## 다음 노트

- [[05_tools_layer]] — `ToolResponse` 가 어떻게 `state.last_tool_results` 에 들어가는가
- [[06_nodes_graph]] — node 가 state 를 어떻게 갱신하는가
- [[20_아키텍처/Trigger_7_Rules]] — 7 rule 의미 + threshold rationale
