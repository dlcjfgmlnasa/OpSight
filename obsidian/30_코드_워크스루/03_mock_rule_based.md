# 03. Mock Rule-based — `vitalagent/fm/mock_rule_based.py`

> Tier 2 mock. **신호를 진짜로 본다**. 임상 휴리스틱 룰 기반으로 그럴듯한 (plausible) 출력을 만든다. Agent 의 reasoning 이 신호에 따라 일관되게 반응하는지 검증하는 데 쓴다. 지금 default tier 다.

## 이 mock 도 임상 결정에 쓰지는 않는다

여기 threshold 들은 모두 **휴리스틱** 이다. 임상 결정 규칙이 아니다. 모든 threshold 에 `[CLINICIAN-REVIEW]` 가 붙어 있다. 결과를 사용할 때 `meta["mock_tier"] == "rule_based"` marker 를 확인해서 "이건 mock 이다" 라는 점을 잊지 말아야 한다.

## 클래스 구조와 modality alias

```python
class RuleBasedBiosignalFM:
    _ABP_ALIASES = ("ABP", "SNUADC/ART", "Solar8000/ART_MBP", "EV1000/ART_MBP")
    _ECG_ALIASES = ("ECG", "ECG_II", "SNUADC/ECG_II")
    _PPG_ALIASES = ("PPG", "SNUADC/PLETH")
    _HR_ALIASES  = ("HR", "Solar8000/HR", "Solar8000/PLETH_HR")
    _BIS_ALIASES = ("BIS", "BIS/EEG1_WAV", "BIS/BIS")

    def __init__(
        self,
        seed: int = 42,
        latent_dim: int = 128,
        sampling_rate_hz: float = 500.0,
        noise_pct: float = 0.0,
        noise_per_method: dict[str, float] | None = None,
        noise_seed: int | None = None,
    ):
        ...
```

### 왜 alias 가 필요한가

호출자는 `signal: dict[str, torch.Tensor]` 를 넘긴다. 그런데 key 가 호출 환경에 따라 다르다.

- 우리 synthetic test 에서는 `"ABP"`, `"ECG_II"`, `"PPG"` 같은 짧은 이름
- 실제 VitalDB 에서는 `"SNUADC/ART"`, `"SNUADC/ECG_II"`, `"SNUADC/PLETH"` 같은 channel 명

`_ABP_ALIASES` 같은 tuple 이 두 형태를 모두 인식한다. `_find_first(signal, candidate_keys)` 라는 헬퍼가 signal dict 에서 첫 매칭 key 를 찾아준다.

자세한 VitalDB track 이름들은 `docs/findings/pre_phase3_findings.md §5`.

## Threshold 들은 모두 module 최상단의 상수로

임상의가 검토 / 조정할 수 있게 한 곳에 모아두었다.

```python
MAP_TARGET: float = 75.0          # 이 MAP 값에서 risk 가 0 에 수렴
MAP_RISK_FLOOR: float = 55.0      # 이 MAP 값 이하에서 map_score 가 saturate
SLOPE_RISK_FLOOR: float = -5.0    # 분당 -5 mmHg 에서 slope_score 가 saturate

ARREST_HR_LOW: float = 40.0
ARREST_HR_HIGH: float = 180.0
ARREST_MAP_LOW: float = 50.0

QUALITY_NAN_CUTOFF: float = 0.10
QUALITY_FLATLINE_STD_EPS: float = 1e-3
# ...
```

⚠️ 모두 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`. Mock Tier 2 의 발화 빈도를 임상의가 분석한 후 조정될 예정이다.

## 8 method 의 핵심 룰을 풀어 쓰면

### `encode` — modality 통계를 latent vector 에 패킹

```python
def encode(self, signal, available_modalities):
    feats = [float(len(available_modalities))]
    for k in available_modalities:
        mean, std, nan, slope = _safe_stats(_to_numpy(signal[k]))
        feats.extend([mean, std, slope])
    arr = np.zeros(self._latent_dim, dtype=np.float32)
    arr[:min(len(feats), self._latent_dim)] = feats[:self._latent_dim]
    return torch.from_numpy(arr)
