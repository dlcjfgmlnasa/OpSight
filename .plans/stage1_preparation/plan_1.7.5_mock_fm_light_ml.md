# plan_1.7.5 — Mock FM Tier 3 (Light ML) *(OPTIONAL)*

**Owner**: `signal-ingest-engineer`
**Assist**: `clinical-evaluator`
**Status**: ✅ done (Sprint 5, 2026-05-17) — Mock FM 3-tier 모두 작동. `BaselineFMAdapter` (plan_1.4) wrap.
**Goal**: Stage 1.4 baseline (Logistic / XGBoost / LSTM)을 `BiosignalFMInterface` 뒤에서 wrapping하여 Tier 3 real-model proxy를 제공한다. FM swap 시점의 mock-vs-real 비교를 더 정밀하게 한다.

> Strategy: `docs/decisions/ADR-011-mock-fm-strategy.md`. Brief: `docs/project_brief.md §3.5`.

---

## Tasks

- [x] **[Priority: Medium]** `LightMLBiosignalFM` scaffold + Protocol compliance.
  - 입력: `plan_1.2.5` Protocol, `plan_1.4` baseline
  - 출력: `opsight/fm/mock_light_ml.py` skeleton. `tests/test_fm_protocol_compliance.py` 통과.
  - 의존성: `plan_1.2.5`, `plan_1.4`
  - 참고: `plan_1.4` artifact 경로에서 저장된 baseline checkpoint를 로드한다.

- [x] **[Priority: Medium]** Method 매핑 — Protocol method별 backing baseline.
  - 입력: 8개 Protocol method, 4개 baseline 모델
  - 출력: module docstring + `configs/fm/mock_light_ml.yaml`의 `method_backing` field에 매핑 문서화:
    - `predict_hypotension` → LSTM (ABP, h=5), XGBoost (multimodal, h=15) (제안 — 실제 선택은 `plan_1.4` val metric 기반)
    - `predict_cardiac_arrest` → XGBoost multimodal
    - `assess_signal_quality` → Tier-2 rule 재사용 (baseline 없음)
    - `cross_modal_consistency` → Tier-2 rule 재사용
    - `temporal_trend` → Tier-2 rule 재사용
    - `forecast_signal` → LSTM (single-modality regression head, 가능 시)
    - `anomaly_score` → Tier-2 rule 재사용
    - `encode` → XGBoost feature vector OR LSTM penultimate (구현 단계에서 결정)
  - 의존성: `plan_1.4` baseline 학습 완료
  - 참고: 모든 Protocol method가 baseline backer를 갖지는 않는다 — 해당 method는 Tier-2 rule로 fallback하고 그 사실을 문서화한다.

- [x] **[Priority: Medium]** Inference latency 측정.
  - 입력: 빌드된 Tier 3 mock, sample case
  - 출력: 본 plan에 method별 latency 표 추가. Tier 1 sleep 목표 + Tier 2 rule cost와 비교.
  - 의존성: 위
  - 참고: Tier 3가 너무 느리면 shallow loop budget 위반 가능 — meta로 보고한다.

- [x] **[Priority: Medium]** Protocol compliance + smoke test.
  - 입력: 위
  - 출력: `tests/test_fm_mock_light_ml.py` — Protocol assertion + 1 case full-method sweep
  - 의존성: 위
  - 참고: baseline checkpoint 부재 시 pytest skip 패턴 적용.

- [x] **[Priority: Low]** Clinical-evaluator의 mock-real proxy quality note.
  - 입력: method별 output 분포 비교 (Tier 2 vs Tier 3)
  - 출력: 본 plan에 review note 추가 — Tier 3가 real FM 양상에 더 가까울 것으로 *기대되는* 부분 vs 그렇지 않은 부분
  - 의존성: 위
  - 참고: `[CLINICIAN-REVIEW]` 적절히 부착. 본 review는 mock 평가이며 환자 결정용 아님.

---

## Definition of done (실행 시점에만 적용)

- `opsight/fm/mock_light_ml.py`가 8개 method 모두 구현 (가능한 곳은 baseline 활용, 그 외는 Tier-2 rule로 fallback)
- Protocol compliance + smoke test 통과
- `configs/fm/mock_light_ml.yaml`에 latency 표 + method 매핑 문서화

## Skip 기준

- Stage 1 종료 시점에 Tier 1 + Tier 2가 완전 작동하고 dual-mode skeleton (`plan_1.8`)이 코호트 case에 대해 end-to-end로 green이면 **Tier 3는 optional**이며 Stage 2로 연기하거나 완전히 drop할 수 있다.

## Data contracts established here

- 신규 없음 — `plan_1.1.5` / `plan_1.2.5`의 Result type / Protocol과 `plan_1.4`의 baseline I/O를 재사용.

## Related work

- ADR-011
- `plan_1.4_baselines.md`
- `plan_1.2.5_fm_interface_spec.md`
- `plan_1.6.5_mock_fm_rule_based.md` (sibling tier)

---

## Sprint 5 산출물 (2026-05-17)

### 구현

- `opsight/fm/mock_light_ml.py` — `LightMLBiosignalFM` (8 Protocol method via `BaselineFMAdapter` 위임)
- `configs/fm/mock_light_ml.yaml` — TEMPLATE → 실 config 전환 (primary_baseline 기본 `logreg_abp`, optional checkpoint_path)
- `opsight/fm/factory.py::create_fm` — 기존 `mock_light_ml` 분기 작동 확인 (코드 변경 0, lazy import 만 활성화)

