# plan_1.2.5 — FM Interface Protocol & Factory

**Owner**: `langgraph-engineer`
**Assist**: `signal-ingest-engineer`
**Status**: not started
**Goal**: FM Interface Protocol + factory + config schema를 결정짓는다. 모든 mock tier와 real FM이 단일 import 경로 뒤에서 plug 가능하게 한다.

> Strategy: `docs/decisions/ADR-011-mock-fm-strategy.md`. Week 2부터 `plan_1.2`와 병행 실행된다.

---

## Tasks

- [x] **[Priority: High]** `BiosignalFMInterface` Protocol 정의. (2026-05-16 완료)
  - 입력: ADR-011 method 목록 / signature, `plan_1.1.5` result type
  - 출력: `vitalagent/fm/interface.py` — `runtime_checkable` `Protocol`. 8개 method를 정밀 typed (signal은 `dict[str, torch.Tensor]`, modality는 `list[str]` 등).
  - 의존성: `plan_1.1.5` result type
  - 참고: Protocol 변경은 ADR-011 개정 필요 — module docstring에 명시.
  - **구현 결정 (sprint Step 2 / B1)**:
    - `torch` runtime 의존 제거: `from __future__ import annotations` + `TYPE_CHECKING` 가드. Annotation은 PEP 563 string-lazy. concrete 구현체가 자체적으로 `torch`를 import한다 (sprint plan §Risk Register의 mitigation 적용).
    - 코드 주석은 한·영 병기 (사용자 결정).
  - **검증 통과**:
    - Import 정상 (torch 미설치 환경 OK)
    - 8 method 정확히 ADR-011 일치
    - `runtime_checkable` positive (FakeFM 통과) / negative (BrokenFM 거부) 모두 작동
    - Raw annotation (string-lazy) 정상: `dict[str, torch.Tensor]` 등 string 형태
    - 알려진 한계: `typing.get_type_hints`는 runtime에 `torch`를 실제 import — 미설치 환경에선 실패. 정적 type check (mypy / pyright)에선 정상. `runtime_checkable`은 method 이름만 보므로 영향 없음.

- [x] **[Priority: High]** `StubBiosignalFM`이 runtime에서 Protocol을 만족하는지 검증. (2026-05-16 완료)
  - 입력: `plan_1.1.5`의 stub, 위 Protocol
  - 출력: `tests/test_fm_protocol_compliance.py` — `assert isinstance(stub, BiosignalFMInterface)`. 후속 mock tier와 real adapter에 대해서도 동일 assertion을 추가한다.
  - 의존성: stub + Protocol ✅
  - 참고: `runtime_checkable`의 한계 인지 — signature 일치까지는 보지 않는다. 보조로 inspect 기반의 더 엄격한 체크 추가를 고려한다.
  - **구현 결정 (sprint Step 2 / B2)**:
    - 3-layer compliance 체크: (1) `runtime_checkable` `isinstance` — method 존재만, (2) method enumeration — 8개 method 모두 존재 + callable, (3) **stricter** signature alignment — `inspect.signature`로 parameter 이름 정확히 일치 검증 (Protocol의 `self` 제외).
    - `FM_IMPLEMENTATIONS` registry list 패턴: `(name, zero-arg factory)` 튜플. 새 tier 추가 시 한 줄 추가만으로 3개 test가 자동 실행됨 (TODO comment로 1.6.5/1.7.5/real 명시).
    - Negative sanity test: `_BrokenFM` (1/8 method만 구현)이 `runtime_checkable`에 거부되는지 확인 → compliance harness가 실제로 enforcing하는지 검증.
    - `tests/conftest.py`로 project root를 `sys.path`에 자동 추가 → editable install 불필요.
    - pytest 설치 (`pytest 9.0.3`) 및 venv permission 자동 승인 (settings.local.json).
  - **검증 통과**:
    ```
    tests/test_fm_protocol_compliance.py::test_runtime_checkable_protocol[StubBiosignalFM]                    PASSED
    tests/test_fm_protocol_compliance.py::test_all_methods_present_and_callable[StubBiosignalFM]             PASSED
    tests/test_fm_protocol_compliance.py::test_method_signatures_match_protocol[StubBiosignalFM]             PASSED
    tests/test_fm_protocol_compliance.py::test_negative_sanity_broken_implementation_rejected                PASSED
    4 passed in 1.48s
    ```