```

"modality 개수 + 각 modality 의 (mean, std, slope)" 를 latent_dim 길이의 vector 로 만든다. 나머지는 0 padding. **결정적** — 같은 signal 에는 항상 같은 vector.

### `predict_hypotension` — MAP 와 slope 를 가중 결합

이 한 method 가 어떻게 짜였는지가 mock 전체의 패턴을 보여준다.

```python
def predict_hypotension(self, signal, horizon_min, available_modalities):
    found = _find_first(signal, self._ABP_ALIASES)
    if found is None:
        return HypotensionResult(risk=0.4, uncertainty=0.7, ...)  # ABP 없을 때 fallback

    key, arr = found
    mean, std, nan_ratio, slope_step = _safe_stats(arr)

    if std < QUALITY_FLATLINE_STD_EPS or nan_ratio > 0.5:
        return HypotensionResult(risk=0.4, uncertainty=0.8, ...)  # 품질 낮을 때 fallback

    # MAP score: MAP_TARGET (75) 에서 0, MAP_RISK_FLOOR (55) 에서 1
    denom = MAP_TARGET - MAP_RISK_FLOOR
    map_score = self._clip01((MAP_TARGET - mean) / denom)

    # Slope score: 0 에서 0, SLOPE_RISK_FLOOR (-5/min) 에서 1
    slope_per_min = slope_step * self._sampling_rate_hz * 60.0
    slope_score = self._clip01(-slope_per_min / -SLOPE_RISK_FLOOR) if slope_per_min < 0 else 0.0

    risk = 0.4 * map_score + 0.6 * slope_score    # weighted combination
    risk = self._clip01(self._apply_noise("predict_hypotension", risk))

    uncertainty = self._clip01(0.2 + 0.3 * (1.0 - min(map_score + slope_score, 1.0)) + nan_ratio * 0.5)

    return HypotensionResult(risk=risk, uncertainty=uncertainty, horizon_min=horizon_min, meta={...})
```

이걸 시나리오 별로 보면 직관이 잡힌다.

| 시나리오 | map_score | slope_score | risk |
|---|---|---|---|
| MAP = 75, 평탄 | 0 | 0 | ≈ 0 |
| MAP = 55, 평탄 | 1 | 0 | 0.4 (40%) |
| MAP = 75, 5 mmHg/min 하락 | 0 | 1 | 0.6 (60%) |
| MAP = 55, 5 mmHg/min 하락 | 1 | 1 | 1.0 (saturate) |

가중치 0.4 / 0.6 은 임상 직관 (절대값 보다는 *trend* 가 더 중요) 을 반영한 것이고, 역시 `[CLINICIAN-REVIEW]`.

### `predict_cardiac_arrest` — flag 누적

```python
def predict_cardiac_arrest(self, signal, horizon_min, available_modalities):
    flags = []
    score = 0.0
    present = 0

    if hr_found:
        if hr_mean < ARREST_HR_LOW:     score += 0.5; flags.append("hr_low_...")
        elif hr_mean > ARREST_HR_HIGH:  score += 0.5; flags.append("hr_high_...")
        present += 1

    if abp_found:
        if abp_mean < ARREST_MAP_LOW:   score += 0.5; flags.append("map_low_...")
        present += 1

    if present == 0:
        return ArrestResult(risk=0.05, uncertainty=0.8, ...)  # rare event 라서 baseline 낮음

    risk_raw = min(1.0, score)  # 0 (flag 없음), 0.5 (1개), 1 (2개 이상)
    risk = 0.02 + 0.6 * risk_raw   # baseline 0.02 + 강도

    return ArrestResult(risk=risk, ...)
