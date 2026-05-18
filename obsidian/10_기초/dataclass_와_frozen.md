# dataclass 와 frozen — 불변 결과 값 표현

> `@dataclass(frozen=True)`: "값이 만들어지면 변경할 수 없다"는 Python 표준 도구. 우리 Result 타입에 적용.

## `@dataclass` 기본

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

p = Point(1.0, 2.0)
p.x = 10.0           # OK — 변경 가능 (mutable)
```

`@dataclass`는 `__init__`, `__repr__`, `__eq__`를 자동 생성. type 검증은 [[Pydantic_과_typed_state]] 참조 — `@dataclass` 자체는 검증 안 함.

## `frozen=True` — 불변 객체

```python
@dataclass(frozen=True)
class Point:
    x: float
    y: float

p = Point(1.0, 2.0)
p.x = 10.0           # FrozenInstanceError 발생!
```

생성 후 field 재할당 금지. **불변 (immutable)**.

장점:
- 의도하지 않은 변경 차단
- hashable — set / dict key로 사용 가능
- multi-thread 환경에서 race 없음

## VitalAgent의 Result types — 모두 `frozen=True`

```python
# vitalagent/fm/result_types.py

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

# ... 7개 Result type 전체 frozen
```

왜 frozen?
- Result는 FM의 *출력*. 한 번 만들어지면 변경할 이유 없음
- LangGraph trace에 저장되므로 *기록 시점의 값*이 보존되어야 함
- Tool wrapper가 `asdict()`로 JSON 변환 — 변경되지 않는 게 안전

## `field(default_factory=dict)` — mutable 기본값 함정 회피

```python
# 잘못된 패턴 (절대 쓰지 말 것)
@dataclass
class Bad:
    items: list = []    # ← 모든 instance가 같은 list 공유!

# 올바른 패턴
@dataclass
class Good:
    items: list = field(default_factory=list)   # 매 instance마다 새 list
```

Pydantic의 `Field(default_factory=list)`와 같은 개념.

## `asdict()` — JSON 직렬화

```python
from dataclasses import asdict

r = HypotensionResult(risk=0.42, uncertainty=0.18, horizon_min=5)
d = asdict(r)
# {"risk": 0.42, "uncertainty": 0.18, "horizon_min": 5, "meta": {}}

import json
json.dumps(d)   # JSON 문자열로
```

우리 tool wrapper는 FM이 반환한 `HypotensionResult` 등을 `asdict`로 변환 → `ToolResponse.result` (dict) 로 넣음. trace JSONL에 저장.

## `Literal["a", "b", "c"]` — 좁은 enum

```python
@dataclass(frozen=True)
class TrendResult:
    label: Literal["rising", "falling", "stable"]
```

`label = "hello"`를 *생성 시점*에 type checker (mypy / pyright)가 경고. ⚠️ 단 runtime은 일반 string으로 들어가도 통과. type checker만 강제.

더 엄격하게 runtime 검증을 원하면 Pydantic (Literal validator 작동).

## Pydantic vs frozen dataclass — 우리 선택 기준

| 상황 | 도구 | 이유 |
|------|------|------|
| 흐름 state (LangGraph) | `pydantic.BaseModel` | type 검증 + serialization + LangGraph 호환 |
| Tool envelope (Request / Response) | `pydantic.BaseModel` | type 검증 + extra="forbid"로 schema drift 방지 |
| FM Result (HypotensionResult 등) | `@dataclass(frozen=True)` | 가벼움 + 불변 + asdict로 충분 |
| 시간 측정 (`TickMeasurement`) | `@dataclass` (mutable) | wall_end 갱신 필요 — `measure_tick_end`에서 in-place |

원칙:
- **검증 + serialization 필요 → Pydantic**
- **단순 + 불변 출력 → frozen dataclass**

## 다음 노트

- [[Pydantic_과_typed_state]] — 무거운 검증이 필요한 흐름 state
- [[30_코드_워크스루/01_fm_layer]] — `result_types.py` 코드 워크스루
