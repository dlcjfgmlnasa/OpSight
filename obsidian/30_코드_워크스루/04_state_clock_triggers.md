# 04. State + SimClock + Triggers — Agent 의 기억과 시간과 분기

> 세 파일이 한 묶음으로 동작한다. **state** 는 agent 의 기억, **sim_clock** 은 시간 인식, **triggers** 는 Shallow ↔ Deep 분기 결정. 어느 하나 빠지면 graph 가 돌지 않는다.

## `vitalagent/state.py` — `AgentState`

LangGraph node 사이를 흘러가는 상태 객체. Pydantic BaseModel 이라서 typed 하다.

```python
class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 모르는 field 는 거부

    # 식별
    case_id: str
    trace_id: str

    # 시계
    sim_time_s: float = 0.0

    # 모드
    mode: Literal["shallow", "deep"] = "shallow"

    # 히스토리 buffer (시간 순서대로 누적)
    last_tool_results: list[ToolResponse] = Field(default_factory=list)
    risk_history: list[RiskSample] = Field(default_factory=list)
    quality_history: list[QualitySample] = Field(default_factory=list)
    brief_history: list[BriefRecord] = Field(default_factory=list)

    # Trigger 추적
    last_deep_trigger_time_s: float | None = None

    # 자유 형식 scratch
    scratch: dict[str, Any] = Field(default_factory=dict)
```

`extra="forbid"` 가 박혀 있어서 schema 에 없는 field 를 누가 set 하려고 하면 즉시 거부한다. typo 가 조용히 통과하는 사고를 막는다.

### 히스토리 buffer 안의 항목은 모두 frozen

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
    sections: dict[str, str]   # 9 섹션 dict
    latency_ms: float = 0.0
```

한번 기록된 sample 은 누구도 수정할 수 없다. trace 의 의미 보존을 위해 강제.

### `scratch` 는 *의도적으로* 자유 형식 dict

특정 schema 를 강제하지 않는다. node 가 메모처럼 쓴다.

- `tick_count` — shallow tick 의 누적 횟수
- `narration` — 가장 최근의 shallow narration 텍스트
- `clinician_on_demand` — `True` 면 trigger 가 즉시 발화

새 use case 가 생기면 schema 를 안 건드리고 scratch 에 key 만 추가하면 된다. typed state 의 장점과 유연성의 절충.

자세한 Pydantic 사용은 [[10_기초/Pydantic_과_typed_state]].

## `vitalagent/sim_clock.py` — `SimClock`

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
        """누수 가드 — query_end 가 now 보다 크면 ValueError 를 raise."""
```

세 가지가 한 객체에 묶여 있다.

- 현재 sim_time (`now_s`)
- tick 으로 시간 전진 + 매 tick 의 wall-clock 실측
- 누수 검사 (`assert_le`)

자세한 누수 정책은 [[20_아키텍처/데이터_누수_방지]].

### `TickMeasurement` — sim 진행과 wall 실측을 함께 기록

```python
@dataclass
class TickMeasurement:
    sim_time_before_s: float
    sim_time_after_s: float
    wall_start: float
    wall_end: float
```

매 tick 마다 sim 안에서 얼마가 흘렀고, wall-clock 으로 실제 얼마가 걸렸는지를 함께 남긴다. Shallow 의 15초 budget 검증에 쓴다.

## `vitalagent/triggers.py` — `should_escalate(state)`

7개 trigger + 60초 cooldown. 결과는 `(fire: bool, reason: str | None)` 튜플. 자세한 7-rule 의 의미는 [[20_아키텍처/Trigger_7_Rules]].

```python
def should_escalate(state: AgentState) -> tuple[bool, str | None]:
    # 1. Clinician on-demand — 항상 우선
    reason = _check_clinician_on_demand(state)
    if reason is not None:
        return True, reason

    # 2. Acute event — cooldown 우회
    reason = _check_arrest(state)
    if reason is not None:
        return True, reason

    # 3. Cooldown gate — 여기부터 cooldown 적용
    if _within_cooldown(state):
        return False, None

    # 4. 나머지 trigger 들
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

순서가 중요하다. **명시적 요청 (1) → 환자 안전 (2) → cooldown gate (3) → 나머지 (4)**. 1과 2는 cooldown 을 우회한다.

### 한 trigger 함수의 예 — `_check_hypotension`

```python
def _check_hypotension(state):
    for sample in reversed(state.risk_history):
        if sample.risk_type.startswith("hypotension"):
            if sample.risk > HYPOTENSION_RISK_THRESHOLD:
                return f"hypotension_risk_gt_{HYPOTENSION_RISK_THRESHOLD} (risk={sample.risk:.2f})"
            return None
    return None
```

가장 최근의 hypotension sample 을 찾아서 threshold 와 비교한다. reason 문자열에 실제 risk 값이 들어가서 trace 에서 디버깅할 때 도움이 된다 ("이 trigger 가 왜 발화했는지" 한눈에).

### 모든 threshold

Project brief §6.3 의 정의와 정확히 일치한다.

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

## 셋이 한 cycle 에서 어떻게 협력하는가

```
Shallow node 호출:
  1. clock.tick(30.0)                      ← sim_time 이 30초 전진
  2. state.sim_time_s = clock.now_s        ← state 동기화
  3. 5개 quick tool 호출 → 결과 받음
  4. state.risk_history 에 sample 추가
  5. 새 state 를 반환

[conditional edge] _route(state):
  6. fire, reason = should_escalate(state)
  7. fire == True 면 deep node 로 라우팅
     아니면 shallow 로 돌아감

Deep node 호출 (fire 일 때):
  8. 21개 tool 호출 + 9-section brief 생성
  9. state.brief_history 에 BriefRecord 추가
  10. state.last_deep_trigger_time_s 갱신 (cooldown 의 기준)
  11. 새 state 반환

→ 다음 iteration 으로
```

LangGraph 가 위 cycle 을 자동으로 진행한다. 자세한 graph 구성은 [[06_nodes_graph]].

## Test

`tests/test_triggers.py` 에 19개 test.

| 그룹 | 개수 |
|------|------|
| trigger 별 positive + negative | 14 (7개 trigger × 2) |
| Cooldown semantics | 3 (block / bypass / expire) |
| On-demand bypass | 1 |
| 데이터 없을 때 baseline | 1 |

19 PASSED. 한 trigger 라도 깨지면 graph 가 잘못 분기할 수 있으니 모두 강제 유지.

## 다음 노트

- [[05_tools_layer]] — tool 호출과 `ToolResponse` 가 어떻게 `state.last_tool_results` 에 들어가는가
- [[06_nodes_graph]] — node 가 state 를 어떻게 갱신하는가
- [[20_아키텍처/Trigger_7_Rules]] — 7-rule 의 의미와 임계치의 근거
- [[20_아키텍처/데이터_누수_방지]] — sim_clock 의 누수 가드 정책
