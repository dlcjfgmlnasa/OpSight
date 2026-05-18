# 03. Mock Rule-based — `opsight/fm/mock_rule_based.py`

> Tier 2. 신호 통계 기반 *plausible* 출력. Agent reasoning 검증용. 현재 default tier.

## ⚠️ HARD CAVEAT

Threshold 는 휴리스틱, 임상 결정 규칙 아님. 모든 threshold 에 `[CLINICIAN-REVIEW]`. 결과 사용 시 `meta["mock_tier"] == "rule_based"` marker 확인.

## 클래스 구조

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

### Modality alias

호출자 signal dict 의 key 가 다양:
- Synthetic test: `"ABP"`, `"ECG_II"`, `"PPG"`
- 실 VitalDB: `"SNUADC/ART"`, `"SNUADC/ECG_II"`, `"SNUADC/PLETH"`

`_ABP_ALIASES` 등 tuple 로 둘 다 인식. `_find_first(signal, candidate_keys)` 가 첫 매칭 key 반환.

자세한 track 명은 `docs/findings/pre_phase3_findings.md §5`.

## Threshold 상수 (module-level)

```python
MAP_TARGET: float = 75.0          # MAP at which risk approaches 0
MAP_RISK_FLOOR: float = 55.0      # MAP at/below which map_score saturates
SLOPE_RISK_FLOOR: float = -5.0    # mmHg/min at which slope_score saturates

ARREST_HR_LOW: float = 40.0
ARREST_HR_HIGH: float = 180.0
ARREST_MAP_LOW: float = 50.0

QUALITY_NAN_CUTOFF: float = 0.10
QUALITY_FLATLINE_STD_EPS: float = 1e-3
# ...
```

모두 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`.

## 8 method 핵심 rule

### `encode` — feature vector

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

"modality 개수 + modality 별 (mean, std, slope)" 패킹. 결정적.

### `predict_hypotension` — MAP + slope 결합

```python
def predict_hypotension(self, signal, horizon_min, available_modalities):
    found = _find_first(signal, self._ABP_ALIASES)
    if found is None:
        return HypotensionResult(risk=0.4, uncertainty=0.7, ...)  # fallback

    key, arr = found
    mean, std, nan_ratio, slope_step = _safe_stats(arr)

    if std < QUALITY_FLATLINE_STD_EPS or nan_ratio > 0.5:
        return HypotensionResult(risk=0.4, uncertainty=0.8, ...)  # low quality fallback

    # MAP score: 0 at MAP_TARGET (=75), 1 at MAP_RISK_FLOOR (=55)
    denom = MAP_TARGET - MAP_RISK_FLOOR
    map_score = self._clip01((MAP_TARGET - mean) / denom)

    # Slope score: 0 at slope=0, 1 at SLOPE_RISK_FLOOR (-5/min)
    slope_per_min = slope_step * self._sampling_rate_hz * 60.0
    slope_score = self._clip01(-slope_per_min / -SLOPE_RISK_FLOOR) if slope_per_min < 0 else 0.0

    risk = 0.4 * map_score + 0.6 * slope_score    # weighted
    risk = self._clip01(self._apply_noise("predict_hypotension", risk))

    uncertainty = self._clip01(0.2 + 0.3 * (1.0 - min(map_score + slope_score, 1.0)) + nan_ratio * 0.5)

    return HypotensionResult(risk=risk, uncertainty=uncertainty, horizon_min=horizon_min, meta={...})
```

시나리오:
- MAP=75 + 평탄 → risk ≈ 0
- MAP=55 + 평탄 → risk = 0.4
- MAP=75 + 5 mmHg/min ↓ → risk = 0.6
- MAP=55 + 5 mmHg/min ↓ → risk = 1.0 saturate

### `predict_cardiac_arrest` — flag composite

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
        return ArrestResult(risk=0.05, uncertainty=0.8, ...)  # rare event fallback

    risk_raw = min(1.0, score)  # 0 (no flags), 0.5 (1 flag), 1 (≥2)
    risk = 0.02 + 0.6 * risk_raw

    return ArrestResult(risk=risk, ...)
```

→ flag 없음 → risk ≈ 0.02, 두 flag → ≈ 0.62.

### 나머지 5 rule

| Method | Rule |
|--------|------|
| `assess_signal_quality` | NaN > 10% → 0.3, std < 1e-3 → 0.2, else 0.95 |
| `cross_modal_consistency` | `\|Pearson r\|` on quality-filtered windows |
| `temporal_trend` | per-min slope + label (`\|slope\| < 1` → stable) |
| `forecast_signal` | linear extrapolation + `residual_std × √i` uncertainty |
| `anomaly_score` | tail 10% 의 worst `\|z\|` / 6 |

## Noise injection — over-fit 방지

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

Real FM 과 출력이 정확히 일치하지 않게 하여 agent 의 mock-overfit 방지.

ADR-011 risk #1 mitigation: [[20_아키텍처/Mock_FM_3_Tier_전략]].

## Private helpers

```python
def _to_numpy(t):
    """tensor / array → 1-D float numpy."""

def _find_first(signal, candidate_keys):
    """signal 에 있는 첫 후보 key 의 (name, arr) 반환."""

def _safe_stats(arr):
    """(mean, std, nan_ratio, slope_per_step) 반환. NaN-safe."""
```

## Tests

`tests/test_fm_mock_rule_based.py`: **31 test**.

| 그룹 | 개수 |
|------|------|
| encode | 2 |
| predict_hypotension | 4 (high / low / no ABP / flatline) |
| predict_cardiac_arrest | 3 |
| assess_signal_quality | 4 |
| cross_modal_consistency | 4 |
| temporal_trend | 3 (rising / falling / stable) |
| forecast_signal | 3 |
| anomaly_score | 3 |
| Noise injection | 3 |
| Smoke | 2 |

## 100-case e2e

`tests/integration/test_e2e_100cases_tier2.py`. 100 case (MAP 55–95 sweep):
- 100/100 deep brief 발화
- p95 per-tick 4.8 ms
- Trigger 분포: hypotension 66 / cross-modal-inconsistency 234

[[20_아키텍처/Trigger_7_Rules]] 참조.

## 다음 노트

- [[02_mock_stub]] — Tier 1 비교
- [[01_fm_layer]] — Protocol + factory
- [[20_아키텍처/Mock_FM_3_Tier_전략]] — 왜 Tier 2 가 default
