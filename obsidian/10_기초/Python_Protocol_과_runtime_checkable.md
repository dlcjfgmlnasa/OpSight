# Python Protocol 과 runtime_checkable

> "이 class 는 이 method 들을 가졌어" 를 *상속 없이* 표현하는 type. Mock FM swap 의 핵심 기법.

## Nominal vs Structural typing

### Nominal — 상속 관계로만

```python
class Animal: pass
class Dog(Animal): pass

d = Dog()
isinstance(d, Animal)  # True — Dog 가 Animal 을 상속
```

상속하지 않으면 아무리 비슷해도 instance 가 아니다.

### Structural (duck typing)

"오리처럼 보이고 오리처럼 우는 건 오리다." 상속 무관, **method 가 있으면** 같은 type.

Python 의 `typing.Protocol` 이 이를 표현.

## `Protocol` — 상속 없이 interface 표현

```python
from typing import Protocol

class HasArea(Protocol):
    def area(self) -> float: ...

class Circle:
    def area(self) -> float:
        return 3.14 * self.r * self.r

class Square:
    def area(self) -> float:
        return self.side * self.side

# Circle / Square 모두 HasArea 를 *상속하지 않았지만* 만족.
```

Type checker (mypy / pyright) 가 structural 일치 검증.

## `@runtime_checkable` — runtime `isinstance` 작동

기본 Protocol 은 type checker 시점만. `@runtime_checkable` 붙이면 runtime 도:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class HasArea(Protocol):
    def area(self) -> float: ...

c = Circle(r=5)
isinstance(c, HasArea)  # True — method 이름만 확인
```

⚠️ 한계: method 이름만 확인. signature 는 X. 엄격하게 보려면 `inspect.signature` 추가.

## OpSight — `BiosignalFMInterface`

`opsight/fm/interface.py`:

```python
@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, signal, available_modalities) -> torch.Tensor: ...
    def predict_hypotension(self, signal, horizon_min, available_modalities) -> HypotensionResult: ...
    def predict_cardiac_arrest(self, signal, horizon_min, available_modalities) -> ArrestResult: ...
    def assess_signal_quality(self, signal, modality) -> QualityResult: ...
    def cross_modal_consistency(self, signal, modality_pair) -> ConsistencyResult: ...
    def temporal_trend(self, signal, modality, window_min) -> TrendResult: ...
    def forecast_signal(self, signal, modality, horizon_min) -> ForecastResult: ...
    def anomaly_score(self, signal, modality) -> AnomalyResult: ...
```

`StubBiosignalFM`, `RuleBasedBiosignalFM`, `LightMLBiosignalFM`, 미래의 `RealBiosignalFM` 모두 8 method 를 각자 구현. **어느 것도 상속하지 않음.**

```python
stub = StubBiosignalFM(seed=42)
isinstance(stub, BiosignalFMInterface)  # True
```

## 왜 Protocol — ABC 와의 비교

### 옵션 A: ABC 상속

```python
class BiosignalFMBase(ABC):
    @abstractmethod
    def encode(self, ...): pass
    # ...

class StubBiosignalFM(BiosignalFMBase):
    def encode(self, ...): ...
```

문제:
- Real FM 이 외부 library 면 base class 상속 강제 불가
- 강결합 (StubBiosignalFM 이 BiosignalFMBase import 필요)

### 옵션 B: Protocol (우리 선택)

```python
@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, ...): ...

class StubBiosignalFM:        # 상속 X
    def encode(self, ...): ...
```

- 외부 library class 도 8 method 만 있으면 사용 가능
- 약결합 (StubBiosignalFM 은 Protocol 모름)
- Agent / tool layer 는 `BiosignalFMInterface` 만 import → swap 시 코드 변경 0

[[20_아키텍처/Mock_FM_3_Tier_전략]] 참조.

## ADR-011 swap mechanism

```python
# opsight/fm/factory.py

def create_fm(config) -> BiosignalFMInterface:
    impl = config["fm"]["implementation"]
    if impl == "mock_stub":
        from opsight.fm.mock_stub import StubBiosignalFM
        return StubBiosignalFM(**config["fm"]["config"])
    if impl == "mock_rule_based":
        from opsight.fm.mock_rule_based import RuleBasedBiosignalFM
        return RuleBasedBiosignalFM(**config["fm"]["config"])
    # ... real, mock_light_ml
```

호출자는 반환 type 을 `BiosignalFMInterface` 로만 안다. **config 한 줄 변경** 으로 swap.

## Compliance test

```python
# tests/test_fm_protocol_compliance.py

FM_IMPLEMENTATIONS = [
    ("StubBiosignalFM",      lambda: StubBiosignalFM(seed=42)),
    ("RuleBasedBiosignalFM", lambda: RuleBasedBiosignalFM(seed=42)),
    ("LightMLBiosignalFM",   lambda: LightMLBiosignalFM(...)),
]

@pytest.mark.parametrize("name, factory", FM_IMPLEMENTATIONS)
def test_runtime_checkable_protocol(name, factory):
    fm = factory()
    assert isinstance(fm, BiosignalFMInterface)
```

새 tier 추가 시 list 에 한 줄 추가 → 자동 검증.

[[30_코드_워크스루/01_fm_layer]] 참조.

## torch 의존성 회피 — `TYPE_CHECKING`

`BiosignalFMInterface` 의 method 가 `torch.Tensor` annotation 을 가진다. 일반적으로 `import torch` 필요하지만:

```python
from __future__ import annotations          # ← PEP 563, annotation 을 string 으로

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import torch                             # ← type 검사 시점만

@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, signal: dict[str, torch.Tensor], ...) -> torch.Tensor: ...
```

`from __future__ import annotations` 효과: 모든 annotation 이 string 으로 lazy 평가. runtime 에 `torch.Tensor` 평가 X.

→ **torch 미설치 환경에서도** `BiosignalFMInterface` import 가능. `isinstance` 도 작동.

## ABC vs Protocol — 언제 어느 것?

| | ABC | Protocol |
|---|-----|----------|
| 상속 | 강제 | 무관 (structural) |
| 외부 class | 적용 불가 | 적용 가능 |
| 결합도 | 강 | 약 |
| Runtime check | `isinstance` 자동 | `@runtime_checkable` 필요 |
| Signature 검사 | 강제 | `runtime_checkable` 은 이름만 |

OpSight: **외부 real FM** 합류 가능성 → Protocol. 통제하는 class 만 있으면 ABC 도 OK.

## 다음 노트

- [[30_코드_워크스루/01_fm_layer]] — `interface.py` 워크스루
- [[20_아키텍처/Mock_FM_3_Tier_전략]] — 왜 3 tier 인가
- [[Pydantic_과_typed_state]] — Pydantic 은 *값* type, Protocol 은 *interface* type
