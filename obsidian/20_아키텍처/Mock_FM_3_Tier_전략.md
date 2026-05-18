# Mock FM 3-Tier 전략 — FM 자리에 무엇을 끼우고 있는가

> 진짜 Foundation Model 은 약 2개월 동안 학습 중이다. 그 사이 agent 를 멈출 수 없으니 **자리에 임시로 끼울 무언가** 가 필요했다. 그 임시 무언가를 3단계로 진화시키며 쓰고 있다.

## 처음 문제 — FM 이 2개월간 없다

VitalAgent 의 backend 는 **Biosignal Foundation Model (BFM)** 이다. 이건 별도 프로젝트 (`C:/Projects/Biosignal-Foundation-Model`) 에서 K-MIMIC ICU 데이터로 pretraining 중이다. Stage 1 (Month 1–2) 의 거의 전부를 학습에 쓴다.

여기서 "real FM 이 도착할 때까지 기다리자" 라고 하면 두 가지 손해가 난다.

- 2개월 동안 agent 시스템 코드를 만들지 못한다.
- 모든 통합이 Stage 2 (Month 3–4) 에 몰린다. 그 때 mock 과 real 차이가 발견되면 시간이 부족하다.

표준 해법은 **mock 으로 먼저 만들고, real 이 도착하면 swap** 이다. 다만 mock 이 *너무 단순* 하면 agent 의 reasoning 을 검증할 수 없고, *너무 복잡* 하면 mock 만 만드는 데 시간이 다 가버린다. 그래서 우리는 mock 을 **3단계로 나눈다** — 각 단계가 노리는 검증이 다르다.

## 3 단계, 각각 무엇을 하나

### Tier 1 — Stub (코드 흐름만 확인하는 mock)

`vitalagent/fm/mock_stub.py`. `np.random.uniform` 같은 걸로 valid range 안의 random 값을 뱉는다. agent 시스템이 *문법적으로* 끊김 없이 돌아가는지만 확인할 때 쓴다.

⚠️ **출력은 random 이다.** Agent 의 reasoning 검증, 임상 결정, real-FM benchmark 에는 절대 쓰지 않는다.

코드 한 줄씩은 [[30_코드_워크스루/02_mock_stub]].

### Tier 2 — Rule-based (지금 실제로 쓰는 mock)

`vitalagent/fm/mock_rule_based.py`. 진짜 신호 통계 (MAP, HR, NaN ratio, Pearson 상관 등) 에 임상 휴리스틱 룰 8개를 적용해서 **그럴듯한 (plausible)** 출력을 만든다.

예를 들어 `predict_hypotension` 은 이런 식이다.

```python
abp = extract(signal, "ABP")
map_proxy = np.nanmean(abp)
slope = np.polyfit(...)
map_score   = (75 - map_proxy) / 20   # MAP 가 75 아래로 갈수록 위험
slope_score = -slope_per_min / 5      # 떨어지는 추세면 위험
risk = 0.4 * map_score + 0.6 * slope_score
```

여기서 중요한 건 **반응성** 이다. real 한 의미를 갖지는 않지만, 신호가 바뀌면 출력도 함께 바뀐다. 그래서 agent 의 reasoning 이 신호에 일관적으로 반응하는지 검증할 수 있다.

⚠️ 여전히 *임상 결정에는 쓰지 않는다*. 모든 threshold 는 `[CLINICIAN-REVIEW]` marker 가 붙어 있다.

코드는 [[30_코드_워크스루/03_mock_rule_based]].

### Tier 3 — Light ML (학습된 모델 wrap)

`vitalagent/fm/mock_light_ml.py`. 우리가 따로 만든 baseline 모델 4종 (Logistic Regression / Random Forest / MLP / 간단한 LSTM) 을 FM interface 로 감싸서 끼운다. Rule-based 보다 한 단계 더 *학습된* 동작을 한다.

이게 필요한 이유는 **real FM 도착 전에 "학습된 모델은 어떻게 다른가" 를 미리 경험** 하기 위함이다. Rule-based 가 출력을 너무 깔끔하게 내면, agent 의 brief 가 mock 의 매끈함에 over-fit 될 수 있다.

조건: baseline 모델이 먼저 완성되어 있어야 한다 (Sprint 4 에서 완료, Sprint 5 에서 Light ML wrap 완료).

### Real FM (Stage 2 에 도착)

`vitalagent/fm/real.py` *(예정)*. K-MIMIC pretrained BFM checkpoint 를 PyTorch 로 load 해서 inference 한다. 실제 5–13개 downstream task 를 호출한다.