```

flag 가 하나도 없으면 risk ≈ 0.02 (baseline), 두 개 모두 켜지면 ≈ 0.62.

### 나머지 5개의 룰 요약

| Method | Rule |
|--------|------|
| `assess_signal_quality` | NaN > 10% → 0.3, std < 1e-3 (flatline) → 0.2, 정상 → 0.95 |
| `cross_modal_consistency` | quality 필터링된 window 에서 `\|Pearson r\|` |
| `temporal_trend` | per-min slope + label (`\|slope\| < 1` → stable) |
| `forecast_signal` | 선형 외삽 + `residual_std × √i` uncertainty |
| `anomaly_score` | 꼬리 10% 의 worst `\|z\|` 를 6으로 나눈 값 |

자세한 코드는 `vitalagent/fm/mock_rule_based.py` 의 module body 직접 참조.

## Over-fit 방지를 위한 noise 주입

Tier 2 출력은 결정적이다. 같은 신호에 항상 같은 risk. 이게 agent 가 *우리 mock 의 매끈한 출력* 에만 익숙해지는 risk 를 만든다.

그래서 ±n% 의 jitter 를 주입할 수 있게 해두었다.

```python
def _apply_noise(self, method, value):
    pct = self._noise_per_method.get(method, self._noise_pct)
    if pct <= 0:
        return value
    delta = float(self._noise_rng.uniform(-pct, pct)) * value
    return value + delta
```

```yaml
# configs/fm/mock_rule_based.yaml
fm:
  config:
    noise_pct: 0.2    # ±20%
    noise_seed: 42
```

Real FM 의 출력과 우리 mock 출력이 정확히 같지 않게 흩뿌리는 효과. agent 가 mock 의 *정확한 숫자* 에 의존하지 않도록.

## Private helper 들

```python
def _to_numpy(t):
    """tensor 든 array 든 1-D float numpy 로 변환."""

def _find_first(signal, candidate_keys):
    """signal 에 있는 첫 후보 key 의 (name, arr) 를 반환."""

def _safe_stats(arr):
    """(mean, std, nan_ratio, slope_per_step) 을 NaN-safe 하게 계산."""
```

자세한 구현은 module 상단.

## Test

`tests/test_fm_mock_rule_based.py` 에 31개 test.

| 그룹 | 개수 | 검증 |
|------|------|------|
| encode | 2 | shape + signal 따라 변화 |
| predict_hypotension | 4 | high risk / low risk / ABP 없을 때 fallback / flatline 때 fallback |
| predict_cardiac_arrest | 3 | baseline 낮음 / flag 2개 → high / HR·ABP 없을 때 fallback |
| assess_signal_quality | 4 | clean / flatline / NaN / 부재 |
| cross_modal_consistency | 4 | 완벽 상관 / 역상관 / 누락 / flatline |
| temporal_trend | 3 | 상승 / 하강 / 안정 |
| forecast_signal | 3 | 길이 / uncertainty 증가 / 선형성 |
| anomaly_score | 3 | 정상 / spike / flatline |
| Noise injection | 3 | variance / 결정성 / per-method override |
| Smoke | 2 | 8 method 모두 synthetic case + meta marker |

## 100 case e2e — Tier 2 가 실제로 driving

`tests/integration/test_e2e_100cases_tier2.py` 가 100 개의 synthetic case (MAP 55–95 sweep) 를 끝까지 돌린다.

- 100/100 case 에서 deep brief 발화
- p95 per-tick latency: 4.8 ms
- Trigger 분포: hypotension 66 회, cross-modal-inconsistency 234 회

자세한 trigger 의미는 [[20_아키텍처/Trigger_7_Rules]].

## 다음 노트

- [[02_mock_stub]] — Tier 1 (random) 과의 비교
- [[01_fm_layer]] — Protocol + factory 추상
- [[20_아키텍처/Mock_FM_3_Tier_전략]] — 왜 Tier 2 가 default 인가
