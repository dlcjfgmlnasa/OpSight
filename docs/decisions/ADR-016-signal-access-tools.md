# ADR-016 — Signal Access Tools (Tool Suite 17–21)

- **Status**: **Accepted** (2026-05-17)
- **Decision drivers**: project-planner (proposal), signal-ingest-engineer (구현 owner — 17–20), langgraph-engineer (registry + Tier 0 wrapping for 21), llm-prompt-engineer (브리프 §[Signal status] / §[Surgery context] 소비자)
- **Related ADRs**: `ADR-014` (Tier 0 Current State Assessment — `[DECISION PENDING]`); Tool 21 의 stub→full 전환은 ADR-014 Accepted 시점에 발효.

> **명명 정책 (Naming policy)**: 본 ADR 은 *deterministic data access* 영역을 다룬다. **ADR-014 의 "Current State Assessment"** (학습된 supervised head — Tier 0 capability #14–16) 와 명칭이 인접하지만 의미 layer 가 다르다. 명칭 충돌을 회피하기 위해 본 카테고리는 일관되게 **"Signal Access Tools"** 로 부른다. 함수명 `get_current_vitals` / `summarize_current_state` 등은 *함수의 의미* 를 반영하므로 그대로 유지한다.
>
> 본 ADR 은 ADR-014 와 *상보적 (complementary)*. ADR-014 가 *학습된 현재 상태 평가 capability* (#14 hemodynamic state classification, #15 anesthesia state, #16 surgical phase) 를 정의한다면, ADR-016 은 *deterministic signal-access tool* (#17–21) 을 정의한다. LLM 이 raw signal 에 접근할 수 없으므로, 브리프 §[Signal status] / §[Surgery context] 작성에 필요한 *현재 vital 값 / 통계 / 변동성 / baseline 비교* 를 명시적 tool 호출로 노출한다.

---

## Context (배경)

### 발견된 누락

기존 16-tool suite (`docs/project_brief.md §7`) 의 카테고리 분포:

| 카테고리 | Tool 수 | 다루는 영역 |
|----------|---------|-------------|
| FM-based prediction (1–7) | 7 | **미래** (predict / forecast) + 신호 *품질* 평가 |
| EMR (8–12) | 5 | 약물 / 수액 / surgery progress / patient baseline |
| Knowledge / Comparative (13–14) | 2 | 코호트 retrieval + intervention response |
| Auxiliary (15–16) | 2 | surgery context priors + quality-aware fusion |

**누락 영역**: 현재 *vital 값* (MAP / HR / SpO₂ 등 *지금 이 순간*) + 통계 요약 + 변동성 (HRV / BPV) + baseline 비교 + 통합 현재 상태.

### Brief 작성 시 막힘 시나리오

LLM (Heavy 70B) 이 브리프 §[Signal status] / §[Surgery context] 작성 시:

- "현재 MAP 65 mmHg" 같은 **정량 claim** 이 필요한데, tool 1–7 은 *예측* 만 반환 (HypotensionResult.risk, ForecastResult.forecast 등 — 미래 값)
- Tool 5 `temporal_trend_analysis` 는 slope/label 만 반환, *현재 값* 아님
- LLM 은 raw waveform tensor 에 접근 못 함 (text-only)
- → 임상의가 가장 먼저 보는 정보 (**현재 vital, 변화 추세, baseline 대비 변화**) 의 source 가 prototype 에서 비어 있음

이는 `BiosignalFMInterface.predict_hypotension` 의 `meta` field 일부에 잡히긴 하지만 *공식 tool surface 가 아님* — LLM 에게 "어디서 가져왔는가" 출처가 모호.

### 임상 사고 흐름과의 정합성

ADR-014 §Context 가 명시한 임상 사고 흐름:

> **현재 상태 (state) → 추세 (trend) → 예측 (prediction) → 대응 (response)**

기존 tool 1–7 은 *추세 + 예측 + 대응* 만 cover. **현재 상태 자체의 explicit access** 가 빠짐 (ADR-014 가 *학습된 supervised capability* 를 추가하지만, 그것조차 raw vital 값 / 통계 / 변동성을 직접 노출하지는 않음).

---

## Decision (결정 — Accepted)

16-tool suite 를 **21-tool suite** 로 확장한다. 신규 카테고리 **Signal Access (5)** 를 추가 (#17–21).

### 신규 5 tool (Signal Access 카테고리)

| # | Tool | 목적 | Owner | Status |
|---|------|------|-------|--------|
| **17** | `get_current_vitals(case_id, time)` | 현재 vital 값 dict 반환 (MAP / SBP / DBP / HR / RR / SpO₂ / EtCO₂ / BIS / core_temp) | signal-ingest-engineer | plan_1.3.5 |
| **18** | `describe_signal(case_id, modality, window_min=5)` | 통계 요약 (mean / std / min / max / median / IQR / missing_ratio / n_samples) | signal-ingest-engineer | plan_1.3.5 |
| **19** | `assess_variability(case_id, modality, window_min=5)` | 변동성 metric — HR: HRV (SDNN, RMSSD, LF/HF), MAP: BPV (SD, ARV), PPG: amplitude variation / SVV | signal-ingest-engineer | plan_1.3.5 |
| **20** | `compare_to_baseline(case_id, modality, current_time)` | 기저값 (baseline) 대비 절대 / 비율 변화 + 방향 | signal-ingest-engineer | plan_1.3.5 |
| **21** | `summarize_current_state(case_id, time)` | 통합 현재 상태 평가 (hemodynamic / anesthesia / respiratory / key concerns / overall) | signal-ingest-engineer + langgraph-engineer (Tier 0 wrapping) | plan_1.3.5 **stub**; full 구현은 ADR-014 Accepted 후 (Tier 0 #14–16 wrap) |

### 21-tool 최종 카테고리 분포

| 카테고리 | 수 | Tool # |
|----------|----|--------|
| FM-based prediction | 7 | 1–7 |
| EMR | 5 | 8–12 |
| Knowledge / Comparative | 2 | 13–14 |
| Auxiliary | 2 | 15–16 |
| **Signal Access** ★ 신규 | **5** | **17–21** |
| **합계** | **21** | |

### 핵심 설계 원칙

1. **Tool 17–20 은 deterministic**: numpy / pandas 기반 계산 (HRV 는 NeuroKit2-style 또는 직접 구현). FM 호출 없음 — `BiosignalFMInterface` 무관.
2. **Tool 21 은 Tier 0 wrapping**: ADR-014 의 #14 (hemodynamic state classifier) + #15 (anesthesia state) + #16 (surgical phase) 출력을 합성. ADR-014 가 `[DECISION PENDING]` 인 동안 **rule-based stub** 으로 시작; ADR-014 Accepted 시 본격 wrap.
3. **Leakage guard**: 17–21 모두 `request.sim_time_s` 또는 `args.current_time` 이 `clock.now_s` 초과 시 `leakage_violation` (brief §13.2).
4. **Shallow / Deep 분배**:
   - Shallow (매 30 초 tick): **17** `get_current_vitals` + **20** `compare_to_baseline` — light, 빠름
   - Deep (event 시): 17–21 *전체* (브리프 §[Signal status] / §[Surgery context] 의 source)
5. **Clinical Fact Guard** (brief §13.1): 모든 tool 17–21 의 출력은 *측정값 / 통계량* 일 뿐 임상 결정 아님. Tool 21 의 `overall_assessment` 같은 합성 출력에는 `[CLINICIAN-REVIEW]` marker 필수.

### 브리프 §[Signal status] / §[Surgery context] 의 tool source 명시

Brief §8 (9-section template) 의 어느 section 이 어느 tool 을 소비하는지 명시:

| Brief section | 주 source tool | 보조 |
|---------------|----------------|------|
| [Surgery context] | 11 `query_surgery_progress` + **21 `summarize_current_state`** | 15 `surgery_context_awareness` |
| [Signal status] | **17 `get_current_vitals`** + **18 `describe_signal`** + 3 `assess_signal_quality` | 4 `cross_modal_consistency` |
| [Assessment confidence] | 3 `assess_signal_quality` + 4 `cross_modal_consistency` | — |
| [Risk evaluation] | 1 `predict_hypotension` + 2 `predict_cardiac_arrest` | — |
| [Evidence] | 5 `temporal_trend_analysis` + 6 `forecast_signal` + 7 `anomaly_score` + **19 `assess_variability`** + **20 `compare_to_baseline`** | — |
| [Intraoperative context] | 8 `query_anesthesia_drugs` + 9 `query_vasoactive_drugs` + 10 `query_fluid_blood` | 11 `query_surgery_progress` |
| [Similar trajectory] | 13 `find_similar_cases` | — |
| [Recommendations] | (LLM 합성) | 14 `intervention_response_prediction` |
| [Limitations] | (LLM 합성) | 모든 tool 의 `quality_meta` |

→ 본 매핑이 plan_1.6 의 Heavy LLM system prompt 에 반영되어야 한다 (plan_1.6 산출물 `prompts/v1_heavy_deep_brief.md` 의 worked-through 예시 갱신 follow-up).

---

## Alternatives Considered (검토한 대안)

| Alternative | Why considered / 기각 사유 |
|-------------|----------------------------|
| **(a) Tool 안 추가 — LLM 이 brief 작성 막힘** | 학습 부담 0. 그러나 LLM 이 brief §[Signal status] / §[Surgery context] 의 정량 claim source 가 모호 → faithfulness 평가 저하. 평가 시 "현재 vital 값이 어느 tool 출력인가" 질문에 답 못함. **기각**. |
| **(b) Tool 추가하되 FM-based 통합 — `predict_*` 류에 vital 정보 합성** | FM Result 의 `meta` 에 raw vital 값을 끼워 넣으면 *학습 모델의 출력* 으로 보이게 됨. Deterministic 측정값이 stochastic 예측과 섞이는 것은 ADR-011 의 "mock-vs-real swap" 깔끔함을 깨뜨림. **기각**. |
| **(c) Framework 가 자동 inject — context 안에 vital 값을 prompt 에 끼움** | Black box — LLM 이 *어디서 왔는지* 출처를 명시 못 함. faithfulness 평가에서 atomic-claim grounding 불가. brief §13 explicit reasoning 정책 위반. **기각**. |
| **(d) (제안) 5 deterministic tool 추가** | LLM tool-call 흐름이 명시적. Faithfulness 평가에서 tool 호출 trace 가 claim 의 출처. ADR-011 swap mechanism 보존. 학습 부담 0 (deterministic). **Accepted**. |

---

## Consequences (예상 결과)

### Positive

- 브리프 §[Signal status] / §[Surgery context] 의 정량 claim source 명확. Faithfulness 평가 (atomic-claim grounding) 가능.
- 임상 사고 흐름 (state → trend → prediction → response) 의 *state* 단계 explicit.
- ADR-011 swap mechanism 보존 — 17–20 은 deterministic, FM Interface 무관.
- 학습 부담 0 (Tool 21 의 stub 도 rule-based).
- Token efficiency — LLM 이 *필요할 때만* signal access 를 부르므로 매 prompt 에 raw 신호 끼우는 것보다 효율적.

### Negative

- Tool 수 16 → 21 — registry / catalog / charter / plan 파일 cross-ref 업데이트 필요 (본 ADR 시점에 일괄).
- Deep mode latency — 16 → 21 tool 호출 시 ~30% 추가 (병렬 호출로 mitigation; mock 환경 측정 시 5 신규 tool 합 < 50 ms 추정).
- Tool 21 (`summarize_current_state`) 의 full 구현은 ADR-014 Accepted 에 의존 — Stage 1 prototype 에서는 stub.

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Tool 21 stub 출력이 Tier 0 capability 미존재로 의미 없음 | Stub 은 *rule-based*: 17–20 출력을 합성한 휴리스틱 + `[CLINICIAN-REVIEW]` marker 명시. ADR-014 Accepted 시 Tier 0 #14–16 호출로 교체. |
| HRV 계산 (Tool 19) 의 metric 선택이 임상 부적절 | `[CLINICIAN-REVIEW]` — 기본 metric (SDNN, RMSSD, LF/HF) 은 lit-standard 이나 임상의 그룹 검토 후 조정. |
| `compare_to_baseline` (Tool 20) 의 baseline 정의 모호 | Baseline 정의: (1순위) `query_patient_baseline.baseline_bp` 등 preop 값, (2순위) intraop 초기 10 분 평균. 명시적 `meta.baseline_source` field 반환. |
| Brief §[Signal status] 가 21 tool 호출 trace 로 *너무 verbose* | Deep mode 만 17–21 전체 호출, Shallow 는 17, 20 만 호출. Brief LLM prompt 가 *필수 정량 claim* 만 인용하도록 plan_1.6 prompt v2 follow-up. |
| Tool 21 의 `overall_assessment` 가 임상 단정으로 새는 phrasing | Brief §13.1 (Clinical Fact Guard) 적용. Output schema 의 `overall_assessment` 는 **conditional phrasing** 만 허용 + `[CLINICIAN-REVIEW]` marker 반드시 포함. |

---

## Open questions (회의 안건)

1. **Tool 19 변동성 metric 선택**: HR 의 HRV (SDNN / RMSSD / LF/HF 모두 vs 1–2개만), MAP 의 BPV (SD vs ARV vs both), PPG 의 SVV (당장 구현 가능한 case 비율). 임상 reviewer 결정.
2. **Tool 20 baseline 정의**: preop_bp 우선 vs intraop early 10 min 우선. 두 source 가 모두 부재 시 fallback 정책.
3. **Tool 21 stub→full 전환 시점**: ADR-014 Accepted 후 zero-day 인가, plan_1.5 surgery_context.yaml 완성 후인가?
4. **Tool 17 dict schema**: 9 key (MAP, SBP, DBP, HR, RR, SpO₂, EtCO₂, BIS, core_temp) 가 충분한가? CVP, urine output 등 추가 필요한가?

---

## References (참조)

- `docs/project_brief.md` §7 (Tool Suite — 21 으로 갱신)
- `docs/project_brief.md` §8 (Brief format — 9 section 의 tool source mapping)
- `.plans/master_plan.md` §3, §4, §5, §7 (21-tool 반영)
- `.plans/stage1_preparation/plan_1.3.5_signal_access_tools.md` (구현 — 본 ADR 의 직접 산출물)
- `.plans/stage1_preparation/plan_1.3_emr_tools.md` ("EMR tools 5 개 그대로 유지; signal access 는 plan_1.3.5 별도")
- `.plans/stage1_preparation/plan_1.7_tool_spec.md` (16 tool spec — 17–21 addendum 추가 권고)
- `.plans/stage1_preparation/plan_1.8_dual_mode_infra.md` (Shallow / Deep tool 분배 — 17, 20 Shallow / 17–21 Deep)
- `docs/decisions/ADR-014-tier0-current-state-assessment.md` (Tool 21 의존성, `[DECISION PENDING]`)
- `docs/decisions/ADR-011-mock-fm-strategy.md` (swap mechanism — Signal Access Tools 가 FM Interface 무관임을 명시)
- `docs/terminology.md` §5.1 / §6.1 (vital signs / HRV / SVV / baseline 용어 추가)

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — Tool 19 의 HRV metric 선택, Tool 20 의 baseline 정의, Tool 17 의 vital key 목록.
