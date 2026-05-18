# ADR-011 — Mock Foundation Model Strategy

- **Status**: Accepted
- **Date**: 2026-05-16
- **Decision drivers**: project-planner (initial), signal-ingest-engineer (implementation owner), langgraph-engineer (interface owner)

---

## Context (배경)

Biosignal Foundation Model (BFM)은 별도 프로젝트 (`C:\Projects\Biosignal-Foundation-Model\`)에서 학습되며, 프로젝트 시작 시점으로부터 **약 2개월** 후 완료될 것으로 예상된다. 이는 **Stage 1 (Month 1–2) 전체 기간**과 일치한다.

OpSight system 개발이 FM 가용성에 막혀 멈춘다면, 핵심 agent 인프라 (LangGraph dual-mode, 16-tool registry, system prompt, dual-LLM orchestration, 시뮬레이션된 실시간 (simulated real-time) loop) 2개월이 유휴 상태가 된다. 이는 낭비일 뿐 아니라 risk 증폭 요인이다 — 통합이 Stage 2 단일 sprint로 압축되어 mock-vs-real 발견과 흡수 시간이 사라진다.

업계 표준 패턴은 **interface로 consumer와 producer를 분리하고**, 동일 interface를 구현한 mock에 대해 consumer를 개발한 뒤, producer가 준비되면 swap하는 것이다.

---

## Decision (결정)

Stage 1 동안 Biosignal Foundation Model에 대해 **3-tier mock strategy**를 채택한다. 모든 tier는 안정적인 **Interface Protocol**을 통해 게이팅되며, real FM 또한 도착 시 동일 Protocol을 만족해야 한다.

### 3 tiers

| Tier | Name | Purpose (목적) | Behavior (동작) | Latency | Owner deliverable |
|------|------|----------------|-----------------|---------|-------------------|
| 1 | **Stub Mock** | Interface 정의 + latency 시뮬레이션 | 유효 shape/range 내 random 출력 | configurable sleep | `opsight/fm/mock_stub.py` (plan_1.1.5) |
| 2 | **Rule-based Mock** | Realistic I/O로 agent reasoning 검증 | 신호 통계 기반 plausible 출력 (ABP trend, NaN-ratio 품질, correlation 기반 consistency 등) | real-FM 예상 latency와 일치 | `opsight/fm/mock_rule_based.py` (plan_1.6.5) |
| 3 | **Light ML Mock** *(optional)* | 학습된 모델로 real-FM proxy 제공 | Stage 1.4 baseline (Logistic / XGBoost / LSTM)을 Protocol 뒤에서 wrapping | real-baseline inference | `opsight/fm/mock_light_ml.py` (plan_1.7.5) |

**필수 (Mandatory)**: Tier 1 + Tier 2. **선택 (Optional)**: Tier 3 — baseline을 재사용하므로 추가 비용이 낮다. 시간 여유 시 수행한다.

### Interface Protocol

`opsight/fm/interface.py`에 정의되는 `runtime_checkable` `typing.Protocol`:

```python
from typing import Protocol, runtime_checkable
import torch

@runtime_checkable
class BiosignalFMInterface(Protocol):
    def encode(
        self,
        signal: dict[str, torch.Tensor],
        available_modalities: list[str],
    ) -> torch.Tensor: ...

    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult: ...

    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult: ...

    def assess_signal_quality(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> QualityResult: ...

    def cross_modal_consistency(
        self,
        signal: dict[str, torch.Tensor],
        modality_pair: tuple[str, str],
    ) -> ConsistencyResult: ...

    def temporal_trend(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        window_min: int,
    ) -> TrendResult: ...

    def forecast_signal(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        horizon_min: int,
    ) -> ForecastResult: ...

    def anomaly_score(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> AnomalyResult: ...
```

모든 Result dataclass (`HypotensionResult`, `ArrestResult`, `QualityResult`, `ConsistencyResult`, `TrendResult`, `ForecastResult`, `AnomalyResult`)는 `opsight/fm/interface.py` (또는 co-located `opsight/fm/result_types.py`)에 정의된다.

모든 mock과 real FM은 본 Protocol을 **반드시** 구현해야 한다. Agent code는 `BiosignalFMInterface`에만 의존하며 concrete class에 의존하지 않는다.

### Swap mechanism (스왑 메커니즘)

`configs/fm/default.yaml`:

```yaml
fm:
  implementation: "mock_rule_based"   # mock_stub | mock_rule_based | mock_light_ml | real
  config:
    latency_sim_sec: 0.5              # for mocks
    seed: 42
```

`opsight/fm/factory.py`:

```python
def create_fm(config) -> BiosignalFMInterface:
    impl = config.fm.implementation
    if impl == "mock_stub":
        return StubBiosignalFM(config)
    elif impl == "mock_rule_based":
        return RuleBasedBiosignalFM(config)
    elif impl == "mock_light_ml":
        return LightMLBiosignalFM(config)
    elif impl == "real":
        return RealBiosignalFM(config)
    raise ValueError(f"Unknown FM implementation: {impl}")
```

따라서 real FM 도착은 **config 변경**이며 agent / tool layer 코드 변경이 아니다.

### Real-FM migration protocol (실 FM 마이그레이션 프로토콜, Month 3)

1. Real FM이 `BiosignalFMInterface`를 만족하는지 검증한다 (`isinstance(fm, BiosignalFMInterface)`, `runtime_checkable` 활용).
2. 100 case에 대해 `mock_rule_based`와 `real`을 병행 (side-by-side) 실행하여 메서드별 출력 delta를 기록한다.
3. Gap 분석: 어느 메서드가 가장 차이가 크고, 어느 방향으로, 어느 수술 유형 / modality regime에서 차이가 큰지 정리한다.
4. `configs/fm/default.yaml`을 `implementation: "real"`로 전환한다. `mock_rule_based` config는 fallback으로 유지한다.
5. Graceful degradation: `real`이 raise하거나 latency budget을 초과하면 runtime이 `mock_rule_based`로 fallback하며 alert를 발생시킨다.

---

## Alternatives Considered (검토한 대안)

| Alternative | Why rejected (기각 사유) |
|-------------|--------------------------|
| **(a) FM 준비될 때까지 대기** | Agent system 개발 2개월 손실. Stage 2가 단일 sprint로 압축되어 통합 risk 증폭. |
| **(b) Mock 생략, 다른 방식으로 병렬화** | Stage 1을 FM이 필요 없는 작업 (baseline + cohort)만으로 재설계해야 함 — 가장 불확실성이 큰 dual-mode infra가 검증되지 않은 채 남음. |
| **(c) Single-tier mock (Tier 1 또는 Tier 2 중 하나만)** | Tier 1 단독으로는 agent reasoning 검증에 너무 random하다. Tier 2 단독으로는 interface 안정화가 늦어지고 저비용 latency-simulation 이득을 놓친다. 2-tier 조합 (Tier 1 + Tier 2)이 두 종류 bug를 모두 잡는다. |

---

## Consequences (결과 / 영향)

### Positive (긍정적 영향)

- Stage 1의 2개월 작업이 callable backend에 대해 end-to-end로 활용 가능.
- LangGraph dual-mode loop (`plan_1.8`)이 Stage 2가 아닌 Stage 1에서 현실적 latency 하에 검증됨.
- 16-tool registry (`plan_1.7`)가 FM 도착 전에 exercised됨 — schema drift 조기 포착.
- 2× L40S에서 FM 가중치 없이 latency profiling 가능 — brief §6 TODO (shallow < 15s, deep < 60s) 정밀화.
- 부수 효과: mock tier 자체가 paper의 자연스러운 ablation comparator가 됨.

### Negative (부정적 영향)

- Mock–real 출력 gap은 불가피하다. Tier 2에 맞춰진 agent logic 일부는 swap 후 재튜닝이 필요할 수 있다.
- 유지 비용: 3개 구현 (Stub / RuleBased / LightML) + real adapter가 모두 Protocol-compliant 상태를 유지해야 한다.

### Risks & mitigations (위험 및 대응책)

| Risk | Mitigation |
|------|------------|
| 설계 결정이 mock 행동에 과적합 (over-fit) | Tier 2 이후부터 **configurable noise를 주입**하여 agent가 mock-vs-real–style 분산에 노출되도록 한다. |
| Protocol과 real FM 간 schema drift | `runtime_checkable` Protocol 검증을 CI에서 real-FM adapter에 대한 단위 테스트로 수행한다. |
| Swap 시점의 "mock은 동작하지만 real은 동작 안 함" surprise | `configs/fm/default.yaml`을 전환하기 **전에** 100-case 병행 비교 + 메서드별 gap 보고서 작성 필수. |
| Mock latency가 real에서 멀어짐 | Tier 2 latency를 real-FM 예상치에 맞춰 구성한다. 첫 real-FM benchmark 후 재조정. |

---

## References (참조)

- Master context: `docs/project_brief.md §3.5 Mock FM Strategy`
- Master plan critical path & ownership: `.plans/master_plan.md §3, §4`
- 구현 plan:
  - `.plans/stage1_preparation/plan_1.1.5_mock_fm_stub.md`
  - `.plans/stage1_preparation/plan_1.2.5_fm_interface_spec.md`
  - `.plans/stage1_preparation/plan_1.6.5_mock_fm_rule_based.md`
  - `.plans/stage1_preparation/plan_1.7.5_mock_fm_light_ml.md` *(optional)*
- 영향을 받은 기존 plan: `plan_1.4_baselines.md`, `plan_1.7_tool_spec.md`, `plan_1.8_dual_mode_infra.md`
