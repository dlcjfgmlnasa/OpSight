# 21 Tool Suite

> Agent 가 호출할 수 있는 21개 외부 함수. **LLM 이 직접 골라 부르지 않음** — rule 이 결정.
> 2026-05-17 (Sprint 5): ADR-016 Signal Access (5) 추가, 16 → 21.

## 카테고리

| 카테고리 | 개수 | Tool # | 의존성 | 상태 |
|----------|------|--------|--------|------|
| FM-based | 7 | 1–7 | Foundation Model | ✅ 완료 |
| EMR-based | 5 | 8–12 | VitalDB EMR | 🟡 stub (per-event timestamp 부재) |
| Knowledge / Comparative | 2 | 13–14 | 코호트 + intervention DB | 🟡 stub (cohort + ADR-013 대기) |
| Auxiliary | 2 | 15–16 | Surgery context + fusion | ✅ tool 15 yaml + tool 16 full |
| **Signal Access** ★ ADR-016 | **5** | **17–21** | numpy / NeuroKit2 | ✅ Sprint 5 |

→ **21 tool 전체 implemented (Sprint 5).** Stub vs full 은 카테고리별로 다름.

## 1. FM-based (7) — `BiosignalFMInterface` 8 method 와 1:1

| # | Tool | FM Method | 출력 |
|---|------|-----------|------|
| 1 | `predict_hypotension` | `predict_hypotension` | `{risk, uncertainty, horizon_min}` |
| 2 | `predict_cardiac_arrest` | `predict_cardiac_arrest` | `{risk, uncertainty, horizon_min}` |
| 3 | `assess_signal_quality` | `assess_signal_quality` | `{score, reason}` |
| 4 | `cross_modal_consistency` | `cross_modal_consistency` | `{score, reason}` |
| 5 | `temporal_trend_analysis` | `temporal_trend` | `{slope, magnitude, label}` |
| 6 | `forecast_signal` | `forecast_signal` | `{forecast: [...], uncertainty: [...]}` |
| 7 | `anomaly_score` | `anomaly_score` | `{score}` |

`encode()` (FM 의 8번째) 는 tool 로 노출 X. 내부 latent (향후 retrieval / similar-case 가능성).

FM Result 구조: [[30_코드_워크스루/01_fm_layer]] + `docs/fm_interface_guide.md §1`.

## 2. EMR-based (5)

| # | Tool | 입력 | 반환 |
|---|------|------|------|
| 8 | `query_anesthesia_drugs` | (case_id, time_window) | `{drugs: [{name, amount, unit, timestamp_s, channel}]}` — RFTN20 / PPF20 / Sevo |
| 9 | `query_vasoactive_drugs` | (case_id, time_window) | `{drugs: [...]}` — `Orchestra/<DRUG>_<VAR>` (PHEN / NEPI / DOPA) |
| 10 | `query_fluid_blood` | (case_id) **case-end retrospective only** | `{intake_cumulative, ebl, urine, transfusion}` — `cases.csv intraop_*` 누적. **per-event timestamp 없음** |
| 11 | `query_surgery_progress` | (case_id, current_time) | `{phase, elapsed_min, estimated_remaining_min}` |
| 12 | `query_patient_baseline` | (case_id) | `{age, sex, asa, comorbidities, baseline_bp, labs}` |

⚠️ 모두 **leakage guard**. `time_window.end > clock.now_s` → `leakage_violation`. [[데이터_누수_방지]] 참조.

### Tool 9 / 10 — 2026-05-17 VitalDB 탐색 결과

`docs/findings/pump_drug_findings.md` (100-case sample, seed=20260517):

