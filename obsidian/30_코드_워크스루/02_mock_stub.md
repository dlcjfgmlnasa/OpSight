# 02. Mock Stub — `opsight/fm/mock_stub.py`

> Tier 1. Valid range 안의 **random** 값. Interface 안착 + latency 시뮬레이션 전용.

## ⚠️ HARD CAVEAT (코드 docstring 에 박혀 있음)

```
DO NOT USE STUB OUTPUT FOR:
1. Clinical decisions or any patient-facing recommendation.
2. Agent-reasoning validation (e.g. brief faithfulness, risk-trend logic).
3. Real-FM latency or accuracy benchmarking.
```

Stub 은 *문법* 만 검증. *의미* 는 Tier 2 (rule-based) 또는 real FM. [[20_아키텍처/Mock_FM_3_Tier_전략]] 참조.

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
        self._latency_sim_sec = float(latency_sim_sec)
        self._latency_per_method = dict(latency_per_method or {})
        self._latency_jitter_pct = float(latency_jitter_pct)
```

RNG 2개: numpy (scalar / array) + torch (`encode` 가 tensor 반환). 같은 seed → 같은 출력 (결정성).

## 8 method — `@_simulate_latency` decorator 로 wrap

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

### Latency simulation

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

- 전역 default + method-specific override
- `latency_jitter_pct`: 분포 시뮬레이션
- `time.sleep` (sync) — LangGraph node 가 sync 라서

## 각 method 의 출력 range

| Method | Range / shape |
|--------|---------------|
| `encode` | `torch.Tensor` `(latent_dim,)`, default `(128,)` |
| `predict_hypotension` | risk ∈ `[0, 1]`, uncertainty ∈ `[0, 0.5]` |
| `predict_cardiac_arrest` | risk ∈ `[0, 0.2]` (rare event proxy) |
| `assess_signal_quality` | score ∈ `[0, 1]`, reason 은 score < 0.5 일 때만 |
| `cross_modal_consistency` | score ∈ `[0, 1]` |
| `temporal_trend` | slope ∈ `[-5, 5]`, label derived |
| `forecast_signal` | `list[float]` len=`horizon_min`, values ∈ `[50, 120]` |
| `anomaly_score` | score ∈ `[0, 1]` |

모든 Result 의 `meta` 에 `"mock_tier": "stub"` 박힘.

## Config — `configs/fm/mock_stub.yaml`

```yaml
fm:
  implementation: mock_stub
  config:
    seed: 42
    latent_dim: 128
    latency_sim_sec: 0.0   # default = no sleep
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

`latency_sim_sec: 0` 이면 sleep 없음 (unit test 친화).

## Tests

| 파일 | 개수 |
|------|------|
| `tests/test_fm_mock_stub.py` | 16 (method 별 + determinism + JSON + latency 4) |
| `tests/test_fm_mock_stub_smoke.py` | 6 (단일 case 통합) |
| `tests/test_fm_protocol_compliance.py` | 3 (Stub 포함) |

총 25.

## "Stub 은 signal 무시" — Pyright info

```
ℹ Parameter 'signal' value is not used
```

Protocol signature 유지를 위해 인자는 받지만 안 씀. 의도. Rule-based (Tier 2) 는 signal 을 실제 사용 → [[03_mock_rule_based]].

## 다음 노트

- [[03_mock_rule_based]] — Tier 2 가 signal 을 어떻게 쓰는가
- [[01_fm_layer]] — Stub 이 Protocol 을 어떻게 만족하는가
- [[10_기초/Pydantic_과_typed_state]] — `latency_per_method` 같은 config 검증
