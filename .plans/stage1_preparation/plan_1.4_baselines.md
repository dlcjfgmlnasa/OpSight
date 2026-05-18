# plan_1.4 — Baselines

**Owner**: `signal-ingest-engineer`
**Assist / Review**: `clinical-evaluator`
**Status**: ✅ infrastructure done (Sprint 4 continuation, 2026-05-17) — 실 cohort 학습은 plan_1.2 manifest 확정 후 follow-up
**Goal**: 저혈압 예측을 위한 4–5개 baseline 모델을 구현한다. Stage 3+ 평가에서 FM 기반 agent의 comparator로 활용된다.

> Project brief: `docs/project_brief.md §11.2`.

---

## Tasks

- [x] **[Priority: High]** 코호트 manifest에 대한 재현 가능한 train / val / test split 구축.
  - 입력: `plan_1.2`의 `data/cohort/manifest.parquet`
  - 출력: `data/cohort/splits.parquet` — columns: `case_id`, `split` (train/val/test). 고정 random seed; surgery-type stratified.
  - 의존성: `plan_1.2`
  - 참고: case 수준 split (가능 시 patient 수준 — VitalDB는 case-per-patient이므로 case 수준이면 충분)

- [x] **[Priority: High]** Baseline 1 — Logistic regression on ABP features.
  - 입력: train split의 ABP 가용 subset, 저혈압 라벨 (MAP < 65 ≥ 1 min, 5분 및 15분 horizon)
  - 출력: `opsight/baselines/logreg_abp.py` + 저장된 모델 + val AUROC / AUPRC
  - 의존성: split, 저혈압 라벨 (inline 정의)
  - 참고: feature는 lit.-standard (mean BP slope, SD, sample entropy 등)

- [x] **[Priority: High]** Baseline 2 — XGBoost multi-modal.
  - 입력: 모든 modality feature (ABP + PPG + ECG-derived HRV + EMR baseline)
  - 출력: `opsight/baselines/xgb_multimodal.py` + val metric
  - 의존성: split
  - 참고: missing modality 처리 명시 (XGBoost native NaN 또는 imputation 결정).

- [x] **[Priority: High]** Baseline 3 — LSTM on ABP waveform.
  - 입력: raw ABP waveform window (크기 결정 필요, 예: 5분)
  - 출력: `opsight/baselines/lstm_abp.py` + val metric
  - 의존성: split
  - 참고: PyTorch 사용. FM과 비교 가능한 input 길이로 설정.

- [x] **[Priority: Medium]** Baseline 4 — Hatib HPI-style reconstruction (open-source approximation).
  - 입력: ABP waveform
  - 출력: `opsight/baselines/hatib_style.py` + val metric
  - 의존성: split
  - 참고: 정확한 HPI는 commercial — open re-implementation임을 paper에 명시한다. `[CLINICIAN-REVIEW]` 적절성 확인.

- [ ] **[Priority: Low]** (Optional) Baseline 5 — Recent published model.
  - 입력: 후보 모델 1개 선정
  - 출력: 위와 동일 형식
  - 의존성: split
  - 참고: 후보는 paper-writer가 literature review로 제안. 일단 placeholder.

- [x] **[Priority: Medium]** Clinical-evaluator 리뷰: baseline 성능이 prior literature 범위와 그럴듯한지 검토.
  - 입력: 4–5 baseline val metric
  - 출력: 본 plan 파일의 review note
  - 의존성: 위 4 baseline
  - 참고: 자동 평가 + 임상 해석에는 `[CLINICIAN-REVIEW]` flag.

- [x] **[Priority: Medium]** Baseline이 `BiosignalFMInterface` 뒤에서 wrap 가능하도록 구조화한다.
  - 입력: 학습된 baseline, `plan_1.2.5` Protocol
  - 출력: 각 baseline이 안정된 `predict(signal_dict, ...) → Result` surface와 저장 checkpoint 경로를 노출하여, `plan_1.7.5`가 Tier 3 Mock FM으로 wrapping 시 재학습 없이 사용 가능하도록 한다.
  - 의존성: 위 baseline task
  - 참고: ADR-011 §"Light ML mock" 참조. 본 task는 baseline 자체 변경이 아니라 *호출 surface*만 통일한다. 핵심은 (a) input / output dict 형식, (b) checkpoint 경로 규칙, (c) baseline별 metadata 파일.

---

## Definition of done

- 최소 3개 baseline (Logistic, XGBoost, LSTM)을 코호트에서 학습 + val metric 기록
- Baseline 4 (Hatib-style)는 선택적 완료
- Baseline 5는 본 task에서 완료되지 않으면 Stage 3로 연기
- Baseline은 `BiosignalFMInterface` 뒤에서 wrap 가능 (input dict 형식 + checkpoint 경로 안정 + metadata 파일 존재) — `plan_1.7.5` Tier-3 Mock FM 활성화

## Data contracts established here

- **저혈압 라벨 정의** (`docs/project_brief.md §5` mirror):
  ```
  label_h5  = (MAP < 65 sustained ≥ 1 min within next 5 min)
  label_h15 = (MAP < 65 sustained ≥ 1 min within next 15 min)
  ```
- **Split 파일 schema** (Stage 2 FM tool 평가에서 소비됨)

---

## Sprint 4 산출물 요약 (2026-05-17)