- **`PUMP*` / `DRUG*` 채널은 0 hit.** 모든 drug infusion 은 `Orchestra/<DRUG>_<VAR>` (51 unique track).
- **Vasoactive infusion 가용률 < 5%** — PHEN 2.0%, NEPI 1.4%, DOPA 0.5%. Tool 9 cohort 작음.
- **Tool 10 real-time stream 불가** — `intraop_eph` (50.3%) / `intraop_phe` (13.2%) / fluid / blood 모두 **case-end 누적값**, per-event timestamp X.
- → Tool 10 scope 축소: case-end retrospective + (선택) clinician annotation (ADR 후보).
- 임상의 검토 필요 `[CLINICIAN-REVIEW]`: drug class 매핑 (PHEN=vasopressor, DOPA dose-dependent), ephedrine IV-push 가정, bolus segmentation rule, vasopressor equivalent dose.

[[30_코드_워크스루/05_tools_layer]] 참조.

## 3. Knowledge / Comparative (2)

Stage 1 prototype 에서 STUB. cohort + ADR-013 결정 후 real.

| # | Tool | 개념 | Status |
|---|------|------|--------|
| 13 | `find_similar_cases` | 현재 state 와 비슷한 과거 case k개 검색 | STUB — `similar_cases=[]` |
| 14 | `intervention_response_prediction` | "약물 X dose Y 투여 시 trajectory 통계 분포". Dose 권고 X | STUB — `n_reference_cases=0` |

미래 설계: ADR-013 (Intervention Response — supervised conditional generation).

## 4. Auxiliary (2)

| # | Tool | 개념 | Status |
|---|------|------|--------|
| 15 | `surgery_context_awareness` | 수술 유형 + phase 별 reasoning hint | ✅ **yaml-backed** — `docs/surgery_context.yaml` 4×3 hint cell |
| 16 | `quality_aware_synthesis` | 여러 prediction 의 quality-weighted 결합 (deterministic) | ✅ Full (3 method: weighted_mean / max_quality / min_uncertainty) |

## 5. Signal Access (5) ★ ADR-016

> 명명: ADR-014 의 "Current State Assessment" (학습 capability) 와 구분하기 위해 **"Signal Access"** 통일. `docs/terminology.md §6.0`.

LLM 이 raw signal 에 직접 접근 못 함 → brief 의 `[Signal status]` / `[Surgery context]` / `[Evidence]` 정량 claim 을 explicit tool 호출로 grounded.

