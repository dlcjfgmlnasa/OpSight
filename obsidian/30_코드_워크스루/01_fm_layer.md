# 01. FM Layer — `result_types.py` + `interface.py` + `factory.py`

> FM 자리에 무엇이든 끼울 수 있도록 만들어둔 추상 layer. ADR-011 의 core. 자세한 배경은 [[20_아키텍처/Mock_FM_3_Tier_전략]].

## 파일 3개

```
opsight/fm/
├── result_types.py   ← 7개 Result dataclass (FM 출력 type)
├── interface.py      ← BiosignalFMInterface Protocol (8 method)
└── factory.py        ← create_fm() + make_fallback()
```

## `result_types.py` — 7개 frozen dataclass

각 FM method 마다 다른 결과 type. 모두 frozen.

```python
@dataclass(frozen=True)
class HypotensionResult:
    risk: float
    uncertainty: float
    horizon_min: int
    meta: dict[str, Any] = field(default_factory=dict)
```

7개 type:
- `HypotensionResult` — tool 1
- `ArrestResult` — tool 2
- `QualityResult` — tool 3 (score + optional reason)
- `ConsistencyResult` — tool 4
- `TrendResult` — tool 5 (slope, magnitude, rising/falling/stable label)
- `ForecastResult` — tool 6 (forecast / uncertainty 모두 list[float])
- `AnomalyResult` — tool 7

### `frozen=True` 인 이유

- 기록되는 값이라 변경되면 trace 의미가 깨짐
- multi-thread safe
- hashable

[[10_기초/dataclass_와_frozen]] 참조.

### `meta` 가 free-form dict 인 이유

Tier 마다 다른 디버깅 정보를 넣음.
- Stub: `{"mock_tier": "stub", "available_modalities": [...]}`
- Rule-based: `{"mock_tier": "rule_based", "map_proxy": 67.5, "slope_score": 0.4, ...}`

Consumer 는 meta 의 특정 key 를 가정하지 않는다. 디버깅용.

### Field 의 정확한 의미

코드에는 1줄 docstring 만. 상세는 `docs/fm_interface_guide.md §1`.

## `interface.py` — `BiosignalFMInterface` Protocol

```python
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import torch        # type checker 시점만

@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, signal: dict[str, torch.Tensor],
                available_modalities: list[str]) -> torch.Tensor: ...

    def predict_hypotension(self, signal: dict[str, torch.Tensor],
                              horizon_min: int,
                              available_modalities: list[str]) -> HypotensionResult: ...

    # ... 총 8 method
```

### `runtime_checkable` Protocol

상속 없이 8 method 만 가지면 `isinstance(obj, BiosignalFMInterface)` 통과. Mock FM swap 의 기반. [[10_기초/Python_Protocol_과_runtime_checkable]] 참조.

### `TYPE_CHECKING` + `from __future__ import annotations`

```python
from __future__ import annotations   # 모든 annotation 을 string 으로
```

→ runtime 에 `torch.Tensor` 가 실제 type 으로 평가되지 않음.

```python
if TYPE_CHECKING:
    import torch
```

→ type checker 시점에만 import. 효과:
- Stub FM 은 torch 없이 작동 가능
- Protocol import 만 하는 client 는 torch 의존성 X
- Unit test 환경 가벼움

## `factory.py` — `create_fm()` + `make_fallback()`

### `create_fm(config)` — config-driven tier 선택

```python
def create_fm(config: dict[str, Any]) -> BiosignalFMInterface:
    fm_section = config.get("fm")
    if not isinstance(fm_section, dict):
        raise ValueError("config must contain an 'fm' object ...")
    impl = fm_section.get("implementation")
    fm_kwargs = fm_section.get("config") or {}

    if impl not in _KNOWN_IMPLEMENTATIONS:
        raise ValueError(f"Unknown FM implementation: {impl!r}. ...")

    if impl == "mock_stub":
        from opsight.fm.mock_stub import StubBiosignalFM
        return StubBiosignalFM(**fm_kwargs)

    if impl == "mock_rule_based":
        try:
            from opsight.fm.mock_rule_based import RuleBasedBiosignalFM
        except ImportError as exc:
            raise NotImplementedError(...) from exc
        return RuleBasedBiosignalFM(**fm_kwargs)

    # ... real, mock_light_ml
```

### 3-step 에러 정책

| 상황 | 동작 |
|------|------|
| `config["fm"]` 없음 | `ValueError("config must contain ...")` |
| Unknown `implementation` | `ValueError("Unknown FM implementation: ...")` |
| Valid name + module 부재 | `NotImplementedError` + 안내 |

### Lazy import

각 tier import 가 함수 안에. 안 쓰는 tier 까지 로딩되는 비용 피함 + 미구현 tier 호출 시 친절한 메시지.

### `make_fallback(primary, fallback)` — graceful degradation

```python
fm = make_fallback(real_fm, mock_rule_based_fm, latency_budget_sec=0.5)
```

`_FallbackFM` wrapper 가 8 method 위임:
- primary 정상 → primary 결과 반환
- primary 예외 → fallback 호출 + alert
- primary latency 초과 → primary 결과 + alert

ADR-011 의 "Real-FM migration protocol" 참조.

## 사용 흐름

```python
import yaml
from opsight.fm.factory import create_fm

with open("configs/fm/default.yaml") as f:
    config = yaml.safe_load(f)
fm = create_fm(config)
# fm: BiosignalFMInterface — concrete class 는 모름

risk_result = fm.predict_hypotension(
    signal={"ABP": ..., "ECG_II": ...},
    horizon_min=5,
    available_modalities=["ABP", "ECG_II"],
)
```

## Tests

| 파일 | 검증 |
|------|------|
| `tests/test_fm_protocol_compliance.py` | Stub / RuleBased Protocol 만족 |
| `tests/test_fm_factory.py` | `create_fm` switch + 에러 정책 |
| `tests/test_fm_config_yaml.py` | 5 yaml round-trip |
| `tests/test_fm_fallback.py` | `make_fallback` wrapper |

35+ test.

## 다음 노트

- [[02_mock_stub]] — Tier 1 구현
- [[03_mock_rule_based]] — Tier 2 구현
- [[10_기초/Python_Protocol_과_runtime_checkable]] — Protocol mechanism
