# FM Interface Guide (`BiosignalFMInterface` & Result Types)

> Foundation Model 백엔드의 contract 문서. ADR-011 (`docs/decisions/ADR-011-mock-fm-strategy.md`)이 governance.
> 모든 FM 구현체 (Tier 1 stub, Tier 2 rule-based, Tier 3 light ML, real FM)는 본 가이드를 따라야 한다.
>
> 마지막 갱신: 2026-05-16 (Result Types 섹션 작성 — sprint Step 1 A1).

---

## 0. 본 가이드 구성 (Sections)

| § | 내용 | 작성 시점 |
|---|------|-----------|
| 1 | Result Types — 7개 dataclass field semantics + 사용 규약 | ✅ A1 완료 |
| 2 | `BiosignalFMInterface` Protocol — 8개 method signature | ✅ B1 완료 |
| 3 | Factory + config schema (`create_fm`, `configs/fm/*.yaml`) | ✅ B3 + B4 완료 |
| 4 | Compliance test 작성 방법 | ✅ B2 완료 |
| 5 | Graceful degradation (`make_fallback`) | ✅ B5 완료 |
| 6 | 새 FM tier 추가 절차 | ✅ B6 완료 |
| 7 | Real-FM 마이그레이션 protocol | ⏳ Stage 2 진입 시 보강 |

본 문서는 sprint 진행과 함께 점진적으로 채워진다. **§1–§6은 Stage 1 Mock FM Foundation sprint 결과로 완성됨**.

---

## 1. Result Types (`vitalagent/fm/result_types.py`)

### 1.1 공통 규약 (All 7 dataclasses)

모든 Result는 다음 속성을 갖는다.

- `@dataclass(frozen=True)` — 생성 후 field 재할당 불가 (`FrozenInstanceError`).
- 모든 field는 **JSON-serializable**: `dataclasses.asdict(r) → json.dumps(...)`가 성공한다.
- 모든 Result는 `meta: dict[str, Any]` field를 보유 (default = `{}`, instance별 독립).
- `meta`는 **free-form** — 구현체별 context (예: 사용한 threshold, source channel, fit 통계)를 보관한다. 소비자 (consumer)는 특정 key의 존재를 가정하지 않는다.
- `encode()`의 출력은 raw `torch.Tensor`이며 Result로 wrap하지 않는다 (ADR-011 결정).

### 1.2 7 dataclass field semantics

#### `HypotensionResult` — tool 1 `predict_hypotension`

| Field | Type | Range | 의미 |
|-------|------|-------|------|
| `risk` | `float` | `[0, 1]` | 저혈압 (hypotension; `MAP < 65 mmHg` ≥ 1 min, brief §5) 발생 확률 |
| `uncertainty` | `float` | `[0, 1]` | 모델 자체 불확실성. 높을수록 신뢰 낮음 |
| `horizon_min` | `int` | 5 or 15 | 예측 horizon (분) |
| `meta` | `dict[str, Any]` | free-form | 구현 context |

> ⚠️ `risk`는 **확률 proxy**다. 임상 개입 threshold가 아니다. 임상 결정은 임상의 (이형철 교수님 그룹) 영역. `[CLINICIAN-REVIEW]`

#### `ArrestResult` — tool 2 `predict_cardiac_arrest`

`HypotensionResult`와 동일한 field. `risk`는 cardiac arrest 발생 확률.

#### `QualityResult` — tool 3 `assess_signal_quality`

| Field | Type | Range | 의미 |
|-------|------|-------|------|
| `score` | `float` | `[0, 1]` | 신호 품질. 높을수록 좋음 |
| `reason` | `str \| None` | — | 낮은 score에 대한 짧은 설명 (예: `"high NaN ratio"`, `"flatline detected"`). 품질이 좋으면 `None` |
| `meta` | `dict[str, Any]` | free-form | 구현 context (예: NaN ratio, std, sample count) |

#### `ConsistencyResult` — tool 4 `cross_modal_consistency`