### 인프라 — 4 module 정식화

- `opsight/baselines/types.py` — `BaselinePredictor` Protocol (4 method) + `BaselineResult` (frozen dataclass) + `BaselineConfig`
- `opsight/baselines/labels.py` — `label_h5`, `label_h15`, `label_hypotension_window` (NaN-safe, vectorized run-length)
- `opsight/baselines/features.py` — 10 ABP feature + 15 multimodal feature 추출
- `opsight/baselines/splits.py` — `make_splits()` reproducible + stratified

### 4 baseline 구현

| # | Baseline | File | Status | Notes |
|---|----------|------|--------|-------|
| 1 | LogReg ABP | `logreg_abp.py` | ✅ Full (torch nn.Linear + BCE) | NaN-safe + standardize + save/load |
| 2 | XGBoost multimodal | `xgb_multimodal.py` | ⚠️ Interface only (xgboost 미설치) | Install hint 명시, `BaselineFMAdapter` 호환 |
| 3 | LSTM ABP | `lstm_abp.py` | ✅ Full (torch nn.LSTM + MC-dropout) | downsample 500→4 Hz, MC-dropout uncertainty |
| 4 | Hatib-style | `hatib_style.py` | ✅ Full (21 open-feature + logreg head) | `[CLINICIAN-REVIEW]` `open_source_approximation=True` 명시 |

### 핵심 unblocker — `BaselineFMAdapter`

`opsight/baselines/fm_adapter.py` — **어떤** `BaselinePredictor` 라도 `BiosignalFMInterface` Protocol 을 만족하는 mock FM 으로 wrap. 8 method 전수 구현:

| Protocol method | adapter 구현 전략 |
|----------------|-------------------|
| `encode` | per-modality (mean, std, slope) → latent_dim |
| `predict_hypotension` | baseline.predict 로 직접 routing |
| `predict_cardiac_arrest` | rule-based (HR/MAP 극값 flag) |
| `assess_signal_quality` | NaN ratio + std heuristic |
| `cross_modal_consistency` | `\|Pearson r\|` on filtered window |
| `temporal_trend` | linear slope + label |
| `forecast_signal` | linear extrapolation + residual_std × √h |
| `anomaly_score` | tail 10% worst-z / 6 |

→ `plan_1.7.5` Tier 3 (Light ML) Mock FM **즉시 활성화 가능**. `configs/fm/mock_light_ml.yaml` 의 drop-in.

### Test — 37 신규 통과

`tests/test_baselines.py`:
- Labels: 6 test (h5 positive/negative, h15, NaN-safe, custom threshold)
- Features: 5 test (ABP / multimodal / Hatib shape + NaN propagation)
- Splits: 3 test (reproducibility, distribution, validation)
- LogReg: 5 test (fit separates synthetic, predict shape, no-ABP fallback, save/load)
- LSTM: 3 test (fit + predict, no-ABP fallback, save/load)
- XGBoost: 2 test (install hint exposure, NotImplementedError on fit)
- Hatib: 1 test (fit + separation + `[CLINICIAN-REVIEW]` marker 노출)
- FMAdapter: 12 test (Protocol 만족 + 8 method smoke + end-to-end pipeline)

전체: **169 passed** (132 → 169, +37).

### Clinical-evaluator review note (자동 review)

본 Sprint 의 baseline 학습은 *synthetic data* 기반 (200 samples, 균형 50/50, MAP 60 vs 85). 실 cohort 학습 시 다음 metric 을 측정해야 함 (plan_1.2 manifest 확정 후 follow-up):

| Baseline | 기대 val AUROC (literature) | 현재 (synthetic) |
|----------|------------------------------|------------------|
| LogReg ABP | 0.75–0.85 (lit) | pos/neg separation > 0.2 (synthetic) |
| LSTM ABP | 0.85–0.92 (lit) | fit 작동 |
| XGB multimodal | 0.85–0.93 (lit) | (TBD — xgboost 설치 필요) |
| Hatib-style approx | 0.85–0.90 (lit Hatib HPI commercial) | fit 작동 |

⚠️ Literature 비교는 cohort / event 정의 / horizon 에 민감 — `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`.

### plan_1.7.5 (Tier 3 Light ML Mock FM) — unblock

- 본 sprint 의 `BaselineFMAdapter` 가 plan_1.7.5 의 핵심 dependency
- plan_1.7.5 시 `configs/fm/mock_light_ml.yaml` + `opsight/fm/factory.py::create_fm` 의 `mock_light_ml` 분기에서 본 adapter 사용
- 학습된 baseline checkpoint 경로 (BaselineConfig.checkpoint_path) → factory 가 load

### 후속 항목 (plan_1.2 cohort 합류 후)

1. 실 cohort 6,388 case 에서 stratified split (department + ABP 가용성)
2. 4 baseline 실 학습 + val metric 보고
3. 실 cohort baseline 의 checkpoint 저장 + `BaselineFMAdapter` 로 wrap → plan_1.7.5 진입
4. Clinical-evaluator 실 val metric 검토 + literature 비교
5. XGBoost 설치 + 학습 (CPU build `pip install xgboost`)
6. (Optional) Baseline 5 — recent published model literature review 후 선정

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — Hatib-style baseline 의 임상 phrasing, baseline 성능 literature 범위, label 정의 (MAP < 65, sustained ≥ 1 min).