- [x] **[Priority: High]** Factory 구현. (2026-05-16 완료)
  - 입력: ADR-011 §"Swap mechanism"
  - 출력: `vitalagent/fm/factory.py` — `create_fm(config) -> BiosignalFMInterface`. `config.fm.implementation ∈ {mock_stub, mock_rule_based, mock_light_ml, real}`을 switch. 알 수 없는 값은 위반 문자열과 함께 `ValueError`를 raise.
  - 의존성: Protocol ✅
  - 참고: `real`, `mock_rule_based`, `mock_light_ml`은 본 plan 시점에 미구현이다 — placeholder import + lazy load 패턴을 권장한다 (import-time crash 방지).
  - **구현 결정 (sprint Step 2 / B3)**:
    - Config 형식: dict (`{"fm": {"implementation": "...", "config": {...}}}`). Pydantic / dataclass는 향후 도입 시 wrap layer로 추가 가능.
    - **3단계 에러 정책**:
      1. `fm` 객체 없음 → `ValueError("config must contain an 'fm' object ...")`.
      2. `implementation` 알 수 없는 값 → `ValueError("Unknown FM implementation: ...")` (offending string 포함).
      3. tier 이름은 valid하지만 module 부재 (`ImportError`) → `NotImplementedError` with plan reference 안내 (예: `"plan_1.6.5"`, `"Stage 2"`).
    - **Lazy import 패턴**: 각 tier import를 함수 안으로. `try / except ImportError → raise NotImplementedError from exc`로 wrap. import-time crash 회피 + 명확한 미구현 안내.
    - `_KNOWN_IMPLEMENTATIONS: Final[tuple[str, ...]]`에 4개 tier 이름 박음 (중앙 정의).
    - Lazy import는 `TYPE_CHECKING` 가드와 분리 — `BiosignalFMInterface`는 type annotation에만 사용 (runtime import 불필요).
  - **검증 통과**:
    ```
    tests/test_fm_factory.py
      test_create_mock_stub_returns_protocol_instance         PASSED
      test_create_mock_stub_without_config_section            PASSED
      test_create_mock_stub_forwards_kwargs                   PASSED
      test_unknown_implementation_raises_valueerror           PASSED
      test_missing_fm_section_raises_valueerror               PASSED
      test_unimplemented_tier_raises_notimplemented[mock_rule_based-plan_1.6.5]  PASSED
      test_unimplemented_tier_raises_notimplemented[mock_light_ml-plan_1.7.5]    PASSED
      test_unimplemented_tier_raises_notimplemented[real-Stage 2]                PASSED
    8 passed (factory) + 4 passed (protocol compliance) = 12 passed in 1.44s
    ```

- [x] **[Priority: High]** 4개 implementation에 대한 config template 작성. (2026-05-16 완료)
  - 입력: factory 계약 ✅
  - 출력:
    - `configs/fm/mock_stub.yaml` ✅ — 8 method별 latency_per_method + jitter 채움 (sprint plan §Risk Register의 latency 시뮬레이션 mitigation 적용)
    - `configs/fm/mock_rule_based.yaml` ✅ *(template, threshold 표 + noise schema는 `plan_1.6.5`에서 확정)*
    - `configs/fm/mock_light_ml.yaml` ✅ *(template + OPTIONAL, method_backing / checkpoints는 `plan_1.7.5`에서 확정)*
    - `configs/fm/real.yaml` ✅ *(template, checkpoint_path / device 등은 Stage 2에서 확정. fallback_on_failure: true 기본)*
    - `configs/fm/default.yaml` ✅ — 첫 주에는 `mock_stub`을 가리키며 lifecycle 주석 명시
  - 의존성: factory ✅
  - 참고: 각 yaml 파일에 commentary 헤더로 어느 plan이 채우는지 명시한다.
  - **구현 결정 (sprint Step 2 / B4)**:
    - 모든 yaml 헤더에 Owner plan / Spec / Status / Purpose 4단 commentary block.
    - `default.yaml`에 lifecycle table 주석 (Week 1–3 mock_stub → Week 4–8 mock_rule_based → optional Tier 3 → Stage 2 real).
    - `mock_stub.yaml`과 `default.yaml`의 latency profile은 동일 (default가 mock_stub을 가리키므로). 향후 default.yaml 갱신 시 분리 가능.
    - TODO marker 일관: `TODO[plan_1.6.5]`, `TODO[plan_1.7.5]`, `TODO[Stage 2]` 형식으로 후속 작업자 명시.
    - 한·영 병기 주석.
  - **검증 통과 (12 yaml-related tests)**:
    ```
    test_all_5_templates_exist                                                 PASSED
    test_template_has_fm_implementation_field[default.yaml]                    PASSED
    test_template_has_fm_implementation_field[mock_light_ml.yaml]              PASSED
    test_template_has_fm_implementation_field[mock_rule_based.yaml]            PASSED
    test_template_has_fm_implementation_field[mock_stub.yaml]                  PASSED
    test_template_has_fm_implementation_field[real.yaml]                       PASSED
    test_default_yaml_points_at_implemented_tier                               PASSED
    test_mock_stub_yaml_instantiates_via_factory                               PASSED
    test_default_yaml_instantiates_via_factory                                 PASSED
    test_unimplemented_yaml_raises_notimplemented[mock_rule_based-plan_1.6.5]  PASSED
    test_unimplemented_yaml_raises_notimplemented[mock_light_ml-plan_1.7.5]    PASSED
    test_unimplemented_yaml_raises_notimplemented[real-Stage 2]                PASSED
    ```
    yaml round-trip (load → factory → Protocol-compliant instance) 검증됨.

