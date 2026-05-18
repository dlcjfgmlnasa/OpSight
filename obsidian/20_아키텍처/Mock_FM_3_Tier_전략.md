# Mock FM 3-Tier 전략

> Real FM 은 2개월 학습이 필요. 그 사이 agent 를 멈출 수 없음 → mock 으로 시작 후 점진적 교체.

## 문제 — FM 이 2개월간 없다

OpSight backend = **Biosignal Foundation Model (BFM)**. 별도 프로젝트에서 K-MIMIC ICU pretraining 중. Stage 1 (Month 1–2) 전체를 학습에 소비.

"기다리자" 면:
- 2개월 동안 agent 시스템 못 만듦
- Stage 2 (Month 3–4) 에 통합 몰림 → risk 증폭
- Mock vs real 차이 발견 시간 X

→ **mock 으로 먼저, real 도착 시 swap.** 표준 software engineering 패턴. mock 을 *너무 단순* 하게 만들면 agent reasoning 검증 X, *너무 복잡* 하면 mock 만 만드는 데 시간 다 감 → **3 단계**.

## 3 단계

| Tier | 이름 | 목적 | 출력 품질 |
|------|------|------|-----------|
| **Tier 1** | Stub | Interface 안착 + latency 시뮬레이션 | random within shape |
| **Tier 2** | Rule-based | Agent reasoning 검증 | plausible (signal 통계 기반) |
| **Tier 3** | Light ML | Real-FM proxy | learned (baseline 모델 wrap) |

### Tier 1 — Stub (Sprint 1 완료)

`opsight/fm/mock_stub.py`. `np.random.uniform` 등으로 valid range 안 random. Agent 시스템이 *문법적으로* 작동하는지만 검증.

⚠️ Random 출력 → reasoning 검증 / 임상 결정 / real-FM benchmark 에 절대 X.

[[30_코드_워크스루/02_mock_stub]] 참조.

### Tier 2 — Rule-based (현재 default, Sprint 3 완료)

`opsight/fm/mock_rule_based.py`. 실제 신호 통계 (MAP / HR / NaN ratio / Pearson) + 임상 휴리스틱 8 rule → plausible 출력.

```python
# 예: predict_hypotension
abp = extract(signal, "ABP")
map_proxy = np.nanmean(abp)
slope = np.polyfit(...)
map_score   = (75 - map_proxy) / 20      # MAP < 75 → 위험
slope_score = -slope_per_min / 5          # 떨어지면 위험
risk = 0.4 * map_score + 0.6 * slope_score
```

핵심: **반응성**. 신호 바뀌면 출력 바뀜 → agent reasoning 일관성 검증 가능.

⚠️ 임상 결정 X. 모든 threshold `[CLINICIAN-REVIEW]`.

[[30_코드_워크스루/03_mock_rule_based]] 참조.

### Tier 3 — Light ML (Sprint 5 완료)

`opsight/fm/mock_light_ml.py`. Stage 1 baseline 4종 (Logistic Regression / Random Forest / MLP / 간단 LSTM) 을 FM interface 로 wrap. Rule-based 보다 *학습된* 동작.

목적: real FM 도착 전 "학습된 모델은 어떻게 다른가" 경험. Rule-based 출력이 너무 매끈해서 agent brief 가 mock 매끈함에 over-fit 되는 risk 방지.

### Real FM (Stage 2)

`opsight/fm/real.py` *(예정)*. K-MIMIC pretrained BFM checkpoint 를 PyTorch load + inference.

## 4 tier 모두 같은 Interface

```
BiosignalFMInterface (Protocol)
       ▲
       │
   ┌───┴───┬─────────┬─────────┐
   │       │         │         │
 Stub  RuleBased  LightML    Real
 (T1)   (T2)      (T3)      (Stage 2)
```

모두 같은 8 method. Agent layer 는 `BiosignalFMInterface` 만 안다. [[10_기초/Python_Protocol_과_runtime_checkable]] 참조.

## Swap — config 한 줄

```yaml
# configs/fm/default.yaml

fm:
  implementation: mock_rule_based     # ← 이 줄만 바꾸면 swap
  config:
    seed: 42
    noise_pct: 0.0
```

Factory 가 적절한 class import:

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

ADR-011 + [[30_코드_워크스루/01_fm_layer]] 참조.

## Lifecycle

```
Week 1–3              : mock_stub        (interface 안착)
Week 4–8 (← 현재)     : mock_rule_based  (agent reasoning 검증)
Sprint 5 추가         : mock_light_ml    (real-FM proxy)
Stage 2 (Month 3+)    : real             (ADR-011 migration 후)
```

## Real FM 마이그레이션 — ADR-011 §"Real-FM migration protocol"

1. Real FM 이 `BiosignalFMInterface` 만족 검증 (`isinstance` 통과)
2. 100 case 에서 `mock_rule_based` vs `real` 비교
3. Gap report — 어느 method 가 가장 다른가
4. `default.yaml` → `real` 로 전환
5. `mock_rule_based` 는 fallback 으로 유지

## Graceful degradation

```python
from opsight.fm.factory import create_fm, make_fallback

real_fm    = create_fm({"fm": {"implementation": "real"}})
rule_based = create_fm({"fm": {"implementation": "mock_rule_based"}})

fm = make_fallback(real_fm, rule_based, latency_budget_sec=0.5)
# real 이 raise / latency 초과 시 rule_based fallback + alert
```

[[30_코드_워크스루/01_fm_layer]] 참조.

## Noise injection — over-fit 방지

Tier 2 출력은 결정적. Agent reasoning 이 *우리 mock 의 매끈함* 에 over-fit 될 risk → ±n% jitter 옵션:

```yaml
# configs/fm/mock_rule_based.yaml
fm:
  config:
    noise_pct: 0.2          # ±20% jitter
    noise_seed: 42
```

Real FM 출력과 약간 다른 게 자연스러움 (over-fit 방지).

## 다음 노트

- [[21_Tool_Suite]] — FM 8 method × 7 FM tool 매핑
- [[30_코드_워크스루/01_fm_layer]] — interface + factory 워크스루
- [[30_코드_워크스루/02_mock_stub]] — Tier 1
- [[30_코드_워크스루/03_mock_rule_based]] — Tier 2
