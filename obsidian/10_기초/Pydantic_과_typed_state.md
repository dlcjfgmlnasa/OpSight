# Pydantic 과 typed state

> Python class 에 *runtime type 검증* 을 강제하는 library. 우리 state / tool envelope 의 기반.

## Python 기본 class — type 강제 없음

```python
class AgentState:
    def __init__(self, case_id, sim_time_s, mode):
        self.case_id = case_id
        self.sim_time_s = sim_time_s
        self.mode = mode

s = AgentState(case_id=42, sim_time_s="이상한 문자열", mode="hello")
# ← 모두 통과. 검사 없음.
```

typo 한 글자로 `case_id` 에 dict 가 들어가도 그대로 굴러간다.

## `dataclass` — type 선언은 가능, 검증은 X

```python
from dataclasses import dataclass

@dataclass
class AgentState:
    case_id: str
    sim_time_s: float
    mode: str

s = AgentState(case_id=42, sim_time_s="문자열", mode="hello")
# ← 여전히 통과. annotation 은 type checker (mypy/pyright) 시점만.
```

`@dataclass` 가 주는 것: `__init__` 자동 생성, 가독성, frozen 옵션. **Runtime type 검증은 없음.** 우리 `result_types.py` 는 frozen dataclass — Result 가 작고 immutable 이라 충분.

## `pydantic.BaseModel` — runtime 검증

```python
from pydantic import BaseModel

class AgentState(BaseModel):
    case_id: str
    sim_time_s: float
    mode: Literal["shallow", "deep"]

s = AgentState(case_id=42, sim_time_s="문자열", mode="hello")
# ← ValidationError !
#   - case_id: Input should be a valid string
#   - sim_time_s: Input should be a valid number
#   - mode: Input should be 'shallow' or 'deep'
```

Runtime 시점에 type 검증. 추가 기능:
- JSON 직렬화: `state.model_dump_json()`
- 역직렬화: `AgentState.model_validate({...})`
- Field default / validator
- `frozen=True` 옵션

## OpSight 어디에 쓰나

| 모듈 | Pydantic? | 이유 |
|------|----------|------|
| `state.py` `AgentState` | ✅ | LangGraph 가 dict 직렬화/역직렬화, validation 필수 |
| `tools/envelope.py` `ToolRequest/Response/Error` | ✅ | tool 간 schema 어긋남 즉시 거부 |
| `fm/result_types.py` `HypotensionResult` 등 | ❌ frozen dataclass | FM 직접 반환, immutable + `asdict` 충분 |

기준:
- **변경 가능 흐름 state** → Pydantic
- **불변 결과 값** → frozen dataclass

## 우리 `AgentState`

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

- `extra="forbid"`: 정의되지 않은 field 거부 — typo / schema drift 방지
- `Field(default_factory=list)`: 매 instance 마다 새 list (mutable default 함정 회피)

## `Literal["a", "b"]` — 좁은 enum

```python
mode: Literal["shallow", "deep"]
```

`mode = "hello"` → ValidationError. Pydantic + mypy 모두 강제.

## `model_copy(update={...})` — functional update

```python
new_state = state.model_copy(
    update={
        "sim_time_s": clock.now_s,
        "mode": "deep",
        "brief_history": [*state.brief_history, new_record],
    }
)
```

원본은 그대로, 새 instance 생성. list field 추가는 `[*old, new]` spread.

## 직렬화

```python
# Pydantic → JSON
json_str = state.model_dump_json()

# Pydantic → dict
d = state.model_dump()

# dict → Pydantic
state = AgentState.model_validate(d)
```

Trace JSONL 은 per-event payload 만 저장 (state 전체는 매 event 마다 저장하기엔 큼).

## 한 줄 비교

| 목적 | Pydantic | frozen dataclass | dict |
|------|----------|------------------|------|
| Runtime type 검증 | ✅ | ❌ | ❌ |
| JSON 직렬화 | ✅ 내장 | `asdict` + 수동 json | 자연스러움 |
| Immutability | `frozen=True` 옵션 | ✅ | ❌ |
| 가벼움 | 약간 무거움 | ✅ | ✅ |
| 우리 사용 | state, envelope | Result | 짧은 payload |

## 다음 노트

- [[Python_Protocol_과_runtime_checkable]] — Pydantic 은 *값* 의 type, Protocol 은 *interface* 의 type
- [[dataclass_와_frozen]] — 가벼운 대안
- [[30_코드_워크스루/04_state_clock_triggers]] — state.py 코드 워크스루
