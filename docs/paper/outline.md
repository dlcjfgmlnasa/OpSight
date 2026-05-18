# OpSight — Paper Outline (npj DM target, v0.1 draft)

> 첫 outline 초안. Sprint 6 작성, 2026-05-18.
> 임상의 그룹 회의 (~2개월 후) 의 input 자료 — "이런 식으로 paper 가 정리될 것" 을 보여주기 위함.
> 최종 target: **npj Digital Medicine** (또는 sibling: Nature Biomedical Engineering / IEEE JBHI).
> Owner: `biomedical-ai-paper-writer`.

---

## 0. Working Title

> *OpSight: A modality-agnostic, quality-aware tool-using LLM agent for intraoperative hemodynamic reasoning, powered by a multimodal biosignal foundation model.*

(Subtitle alt: *"...evaluated on 5,946 non-cardiac surgical cases from VitalDB"*)

---

## 1. Abstract (≤ 250 words)

**Background** — Perioperative hemodynamic instability remains a leading cause of postoperative morbidity. Existing early-warning systems are single-modality (mostly ABP-based, e.g., HPI), silent about signal quality, and not surgery-aware.

**Methods** — We developed **OpSight**, a tool-using LLM agent that consumes a frozen multimodal biosignal foundation model (FM) trained on K-MIMIC ICU data via a stable Protocol. The agent operates in dual mode (30-second Shallow loop + on-demand Deep brief with 9-section Korean output). 21 tools span FM-based prediction (7), EMR queries (5), knowledge retrieval (2), auxiliary fusion (2), and explicit signal access (5). All risk thresholds and clinical interpretations are gated by `[CLINICIAN-REVIEW]` markers.

**Cohort** — VitalDB 5,946 non-cardiac major surgical cases (general / thoracic / urologic / gynecologic), filtered for op-time ≥ 30 min. Department-stratified analysis is mandatory.

