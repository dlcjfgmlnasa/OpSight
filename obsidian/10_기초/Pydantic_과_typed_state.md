# Pydantic 과 typed state

> Python class에 *타입 검증*을 강제하는 library. 우리 state / tool envelope의 기반.

## Python의 기본 class — type이 강제되지 않는다

```python
class AgentState:
    def __init__(self, case_id, sim_time_s, mode):
        self.case_id = case_id
        self.sim_time_s = sim_time_s
        self.mode = mode

s = AgentState(case_id=42, sim_time_s="이상한 문자열", mode="hello")
# ← 위 모두 통과. case_id는 int여도, sim_time_s가 str이어도 검사 없음.
```

대규모 프로젝트에서 이런 코드는 위험. **typo 한 글자로 case_id에 dict가 들어가도 코드가 멋대로 굴러간다.**

## `dataclass` — type 선언은 가능, 검증은 X

```python
from dataclasses import dataclass

@dataclass
class AgentState:
    case_id: str
    sim_time_s: float
    mode: str

s = AgentState(case_id=42, sim_time_s="문자열", mode="hello")
# ← 여전히 통과. annotation은 type checker (mypy/pyright)에서만 검증.
```

`@dataclass`는 `__init__` 자동 생성 + 코드 가독성 + (frozen 옵션) 불변성에 유용. 하지만 runtime에 type을 검증하지 않는다.

우리 `result_types.py`는 frozen dataclass 사용 (Result는 immutable + 작아서 충분).

## `pydantic.BaseModel` — runtime type 검증

```python
from pydantic import BaseModel

class AgentState(BaseModel):
    case_id: str
    sim_time_s: float
    mode: Literal["shallow", "deep"]

s = AgentState(case_id=42, sim_time_s="문자열", mode="hello")
# ← ValidationError 발생!
#   - case_id: Input should be a valid string
#   - sim_time_s: Input should be a valid number
#   - mode: Input should be 'shallow' or 'deep'
```

Pydantic은 **runtime 시점에 type을 검증**한다. 잘못된 값은 즉시 거부. 추가 기능:

- 자동 JSON serialization: `state.model_dump_json()`
- 자동 deserialization: `AgentState.model_validate({"case_id": "c1", ...})`
- Field 기본값 / validator
- `frozen=True` 옵션도 가능

## VitalAgent에서 어디에 쓰나

| 모듈 | Pydantic | 이유 |
|------|----------|------|
| `vitalagent/state.py` `AgentState` | ✅ | LangGraph가 dict로 직렬화/역직렬화. validation 필수. |
| `vitalagent/tools/envelope.py` `ToolRequest/Response/Error` | ✅ | tool 간 데이터 교환 — 잘못된 schema는 즉시 거부 |
| `vitalagent/fm/result_types.py` `HypotensionResult` 등 | ❌ (frozen dataclass) | FM이 직접 반환. shape 단순 + immutable + asdict로 serialize 충분 |

선택 기준:
- **변경 가능한 흐름 state** → Pydantic (validation + serialization 필요)
- **불변 결과 값** → frozen dataclass (가벼움 + serialization 자체로 충분)

## 우리 `AgentState` 전체 (요약)

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

Mode = Literal["shallow", "deep"]

class RiskSample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sim_time_s: float
    risk_type: str
    risk: float
    uncertainty: float

class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")   # 모르는 field 거부

    case_id: str
    trace_id: str
    sim_time_s: float = 0.0
    mode: Mode = "shallow"
    last_tool_results: list[ToolResponse] = Field(default_factory=list)
    risk_history: list[RiskSample] = Field(default_factory=list)
    # ... etc
```

`ConfigDict(extra="forbid")`: 정의되지 않은 field가 dict로 들어오면 에러 — typo / schema drift 방지.

`Field(default_factory=list)`: mutable 기본값은 매번 새 list로 생성. 모든 instance가 같은 list를 공유하지 않도록.

## `Literal["a", "b"]` — 좁은 enum 같은 type

```python
mode: Literal["shallow", "deep"]
```

`mode = "hello"` → ValidationError. 두 값 중 하나만 허용. Pydantic + mypy 모두 강제.

## `model_copy(update={...})` — functional update

LangGraph node는 새 state를 반환하는 패턴.

```python
new_state = state.model_copy(
    update={
        "sim_time_s": clock.now_s,
        "mode": "deep",
        "brief_history": [*state.brief_history, new_record],
    }
)
```

원본은 그대로, 새 instance가 생성됨. 한 list field에 항목 추가 시 `[*old, new]` 패턴.

## 직렬화 — JSON / dict

```python
# Pydantic → JSON 문자열
json_str = state.model_dump_json()      # 다른 system / 파일에 보낼 때

# Pydantic → dict
d = state.model_dump()                  # 다른 dict로 합칠 때

# dict → Pydantic
state = AgentState.model_validate(d)    # JSON에서 다시 복원
```

우리 trace JSONL은 `model_dump()` 결과를 한 줄씩 쓰는 게 아니라, **per-event payload**만 쓴다 (state 전체는 크기 때문에 매 event마다 저장하지 않음).

## 한 줄 비교

| 목적 | Pydantic | frozen dataclass | dict |
|------|----------|------------------|------|
| Runtime type 검증 | ✅ | ❌ | ❌ |
| JSON 직렬화 / 역직렬화 | ✅ 내장 | dataclasses.asdict / json 수동 | 자연스러움 |
| Immutability | `frozen=True` 옵션 | ✅ | ❌ |
| 가벼움 | 약간 무거움 | ✅ 매우 가벼움 | ✅ |
| 우리 사용 | state, envelope | Result | 단순 짧은 payload |

## 다음 노트

- [[Python_Protocol_과_runtime_checkable]] — Pydantic은 *type 검증*, Protocol은 *interface 검증*
- [[30_코드_워크스루/04_state_clock_triggers]] — 우리 state.py 전체 워크스루
