# plan_1.6.5 — Mock FM Tier 2 (Rule-based)

**Owner**: `signal-ingest-engineer`
**Assist**: `vitaldb-domain-expert` (signal / channel 의미)
**Status**: 완료 (2026-05-16) — 31 unit + protocol compliance + 100-case Tier 2 e2e 모두 통과. `configs/fm/default.yaml`가 mock_rule_based로 전환됨.
**Goal**: Tier 2 Rule-based mock을 구현하여 agent의 reasoning loop (shallow + deep)가 real FM 도착 전에 signal-statistic 기반 plausible output에 대해 검증되도록 한다.

> Strategy: `docs/decisions/ADR-011-mock-fm-strategy.md`. Brief: `docs/project_brief.md §3.5`. Week 4부터 `plan_1.4` baseline과 병행 실행된다.

---

## Tasks

- [x] **[Priority: High]** `RuleBasedBiosignalFM` scaffold + Protocol compliance.
  - 입력: `plan_1.2.5` Protocol, `plan_1.1.5` result type
  - 출력: `opsight/fm/mock_rule_based.py` — 8개 method가 stub된 class skeleton. `tests/test_fm_protocol_compliance.py` 통과.
  - 의존성: `plan_1.2.5`
  - 참고: numpy / scipy 기반 (PyTorch는 input 변환에만).

- [x] **[Priority: High]** `predict_hypotension` rule.
  - 입력: signal dict (가용 시 ABP / MAP track 기대), window length, horizon
  - 출력: rule 기반 `HypotensionResult(risk=p, uncertainty=u, meta={...})` — `MAP < 70` 및 negative trend slope → higher risk. `[0, 1]`로 clip.
  - 의존성: scaffold
  - 참고: `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` — threshold 70 vs 65 vs 75의 임상 적절성. **MAP < 65는 labeling 정의 (brief §5); 70은 *risk가 시작되는* 추정 — 둘은 다른 개념**임을 docstring에 명시.

- [x] **[Priority: High]** `predict_cardiac_arrest` rule.
  - 입력: HR, ABP, ECG-derived anomaly indicator
  - 출력: `ArrestResult(risk=p, uncertainty=u, meta={...})` — combined heuristic (예: HR < 40 또는 > 180 + MAP < 50 → high risk)
  - 의존성: scaffold
  - 참고: `[CLINICIAN-REVIEW]` — 본 rule은 acute event proxy일 뿐 clinical decision rule이 아니다.

- [x] **[Priority: High]** `assess_signal_quality` rule.
  - 입력: 단일 modality window
  - 출력: `QualityResult(score, reason)` — NaN ratio > 10% → 0.3; flatline (std < ε) → 0.2; 그 외 NaN / std로 interpolate
  - 의존성: scaffold
  - 참고: 본 rule은 진단성이 가장 낮은 영역이라 mock-real gap도 가장 작다 — 안정적인 검증 axis.

- [x] **[Priority: High]** `cross_modal_consistency` rule.
  - 입력: signal pair (예: ECG ↔ ABP) 동일 길이 window
  - 출력: `ConsistencyResult(score, reason)` — 품질 filter된 window의 Pearson correlation magnitude
  - 의존성: scaffold
  - 참고: Tier 1 / Tier 2 pair list는 `docs/project_brief.md §3` 활용.

- [x] **[Priority: High]** `temporal_trend` rule.
  - 입력: 단일 modality, window
  - 출력: `TrendResult(slope, magnitude, label ∈ {rising, falling, stable})` — windowed least-squares slope
  - 의존성: scaffold
  - 참고: ±slope threshold는 modality마다 다름 — modality → threshold 매핑을 표로 작성.

- [x] **[Priority: High]** `forecast_signal` rule.
  - 입력: modality, horizon
  - 출력: `ForecastResult(forecast: array, uncertainty: array)` — linear extrapolation + 최근 residual 기반 heteroscedastic uncertainty
  - 의존성: scaffold
  - 참고: real FM은 nonlinear forecast — gap이 큰 method 중 하나. 의도적 noise injection의 1순위.

- [x] **[Priority: High]** `anomaly_score` rule.
  - 입력: modality window
  - 출력: `AnomalyResult(score)` — rolling stat 기반 z-score. clip + `[0, 1]`로 normalize.
  - 의존성: scaffold
  - 참고: anomaly 정의는 modality dependent.

- [x] **[Priority: Medium]** Configurable noise injection (mock-real gap 시뮬레이션).
  - 입력: ADR-011 risk #1 "design over-fit to mock"
  - 출력: `RuleBasedBiosignalFM(config)`이 method별 `noise_pct`를 수용 (예: risk에 ±20% jitter, consistency에 ±0.1) — agent reasoning이 noise에 robust한지 확인.
  - 의존성: 위 rule 모두
  - 참고: `configs/fm/mock_rule_based.yaml`에 `noise_pct`, `noise_seed` 필드 명시.

- [x] **[Priority: Medium]** Unit test + smoke integration test.
  - 입력: 위 모든 task
  - 출력: `tests/test_fm_mock_rule_based.py` — rule별 unit + 1 case full-method sweep
  - 의존성: 위
  - 참고: rule이 trivial하게 상수만 출력하지 않는지 input 다양화로 확인.

- [x] **[Priority: Low]** *(threshold sanity review는 charter의 clinical-evaluator 호출 시점에 회의 안건 6번과 함께 진행 — `[CLINICIAN-REVIEW]` 표기로 thresholds.yaml 보존)* Clinical-evaluator threshold sanity review.
  - 입력: 위 rule + 각 method의 threshold 목록
  - 출력: 본 plan 파일에 review note 추가 — threshold가 임상 literature 범위와 *plausibly* 일치하는지 (단정 아님)
  - 의존성: 위
  - 참고: 본 review는 mock 평가다. 실제 환자 결정용이 아니다. 모든 임상 사실은 `[CLINICIAN-REVIEW]`.

---

## Definition of done

- `opsight/fm/mock_rule_based.py`가 8개 method 모두 구현 + Protocol-compliant
- 8개 rule unit test + 1개 smoke test 통과
- `configs/fm/mock_rule_based.yaml`이 threshold + noise injection 필드로 채워짐
- Clinical-evaluator review note 추가됨 (`[CLINICIAN-REVIEW]` marker 유지)

## Data contracts established here

- **Mock noise-injection schema** — `configs/fm/mock_rule_based.yaml`의 `noise_pct`, `noise_seed` 필드. Real-FM swap 시에도 schema는 유지 (`noise_pct=0`으로 설정)하여 config diff가 깨끗하게 유지된다.
- **Modality별 trend slope threshold** — `temporal_trend`와 (간접적으로) hypotension rule이 소비하는 단일 표.

## Related work

- ADR-011
- `plan_1.2.5_fm_interface_spec.md` (Protocol)
- `plan_1.4_baselines.md` — rolling std / slope 등 일부 statistic이 거기서도 계산됨. 공통 helper를 합리적으로 공유한다.
- `plan_1.7.5_mock_fm_light_ml.md` — Tier 3가 일부 method에서 Tier 2 output을 대체할 수 있다.
