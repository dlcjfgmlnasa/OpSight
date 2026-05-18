# plan_1.1.5 — Mock FM Tier 1 (Stub)

**Owner**: `signal-ingest-engineer`
**Assist**: `langgraph-engineer`
**Status**: not started
**Goal**: Biosignal Foundation Model의 Tier 1 Stub mock을 구동하여, real FM 도착 전에도 agent system이 end-to-end로 개발 가능하게 한다.

> Strategy: `docs/decisions/ADR-011-mock-fm-strategy.md`. Brief: `docs/project_brief.md §3.5`. Week 1부터 `plan_1.1`과 병행 실행된다.

---

## Tasks

- [x] **[Priority: High]** Result dataclass 정의 (`HypotensionResult`, `ArrestResult`, `QualityResult`, `ConsistencyResult`, `TrendResult`, `ForecastResult`, `AnomalyResult`). (2026-05-16 완료)
  - 입력: ADR-011 method signature, `docs/project_brief.md §7.1` FM-tool output
  - 출력: `opsight/fm/result_types.py` — 7개 frozen dataclass, typed field, JSON-serializable
  - 의존성: 없음
  - 참고: 본 shape는 모든 mock + real FM이 따른다. 변경 시 ADR 갱신 필요.
  - **구현 결정 (sprint Step 1)**:
    - `meta`는 free-form `dict[str, Any]` (사용자 결정 #2).
    - `forecast` / `uncertainty`는 `list[float]` (np.ndarray 미사용 — JSON-serializability 보장).
    - `encode()`는 raw `torch.Tensor` 반환 (Result wrap 없음 — 사용자 결정 #3).
    - `TrendResult.label`은 `Literal["rising", "falling", "stable"]` (runtime 미강제, mypy / pyright 강제).
  - **검증 통과**: frozen 강제 / 7 type 모두 JSON-serializable / default meta 인스턴스별 독립.

- [x] **[Priority: High]** `StubBiosignalFM` class 구현. (2026-05-16 완료)
  - 입력: ADR-011 Protocol method 목록
  - 출력: `opsight/fm/mock_stub.py` — 8개 method 모두를 valid shape / range 범위의 random output (seedable)으로 반환하는 class
  - 의존성: result types ✅, interface Protocol ✅
  - 참고: numpy / torch random 사용. `seed`로 deterministic.
  - **구현 결정 (sprint Step 2 / C1)**:
    - `__init__(seed=42, latent_dim=128)`. `np.random.default_rng(seed)` + `torch.Generator().manual_seed(seed)` 두 generator를 인스턴스 state로 보관 (sync 결정 #1).
    - 사용자 결정: 코드 주석 한·영 병기.
    - `encode` → `torch.randn(latent_dim)` `(128,)` shape.
    - `predict_hypotension`: risk `[0,1]`, uncertainty `[0,0.5]`.
    - `predict_cardiac_arrest`: risk `[0,0.2]` (rare event proxy), uncertainty `[0,0.5]`.
    - `assess_signal_quality`: score `[0,1]`, reason은 score < 0.5일 때만 채움.
    - `cross_modal_consistency` / `anomaly_score`: score `[0,1]`.
    - `temporal_trend`: slope `[-5,5]`. label 규칙: `|slope|<1` → stable, slope>0 → rising, slope<0 → falling.
    - `forecast_signal`: `list[float]` 길이 = `horizon_min` (1 sample/min — stub 단순화). meta에 `sampling_rate_hz=1/60` 명시.
    - 모든 Result의 `meta`에 `mock_tier="stub"` + 호출 args (modality, available_modalities 등) 기록 → swap 시 trace 디버깅 용이.
  - **검증 통과**:
    - `isinstance(stub, BiosignalFMInterface)` ✓ (`runtime_checkable` positive)
    - 8 method 호출 시 expected Result type + valid range 모두 통과
    - Deterministic: 동일 seed → 동일 risk; 다른 seed → 다른 risk
    - `HypotensionResult` JSON-serializable
    - `encode` torch.Tensor shape `(128,)` 정확
  - **C2 (latency simulation)는 별도 task로 진행 예정**.

- [x] **[Priority: High]** Configurable latency 시뮬레이션 추가. (2026-05-16 완료)
  - 입력: brief §6의 shallow / deep latency 목표
  - 출력: `StubBiosignalFM`이 method별 (또는 전역) `latency_sim_sec`을 수용. async면 `asyncio.sleep`, sync면 `time.sleep` 사용. 선택한 async 입장을 문서화.
  - 의존성: stub class ✅
  - 참고: latency 분포 (고정 vs jitter)도 옵션화 — `latency_jitter_pct` 같은 field.
  - **구현 결정 (sprint Step 2 / C2)**:
    - **Sync 입장 채택** (sprint Step 1 결정 #1): `time.sleep` 사용. LangGraph node가 sync이므로 blocking sleep 허용. 미래 async backend는 호출 사이트에서 `asyncio.to_thread`로 wrap. module docstring에 명시.
    - `__init__` 인자 추가: `latency_sim_sec: float = 0.0` (전역 default), `latency_per_method: dict[str, float] | None = None` (method별 override), `latency_jitter_pct: float = 0.0` (±jitter 비율).
    - Resolution 순서: per-method override → 없으면 전역 default. jitter는 양쪽 모두 적용. 결과는 max(0, base+jitter)로 clip.
    - 구현 방식: module-level `_simulate_latency` decorator로 8 method 모두 wrap. 가독성 + Protocol signature 보존.
    - 기본값 0.0이라 unit test에서 빠르게 실행 (no sleep).
  - **검증 통과**:
    - 기본 (zero latency): 8 호출 0.1ms — 즉시 반환 ✓
    - 전역 50ms: 단일 호출 50.2ms (오차 < 1ms) ✓
    - per-method override: predict_hypotension(30ms), encode(100ms), anomaly_score(0ms — global=0 fallback) 모두 정확 ✓
    - Jitter (±50% on 50ms base): 10회 호출 range [27.5, 66.7]ms, std=13.6ms — 분포 합리적 ✓
    - `isinstance(stub, BiosignalFMInterface)` 데코레이터 적용 후에도 유효 ✓
    - Determinism: 동일 seed → 동일 risk (latency 적용 후에도) ✓

- [x] **[Priority: High]** Output shape & range에 대한 unit test. (2026-05-16 완료)
  - 입력: 위 산출물 ✅
  - 출력: `tests/test_fm_mock_stub.py` — method별 assertion: dataclass field 존재, range가 예상 안에 있음 (예: `risk ∈ [0,1]`), latency ≥ 구성된 sleep
  - 의존성: 위 ✅
  - 참고: pytest-only. 외부 데이터 없음.
  - **구현 결정 (sprint Step 2 / C3)**:
    - 16 test 그룹화: per-method output (9) + determinism (2) + JSON-serializability (1) + latency simulation (4).
    - `pytest.fixture`로 `stub`과 `signal` 공유. signal은 synthetic `torch.zeros(1000)` 3 modality.
    - **Branch coverage 강제**:
      - `assess_signal_quality` reason 규칙: 200 seed로 두 분기 (score<0.5 reason 채움 / score≥0.5 reason None) 모두 관찰.
      - `temporal_trend` label 규칙: 100 seed로 3개 label (stable / rising / falling) 모두 관찰.
    - `dataclasses.fields(cls)`로 expected field 이름 set 검증 → 미래 field 추가 시 본 test 갱신 강제.
    - Latency test에 scheduling slack 허용 (max 50ms 기준 ≤ 85ms 등 — sleep granularity 고려).
  - **검증 통과 (16/16 test)**:
    ```
    test_encode_returns_tensor_with_expected_shape           PASSED
    test_encode_respects_custom_latent_dim                   PASSED
    test_predict_hypotension_fields_and_ranges               PASSED
    test_predict_cardiac_arrest_risk_capped_at_low_range     PASSED
    test_assess_signal_quality_reason_rule                   PASSED
    test_cross_modal_consistency_range                       PASSED
    test_temporal_trend_label_derives_from_slope             PASSED
    test_forecast_signal_length_and_range                    PASSED
    test_anomaly_score_range                                 PASSED
    test_same_seed_yields_same_output                        PASSED
    test_different_seed_yields_different_output              PASSED
    test_all_results_are_json_serializable                   PASSED
    test_zero_latency_default_is_fast                        PASSED
    test_global_latency_applied                              PASSED
    test_per_method_override_takes_precedence                PASSED
    test_jitter_introduces_variance                          PASSED
    16 passed in 2.19s
    ```

- [x] **[Priority: Medium]** 단일 코호트 case smoke test. (2026-05-16 완료)
  - 입력: 1 코호트 case (`plan_1.2` 가용 시. 그 전엔 synthetic dict) — **현재 synthetic 사용**, plan_1.2 도착 시 fixture 교체만 하면 됨.
  - 출력: `tests/test_fm_mock_stub_smoke.py` — case payload로 8개 method 호출. 예외 없음 + 모든 Result well-formed assertion.
  - 의존성: stub + unit test ✅
  - 참고: `plan_1.2` 코호트가 늦으면 synthetic 신호로 시작 후 추후 교체.
  - **구현 결정 (sprint Step 2 / C4)**:
    - Synthetic 4-modality case: ABP / ECG_II / PPG (500 Hz) + BIS (100 Hz), 30초 window. Content는 zeros (stub은 content 무관). plan_1.2 도착 시 fixture만 swap.
    - 6 test 구성:
      - `test_smoke_all_eight_methods_on_single_case` — 8 method 통합 호출, type assertion만
      - `test_smoke_modality_subset_only` — ABP-only subset (Thoracic-like) edge
      - `test_smoke_no_modalities` — 빈 modality 리스트 (modality-agnostic 극단)
      - `test_smoke_all_results_serialize` — 7개 Result JSON-serializable (encode 제외 — tensor)
      - `test_smoke_shallow_loop_latency_within_budget` — 8 method sequential sweep latency 측정. shallow loop 15초 budget 안에 머무는지 sanity check (실제는 250ms base + jitter).
      - `test_smoke_idempotent_state_across_repeated_calls` — 20회 반복 호출 시 예외 / leak 없음
    - C3 (per-method 의미 검증)와 C4 (통합 호출 + budget)의 책임 명확 분리.
  - **검증 통과 (6/6 test)**: 1.73s.

- [x] **[Priority: Medium]** Stub의 caveat 문서화. (2026-05-16 완료)
  - 입력: 위 산출물 ✅
  - 출력: `opsight/fm/mock_stub.py` module docstring — "output은 random이며 reasoning 검증용 아님. Tier 2를 사용할 것" 명시
  - 의존성: 없음
  - 참고: 미래의 본인 / 타 agent가 stub 출력으로 reasoning을 평가하는 사고를 방지.
  - **구현 결정 (sprint Step 2 / C5)**:
    - Module docstring 상단에 ASCII frame으로 둘러싼 **HARD CAVEAT** block — 3개 금지 용도 명시 (임상 결정 / agent reasoning 검증 / real FM benchmark).
    - `meta["mock_tier"] == "stub"` marker 언급 — downstream agent / trace consumer가 출처 식별 + 거부 가능.
    - 임상 사실 가드 (Clinical Fact Guard) 한 단락 추가 — `docs/project_brief.md §13.1` reference + `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` marker 사용 의무.
    - `StubBiosignalFM` class docstring에도 1-line 강조 추가.
    - 한·영 병기 유지.
  - **회귀 검증**: 52 test 모두 통과 (caveat 강화 후에도 동작 동일).

---

## Definition of done

- `opsight/fm/result_types.py`와 `opsight/fm/mock_stub.py`가 commit되고 importable
- Unit test + smoke test 통과
- Stub이 `BiosignalFMInterface`를 만족 (`plan_1.2.5`에서 추후 검증)

## Data contracts established here

- **Result dataclass shape** — 모든 mock tier와 real FM이 정확히 이 type을 산출해야 한다. Schema는 `opsight/fm/result_types.py`에 위치.

## Related work

- ADR-011 (strategy)
- `plan_1.2.5_fm_interface_spec.md` — 본 plan의 result type에 의존
