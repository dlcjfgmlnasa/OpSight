# VitalAgent — Project Brief (Master Context)

> 프로젝트 정체성, 범위, 설계 결정에 대한 **단일 진실 원천 (Single Source of Truth, SoT)**.
> `.claude/agents/*.md`와 `.plans/*.md`는 모두 본 파일을 참조한다. 본 brief가 변경되면
> 하위 문서들은 그에 맞게 재조정되어야 한다.
>
> 마지막 갱신: 2026-05-16. 상태: **Stage 1 (Month 1–2) — Preparation**.

---

## 1. 프로젝트 정체성 (Project Identity)

- **이름**: VitalAgent
- **Tagline**: *A universal, modality-agnostic, quality-aware LLM agent for real-time intraoperative hemodynamic reasoning, powered by a cross-domain pretrained multimodal biosignal foundation model.*
- **작업 디렉토리**: `C:\Projects\VitalAgent\`
- **목표 venue**: npj Digital Medicine
- **제출 목표 시점**: Month 10 (≈ 2026 Q4 — 정확한 날짜 TBD)

### 핵심 특성 (Core characteristics)

1. **Universal** — 모든 비심장 주요 수술 (non-cardiac major surgery; general / thoracic / urologic / gynecologic)
2. **모달리티 비의존 (modality-agnostic)** — 가용한 신호만으로 동작한다
   - ⚠️ 층화 규칙 (stratification rule): ABP 가용성은 **department와 강하게 상관**한다 (Thoracic surgery 97.5% 존재, General surgery 48.1% 존재 — `docs/findings/pre_phase3_findings.md §5` 참조). modality-agnostic 주장의 평가는 ABP-absent 비율을 **department별 stratified**로 보고해야 한다. Aggregate 단일 수치 보고는 허용되지 않는다.
3. **신호 품질 인지 (quality-aware)** — 신호 품질이 저하되면 불확실성 (uncertainty)을 정직하게 표현한다
4. **수술 인지 (surgery-aware)** — 수술 (surgery) 유형에 따라 추론 방식이 적응한다
5. **시뮬레이션된 실시간 (simulated real-time)** — 30초 Shallow cycle + on-demand Deep 모드

---

## 2. 문제 정의 (Problem Statement / Why Now)

수술기 혈역학적 불안정성 (perioperative hemodynamic instability), 특히 저혈압 (hypotension)은 술후 합병증 (postoperative morbidity)의 주요 조정 가능 요인이다. 그러나 기존 조기 경보 시스템 (early-warning system)은 일반적으로 다음 특성을 가진다.

- 단일 모달리티 (single-modality) — ABP만 활용 (예: Hatib 방식)
- 신호 품질과 불확실성에 대해 침묵함
- surgery-aware 아님
- 시간 압박 하의 임상의 (clinician)에게 해석 불가능

VitalAgent의 가설: multimodal biosignal Foundation Model 위에 놓인 **tool-using LLM agent**는 근거에 충실하고 자신의 한계에 정직한, **interpretable·quality-aware·surgery-aware**한 술중 (intraoperative) 추론을 제공할 수 있다.

<!-- TODO: expand clinical motivation with citations once paper outline starts -->

---

## 3. Foundation Model 맥락 (Foundation Model Context — separate ongoing project)

FM은 별도 프로젝트 `C:\Projects\Biosignal-Foundation-Model\`에서 개발 중이다. VitalAgent는 FM을 가중치 동결된 (frozen) tool backend로 **소비**할 뿐, FM 학습 코드는 수정하지 않는다.

- **Pretraining 데이터**: K-MIMIC ICU (SNUH)
- **모달리티**: ECG, ABP, PPG, CVP, PAP, ICP (6 신호)
- **Context window**: 600 patch = 10분
- **아키텍처 구성요소**: Loc/Scale Injection, Dual Additive Embedding, GQA + RoPE + GLU FFN, Binary Attention Bias, Mixture of Experts, Efficient Sequence Packing
- **Pretraining objectives**: MPM, NPP, CMPM, CMCL (InfoNCE)
- **2-phase curriculum**: Channel-Independent → Cross-Modal Alignment
- **Cross-modal pairs**:
  - Tier 1: ECG↔ABP, ECG↔PPG, ABP↔PPG
  - Tier 2: CVP↔PAP, ABP↔ICP, ABP↔PAP
- **상태**: 학습 진행 중, 약 2개월 후 완료 예정 → 그 사이에 VitalAgent를 멈추지 않기 위해 **§3.5 Mock FM Strategy** 채택
- **13 downstream tasks** (병행 학습 중; Stage 2에서 통합):

| # | Task | 확정 여부 |
|---|------|-----------|
| 1 | Arrhythmia classification | ✅ |
| 2 | MI detection | ✅ |
| 3 | Hypotension prediction | ✅ |
| 4 | Cardiac arrest prediction | ✅ |
| 5 | Sepsis prediction | ✅ |
| 6 | Mortality prediction | ✅ |
| 7 | PO-AKI prediction | ✅ |
| 8 | Extubation success | ✅ |
| 9 | Cross-modal reconstruction + intra-modal forecasting | ✅ |
| 10–13 | <!-- TODO: 4 additional downstream tasks — not yet confirmed --> | ⏳ |

---

## 3.5. Mock FM 전략 (Mock FM Strategy)

실제 FM은 Stage 1 (약 2개월) 전체를 학습에 사용한다. agent system 작업이 멈추는 것을 막기 위해 VitalAgent는 안정적인 Interface Protocol 뒤에서 **3-tier mock**으로 개발하고, Stage 2 시작 시점에 real FM으로 교체한다.

| Tier | 이름 | 시점 | 목적 |
|------|------|------|------|
| 1 | Stub mock | Week 1 | Interface 고정 + latency 시뮬레이션 |
| 2 | Rule-based mock | Week 4 | plausible I/O로 agent reasoning 검증 |
| 3 | Light ML mock *(optional)* | Week 6 | Stage 1.4 baselines를 wrapping한 real-FM proxy |

**Interface Protocol** (`vitalagent/fm/interface.py`):
`runtime_checkable` `BiosignalFMInterface`, 8개 메서드 (`encode`, `predict_hypotension`, `predict_cardiac_arrest`, `assess_signal_quality`, `cross_modal_consistency`, `temporal_trend`, `forecast_signal`, `anomaly_score`). Result dataclass는 모든 tier와 real FM이 공유한다.

**Swap 메커니즘**: `configs/fm/default.yaml`의 `fm.implementation ∈ {mock_stub, mock_rule_based, mock_light_ml, real}` 필드. agent code는 Protocol에만 의존하므로 swap은 config 변경만으로 완료된다.

**Real-FM 마이그레이션 (Month 3 시작 시점)**:
1. Real FM이 `BiosignalFMInterface`를 만족하는지 검증한다.
2. 100 case에서 `mock_rule_based` vs `real` 비교 + 메서드별 gap 보고서 생성한다.
3. Config를 `real`로 전환하며 `mock_rule_based`는 fallback으로 유지한다.
4. Graceful degradation: real-FM 실패 시 자동 fallback + 알림.

전체 근거, 검토한 대안, 결과, 위험: **ADR-011** (`docs/decisions/ADR-011-mock-fm-strategy.md`).

구현 plan:
- `.plans/stage1_preparation/plan_1.1.5_mock_fm_stub.md`
- `.plans/stage1_preparation/plan_1.2.5_fm_interface_spec.md`
- `.plans/stage1_preparation/plan_1.6.5_mock_fm_rule_based.md`
- `.plans/stage1_preparation/plan_1.7.5_mock_fm_light_ml.md` *(optional)*

---

## 4. 데이터셋 — VitalDB (Dataset)

- **출처**: https://vitaldb.net (PhysioNet에도 미러링됨)
- **참조**: Lee HC et al. *Sci Data* 2022. doi:10.1038/s41597-022-01411-5
- **규모**: 6,388 case (SNUH 비심장 (non-cardiac) 수술, 2016년 8월 – 2017년 6월)
- **API**: `vitaldb` Python library
- **라이선스**: 학술 무료 공개
- **수술 유형**: general/abdominal, thoracic, urologic, gynecologic
- **Waveform 모달리티** — 우선순위 채널 선별 (전체 enumeration은 `plan_1.1`에서 수행):
  - `SNUADC/ART` — invasive arterial pressure (radial)
  - `SNUADC/PLETH` — PPG
  - `SNUADC/ECG_II` — ECG lead II
  - `BIS/EEG1_WAV` — EEG
  - `Primus/CO2` — capnography (호기말 이산화탄소)
  - `Primus/AWP` — airway pressure
  - `Primus/EXP_SEVO` / `Primus/INSP_SEVO` — sevoflurane (호기 / 흡기)
  - <!-- TODO: full waveform-channel list (target: 12) — vitaldb-domain-expert to enumerate in plan_1.1 from the 196-track listing -->
- **Numerics**: `Solar8000/ART_MBP`, `Solar8000/NIBP_MBP`, HR, SpO2, `Orchestra/*` drug effect-site (§4.3 참조) 등
- **73 perioperative clinical parameters** (case 단위)
- **34 time-series lab parameters**

### 4.2 `abp_any` 운용 정의 (operational definition)

코호트의 "ABP available" 플래그는 tool, baseline, 평가, Mock FM Tier 2가 모두 동일한 정의로 참조한다.

| Tier | 채널 |
|------|------|
| **Primary** (invasive ABP 주장 시 기본) | `SNUADC/ART` (raw waveform) **또는** `Solar8000/ART_MBP` (numeric MAP) |
| **Extended** (`abp_any` 기본값) | Primary **또는** `EV1000/ART_MBP` **또는** `Solar8000/FEM_MBP` |

기본값: **`abp_any`는 Extended를 사용한다.** tool의 docstring에서 명시적으로 재정의하는 경우에만 변경된다.
`[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` — `EV1000/ART_MBP` (case의 9.3%)와 `Solar8000/FEM_MBP` (2.2%)를 radial line의 `SNUADC/ART`와 동등하게 modality-agnostic 평가에 포함할지, 별도 "central/femoral ABP" 카테고리로 분리할지 결정 필요.

### 4.3 마취제 (anesthetic) channel 우선순위

tool 8 `query_anesthesia_drugs` 및 anesthetic-effect-site 채널이 필요한 FM 입력은 다음 case-level 가용성을 따른다.

| 채널 | % cases | 역할 |
|------|---------|------|
| `Orchestra/RFTN20_*` (레미펜타닐, remifentanil) | **74.7%** | **first-class** (진통제, analgesic) — 가장 가용한 effect-site 채널 |
| `Orchestra/PPF20_*` (프로포폴, propofol) | 55.0% | first-class (최면제, hypnotic) |
| `Primus/EXP_SEVO` / `INSP_SEVO` (세보플루레인, sevoflurane) | 57.7% | first-class (흡입 최면제) |
| `Orchestra/ROC_*` (rocuronium) | 4.4% | secondary (근이완제, muscle relaxant) |
| `Orchestra/PHEN_*` (phenylephrine) | 2.0% | 혈관활성 (vasoactive) — tool 9에서 처리 |

수술 유형에 따라 어떤 채널이 더 중요한지가 달라진다. `query_anesthesia_drugs`는 가용한 모든 first-class 채널을 반환하며 임의로 하나를 선택하지 않는다. (2026-05-16 `docs/findings/pre_phase3_findings.md`로부터 패치: RFTN이 PPF보다 가용성이 높다는 데이터를 바탕으로 first-class로 승격됨.)

### 4.1 코호트 정책 (Cohort policy — minimal filter)

| 규칙 | 처리 |
|------|------|
| 수술시간 < 30분 | 제외 |
| 모든 신호 완전 결손 | 제외 |
| 환자 정보 완전 결손 | 제외 |
| ABP 없는 case | **포함** (modality-agnostic 시연을 위해) |

**`<30 min` 필터 적용 후 코호트 크기**: **5,946 cases** (2026-05-16 측정; raw 6,388 − 442 단시간 case).

#### 보류 중인 임상 결정 — `plan_1.2`의 manifest 확정을 블록함

`[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` `[DECISION PENDING]`

`plan_1.2`가 최종 manifest를 산출하기 전에 다음 두 가지 코호트 범위 질문이 해결되어야 한다.

1. **Pediatric inclusion** (`age < 18`): VitalDB에는 18세 미만 환자가 포함된다 (관찰된 최소값: 0.3세, 최소 체중 4.8 kg, 최소 신장 42 cm — `docs/findings/pre_phase3_findings.md §3`). brief는 연령 컷오프에 대해 침묵한다. 선택지:
   - (A) 모든 연령 포함 — 가장 넓은 코호트
   - (B) 성인만 (`age ≥ 18`) — 많은 수술기 연구의 표준; 코호트 축소 + confounder 제거
2. **`ASA = 6` inclusion**: VitalDB에는 ASA 6 (뇌사 장기 기증자, brain-dead organ donor) case가 존재하며 이는 transplantation 사례로 추정된다. 선택지:
   - (A) 포함 — 장기 기증 case 구성 보존
   - (B) 제외 — 생리적으로 distinct하며 baseline을 왜곡할 가능성

두 결정에 따라 최종 코호트 크기가 변동한다. tracking entry는 `master_plan.md §8 Risk Register`에 위치한다.

---

## 5. 저혈압 (hypotension) 이벤트 정의 (Event Definition)

- **Primary outcome (주요 결과지표)**: MAP < 65 mmHg가 ≥ 1분 지속
- **Secondary (severe)**: MAP < 55 mmHg ≥ 1분
- **예측 horizon**: 5분, 15분
- **레이블 소스**:
  - ABP 가용 시: invasive MAP
  - ABP 부재 시: `NIBP_MBP` (cuff)를 surrogate로 사용

> ⚠️ 본 threshold는 *label*의 운용 정의다. 개입 시점에 대한 임상 권고가 **아니다**. 개입 threshold는 임상적으로 변화 중인 질문이며 임상의의 판단 영역에 속한다.
> `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`

---

## 6. 이중 모드 아키텍처 (Dual-Mode Architecture)

### 6.1 Shallow Mode (30초마다)

- FM forward pass
- 5–6개 "quick" tool 병렬 호출
- **Light LLM**: Llama-3.1-8B (4-bit, vLLM)
- 출력: 구조화된 score + 1문장 한글 narration
- **Latency 목표**: < 15초 <!-- TODO: actual measured latency, Stage 1 -->

### 6.2 Deep Mode (event-triggered)

- 21-tool suite 전체 (ADR-016 — Signal Access 카테고리 추가 후)
- **Heavy LLM**: Llama-3.3-70B (4-bit, vLLM, streaming)
- 출력: 9-section 한글 브리프 (500–800 tokens)
- **Latency 목표**: < 60초 <!-- TODO: actual measured latency, Stage 1 -->

### 6.3 Deep-mode trigger (7개) — rule-based, NOT LLM

1. Hypotension risk > 0.7
2. Risk 급상승 (Δ > 0.3 in 30 sec)
3. 신호 품질 저하 (avg drop > 0.3)
4. Cross-modal inconsistency (< 0.4 with good quality)
5. Acute event warning (arrest > 0.5)
6. 임상의 on-demand 요청
7. 주기적 deep check (5분마다)

**Cooldown**: deep trigger 간 60초 (단, 새로운 사유 발생 시 무시).

---

## 7. Tool Suite — 21 tools

> 2026-05-17 업데이트 (ADR-016 Accepted): 16 → 21 tool. 신규 카테고리 **Signal Access (5)** 추가. 자세한 rationale 은 `docs/decisions/ADR-016-signal-access-tools.md`.

### 7.1 FM-based (7)

| # | Tool | Signature (sketch) |
|---|------|--------------------|
| 1 | `predict_hypotension` | `(case_id, horizon ∈ {5,15}) → {risk, uncertainty}` |
| 2 | `predict_cardiac_arrest` | `(case_id, horizon=5) → {risk, uncertainty}` |
| 3 | `assess_signal_quality` | `(case_id, modality, window) → quality_score` |
| 4 | `cross_modal_consistency` | `(case_id, modality_pair, window) → consistency_score` |
| 5 | `temporal_trend_analysis` | `(case_id, modality, window) → trend_summary` |
| 6 | `forecast_signal` | `(case_id, modality, horizon) → forecast` |
| 7 | `anomaly_score` | `(case_id, modality, window) → anomaly` |

### 7.2 EMR-based (5)

| # | Tool | Signature (sketch) |
|---|------|--------------------|
| 8 | `query_anesthesia_drugs` | `(case_id, time_window)` |
| 9 | `query_vasoactive_drugs` | `(case_id, time_window)` |
| 10 | `query_fluid_blood` | `(case_id, time_window)` |
| 11 | `query_surgery_progress` | `(case_id, current_time)` |
| 12 | `query_patient_baseline` | `(case_id)` |

### 7.3 Knowledge / Comparative (2)

| # | Tool | Signature (sketch) |
|---|------|--------------------|
| 13 | `find_similar_cases` | `(current_state, surgery_type, k=5)` |
| 14 | `intervention_response_prediction` | `(intervention, dose)` |

### 7.4 Auxiliary (2)

| # | Tool | Signature (sketch) |
|---|------|--------------------|
| 15 | `surgery_context_awareness` | `(surgery_type, phase)` |
| 16 | `quality_aware_synthesis` | `(predictions, qualities)` |

### 7.5 Signal Access (5) ★ ADR-016 신규

LLM 이 *현재 vital 값 / 통계 / 변동성 / baseline 비교* 에 explicit 하게 접근하기 위한 deterministic signal-access tool. 브리프 §8.2 [Signal status] / §8.1 [Surgery context] / §8.5 [Evidence] section 의 정량 claim source. *명명 정책*: ADR-014 의 "Current State Assessment" (학습 capability) 와 구분하기 위해 본 카테고리는 **"Signal Access"** 로 통일 (자세한 건 ADR-016 §"명명 정책").

| # | Tool | Signature (sketch) |
|---|------|--------------------|
| 17 | `get_current_vitals` | `(case_id, time) → {MAP, SBP, DBP, HR, RR, SpO2, EtCO2, BIS, core_temp}` |
| 18 | `describe_signal` | `(case_id, modality, window_min=5) → {mean, std, min, max, median, IQR, missing_ratio, n_samples}` |
| 19 | `assess_variability` | `(case_id, modality, window_min=5) → {HRV (SDNN/RMSSD/LF-HF), BPV (SD/ARV), or SVV}` |
| 20 | `compare_to_baseline` | `(case_id, modality, current_time) → {baseline_value, current_value, absolute_change, percent_change, direction}` |
| 21 | `summarize_current_state` | `(case_id, time) → {hemodynamic_state, anesthesia_state, respiratory_state, key_concerns, overall_assessment}` — Tool 21 의 full 구현은 ADR-014 Accepted 후 (Tier 0 #14–16 wrap); 그 전에는 **rule-based stub** `[DECISION PENDING ADR-014]` |

> Tool 17–20 은 deterministic (numpy/pandas). Tool 21 의 stub→full 전환은 `ADR-014` 의존.
> JSON-schema 수준의 상세 spec 은 `.plans/stage1_preparation/plan_1.7_tool_spec.md` (1–16) + `.plans/stage1_preparation/plan_1.3.5_signal_access_tools.md` (17–21).

---

## 8. 브리프 형식 (Brief Format — Deep Mode 출력) — 9 Sections

출력 언어: **한글**. 길이: **500–800 tokens**.

1. **[Surgery context]** — 수술 유형, phase, 경과 시간 · *source: tool 11 `query_surgery_progress` + tool 21 `summarize_current_state` (+15 priors)*
2. **[Signal status]** — modality 가용성 + 현재 vital 값 + modality별 품질 + cross-modal consistency · *source: **tool 17 `get_current_vitals` + tool 18 `describe_signal`** + tool 3 `assess_signal_quality` + tool 4 `cross_modal_consistency`*
3. **[Assessment confidence]** — `HIGH / MEDIUM / LOW / UNRELIABLE` · *source: tool 3 + tool 4*
4. **[Risk evaluation]** — 주요 risk score 및 horizon · *source: tool 1 + tool 2*
5. **[Evidence]** — modality별 trend + cross-modal validation + 변동성 + baseline 대비 변화 · *source: tool 5 + tool 6 + tool 7 + **tool 19 `assess_variability` + tool 20 `compare_to_baseline`***
6. **[Intraoperative context]** — anesthetic, vasopressor, fluid, surgery phase · *source: tool 8 + tool 9 + tool 10 (+11)*
7. **[Similar trajectory]** — N개 similar case (가용 시) · *source: tool 13 `find_similar_cases`*
8. **[Recommendations]** — 임상적 *고려사항* (특정 dose 제시 금지) `[CLINICIAN-REVIEW]` · *source: LLM 합성 + tool 14 (intervention response)*
9. **[Limitations]** — 신호 품질 문제, 누락된 modality, 기타 caveat · *source: 모든 tool 의 `quality_meta`*

> Tool source mapping 의 정식 명세는 `docs/decisions/ADR-016-signal-access-tools.md` §"브리프 §[Signal status] / §[Surgery context] 의 tool source 명시".

### 8.1 Shallow Mode 출력 (Light LLM)

- 형식: 1문장, ≤ 50 tokens, 한글
- 상태별 톤:
  - **안정** (모든 risk < 0.3): 짧고 담백
  - **주의** (0.3–0.5): 추세 명시
  - **경고** (0.5–0.7): 명확한 우려
  - **위험** (> 0.7): "Deep mode 권고" 포함

---

## 9. 5-Stage 계획 (5-Stage Plan)

| Stage | 기간 (months) | 핵심 산출물 | 담당 agent (lead) |
|-------|---------------|-------------|-------------------|
| **1. Preparation** | 1–2 | VitalDB exploration, EMR tools, baselines, dual-mode infra | vitaldb-domain-expert, signal-ingest-engineer, langgraph-engineer, llm-prompt-engineer |
| **2. FM integration** | 3–4 | FM 통합 + FM-based tools 구현 | langgraph-engineer, signal-ingest-engineer |
| **3. Full agent** | 5–6 | Full agent integration + internal validation | langgraph-engineer, llm-prompt-engineer, clinical-evaluator |
| **4. Clinician eval** | 7–8 | 임상 평가 (5–7 anesthesiologists, 200–300 briefs) | clinical-evaluator, project-planner |
| **5. Paper** | 9–10 | 논문 작성 + npj DM 제출 | biomedical-ai-paper-writer |

Stage 1 상세 sub-plan은 `.plans/stage1_preparation/plan_1.{1..8}_*.md`에 있다.
Stage 2–5는 현재 **placeholder README**만 존재하며, 선행 stage가 완료에 가까워질 때 상세를 채운다.

---

## 10. 실시간 프레이밍 (Real-time Framing)

**본 PoC (Proof-of-Concept, 개념 증명)의 "실시간" = 시뮬레이션된 실시간 (simulated real-time)**이며 prospective가 아니다.

- 환자 timeline이 VitalDB recording의 시간 순서대로 streaming된다
- 시점 t에서는 t 이하의 데이터만 접근 가능하다 (data-leakage guard)
- Wall-clock latency는 30초 cycle 목표에 대해 측정된다
- 목표 hardware에서 30초 cycle 실행 가능성을 검증한다

**True prospective 배포**: 본 PoC의 범위 밖. NRF 도전형 2–3년차 후속 과제로 예정.

---

## 11. 평가 프로토콜 (Evaluation Protocol)

### 11.0 Department별 stratified 보고 (mandatory)

Aggregate 단일 수치는 충분하지 않다. ABP 가용성과 수술 복잡도가 department와 강하게 상관하기 때문에, 다음 항목은 `department`별 (general / thoracic / urologic / gynecologic)로 + aggregate로 **모두 보고**되어야 한다.

- ABP-absent 비율
- AUPRC, AUROC, sens@spec
- Latency 분포
- 브리프 9-section faithfulness score
- 임상의 평가 Likert score

작은 subgroup (Urology n ≈ 94 post-filter)에 대해서는 collapse하지 말고 **넓은 신뢰구간 (wide confidence interval)**으로 보고한다. `master_plan.md §8 Risk Register` 참조.

### 11.1 3-layer 평가

1. **자동 metric (Automated metrics)**
   - 예측의 AUPRC, AUROC, sens@spec
   - Faithfulness (atomic-claim grounding)
   - Tool selection precision / recall
   - Latency 분포
2. **LLM-as-judge** (Llama 출력을 Claude가 판정)
3. **임상의 평가 (Clinician evaluation)**
   - **5–7명 anesthesiologists** (이형철 교수님 그룹) <!-- TODO: confirm exact N (5 vs 7) -->
   - **200–300 브리프** 평가
   - Baselines와 blinded 비교
   - 5-point Likert × 5 차원
   - Inter-rater agreement: Cohen's κ

### 11.2 Baselines

- Logistic regression (ABP features)
- XGBoost multi-modal
- LSTM (ABP waveform)
- Hatib HPI-style reconstruction
- (Optional) Recent published model — TBD

### 11.3 Validation scope

- **External validation**: PoC에서는 VitalDB 단일 데이터셋만 사용
- **Future**: MOVER, INSPIRE 등 추가 가능 (PoC 범위 밖)

---

## 12. 기술 스택 (Technology Stack)

| Layer | 선택 |
|-------|------|
| Orchestration | LangGraph |
| LLM inference | vLLM |
| Quantization | 4-bit |
| Light LLM | Llama-3.1-8B |
| Heavy LLM | Llama-3.3-70B |
| FM framework | PyTorch |
| Data API | `vitaldb` Python library |
| Storage | parquet / sqlite (cohort + events) |
| GPU | 2× L40S 48GB (GPU1: FM + Light LLM, GPU2: Heavy LLM) |

---

## 13. 프로젝트 전반 강제 규칙 (Project-wide Hard Rules)

본 규칙은 모든 agent의 system prompt에 동일하게 반영된다.

### 13.1 ⚠️ Clinical Fact Guard (임상 사실 가드)

본 프로젝트는 수술기 모니터링 도메인에서 동작한다. 어떤 agent도 임상 결정을 단독으로 단정하지 않는다. 임상 상태, 진단 (diagnosis), 약물 효과, 예후 (prognosis)를 단정하는 모든 문장은 다음 중 하나여야 한다.

- `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` marker가 붙어 있거나
- 조건문 (conditional) 형태로 재서술 (예: "수치는 X이며 임상의 판단 필요")

실제 임상 해석은 임상의 협력자 (이형철 교수님 그룹)의 소유다. 본 repo 내 어떤 agent의 영역도 아니다.

### 13.2 데이터 누수 (data leakage) 금지

시뮬레이션 시점 t에서는 t 이하의 데이터만 읽을 수 있다. 본 규칙을 위반하는 tool은 조용히 통과하지 않고 명시적으로 실패해야 한다.

### 13.3 Trigger 로직은 rule-based

Deep-mode trigger (§6.3)는 deterministic rule 코드이며 LLM-driven이 아니다.

### 13.4 한글 우선 보고 (Korean-first reporting)

사용자 대상 브리프, planner 보고, 임상의 검토용 출력은 기본이 한글이다. tool I/O, 코드 식별자, paper draft에는 영문이 허용된다.

---

## 14. 미결 TODO (Open TODOs — tracked for resolution)

- [ ] 13-task FM downstream lineup 중 남은 4개 task 확정 (§3)
- [ ] 2× L40S에서 측정된 실 shallow/deep latency 값 (§6) — Stage 1 인프라 완성 후 채운다
- [ ] 정확한 임상의 N 확정: 5 vs 7 (§11)
- [ ] 주요 design 결정에 대한 ADR — `docs/decisions/ADR-*.md`로 작성 (별도 task; ADR-011 Mock FM Strategy, ADR-016 Signal Access Tools 는 Accepted)
- [ ] 12-channel VitalDB modality 전체 목록 (§4) — `vitaldb-domain-expert`가 `plan_1.1_vitaldb_exploration.md`에서 enumerate

---

## 15. 상호 참조 (Cross-references)

- Agent 라인업 + plan 파일 담당: `.plans/master_plan.md`
- Stage 1 작업 분해: `.plans/stage1_preparation/plan_1.*.md`
- Agent별 정체성: `.claude/agents/*.md`
- Agent별 persistent memory: `.claude/agent-memory/<agent>/MEMORY.md`
- 용어집 (translation ground truth): `docs/terminology.md`