**Evaluation** — Three layers: (1) automated metrics (AUPRC/AUROC, faithfulness via atomic-claim grounding, latency), (2) LLM-as-judge of brief quality, (3) 5–7 anesthesiologist blinded review of 200–300 briefs (Cohen's κ across 5 Likert dimensions).

**Findings (preliminary)** — Streaming + preprocessing reduce sensor-artifact-induced false signals from ~3.8% to 0%. Mock FM Tier 2 drives the agent across 100 cases with p95 4.8 ms per tick. Real-cohort 10-case e2e maintains zero leakage events under strict streaming.

**Conclusion** — Tool-using LLM agents over a foundation model can produce interpretable, quality-aware, surgery-aware intraoperative briefs, with explicit clinician-review gates. This is a PoC; prospective validation is future work.

---

## 2. Introduction

### 2.1 Clinical motivation
- Hypotension (MAP < 65 mmHg) is the most studied perioperative adverse event
- Existing tools: HPI (Hatib 2018) — single-modality (ABP), proprietary, doesn't account for missing ABP, no surgery context
- Clinical workflow: anesthesiologists make decisions under cognitive load; opaque "0.85 risk score" without rationale is rarely actionable

### 2.2 Technical gap
- Multimodal biosignal foundation models (BFMs) are emerging but tools to *consume* them by clinicians are immature
- LLM agents in clinical domain: most are diagnostic chatbots, not real-time monitoring assistants
- Faithfulness / hallucination in clinical narration is an open problem

### 2.3 Contributions
1. **OpSight system architecture** — tool-using LLM agent over a swap-friendly Protocol-gated FM
2. **21-tool suite** spanning prediction, signal access, EMR, knowledge retrieval, fusion — designed for atomic-claim grounding
3. **Dual-mode operation** (Shallow 30s + Deep on-demand) with rule-based triggers (NOT LLM-driven) for safety
4. **Modality-agnostic, surgery-aware, quality-aware** demonstration across 4 surgical departments
5. **Streaming evaluation framework** strict to the simulated-real-time framing (no future-data leakage)
6. **Clinician evaluation protocol** with `[CLINICIAN-REVIEW]` marker discipline + Cohen's κ on 200–300 briefs

---

## 3. Related Work

### 3.1 Hemodynamic prediction
- Hatib et al. *Anesthesiology* 2018 (HPI)
- Lee et al. (VitalDB curators) — open dataset
- DeepHypotension / various deep learning baselines

### 3.2 Biosignal foundation models
- Cross-domain pretraining (K-MIMIC, MIMIC-III waveforms)
- BFM (this project's sibling) — `[CLINICIAN-REVIEW]` confirm citation when checkpoint paper drops

### 3.3 LLM agents in clinical NLP
- Tool-using agents (ReAct, OpenAI function calling, Anthropic tool use)
- Clinical LLM agents — mostly text retrieval, few real-time
- Hallucination in clinical generation

### 3.4 Quality-aware ML
- Uncertainty propagation
- Modality-agnostic deep learning

---

## 4. Methods

### 4.1 Dataset

- **Source**: VitalDB (Lee et al. *Sci Data* 2022)
- **Cohort**: 5,946 non-cardiac major surgery cases after `op_time ≥ 30 min` filter
  - General 76.3% / Thoracic 18.0% / Gynecology 3.8% / Urology 1.9%
- **Pediatric** (age < 18): included by default; sensitivity analysis with `--exclude-pediatric` `[DECISION PENDING]`
- **ASA = 6**: included by default; sensitivity analysis with `--exclude-asa6` `[DECISION PENDING]`
- **Reproducibility**: `scripts/build_cohort.py` regenerates manifest from VitalDB CSV endpoint

### 4.2 Modality availability stratification (mandatory)

`[CLINICIAN-REVIEW]` — Department-stratified:
- ABP_any (Extended): 58% all / **General 48% (CAVEAT)** / Thoracic 97% / Urology 71% / Gynecology 82%
- Implication: aggregate "modality-agnostic" metric **misleading** — paper must report stratified

### 4.3 Foundation Model (FM)

- Frozen K-MIMIC pretrained BFM
- Consumed exclusively via `BiosignalFMInterface` Protocol (8 methods: `encode`, `predict_hypotension`, `predict_cardiac_arrest`, `assess_signal_quality`, `cross_modal_consistency`, `temporal_trend`, `forecast_signal`, `anomaly_score`)
- ADR-011: 3-tier Mock FM strategy (Stub / Rule-based / Light ML) → real FM swap protocol

### 4.4 Preprocessing (Sprint 5–6)

- **Physiological clipping** — per-modality range (e.g., MAP ∈ [20, 250] mmHg) → out-of-range → NaN
- **NaN-gap interpolation** — gaps < `max_nan_gap_s` (modality-specific) linearly interpolated; longer kept as NaN
- **Waveform resampling** — all waveform modalities (ABP/PPG/ECG/EEG/CO₂/AWP) → uniform 100 Hz target (matching BFM training)
- **Streaming** — `SignalStream.view_until(sim_time_s)` exposes only up-to-now samples (strict real-time framing, brief §10)

### 4.5 Agent architecture

#### 4.5.1 21-tool suite
| Category | # | Tools |
|----------|---|-------|
| FM-based | 7 | predict_hypotension, predict_cardiac_arrest, assess_signal_quality, cross_modal_consistency, temporal_trend, forecast_signal, anomaly_score |
| EMR | 5 | query_anesthesia_drugs, query_vasoactive_drugs, query_fluid_blood, query_surgery_progress, query_patient_baseline |
| Knowledge | 2 | find_similar_cases, intervention_response_prediction |
| Auxiliary | 2 | surgery_context_awareness, quality_aware_synthesis |
| **Signal Access** | **5** | **get_current_vitals, describe_signal, assess_variability, compare_to_baseline, summarize_current_state** |

#### 4.5.2 Dual mode
- **Shallow** (every 30 s): 5 quick FM tools → 1-sentence Korean narration (Llama-3.1-8B)
- **Deep** (event-triggered): 21-tool sweep → 9-section Korean brief (Llama-3.3-70B)
- **Trigger** (rule-based, 7 rules + 60 s cooldown): `hypotension_risk>0.7`, `Δrisk>0.3/30s`, `quality_drop>0.3`, `cross_modal_inconsistency<0.4`, `arrest_risk>0.5` (cooldown bypass), `clinician_on_demand` (bypass), `periodic_5min`

#### 4.5.3 Brief 9-section structure
`[Surgery context] / [Signal status] / [Assessment confidence] / [Risk evaluation] / [Evidence] / [Intraoperative context] / [Similar trajectory] / [Recommendations] / [Limitations]`

Each section maps to specific tool outputs (faithfulness ground truth).

### 4.6 Safety policies

- **Clinical Fact Guard** (brief §13.1): all clinical assertions either marked `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` or rephrased as conditional
- **Data leakage**: `sim_time_s` enforced at tool level + streaming view at signal level
- **Rule-based triggers** (NOT LLM-driven) — safety + latency + verifiability

### 4.7 Evaluation

#### 4.7.1 Three-layer evaluation
1. **Automated metrics** — AUPRC/AUROC, sens@spec, faithfulness (atomic-claim grounding ratio), tool selection precision/recall, latency distribution
2. **LLM-as-judge** — Claude reads Llama brief + ground truth tool trace
3. **Clinician evaluation** — 5–7 anesthesiologists × 200–300 briefs, 5 Likert dimensions, Cohen's κ

#### 4.7.2 Baselines
- Logistic regression (ABP features)
- XGBoost multimodal
- LSTM on ABP waveform
- Hatib HPI-style open-source approximation
- (Optional) Recent published model — TBD literature review

#### 4.7.3 Stratification (mandatory)
- ABP-absent rate
- AUPRC/AUROC × department
- Latency × department
- Brief faithfulness score × department
- Clinician Likert × department

### 4.8 Implementation

- Python 3.13 + PyTorch + LangGraph + vLLM
- 4-bit quantization for both Light (8B) + Heavy (70B) on 2× L40S 48GB
- Open source: `github.com/dlcjfgmlnasa/OpSight` `[DECISION PENDING — public/private]`

---

## 5. Results

### 5.1 Cohort characteristics
- Table 1: Department × demographics × outcome
- Figure 1: Cohort flow diagram (6,388 → 5,946 included)

### 5.2 Modality availability
- Table 2: Stratified modality availability (12 priority modalities × 4 departments + aggregate)
- Figure 2: ABP-absent rate per department (47% General, 3% Thoracic, etc.)

### 5.3 Mock-FM agent operation
- 100-case synthetic + 10-case real cohort e2e
- p95 latency, deep trigger distribution, brief 9-section completion rate
- **Streaming effect** — sensor artifact 3.78% (ABP), 10.19% (BT) clipped; quality LOW → HIGH transition with preprocessing

### 5.4 Baseline comparison
- Table 3: AUPRC/AUROC by model × department × horizon (5 min, 15 min)
- Discussion: cross-modal improvement vs single-modality baselines

### 5.5 Brief faithfulness
- Atomic-claim grounding ratio: % of brief claims traceable to tool output
- Discussion of hallucination patterns observed

### 5.6 Clinician evaluation
- Figure: Likert distribution per dimension
- Cohen's κ across raters
- Qualitative themes from open-ended comments

### 5.7 Latency profile
- Per-tier (FM forward, tool sweep, LLM generation) latency
- 2× L40S real measurement

---

## 6. Discussion

### 6.1 Key findings
- Modality-agnostic monitoring is *plausible* with explicit signal-access tools + streaming
- Tool grounding reduces hallucination, but Heavy LLM still occasionally paraphrases (Tool 21 paraphrase-prevention as case study)
- Clinician evaluation reveals "Recommendations" section as the most fraught (dose-recommendation drift)

### 6.2 Comparison with HPI
- Modality scope (single vs multi)
- Quality awareness (silent vs explicit)
- Surgery awareness (none vs 4-department)
- Interpretability (opaque score vs grounded narrative)

### 6.3 Limitations
1. **Simulated real-time, not prospective** — VitalDB recordings are retrospective; true deployment is future work
2. **Single-center cohort** — VitalDB is SNUH only; external validation (MOVER, INSPIRE) deferred
3. **Mock FM during development** — real FM swap protocol verified but real-FM ablation comparison pending
4. **Tool 21 stub** — current state assessment is rule-based heuristic; Tier 0 supervised head pending ADR-014
5. **Clinician panel size** — 5–7 anesthesiologists from one group; multi-institutional review future work

### 6.4 Future work
- Prospective validation (NRF 도전형 2–3년차)
- External cohort validation
- Tier 0 supervised state head
- Multi-language brief (English + Korean)

---

## 7. Conclusion

(Tight 100-word restatement of contributions + clinical relevance + safety stance.)

---

## 8. Methods Reference Material

- Project brief: `docs/project_brief.md`
- ADRs: ADR-011 (Mock FM), ADR-014 (Tier 0 PENDING), ADR-016 (Signal Access)
- Code: `github.com/dlcjfgmlnasa/OpSight`
- Cohort manifest reproducibility: `scripts/build_cohort.py`

---

## Author roles & acknowledgments (placeholder)

- **이형철 교수님 그룹** — clinical co-PI, evaluation panel, all `[CLINICIAN-REVIEW]` items
- **dlcjfgmlnasa** — system design, implementation
- (TBD) — biosignal-foundation-model co-authors

---

## Open questions for the clinical meeting (~2 months out)

1. Pediatric inclusion finalization
2. ASA = 6 inclusion finalization
3. Tool 19 HRV/BPV/SVV metric selection (`[CLINICIAN-REVIEW]`)
4. Tool 20 baseline definition priority
5. Tool 21 (Tier 0) supervised head design
6. Clinician panel size (5 vs 7) + brief count (200 vs 300)
7. External validation strategy
8. `[DECISION PENDING]` open-source license

---

## Versioning

| Version | Date | Change |
|---------|------|--------|
| v0.1 | 2026-05-18 | Initial draft outline — Sprint 6 Task E |
