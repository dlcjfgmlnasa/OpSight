# 01. FM Layer — Foundation Model 자리에 무엇이든 끼울 수 있게 만들어 둔 레이어

> 진짜 FM 이 도착하기 전부터 agent 를 만들어야 했다. 그래서 FM 자리에 **무엇이든 끼울 수 있는 추상 layer** 를 먼저 만들었다. 이 레이어는 세 개의 파일로 구성된다.

## 세 파일이 각자 무엇을 하나

```
vitalagent/fm/
├── result_types.py   ← FM 이 무엇을 반환하는지 (7개 dataclass)
├── interface.py      ← FM 이 어떤 method 를 가져야 하는지 (Protocol)
└── factory.py        ← config 보고 어떤 tier 의 FM 을 만들지
```

세 파일을 합치면 "FM 은 이런 모양이다 + 누가 실제로 그 모양을 채우는지" 의 약속이 된다.

## `result_types.py` — FM 이 반환하는 7가지 결과 type

FM 은 method 마다 다른 모양의 결과를 반환한다. risk 예측은 `{risk, uncertainty, horizon_min}` 이고, 신호 품질 평가는 `{score, reason}` 이고. 이걸 dict 로 두면 typo 에 약하니까 dataclass 로 둔다.

```python
@dataclass(frozen=True)
class HypotensionResult:
    """Tool 1 ``predict_hypotension`` output / Tool 1 출력."""
    risk: float
    uncertainty: float
    horizon_min: int
    meta: dict[str, Any] = field(default_factory=dict)
```

같은 패턴으로 7개:

- `HypotensionResult` — 저혈압 위험 (tool 1)
- `ArrestResult` — 심정지 위험 (tool 2)
- `QualityResult` — 신호 품질 (tool 3, score + optional reason)
- `ConsistencyResult` — 신호 간 일치도 (tool 4)
- `TrendResult` — 추세 (tool 5, slope + magnitude + rising/falling/stable label)
- `ForecastResult` — 향후 예측 (tool 6, forecast 와 uncertainty 모두 list[float])
- `AnomalyResult` — 이상 score (tool 7)

### 왜 `frozen=True` 인가

세 가지 이유가 한꺼번에 만족된다.

- **기록되는 값이라서 변경되면 안 된다** — FM 출력은 trace JSONL 에 들어간다. 누가 나중에 손대면 trace 의 의미가 달라진다.
- **multi-thread 안전** — 변경 불가능한 객체는 thread 간 공유해도 안전.
- **hashable** — set 이나 dict 의 key 로 쓸 수 있다.

dataclass 기초는 [[10_기초/dataclass_와_frozen]].

### `meta` 가 자유 형식 dict 인 이유

각 FM tier 가 디버깅 정보를 다르게 넣는다.

- Stub: `{"mock_tier": "stub", "available_modalities": [...]}`
- Rule-based: `{"mock_tier": "rule_based", "map_proxy": 67.5, "slope_score": 0.4, ...}`

Consumer (예: brief 생성하는 LLM) 는 `meta` 의 특정 key 가 있다고 가정하지 않는다. 디버깅용이라서.

### Field 의 정확한 의미는 어디 있나

코드에는 한 줄짜리 docstring 만 둔다. 자세한 의미는 `docs/fm_interface_guide.md §1` 에. 이렇게 분리한 이유는 — 사용자가 IDE 에서 코드를 처음 열었을 때 inline docstring 이 너무 길면 압도된다.

## `interface.py` — FM 이 가져야 할 8개 method 의 contract

```python
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import torch        # type checker 시점에만 import, runtime 에는 불필요

@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(self, signal: dict[str, torch.Tensor],
                available_modalities: list[str]) -> torch.Tensor: ...

    def predict_hypotension(self, signal: dict[str, torch.Tensor],
                              horizon_min: int,
                              available_modalities: list[str]) -> HypotensionResult: ...

    # ... 총 8 method
```

이 Protocol 이 swap mechanism 의 핵심이다. 두 가지 트릭이 들어가 있다.

### 트릭 1 — `runtime_checkable` Protocol

상속 (`class StubBiosignalFM(BiosignalFMInterface)`) 없이도, **8개 method 만 가지면** `isinstance(obj, BiosignalFMInterface)` 검사가 통과한다. 그래서 Mock FM 들이 이 Protocol 과 *공식적으로* 연결되지 않아도 (import 의존성 없이도) interface 를 만족할 수 있다.

자세한 mechanism 은 [[10_기초/Python_Protocol_과_runtime_checkable]].

### 트릭 2 — `TYPE_CHECKING` 으로 torch 를 lazy import

```python
from __future__ import annotations   # 모든 annotation 을 string 으로
```

이게 있으면 runtime 에 `torch.Tensor` 가 실제 type 으로 *평가되지 않는다*. 그냥 문자열 `"torch.Tensor"` 로 남는다.

