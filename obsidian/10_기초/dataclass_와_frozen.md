# dataclass 와 frozen

> `@dataclass(frozen=True)`: 값이 만들어지면 변경 불가. 우리 FM Result type 에 적용.

## `@dataclass` 기본

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

p = Point(1.0, 2.0)
p.x = 10.0           # OK — mutable
```

`@dataclass` 가 자동 생성: `__init__`, `__repr__`, `__eq__`. Type 검증은 [[Pydantic_과_typed_state]] 참조 — `@dataclass` 자체는 X.

## `frozen=True` — 불변

```python
@dataclass(frozen=True)
class Point:
    x: float
    y: float

p = Point(1.0, 2.0)
p.x = 10.0           # FrozenInstanceError !
```

생성 후 field 재할당 금지. **Immutable.**

장점:
- 의도하지 않은 변경 차단
- Hashable — set / dict key 가능
- Multi-thread safe

## OpSight Result types — 모두 frozen

```python
# opsight/fm/result_types.py

@dataclass(frozen=True)
class HypotensionResult:
    risk: float
    uncertainty: float
    horizon_min: int
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class TrendResult:
    slope: float
    magnitude: float
    label: Literal["rising", "falling", "stable"]
    meta: dict[str, Any] = field(default_factory=dict)

# ... 7개 모두 frozen
```

이유:
- FM 의 *출력*, 한 번 만들어지면 변경할 이유 없음
- LangGraph trace 에 저장 — 기록 시점 값 보존
- Tool wrapper 가 `asdict()` 로 JSON 변환

## `field(default_factory=dict)` — mutable 기본값 함정

```python
# 잘못된 패턴 (절대 X)
@dataclass
class Bad:
    items: list = []    # ← 모든 instance 가 같은 list 공유!

# 올바른 패턴
@dataclass
class Good:
    items: list = field(default_factory=list)   # 매 instance 새 list
```

Pydantic 의 `Field(default_factory=list)` 와 같은 개념.

## `asdict()` — JSON 직렬화

```python
from dataclasses import asdict

r = HypotensionResult(risk=0.42, uncertainty=0.18, horizon_min=5)
d = asdict(r)
# {"risk": 0.42, "uncertainty": 0.18, "horizon_min": 5, "meta": {}}

import json
json.dumps(d)
```

Tool wrapper 가 `HypotensionResult` 등을 `asdict` 로 변환 → `ToolResponse.result` (dict) → trace JSONL.

## `Literal["a", "b", "c"]` — 좁은 enum

```python
@dataclass(frozen=True)
class TrendResult:
    label: Literal["rising", "falling", "stable"]
```

`label = "hello"` → 생성 시점에 type checker (mypy / pyright) 경고. ⚠️ Runtime 은 일반 string 도 통과 — type checker 만 강제. 엄격히는 Pydantic.

## Pydantic vs frozen dataclass — 선택 기준

| 상황 | 도구 | 이유 |
|------|------|------|
| 흐름 state (LangGraph) | `pydantic.BaseModel` | type 검증 + serialization + LangGraph 호환 |
| Tool envelope | `pydantic.BaseModel` | type 검증 + `extra="forbid"` 로 schema drift 방지 |
| FM Result (`HypotensionResult` 등) | `@dataclass(frozen=True)` | 가벼움 + 불변 + `asdict` 충분 |
| `TickMeasurement` | `@dataclass` (mutable) | `wall_end` in-place 갱신 필요 |

원칙:
- **검증 + serialization 필요** → Pydantic
- **단순 불변 출력** → frozen dataclass

## 다음 노트

- [[Pydantic_과_typed_state]] — 무거운 검증이 필요한 흐름 state
- [[30_코드_워크스루/01_fm_layer]] — `result_types.py` 워크스루