| Field | Type | Range | 의미 |
|-------|------|-------|------|
| `score` | `float` | `[0, 1]` | Modality pair 간 일관성 (전형: 품질 필터된 window의 \|Pearson r\|) |
| `reason` | `str \| None` | — | 선택적 설명 (예: `"low quality in one channel masked half the window"`) |
| `meta` | `dict[str, Any]` | free-form | window 길이, n_valid samples 등 |

#### `TrendResult` — tool 5 `temporal_trend_analysis`

| Field | Type | Range | 의미 |
|-------|------|-------|------|
| `slope` | `float` | (signed) | 분당 변화량 (예: MAP `mmHg/min`). 음수 = falling. |
| `magnitude` | `float` | ≥ 0 | `\|slope\|` 또는 std-normalized magnitude |
| `label` | `Literal["rising", "falling", "stable"]` | — | 이산 trend 라벨 |
| `meta` | `dict[str, Any]` | free-form | window 길이, fit r² 등 |

> ⚠️ `label`은 `Literal[...]` 타입이지만 runtime에 강제되지 않는다. mypy / pyright 정적 검증이 강제 메커니즘.

#### `ForecastResult` — tool 6 `forecast_signal`

| Field | Type | Shape | 의미 |
|-------|------|-------|------|
| `forecast` | `list[float]` | `T` | 예측 trajectory. 길이는 `horizon_min × meta["sampling_rate_hz"] / 60` 같은 식 (구현체별 결정) |
| `uncertainty` | `list[float]` | `T` | per-step 불확실성. `forecast`와 동일 길이 |
| `horizon_min` | `int` | — | forecast horizon (분) |
| `meta` | `dict[str, Any]` | free-form | 관례적으로 `"sampling_rate_hz"`, `"modality"`, `"model_name"` 등을 포함. **소비자는 존재를 가정하지 않는다.** |

> `np.ndarray` 대신 `list[float]`를 사용하는 이유: JSON-serializability 보존. 성능 critical 경로는 call site에서 ndarray로 변환한다.

#### `AnomalyResult` — tool 7 `anomaly_score`

| Field | Type | Range | 의미 |
|-------|------|-------|------|
| `score` | `float` | `[0, 1]` | anomaly score. 높을수록 baseline에서 더 벗어남. 정확한 정의는 구현체 의존. |
| `meta` | `dict[str, Any]` | free-form | z-score, baseline window 길이 등 |

### 1.3 변경 governance

Result type field의 추가 / 제거 / 의미 변경은 다음 절차를 거친다.

1. ADR-011을 amend (Decision Log entry 추가)
2. `vitalagent/fm/result_types.py` 갱신
3. 본 §1 갱신
4. 모든 FM 구현체 (`mock_stub`, `mock_rule_based`, `mock_light_ml`, real adapter) 동시 갱신
5. Protocol compliance test 갱신

위 5 step을 동일 commit으로 묶는다 (drift 방지).

### 1.4 사용 예 (mock — 구현체별 상세는 §3에 추가 예정)

```python
from vitalagent.fm.result_types import HypotensionResult

# Construct
r = HypotensionResult(
    risk=0.42,
    uncertainty=0.18,
    horizon_min=5,
    meta={"source_modality": "ABP", "rule_threshold": 70},
)

# Frozen
# r.risk = 0.9   # → FrozenInstanceError

# JSON-serialize
import json
from dataclasses import asdict
json.dumps(asdict(r))
# → '{"risk": 0.42, "uncertainty": 0.18, "horizon_min": 5, "meta": {...}}'
```

---

## 2. `BiosignalFMInterface` Protocol

### 2.1 정의 위치 (Location)

`vitalagent/fm/interface.py`. `@runtime_checkable typing.Protocol`. 모든 FM tier (Tier 1 stub / Tier 2 rule-based / Tier 3 light ML / real FM adapter)가 본 Protocol을 구현해야 한다.

### 2.2 8 Method Signature