## 4 단계 모두 같은 인터페이스를 만족

```
BiosignalFMInterface (Protocol)
       ▲
       │
   ┌───┴───┬─────────┬─────────┐
   │       │         │         │
 Stub  RuleBased  LightML    Real
 (T1)   (T2)      (T3)      (Stage 2)
```

모두 같은 8개 method (`encode`, `predict_hypotension`, ...) 를 구현한다. Agent 코드는 `BiosignalFMInterface` 라는 abstract type 만 안다. 어떤 concrete class 가 실제로 들어와 있는지는 모른다.

이런 식으로 만들면 **config 한 줄만 바꿔서** swap 할 수 있다. 자세한 mechanism 은 [[10_기초/Python_Protocol_과_runtime_checkable]].

## Swap 은 정말로 한 줄

```yaml
# configs/fm/default.yaml

fm:
  implementation: mock_rule_based     # ← 이 줄만 바꾸면 다른 tier 로 swap
  config:
    seed: 42
    noise_pct: 0.0
```

코드 변경 0. Factory 가 알아서 적절한 class 를 import 한다.

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
    # ... 그리고 real, mock_light_ml
```

이 디자인 결정의 정식 기록은 ADR-011, 코드 워크스루는 [[30_코드_워크스루/01_fm_layer]].

## 지금까지의 변천

```
Week 1–3              : mock_stub        (인터페이스 안착)
Week 4–8 (← 현재)     : mock_rule_based  (agent reasoning 검증)
Sprint 5 추가         : mock_light_ml    (학습된 모델 proxy)
Stage 2 (Month 3+)    : real             (ADR-011 의 migration protocol 후)
```

지금 default 는 `mock_rule_based` 다. 코드 변경 없이 다른 tier 로 갈 수 있다.

## Real FM 이 도착하면 어떻게 갈아끼우나

ADR-011 의 "Real-FM migration protocol" 에 명시된 5단계:

1. Real FM 이 `BiosignalFMInterface` 를 만족하는지 검증 (`isinstance` 통과)
2. 100 case 에서 `mock_rule_based` vs `real` 결과 비교
3. Gap report 작성 — 어느 method 출력이 가장 다른가
4. `configs/fm/default.yaml` 을 `real` 로 전환
5. `mock_rule_based` 는 fallback 으로 유지

자세한 건 ADR-011 + `vitalagent/fm/factory.py::make_fallback`.

## 만약 real 이 도중에 실패하면 — graceful degradation

Real FM 이 latency 초과 / 예외를 던질 때 자동으로 rule-based 로 떨어지는 mechanism 이 있다.

```python
from vitalagent.fm.factory import create_fm, make_fallback

real_fm    = create_fm({"fm": {"implementation": "real"}})
rule_based = create_fm({"fm": {"implementation": "mock_rule_based"}})

fm = make_fallback(real_fm, rule_based, latency_budget_sec=0.5)
# real 이 raise 하거나 latency 초과 시 rule_based 로 fallback + alert
```

코드: [[30_코드_워크스루/01_fm_layer]] 의 `make_fallback`.

## Over-fit 방지 — noise injection

Tier 2 출력은 결정적 (deterministic) 이다. 같은 신호엔 항상 같은 risk. 이게 agent reasoning 을 *우리 mock 에만 특화* 시키는 risk 가 있다 (real FM 이 정확히 같은 값을 내지는 않을 테니까).

그래서 ±n% jitter 를 주입할 수 있게 해두었다.

```yaml
# configs/fm/mock_rule_based.yaml
fm:
  implementation: mock_rule_based
  config:
    noise_pct: 0.2          # ±20% 흔들기
    noise_seed: 42
```

Real FM 도착 시 출력이 우리 mock 과 약간 다른 게 자연스러워야 하니, 이 noise 가 그 차이를 미리 시뮬레이션해주는 셈이다.

## 다음 노트

- [[21_Tool_Suite]] — FM 이 출력하는 8 method 가 21개 tool 중 7개에 어떻게 매핑되는가
- [[30_코드_워크스루/01_fm_layer]] — interface + factory + result types 코드 워크스루
- [[30_코드_워크스루/02_mock_stub]] — Tier 1 코드
- [[30_코드_워크스루/03_mock_rule_based]] — Tier 2 코드
- [[10_기초/Python_Protocol_과_runtime_checkable]] — swap 의 기술적 기반
