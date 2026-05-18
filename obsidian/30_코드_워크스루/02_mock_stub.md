# 02. Mock Stub — `vitalagent/fm/mock_stub.py`

> FM 자리에 끼우는 첫 단계 mock. 신호를 *보지 않고* 그저 valid range 안의 random 숫자를 뱉는다. 코드 흐름과 latency 시뮬레이션만 검증하기 위한 것.

## 이 mock 으로 무엇을 하면 안 되는가

코드 docstring 에 박아둔 경고가 그대로 있다.

```
STUB OUTPUT 으로 절대 하지 말 것:
1. 임상 결정 / 환자 대상 권고
2. Agent reasoning 검증 (brief 의 faithfulness, risk-trend logic 등)
3. Real-FM 의 latency 또는 accuracy benchmark
```

이 mock 은 *문법* 만 검증한다. *의미* 는 Tier 2 (rule-based) 또는 real FM 의 영역이다. 자세한 배경은 [[20_아키텍처/Mock_FM_3_Tier_전략]].

## 클래스 구조

```python
class StubBiosignalFM:
    def __init__(
        self,
        seed: int = 42,
        latent_dim: int = 128,
        latency_sim_sec: float = 0.0,
        latency_per_method: dict[str, float] | None = None,
        latency_jitter_pct: float = 0.0,
    ) -> None:
        self._seed = seed
        self._latent_dim = latent_dim
        self._np_rng = np.random.default_rng(seed)
        self._torch_gen = torch.Generator()
        self._torch_gen.manual_seed(seed)
        # Latency 설정
        self._latency_sim_sec = float(latency_sim_sec)
        self._latency_per_method = dict(latency_per_method or {})
        self._latency_jitter_pct = float(latency_jitter_pct)
```

### Random number generator 가 2개인 이유

```python
self._np_rng = np.random.default_rng(seed)
self._torch_gen = torch.Generator()
self._torch_gen.manual_seed(seed)
```

scalar/array 는 numpy 로, `encode` 가 반환할 tensor 는 torch 로 만든다. 둘 다 같은 seed 에서 시작한다. 그래서 **결정적** 이다 — 같은 seed 면 항상 같은 출력이 나온다. Unit test 에서 expected value 를 박을 수 있다.

## 8 method 가 모두 latency decorator 로 감싸진다

```python
def _simulate_latency(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        self._sleep_for(method.__name__)
        return method(self, *args, **kwargs)
    return wrapper

class StubBiosignalFM:
    @_simulate_latency
    def encode(self, signal, available_modalities):
        return torch.randn(self._latent_dim, generator=self._torch_gen)

    @_simulate_latency
    def predict_hypotension(self, signal, horizon_min, available_modalities):
        return HypotensionResult(
            risk=float(self._np_rng.uniform(0.0, 1.0)),
            uncertainty=float(self._np_rng.uniform(0.0, 0.5)),
            horizon_min=horizon_min,
            meta={"mock_tier": "stub", "available_modalities": list(available_modalities)},
        )

    # ... 6개 더
```

decorator 가 method 호출 직전에 `_sleep_for(method_name)` 을 부른다. method 본체는 그저 random 값 반환.

### Latency 시뮬레이션 — 진짜 FM 인 척 시간을 쓴다

```python
def _sleep_for(self, method_name):
    base = self._latency_per_method.get(method_name, self._latency_sim_sec)
    if base <= 0:
        return
    if self._latency_jitter_pct > 0:
        jitter = base * self._latency_jitter_pct
        base = base + float(self._np_rng.uniform(-jitter, jitter))
        base = max(0.0, base)
    if base > 0:
        time.sleep(base)
```

세 가지 옵션이 있다.

- **전역 기본값** (`latency_sim_sec`)
- **method 별 override** (`latency_per_method`)
- **jitter** (`latency_jitter_pct`) — 분포를 시뮬레이션. 실제 inference 도 매번 같은 시간이 걸리진 않으니까

`time.sleep` (sync) 을 쓰는 이유는 — LangGraph node 가 sync 환경이라서. async 가 아니다.

자세한 dual-mode 의 latency 의미는 [[20_아키텍처/Dual_mode_architecture]].

## 각 method 가 반환하는 값의 range

| Method | 출력 range / shape |
|--------|---------------------|
| `encode` | `torch.Tensor`, shape `(latent_dim,)`, 기본 `(128,)` |
| `predict_hypotension` | risk ∈ `[0, 1]`, uncertainty ∈ `[0, 0.5]` |
| `predict_cardiac_arrest` | risk ∈ `[0, 0.2]` (rare event 라서 좁게), uncertainty ∈ `[0, 0.5]` |
| `assess_signal_quality` | score ∈ `[0, 1]`, reason 은 score < 0.5 일 때만 `"stub-random low quality"` |
| `cross_modal_consistency` | score ∈ `[0, 1]` |
| `temporal_trend` | slope ∈ `[-5, 5]`, label 은 derived (`\|slope\| < 1` → stable, > 0 → rising, < 0 → falling) |
| `forecast_signal` | `list[float]`, 길이 = `horizon_min`, value ∈ `[50, 120]` |
| `anomaly_score` | score ∈ `[0, 1]` |

모든 Result 의 `meta` 에 `"mock_tier": "stub"` 이 박힌다. 그래서 trace 를 보는 사람이 이 값이 stub 에서 왔다는 걸 명확히 알 수 있다.

## Config 파일

```yaml
# configs/fm/mock_stub.yaml
fm:
  implementation: mock_stub
  config:
    seed: 42
    latent_dim: 128
    latency_sim_sec: 0.0   # 기본 = sleep 없음
    latency_per_method:
      encode:                   0.080
      predict_hypotension:      0.030
      predict_cardiac_arrest:   0.030
      assess_signal_quality:    0.010
      cross_modal_consistency:  0.020
      temporal_trend:           0.015
      forecast_signal:          0.050
      anomaly_score:            0.015
    latency_jitter_pct: 0.15
```

이렇게 두면 8 method 가 실제 FM 과 비슷한 latency 분포를 흉내낸다. `latency_sim_sec: 0` 이면 sleep 자체가 없어서 unit test 가 빠르게 돈다.

## Test

| 파일 | 개수 |
|------|------|
| `tests/test_fm_mock_stub.py` | 16 (method 별 출력 + 결정성 + JSON + latency 4종) |
| `tests/test_fm_mock_stub_smoke.py` | 6 (단일 case 통합 sweep) |
| `tests/test_fm_protocol_compliance.py` | 3 (parametrized — Stub 자동 포함) |

합 25개.

## "Stub 은 signal 을 무시한다" — pyright 경고

```
ℹ Parameter 'signal' value is not used
```

Stub 의 8 method 는 signal 인자를 받지만 안 쓴다 (그저 random 을 뱉으니까). Pyright 는 이걸 info-level 로 경고한다.

이건 **의도된 동작** 이다. Protocol signature (`def encode(self, signal, ...)`) 를 따라야 isinstance 검사가 통과하니까 인자는 반드시 받아야 한다. 안 쓸 뿐이다.

Tier 2 (rule-based) 는 signal 을 *실제로* 쓴다. 거기 가서 보면 차이가 명확하다 → [[03_mock_rule_based]].

## 다음 노트

- [[03_mock_rule_based]] — Tier 2 가 signal 을 어떻게 *실제로* 쓰는가
- [[01_fm_layer]] — Stub 이 어떻게 Protocol 을 만족하는가
- [[20_아키텍처/Mock_FM_3_Tier_전략]] — Stub 의 위치가 전체 그림에서 어디인가