| # | Method | Signature | Return |
|---|--------|-----------|--------|
| 1 | `encode` | `(signal: dict[str, torch.Tensor], available_modalities: list[str])` | `torch.Tensor` (raw, **not wrapped** in Result — ADR-011 결정) |
| 2 | `predict_hypotension` | `(signal, horizon_min: int, available_modalities)` | `HypotensionResult` |
| 3 | `predict_cardiac_arrest` | `(signal, horizon_min: int, available_modalities)` | `ArrestResult` |
| 4 | `assess_signal_quality` | `(signal, modality: str)` | `QualityResult` |
| 5 | `cross_modal_consistency` | `(signal, modality_pair: tuple[str, str])` | `ConsistencyResult` |
| 6 | `temporal_trend` | `(signal, modality: str, window_min: int)` | `TrendResult` |
| 7 | `forecast_signal` | `(signal, modality: str, horizon_min: int)` | `ForecastResult` |
| 8 | `anomaly_score` | `(signal, modality: str)` | `AnomalyResult` |

`signal`은 항상 `dict[str, torch.Tensor]` — key는 modality 이름 (`"ECG"`, `"ABP"`, `"PPG"` 등), value는 해당 modality의 raw tensor.

### 2.3 `torch` runtime 의존 처리 (Risk mitigation)

Sprint plan §Risk Register에서 식별된 "Protocol `torch.Tensor` 의존" risk는 다음으로 해소된다.

- `from __future__ import annotations` (PEP 563): 모든 annotation을 module-load 시점 string으로 lazy 평가.
- `if TYPE_CHECKING: import torch`: runtime 시 torch import 안 함. 정적 type-checker (mypy / pyright)에서만 사용.
- 결과: 본 module은 `torch` 미설치 환경에서도 정상 import + Protocol compliance check 가능. concrete FM 구현체는 자체적으로 `import torch`.
- 알려진 한계: `typing.get_type_hints(...)` 호출은 runtime에 실제 `torch` import를 시도 — 미설치 환경에선 `NameError`. `runtime_checkable` 자체 (method 이름 비교)는 영향 없음.

### 2.4 사용 예 (구현체와 무관)

```python
from vitalagent.fm.interface import BiosignalFMInterface

def consume_fm(fm: BiosignalFMInterface) -> None:
    """Protocol에만 의존. concrete class를 import하지 않는다.
    Depends only on Protocol; no concrete-class import.
    """
    # signal is a dict produced by the signal-ingest layer
    # signal은 signal-ingest layer가 생성한 dict
    result = fm.predict_hypotension(
        signal={"ABP": ..., "ECG": ...},
        horizon_min=5,
        available_modalities=["ABP", "ECG"],
    )
    risk = result.risk  # float in [0, 1]
```

### 2.5 변경 governance

Protocol의 method 추가 / 제거 / signature 변경은 다음 절차를 거친다.

1. ADR-011을 amend (Decision Log entry 추가)
2. `vitalagent/fm/interface.py` 갱신
3. 본 §2 갱신
4. 모든 FM 구현체 동시 갱신 (Tier 1–3 + real adapter)
5. Protocol compliance test 갱신 (`tests/test_fm_protocol_compliance.py`)

위 5 step을 동일 commit으로 묶는다 (drift 방지).

### 2.6 verification 산출물 (B1 sprint Step 2 결과)

- ✅ Import 정상 (torch 미설치 환경 OK)
- ✅ 8 method 정확히 ADR-011 일치
- ✅ `runtime_checkable` positive / negative 모두 작동
- ✅ Raw annotation (string-lazy) 정상

---

## 3. Factory & config schema

### 3.1 진입점 (Entry point)

`vitalagent/fm/factory.py`의 `create_fm(config: dict) -> BiosignalFMInterface`. Agent / tool layer는 본 함수만으로 FM backend를 획득한다. 구현체 교체는 **config 변경**이며 코드 변경이 아니다 (ADR-011 swap mechanism).

### 3.2 Config 스키마

```yaml
fm:
  implementation: mock_stub | mock_rule_based | mock_light_ml | real
  config:                    # optional, kwargs for the implementation
    seed: 42
    # ... tier-specific
```

- `implementation`: 4개 허용 값 중 하나. 그 외엔 `ValueError` (위반 문자열 포함).
- `config`: 선택. 누락 시 빈 dict로 처리. 구현체 생성자의 `**kwargs`로 전달.

### 3.3 5개 yaml template (`configs/fm/`)

