# Python Protocol 과 runtime_checkable

> "이 class는 이 method들을 가졌어"를 *상속 없이* 표현하는 type. Mock FM swap의 핵심 기법.

## 두 가지 다른 type 개념 — nominal vs structural

### Nominal typing (전통적)

class A가 class B의 instance인가? → **상속 관계로만** 결정.

```python
class Animal: pass
class Dog(Animal): pass
class Cat(Animal): pass

d = Dog()
isinstance(d, Animal)  # True — Dog가 Animal을 상속
```

### Structural typing (duck typing)

"오리처럼 보이고 오리처럼 우는 건 오리다." 상속 무관, **method가 있으면** instance로 간주.

Python의 `typing.Protocol`이 이를 표현.

## `Protocol` — interface를 *상속 없이* 표현

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

# Circle / Square 모두 HasArea를 *상속하지 않았지만* HasArea Protocol을 *만족*한다.
```

`Protocol`은 "이런 method 가지고 있으면 type 일치"를 표현. **상속 강제 없음**. type checker (mypy / pyright)는 structural 일치를 검증.

## `@runtime_checkable` — runtime에 `isinstance` 사용 가능

기본 Protocol은 type checker 시점에만 검증. Runtime의 `isinstance(obj, Proto)`는 작동하지 않음. `@runtime_checkable` 데코레이터를 붙이면 runtime에도 작동:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class HasArea(Protocol):
    def area(self) -> float: ...

c = Circle(r=5)
isinstance(c, HasArea)  # True — runtime에 method 이름만 확인
```

⚠️ **`runtime_checkable`의 한계**: method 이름만 확인. signature (인자 type)는 확인하지 않는다. 더 엄격하게 보려면 `inspect.signature` 추가 검사.

## VitalAgent에서 — `BiosignalFMInterface`

핵심 코드 (`vitalagent/fm/interface.py`):

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

`StubBiosignalFM` (Tier 1), `RuleBasedBiosignalFM` (Tier 2), 미래의 `RealBiosignalFM` (real FM adapter)는 모두 이 8개 method를 *각자* 구현. 어느 것도 `BiosignalFMInterface`를 상속하지 않는다.

```python
stub = StubBiosignalFM(seed=42)
isinstance(stub, BiosignalFMInterface)  # True

rule = RuleBasedBiosignalFM(seed=42)
isinstance(rule, BiosignalFMInterface)  # True
```

## 왜 *Protocol*을 쓰는가 — Mock FM swap

`real FM` 또는 `mock` 모두 같은 8 method를 제공해야 한다. 두 가지 옵션:

### 옵션 A: 추상 base class (ABC) 상속

```python
class BiosignalFMBase(ABC):
    @abstractmethod
    def encode(self, ...): pass
    # ... 8 method

class StubBiosignalFM(BiosignalFMBase):
    def encode(self, ...): ...
    # ...
```

- 단점: real FM이 외부 library에서 오면 base class 상속 강제 불가
- 단점: 강한 결합 (StubBiosignalFM이 BiosignalFMBase를 import해야 함)

### 옵션 B: Protocol (우리 선택)

```python
@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, ...): ...
    # ...

class StubBiosignalFM:        # 상속 X
    def encode(self, ...): ...
    # ...
```

- 외부 library의 class도 8 method만 있으면 그대로 사용 가능
- 약결합 (StubBiosignalFM은 Protocol을 모름)
- Agent / tool layer는 `BiosignalFMInterface`만 import → swap 시 코드 변경 0

자세한 swap mechanism은 [[20_아키텍처/Mock_FM_3_Tier_전략]].

## ADR-011 swap mechanism의 코어

```python
# vitalagent/fm/factory.py 일부

def create_fm(config) -> BiosignalFMInterface:
    impl = config["fm"]["implementation"]
    if impl == "mock_stub":
        from vitalagent.fm.mock_stub import StubBiosignalFM
        return StubBiosignalFM(**config["fm"]["config"])
    if impl == "mock_rule_based":
        from vitalagent.fm.mock_rule_based import RuleBasedBiosignalFM
        return RuleBasedBiosignalFM(**config["fm"]["config"])
    # ... real, mock_light_ml
```

호출자는 결과 type을 `BiosignalFMInterface`로만 안다. 어느 concrete class인지 모름. **config 한 줄 변경**으로 mock_stub ↔ mock_rule_based ↔ real 전환.

## Compliance test — Protocol 강제 검증

```python
# tests/test_fm_protocol_compliance.py

FM_IMPLEMENTATIONS = [
    ("StubBiosignalFM",      lambda: StubBiosignalFM(seed=42)),
    ("RuleBasedBiosignalFM", lambda: RuleBasedBiosignalFM(seed=42)),
    # 새 tier 추가 시 한 줄 추가
]

@pytest.mark.parametrize("name, factory", FM_IMPLEMENTATIONS)
def test_runtime_checkable_protocol(name, factory):
    fm = factory()
    assert isinstance(fm, BiosignalFMInterface)
```

새 tier (예: `LightMLBiosignalFM`)가 도착하면 위 list에 한 줄 추가 → 3개 test가 자동 실행되어 Protocol 만족 검증.

자세한 건 [[30_코드_워크스루/01_fm_layer]].

## `from __future__ import annotations` — Protocol 의 torch 의존 회피

`BiosignalFMInterface`의 method가 `torch.Tensor` annotation을 가진다. 일반적으로 `import torch`가 필요하지만:

```python
from __future__ import annotations          # ← PEP 563, annotation을 string으로

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import torch                             # ← type 검사 시점에만 import

@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, signal: dict[str, torch.Tensor], ...) -> torch.Tensor: ...
```

`from __future__ import annotations` 효과: 모든 annotation이 string으로 lazy 평가. runtime에 `torch.Tensor`를 실제 type으로 평가하지 않음.

→ **torch 미설치 환경에서도 `BiosignalFMInterface` import 가능**. `isinstance` check도 작동.

자세한 건 [[30_코드_워크스루/01_fm_layer]].

## ABC vs Protocol — 언제 어느 것?

| | ABC | Protocol |
|---|-----|----------|
| 상속 | 강제 | 무관 (structural) |
| 외부 class | 적용 불가 | 적용 가능 |
| 결합도 | 강 | 약 |
| Runtime check | `isinstance` 자동 | `@runtime_checkable` 필요 |
| Signature 검사 | 강제 | `runtime_checkable`은 method 이름만 |

VitalAgent는 **외부 real FM이 들어올 수 있도록** Protocol 채택. 우리가 통제하는 class만 있으면 ABC도 OK.

## 다음 노트

- [[30_코드_워크스루/01_fm_layer]] — `interface.py` 전체 워크스루
- [[20_아키텍처/Mock_FM_3_Tier_전략]] — 왜 3 tier가 필요한가