- [x] **[Priority: Medium]** Interface user guide. (2026-05-16 완료)
  - 입력: 위 산출물 ✅
  - 출력: `docs/fm_interface_guide.md` — 새 FM tier를 추가하는 agent / developer를 위한 안내: 필요한 method, return shape, config 구조, factory wiring, compliance test
  - 의존성: 위 task 모두 ✅
  - 참고: `langgraph-engineer` charter가 본 문서를 SoT로 reference한다 (Phase 3에서 반영).
  - **구현 결정 (sprint Step 2 / B6)**:
    - §3 Factory & config schema — entry point, 스키마, 5 yaml template 일람 + lifecycle, 에러 정책, lazy import 패턴, 사용 예
    - §4 Compliance test — 3-layer 구조, registry 패턴, 실행 명령
    - §5 Graceful degradation — `make_fallback` 진입점, 2단계 정책, `AlertCallback` 시그니처, 사용 예
    - §6 새 FM tier 추가 절차 — 8 step 체크리스트 (real adapter는 추가 2 step: gap analysis + default.yaml 전환)
    - §7 Real-FM 마이그레이션은 Stage 2 진입 시점 보강 (현재는 ADR-011 reference만)
    - 한·영 병기 유지.
  - **현재 §0 (TOC)에서 §1~§6 모두 ✅ 표시, §7만 ⏳ Stage 2 대기**.

- [x] **[Priority: Medium]** Graceful-degradation hook 문서화. (2026-05-16 완료)
  - 입력: ADR-011 §"Real-FM migration protocol" step 5
  - 출력: `vitalagent/fm/factory.py`에 `make_fallback(primary, fallback) -> BiosignalFMInterface` helper + 사용 예시 docstring
  - 의존성: factory ✅
  - 참고: 실제 호출 site (LangGraph node)에서 wrap한다. 본 task는 helper와 docs까지.
  - **구현 결정 (sprint Step 2 / B5)**:
    - `_FallbackFM` private class를 명시적으로 8 method 위임 (가독성). 동적 `__getattr__` 방식 대신 explicit method 정의.
    - **2단계 fallback 정책**:
      1. **Exception → 즉시 fallback** 호출 + `alert("primary_failed", method, exc, {})`. 예외는 alert 안에서 흡수.
      2. **Latency budget 초과 → primary 결과는 그대로 반환** + `alert("latency_exceeded", method, None, {elapsed_sec, budget_sec})`. 현재 호출 강제 종료 X (sync sleep interrupt 불가). Stage 2에서 circuit-breaker 추가 가능.
    - `AlertCallback` type alias 공개 (외부에서 custom alert 주입 가능).
    - Default alert: `logging` WARNING level + reason / method / exc / extra 모두 기록.
    - `make_fallback(primary, fallback, latency_budget_sec=None, alert=None)` factory 시그니처. 모두 optional 인자.
  - **검증 통과 (6 fallback test)**:
    - `test_fallback_satisfies_protocol` — wrapped instance가 Protocol 만족 ✓
    - `test_happy_path_primary_only` — primary 정상 시 primary 결과 사용 (fallback 미호출) ✓
    - `test_exception_path_uses_fallback_and_alerts` — primary 예외 → fallback 결과 + alert ✓
    - `test_latency_budget_alerts_but_returns_primary` — 느린 primary → primary 결과 + alert ✓
    - `test_failure_on_one_method_does_not_affect_others` — predict_hypotension 실패가 anomaly_score에 영향 없음 ✓
    - `test_default_alert_emits_warning_log` — default alert가 WARNING log ✓
  - **전체 sprint 누적 30 test 통과**.

---

## Definition of done

- `BiosignalFMInterface` Protocol + factory + 5개 config yaml template commit됨
- `mock_stub`에 대한 Protocol-compliance test 통과
- `docs/fm_interface_guide.md` publish됨

## Data contracts established here

- **`BiosignalFMInterface` Protocol** — 변경 시 모든 FM tier에 영향. ADR-011 개정 필수.
- **Factory config schema** — `configs/fm/*.yaml` shape

## Related work

- ADR-011
- `plan_1.1.5_mock_fm_stub.md` (선행)
- `plan_1.6.5_mock_fm_rule_based.md` (다음 구현)
- `plan_1.7.5_mock_fm_light_ml.md` (optional)