| 파일 | 상태 | 채울 plan |
|------|------|-----------|
| `mock_stub.yaml` | **Active** | — (plan_1.1.5에서 완성) |
| `mock_rule_based.yaml` | TEMPLATE | `plan_1.6.5` |
| `mock_light_ml.yaml` | TEMPLATE, OPTIONAL | `plan_1.7.5` |
| `real.yaml` | TEMPLATE | Stage 2 |
| `default.yaml` | **Active pointer** — 현재 `mock_stub` 가리킴. lifecycle 주석 명시 |

`default.yaml`의 lifecycle:
```
Week 1–3 (now)        : mock_stub
Week 4–8              : mock_rule_based
Optional (time-perm.) : mock_light_ml
Stage 2 (Month 3+)    : real
```

### 3.4 에러 정책

| 상황 | 동작 |
|------|------|
| `config["fm"]` 객체 없음 | `ValueError("config must contain an 'fm' object ...")` |
| 알 수 없는 `implementation` 값 | `ValueError("Unknown FM implementation: ...")` + offending string |
| Tier 이름은 valid하나 module 부재 | `NotImplementedError` + plan / stage reference (`"plan_1.6.5"`, `"Stage 2"` 등) |

### 3.5 Lazy import 패턴

`create_fm`은 요청된 tier만 import한다. `try / except ImportError → raise NotImplementedError from exc`. import-time crash 회피 + 미구현 tier 호출 시 명확한 안내.

### 3.6 사용 예

```python
import yaml
from vitalagent.fm.factory import create_fm

with open("configs/fm/default.yaml") as f:
    config = yaml.safe_load(f)
fm = create_fm(config)
# fm satisfies BiosignalFMInterface — use like any other FM
```

---

## 4. Compliance test

### 4.1 위치 (Location)

`tests/test_fm_protocol_compliance.py`. 새 FM tier가 도착할 때마다 본 파일의 `FM_IMPLEMENTATIONS` registry에 한 줄 추가만으로 3개 parametrized test가 자동 실행된다.

### 4.2 3-Layer compliance

| Layer | Test | 강도 |
|-------|------|------|
| 1 | `test_runtime_checkable_protocol` | `isinstance(fm, BiosignalFMInterface)` — method 이름만 |
| 2 | `test_all_methods_present_and_callable` | 8 method 존재 + callable |
| 3 | `test_method_signatures_match_protocol` | **Stricter** — `inspect.signature`로 parameter 이름 정확 일치 검증 |

추가: `test_negative_sanity_broken_implementation_rejected` — incomplete impl이 거부되는지 확인 (harness 자체가 enforcing함을 검증).

### 4.3 Registry 패턴

```python
FM_IMPLEMENTATIONS: list[tuple[str, Callable[[], object]]] = [
    ("StubBiosignalFM", lambda: StubBiosignalFM(seed=42)),
    # TODO: ("RuleBasedBiosignalFM", lambda: RuleBasedBiosignalFM(...))  # after plan_1.6.5
    # TODO: ("LightMLBiosignalFM",   lambda: LightMLBiosignalFM(...))    # after plan_1.7.5
    # TODO: ("RealBiosignalFM",      lambda: RealBiosignalFM(...))       # when real FM lands
]
```

### 4.4 실행

```bash
.venv/Scripts/python.exe -m pytest tests/test_fm_protocol_compliance.py -v
```

---

## 5. Graceful degradation

### 5.1 진입점

`vitalagent/fm/factory.py`의 `make_fallback(primary, fallback, latency_budget_sec=None, alert=None) -> BiosignalFMInterface`. 반환값은 Protocol을 만족하는 wrapper. agent / tool은 일반 FM처럼 사용.

### 5.2 2단계 정책

| 트리거 | 동작 | Alert |
|--------|------|-------|
| Primary 예외 | `fallback`으로 위임 후 결과 반환. 예외 흡수. | `("primary_failed", method, exc, {})` |
| Primary latency budget 초과 | **primary 결과 그대로 반환** (현재 호출 강제 종료 X — sync sleep interrupt 불가) | `("latency_exceeded", method, None, {elapsed_sec, budget_sec})` |