| # | Tool | 입력 | 반환 | Status |
|---|------|------|------|--------|
| 17 | `get_current_vitals` | (case_id, time) | `{map_mmHg, sbp_mmHg, dbp_mmHg, hr_bpm, rr_per_min, spo2_pct, etco2_mmHg, bis, core_temp_c}` 9 field | ✅ Full |
| 18 | `describe_signal` | (case_id, modality, window_min) | `{mean, std, min, max, median, iqr, missing_ratio, n_samples}` | ✅ Full |
| 19 | `assess_variability` | (case_id, modality) | HR: HRV (SDNN/RMSSD/LF-HF); MAP: BPV (SD/ARV); PPG: amplitude_var/SVV | ✅ Full (NeuroKit2 PRIMARY) |
| 20 | `compare_to_baseline` | (case_id, modality, preop_baseline?) | `{baseline_value, current_value, absolute_change, percent_change, direction}` | ✅ Full |
| 21 | `summarize_current_state` | (case_id, time) | `{hemodynamic_state, anesthesia_state, respiratory_state, key_concerns, overall_assessment}` | 🟡 **STUB** (rule-based; full = ADR-014 후 Tier 0 #14–16 wrap) |

⚠️ **Tool 21 phrasing 강제** (brief §13.1):
- Conditional phrasing 만 ("X 가능성 시사")
- 단정형 X ("X 이다")
- Dose 권고 절대 X
- `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` MANDATORY (test 강제)

코드: `opsight/tools/signal_access_tools.py` + `signal_access_types.py`. ADR: `docs/decisions/ADR-016-signal-access-tools.md`.

## Tool envelope — 공통 입출력

```python
class ToolRequest(BaseModel):
    case_id: str
    sim_time_s: float       # leakage guard 용
    tool_name: str
    args: dict[str, Any]

class ToolResponse(BaseModel):
    case_id: str
    sim_time_s: float
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    error: ToolError | None = None
    quality_meta: dict[str, Any]      # quality-aware claim 근거
    latency_ms: float
```

`quality_meta` 는 *모든* tool 의무 — quality-aware 특성 근거. [[30_코드_워크스루/05_tools_layer]] 참조.

## Dispatch — `call_tool(name, ...)`

```python
from opsight.tools.registry import call_tool, TOOLS

response = call_tool(
    "predict_hypotension",
    request=ToolRequest(case_id="c1", sim_time_s=30.0,
                         tool_name="predict_hypotension",
                         args={"horizon_min": 5, "available_modalities": ["ABP"]}),
    fm=fm, clock=clock, signal=signal,
)
```

| `needs_fm` | `needs_signal` | Args | 적용 |
|-----------|----------------|------|------|
| True | True | (request, fm, clock, signal) | FM tool (1–7) |
| False | True | (request, clock, signal) | Signal Access (17–21) |
| False | False | (request, clock) | EMR / Knowledge / Auxiliary |

## Shallow vs Deep

```python
# opsight/tools/registry.py

SHALLOW_TOOL_NAMES: Final[tuple[str, ...]] = (
    "predict_hypotension",
    "predict_cardiac_arrest",
    "assess_signal_quality",
    "cross_modal_consistency",
    "anomaly_score",
    # ADR-016 follow-up — Signal Access 17 + 20 권고:
    # "get_current_vitals",
    # "compare_to_baseline",
)
```

| Mode | Tool 호출 |
|------|-----------|
| Shallow (30s tick) | 위 5개 quick |
| Deep (event-triggered) | **21개 전체** |

ADR-016 follow-up: Signal Access 17, 20 도 Shallow 에 추가 권고 ([Signal status] 정량 source).

[[Dual_mode_architecture]] 참조.

## "LLM 이 tool 직접 선택 X" 정책

LLM 이 매번 골라 부르지 않음. **rule 이 결정**:
- Shallow tick → 5 quick tool 모두
- Deep mode → 21 tool 모두

LLM 은 결과 *해석* 만. 이유:
- Safety: LLM 환각으로 누락 시 brief 잘못됨
- Latency 예측성
- Trace 의 tool sequence 가 deterministic

[[10_기초/Tool_calling_과_Function_calling]] + [[Dual_mode_architecture]].

## Brief 9-section × tool source mapping

| Brief section | 주 source | 보조 |
|---------------|-----------|------|
| `[Surgery context]` | 11 + **21** | 15 |
| `[Signal status]` | **17** + **18** + 3 | 4 |
| `[Assessment confidence]` | 3 + 4 | — |
| `[Risk evaluation]` | 1 + 2 | — |
| `[Evidence]` | 5 + 6 + 7 + **19** + **20** | — |
| `[Intraoperative context]` | 8 + 9 + 10 | 11 |
| `[Similar trajectory]` | 13 | — |
| `[Recommendations]` | (LLM 합성) | 14 |
| `[Limitations]` | (LLM 합성) | 모든 tool 의 `quality_meta` |

Heavy LLM prompt v2 가 본 매핑 반영.

## Tool description — LLM 결과 해석 도움

```
Tool: predict_hypotension
Description: Probability of hypotension (MAP < 65 mmHg sustained ≥ 1 min)
             within horizon_min minutes. Returns risk in [0, 1] and
             uncertainty in [0, 1]. Higher uncertainty = less reliable.
```

→ LLM 이 "risk 0.42 (uncertainty 0.18)" 의미 정확히 사용.

정식 tone guide: `prompts/v1_tool_description_style.md`.

21 tool 정식 spec:
- 1–16: `docs/tool_envelope.md` + `docs/tool_spec/{fm,emr,knowledge,auxiliary}_tools.md`
- 17–21: `docs/tool_spec/signal_access_tools.md`

## 다음 노트

- [[9_Section_Brief]] — 21 tool 결과가 어떻게 brief 가 되는가
- [[30_코드_워크스루/05_tools_layer]] — tools 레이어 워크스루
- [[데이터_누수_방지]] — leakage guard