```python
if TYPE_CHECKING:
    import torch
```

그리고 import 자체는 type checker (mypy, pyright) 가 돌 때만 일어난다. runtime 에선 일어나지 않는다.

왜 이렇게까지 하는가?

- **Stub FM 은 torch 없이 작동** 가능 (그냥 numpy random 만 쓰니까)
- **Protocol 만 import 하는 client code** 는 torch 의존성을 끌어들이지 않아도 된다
- **Unit test 환경 단순화** — 가볍게 돌릴 수 있다

## `factory.py` — config 한 줄 보고 어떤 tier 를 만들지 결정

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
        from vitalagent.fm.mock_stub import StubBiosignalFM
        return StubBiosignalFM(**fm_kwargs)

    if impl == "mock_rule_based":
        try:
            from vitalagent.fm.mock_rule_based import RuleBasedBiosignalFM
        except ImportError as exc:
            raise NotImplementedError(
                "FM tier 'mock_rule_based' is not yet implemented."
            ) from exc
        return RuleBasedBiosignalFM(**fm_kwargs)

    # ... real, mock_light_ml 도 같은 패턴
```

### 에러 정책이 3단계로 갈라진다

같은 잘못이라도 어디서 실수했는지에 따라 다른 에러를 던진다.

| 상황 | 동작 |
|---|---|
| `config["fm"]` 객체가 아예 없음 | `ValueError("config must contain ...")` |
| `implementation` 값이 우리가 모르는 이름 | `ValueError("Unknown FM implementation: ...")` |
| Tier 이름은 valid 한데 module 이 아직 없음 | `NotImplementedError` + 친절한 안내 |

이 구분 덕분에 "오타냐 / 모르는 tier 냐 / 아직 안 만든 tier 냐" 를 메시지만 보고 안다.

### Lazy import — 모든 tier 를 미리 import 하지 않는다

각 tier 의 import 가 함수 *안에* 있다. 모듈 최상단에 두면 안 쓰는 tier 까지 다 로딩되어 시작 시간이 느려진다.

또 한 가지 이점: 미구현 tier 를 호출했을 때 ImportError 가 그대로 새지 않고 친절한 메시지로 변환된다.

```
NotImplementedError: FM tier 'real' is not yet implemented
(real FM lands at the start of Stage 2 / Month 3).
```

### `make_fallback(primary, fallback)` — primary 실패 시 자동으로 fallback 으로

```python
fm = make_fallback(real_fm, mock_rule_based_fm, latency_budget_sec=0.5)
```

내부적으로 `_FallbackFM` 이라는 wrapper 가 8 method 를 모두 위임한다. 동작 규칙:

- primary 가 정상 종료 → primary 결과 반환
- primary 가 예외를 던짐 → fallback 호출 + alert 기록
- primary 가 latency budget 초과 → primary 결과는 그대로 반환하되 alert 만 기록

자세한 정책은 ADR-011 의 "Real-FM migration protocol" 절.

## 실제로 어떻게 쓰이는가

```python
import yaml
from vitalagent.fm.factory import create_fm

with open("configs/fm/default.yaml") as f:
    config = yaml.safe_load(f)
fm = create_fm(config)
# fm 은 BiosignalFMInterface — 어떤 concrete class 가 실제로 들어왔는지는 모름

# Tool wrapper / LangGraph node 에서 사용
risk_result = fm.predict_hypotension(
    signal={"ABP": ..., "ECG_II": ...},
    horizon_min=5,
    available_modalities=["ABP", "ECG_II"],
)
print(risk_result.risk, risk_result.uncertainty)
```

호출자는 `BiosignalFMInterface` 만 안다. 그 인터페이스 뒤에 stub 이 있든 rule-based 가 있든 real FM 이 있든, 호출자 코드는 *변하지 않는다*.

## 어떤 test 가 이 레이어를 지키나

| Test 파일 | 검증 |
|---|---|
| `tests/test_fm_protocol_compliance.py` | Stub / RuleBased 가 Protocol 을 만족 (positive 3 layer + negative) |
| `tests/test_fm_factory.py` | `create_fm` 의 switch + 에러 정책 |
| `tests/test_fm_config_yaml.py` | 5개 yaml round-trip |
| `tests/test_fm_fallback.py` | `make_fallback` wrapper (happy / exception / latency / per-method isolation / default alert) |

총 35개 이상의 test.

## 다음 노트

- [[02_mock_stub]] — Tier 1 의 실제 구현
- [[03_mock_rule_based]] — Tier 2 의 실제 구현
- [[10_기초/Python_Protocol_과_runtime_checkable]] — Protocol mechanism 의 기초
- [[20_아키텍처/Mock_FM_3_Tier_전략]] — 왜 mock 이 3단계로 나뉘는가