> Stage 2에서 필요 시 circuit-breaker 패턴 추가 가능. 본 PoC 단계엔 overkill.

### 5.3 `AlertCallback` 시그니처

```python
AlertCallback = Callable[[str, str, BaseException | None, dict[str, Any]], None]
#                       (reason, method_name, exc, extra) -> None
```

기본 alert: `vitalagent.fm.factory` logger의 WARNING 항목. 사용자 코드에서 custom callback 주입 가능 (예: Slack / Sentry 알림).

### 5.4 사용 예 (Stage 2 — real FM with safety net)

```python
from vitalagent.fm.factory import create_fm, make_fallback

real_fm    = create_fm({"fm": {"implementation": "real"}})
rule_based = create_fm({"fm": {"implementation": "mock_rule_based"}})

fm = make_fallback(real_fm, rule_based, latency_budget_sec=0.5)
# fm은 BiosignalFMInterface-compliant — 일반 FM처럼 사용
```

ADR-011 §"Real-FM migration protocol" step 5 reference.

---

## 6. 새 FM tier 추가 절차 (Adding a new FM tier)

새 tier (예: Tier 2 / Tier 3 / 또는 별도 backend)를 시스템에 추가할 때 다음 6 step을 따른다. 모든 step은 **하나의 commit**에 묶는다 (drift 방지).

### Step 1 — 명세 / 의사결정

ADR-011을 amend하거나 새 ADR (예: ADR-015)을 추가한다. 변경되는 Protocol 부분이 있다면 본 가이드 §2도 같은 commit에서 갱신한다.

### Step 2 — 구현체 작성

`vitalagent/fm/<tier_name>.py`에 class 작성. `BiosignalFMInterface`의 8 method 모두 구현. concrete class는 `BiosignalFMInterface`를 상속하지 않아도 됨 (`runtime_checkable` Protocol — structural). 단, **`BiosignalFMInterface`를 `Protocol`로만 import**하고 concrete-class import는 금지.

### Step 3 — Factory 등록

`vitalagent/fm/factory.py`의 `_KNOWN_IMPLEMENTATIONS`에 이름 추가. `create_fm` switch에 lazy-import branch 추가 (`try / except ImportError → NotImplementedError` 패턴 동일).

### Step 4 — Config template 작성

`configs/fm/<tier_name>.yaml` 생성. 헤더 commentary block (Owner / Spec / Status / Purpose / Tunable fields)을 다른 yaml과 일관되게 작성. 초기엔 `TEMPLATE` status로 둬도 OK.

### Step 5 — Compliance test 등록

`tests/test_fm_protocol_compliance.py`의 `FM_IMPLEMENTATIONS` list에 한 줄 추가:

```python
("MyNewFM", lambda: MyNewFM(seed=42)),
```

3개 parametrized test가 자동 실행됨. 통과 확인.

### Step 6 — Output 의미 검증 + smoke test

해당 tier가 의미 있는 출력을 내는 tier (rule-based / ML / real)라면 `tests/test_fm_<tier>.py`에 의미 검증 추가. Stub처럼 random인 경우 smoke만으로 충분.

### Step 7 (real adapter 한정) — Mock-vs-Real gap 분석

ADR-011 §"Real-FM migration protocol" step 2: 100 case에 대해 `mock_rule_based` vs `real` 결과 delta 측정. method별 gap report 작성 → `findings/real_fm_gap_<date>.md`.

### Step 8 (real adapter 한정) — `default.yaml` 전환

검증 완료 후 `configs/fm/default.yaml`의 `implementation: real`로 전환. `make_fallback(real, mock_rule_based)` 적용 권장.

---

## 7. Real-FM 마이그레이션 protocol

⏳ Stage 2 진입 시점에 ADR-011 §"Real-FM migration protocol"을 기반으로 보강된다.

---

## References

- `docs/decisions/ADR-011-mock-fm-strategy.md` — strategy & governance
- `docs/project_brief.md §7.1` — FM tool 1–7 signatures
- `docs/project_brief.md §3.5` — Mock FM strategy 개요
- `vitalagent/fm/result_types.py` — 본 §1의 코드 구현