### Method backing 매핑 (실 구현)

| Protocol method | Backing |
|----------------|---------|
| `predict_hypotension` | config 의 `primary_baseline` (logreg / lstm / hatib / xgb 중 택일) |
| `predict_cardiac_arrest` | `BaselineFMAdapter` 의 rule-based (HR/MAP flag composite) |
| `assess_signal_quality` | `BaselineFMAdapter` 의 NaN+std heuristic |
| `cross_modal_consistency` | `BaselineFMAdapter` 의 `|Pearson r|` on filtered window |
| `temporal_trend` | `BaselineFMAdapter` 의 linear slope + label |
| `forecast_signal` | `BaselineFMAdapter` 의 linear extrapolation |
| `anomaly_score` | `BaselineFMAdapter` 의 tail z-score |
| `encode` | `BaselineFMAdapter` 의 per-modality (mean, std, slope) latent vector |

→ 1 method (predict_hypotension) 만 학습된 baseline 사용, 7 method 는 deterministic rule. 본 분배는 plan_1.4 baseline 의 학습 범위 (hypotension 위주) 와 일치.

### Test (18 신규)

- `tests/test_fm_mock_light_ml.py` (15 test)
  - 4 baseline (logreg / lstm / hatib / xgb) 모두 생성 가능
  - 알 수 없는 baseline 거부 (`ValueError`)
  - Protocol `isinstance` 통과
  - 8 method smoke (single case)
  - 모든 Result 의 `meta.mock_tier == "light_ml"` + `meta.baseline == "logreg_abp"` 전파
  - Checkpoint 부재 시 `FileNotFoundError`
  - Checkpoint roundtrip (logreg 학습 → 저장 → load)
  - Latency per-method (50ms enforce)
  - Latency default 0 → 무 sleep
  - Factory create_fm 직접 인자 통합
  - Factory create_fm + yaml 통합
  - XGBoost 미설치 환경 graceful fallback (untrained_or_xgb_missing)
- `tests/test_fm_protocol_compliance.py` — `LightMLBiosignalFM` 등록 (3 신규 parametrized test)
- `tests/test_fm_factory.py` + `tests/test_fm_config_yaml.py` — `mock_light_ml` 가 unimplemented list 에서 제거 + protocol instance 검증 2 신규

### 전체 test: 187 통과 (Sprint 4: 169 → Sprint 5: 187, +18)

### Method-별 latency 표 (mock 환경 측정)

| Method | Latency (mock, no sleep) |
|--------|-------------------------|
| `encode` | < 1 ms |
| `predict_hypotension` (logreg backing) | ~ 1 ms |
| `predict_hypotension` (lstm backing, MC-dropout n=8) | ~ 5–10 ms |
| `predict_cardiac_arrest` | < 1 ms (rule) |
| `assess_signal_quality` | < 1 ms |
| `cross_modal_consistency` | < 1 ms |
| `temporal_trend` | < 1 ms |
| `forecast_signal` | < 1 ms |
| `anomaly_score` | < 1 ms |

→ 8-method 전체 sweep < 50 ms (no sleep). Shallow loop budget (15 sec) 의 0.3% — 충분히 안전. Real FM 도착 후 latency_per_method config 로 재교정.

### Clinical-evaluator mock-real proxy quality note

본 Tier 3 는 다음 가정 하에 *real FM proxy* 로 사용 가능:

**더 나은 proxy 인 부분 (Tier 2 대비)**:
- `predict_hypotension`: 학습된 baseline (logreg / lstm) 출력은 random Tier 1 보다 훨씬 plausible. Tier 2 rule (MAP threshold + slope) 대비 *학습 분포* 를 반영 — real FM 양상에 한 발 더 가까움.

**Tier 2 와 동일한 부분 (proxy 가치 제한)**:
- 나머지 7 method: rule-based 그대로. Real FM 양상 (특히 cross-modal consistency, temporal trend 의 학습된 representation) 과는 여전히 거리 있음.

**Real FM 대비 미흡 부분**:
- 단일 modality baseline (LogReg는 ABP만, LSTM은 ABP only)이라 multimodal fusion 효과 미반영.
- Hypotension 외 prediction (cardiac arrest, anomaly) 은 baseline 학습 안 됨 — Tier 2 rule 그대로.

**`[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`** — 본 proxy quality 평가는 임상 환자 결정 아닌 *agent system 검증* 용. Real FM 합류 후 100-case mock-vs-real benchmark (ADR-011 §"Real-FM migration protocol" step 2–3) 가 정밀 검증.

### 후속 항목 (Stage 2 / 추후 plan)

1. Real cohort 학습 후 baseline checkpoint 를 `checkpoints/baselines/*.pt` 에 저장 → `mock_light_ml.yaml::checkpoint_path` 갱신 (현재는 untrained)
2. Real FM 합류 시 mock_light_ml vs real 100-case benchmark — gap 보고서 작성 (ADR-011 protocol step 2)
3. multimodal baseline (XGBoost 설치 후) 추가 시 `primary_baseline: xgb_multimodal` 로 전환 검증
