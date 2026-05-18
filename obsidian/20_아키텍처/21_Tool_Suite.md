# 21 Tool Suite — Agent 가 호출할 수 있는 외부 함수들

> Agent 의 손과 발. 21개 함수가 5개 카테고리로 묶여 있다. **LLM 이 직접 골라 부르지 않는다** — 규칙이 어떤 tool 을 부를지 결정한다.

## 전체 구도

21개를 카테고리로 나누면 다음과 같다. 카테고리는 "어떤 종류의 정보를 가져오는가" 로 구분된다.

| 카테고리 | 개수 | Tool 번호 | 무엇을 하는가 | 현재 상태 |
|---|---|---|---|---|
| **FM-based** | 7 | 1–7 | Foundation Model 로 risk / 품질 / 추세 / 예측 등을 계산 | ✅ 완료 |
| **EMR-based** | 5 | 8–12 | VitalDB 의 EMR 데이터 (약물·수액·차트) 를 조회 | 🟡 stub — VitalDB 데이터 한계 (per-event timestamp 없음) 때문 |
| **Knowledge / Comparative** | 2 | 13–14 | 유사 case 검색, intervention response 예측 | 🟡 stub — 코호트 확정 + ADR-013 결정 대기 |
| **Auxiliary** | 2 | 15–16 | 수술 맥락 hint, 여러 prediction 의 quality-weighted fusion | ✅ tool 15 yaml-backed, tool 16 deterministic |
| **Signal Access** ★ | 5 | 17–21 | 신호 자체에 직접 접근해서 vitals / 통계 / variability 추출 | ✅ 완료 (Sprint 5, ADR-016) |

Signal Access (17–21) 는 가장 최근에 추가된 카테고리다. ADR-016 에서 "LLM 이 raw signal 에 직접 접근하지 못하므로, brief 의 정량 claim 을 explicit tool 결과로 grounded 해야 한다" 는 결정 후 신설.

## 1. FM-based (7) — Foundation Model 의 8 method 와 1:1 매핑

이 7개는 모두 `BiosignalFMInterface` 의 method 를 직접 호출하는 thin wrapper 다. FM 이 mock 이든 real 이든 동일하게 동작한다.

| # | Tool | FM Method | 출력 |
|---|------|-----------|------|
| 1 | `predict_hypotension` | `predict_hypotension` | `{risk, uncertainty, horizon_min}` |
| 2 | `predict_cardiac_arrest` | `predict_cardiac_arrest` | `{risk, uncertainty, horizon_min}` |
| 3 | `assess_signal_quality` | `assess_signal_quality` | `{score, reason}` |
| 4 | `cross_modal_consistency` | `cross_modal_consistency` | `{score, reason}` |
| 5 | `temporal_trend_analysis` | `temporal_trend` | `{slope, magnitude, label}` |
| 6 | `forecast_signal` | `forecast_signal` | `{forecast: [...], uncertainty: [...]}` |
| 7 | `anomaly_score` | `anomaly_score` | `{score}` |

FM 에는 8번째 method `encode()` 가 더 있지만 이건 tool 로 노출되지 않는다. 내부 latent representation 이라서 agent 코드가 직접 쓸 일은 없고, 나중에 retrieval / similar-case 검색에 쓰일 가능성이 있다.

자세한 FM Result 구조는 [[30_코드_워크스루/01_fm_layer]] + `docs/fm_interface_guide.md §1`.

## 2. EMR-based (5) — VitalDB 의 차트·약물·수액

VitalDB 의 metadata 와 `intraop_*` 컬럼들을 읽는다. 지금은 모두 stub. 실제 데이터로 교체할 때 한계가 있어서 (per-event timestamp 가 없음) prototype 단계에선 stub 으로 충분할 가능성이 높다.

| # | Tool | 입력 | 반환 |
|---|------|------|------|
| 8 | `query_anesthesia_drugs` | (case_id, time_window) | `{drugs: [{name, amount, unit, timestamp_s, channel}]}` — RFTN20 / PPF20 / Sevo 등 |
| 9 | `query_vasoactive_drugs` | (case_id, time_window) | `{drugs: [...]}` — `Orchestra/<DRUG>_<VAR>` 채널 기반 (PHEN / NEPI / DOPA 등) |
| 10 | `query_fluid_blood` | (case_id) — **case-end retrospective 만** | `{intake_cumulative, ebl, urine, transfusion}` — `cases.csv` 의 `intraop_*` 누적값. **per-event timestamp 없음** |
| 11 | `query_surgery_progress` | (case_id, current_time) | `{phase, elapsed_min, estimated_remaining_min}` |
| 12 | `query_patient_baseline` | (case_id) | `{age, sex, asa, comorbidities, baseline_bp, labs}` |

⚠️ 모든 EMR tool 에는 **leakage guard** 가 적용된다. `time_window.end` 가 현재 sim_time 을 넘으면 `leakage_violation` 에러를 반환한다. 자세한 건 [[데이터_누수_방지]].

### Tool 9 / 10 — 2026-05-17 VitalDB 탐색 결과 반영

100 case sample (seed=20260517) 로 확인한 결과 (`docs/findings/pump_drug_findings.md`):

- **`PUMP*` 나 `DRUG*` 패턴의 채널은 schema 에 0 hit.** 모든 drug infusion 은 `Orchestra/<DRUG>_<VAR>` 형식 (51개 unique track).
- **Vasoactive infusion 가용률이 작다** — PHEN 2.0%, NEPI 1.4%, DOPA 0.5%. Tool 9 의 cohort 자체가 작다.
- **Tool 10 은 real-time stream 이 불가능** — `cases.csv` 의 `intraop_eph` (50.3%), `intraop_phe` (13.2%), fluid, blood 가 모두 **case-end 누적값** 이라서 per-event timestamp 가 없다. Orchestra 채널에 ephedrine 자체가 부재.
- → Tool 10 의 scope 을 **case-end retrospective + (선택) clinician annotation** 으로 축소하자는 ADR 후보가 올라와 있다.
- 임상의 검토 필요한 항목들 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`: drug class 매핑 (PHEN=vasopressor, DOPA dose-dependent), ephedrine IV-push 가정, bolus segmentation rule, vasopressor equivalent dose 정의.

자세한 코드는 [[30_코드_워크스루/05_tools_layer]].

## 3. Knowledge / Comparative (2) — 비교와 검색

| # | Tool | 무엇을 하는가 | 현재 상태 |
|---|------|---|---|
| 13 | `find_similar_cases` | 현재 환자 state 와 비슷한 과거 case k개를 검색 (코호트 retrieval) | STUB — `similar_cases=[]` 반환 |
| 14 | `intervention_response_prediction` | "이 약물을 이 dose 로 투여하면 trajectory 가 어떻게 될까" 의 통계적 response distribution. **Dose 권고 절대 금지** | STUB — `n_reference_cases=0` |

미래 설계는 ADR-013 (Intervention Response — supervised conditional generation).

## 4. Auxiliary (2) — 맥락과 합성

| # | Tool | 무엇을 하는가 | 현재 상태 |
|---|------|---|---|
| 15 | `surgery_context_awareness` | 수술 유형 + phase 에 따른 reasoning hint 제공 | ✅ **yaml-backed** — `docs/surgery_context.yaml` 의 4×3 hint cell 사용 |
| 16 | `quality_aware_synthesis` | 여러 prediction 을 quality-weighted 로 결합 (LLM 없는 deterministic fusion) | ✅ 3가지 method (weighted_mean / max_quality / min_uncertainty) |

## 5. Signal Access (5) ★ — 신호 자체에 직접 접근 (ADR-016)

> 명명 정책: ADR-014 의 "Current State Assessment" (학습된 capability) 와 구분하기 위해 본 카테고리는 **"Signal Access"** 로 통일. 자세한 건 `docs/terminology.md §6.0`.

LLM 은 raw signal 에 직접 접근하지 못한다. 그래서 brief 의 "지금 MAP 이 얼마야?", "HRV 가 어때?", "기준선 대비 얼마나 떨어졌어?" 같은 정량 claim 을 explicit tool 호출로 grounded 시킨다.

| # | Tool | 입력 | 반환 | 상태 |
|---|------|------|------|------|
| 17 | `get_current_vitals` | (case_id, time) | `{map_mmHg, sbp_mmHg, dbp_mmHg, hr_bpm, rr_per_min, spo2_pct, etco2_mmHg, bis, core_temp_c}` 9 field | ✅ Full |
| 18 | `describe_signal` | (case_id, modality, window_min) | `{mean, std, min, max, median, iqr, missing_ratio, n_samples}` | ✅ Full |
| 19 | `assess_variability` | (case_id, modality) | HR: HRV (SDNN/RMSSD/LF-HF); MAP: BPV (SD/ARV); PPG: amplitude_var/SVV | ✅ Full (NeuroKit2 PRIMARY) |
| 20 | `compare_to_baseline` | (case_id, modality, preop_baseline?) | `{baseline_value, current_value, absolute_change, percent_change, direction}` | ✅ Full |
| 21 | `summarize_current_state` | (case_id, time) | `{hemodynamic_state, anesthesia_state, respiratory_state, key_concerns, overall_assessment}` | 🟡 **STUB** (rule-based) — ADR-014 가 Accept 되면 Tier 0 #14–16 으로 wrap 예정 |

⚠️ **Tool 21 의 phrasing 은 강제된다** (brief §13.1 Clinical Fact Guard).

- Conditional phrasing 만 ("X 가능성을 시사함")
- 단정형 금지 ("X 이다")
- Dose 권고 절대 금지
- `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` 마커가 MANDATORY (test 가 강제)

자세한 코드는 `vitalagent/tools/signal_access_tools.py` + `vitalagent/tools/signal_access_types.py`. ADR 은 `docs/decisions/ADR-016-signal-access-tools.md`.

## 모든 tool 이 공유하는 입출력 형식 — Envelope

21개 tool 모두 같은 envelope 을 쓴다. 그래서 caller 는 어떤 tool 이든 같은 방식으로 결과를 받는다.

```python
class ToolRequest(BaseModel):
    case_id: str
    sim_time_s: float       # 시뮬레이션 시간 — leakage guard 가 본다
    tool_name: str
    args: dict[str, Any]

class ToolResponse(BaseModel):
    case_id: str
    sim_time_s: float
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    error: ToolError | None = None
    quality_meta: dict[str, Any]      # quality-aware claim 의 근거
    latency_ms: float
```

`quality_meta` 는 *모든* tool 이 채워야 한다. brief 의 "이 정보는 stub 이라 신뢰도 낮음" 같은 한계 표현이 여기서 나온다. 자세한 건 [[30_코드_워크스루/05_tools_layer]].

## Tool 을 부르는 방법 — `call_tool(name, ...)`

```python
from vitalagent.tools.registry import call_tool, TOOLS

response = call_tool(
    "predict_hypotension",
    request=ToolRequest(case_id="c1", sim_time_s=30.0,
                         tool_name="predict_hypotension",
                         args={"horizon_min": 5, "available_modalities": ["ABP"]}),
    fm=fm,
    clock=clock,
    signal=signal,
)
```

`call_tool` 은 카테고리에 따라 다른 argument 를 받는다.

| `needs_fm` | `needs_signal` | 전달 args | 카테고리 |
|-----------|---|---|---|
| True | True | (request, fm, clock, signal) | FM tool (1–7) |
| False | True | (request, clock, signal) | Signal Access (17–21) |
| False | False | (request, clock) | EMR / Knowledge / Auxiliary |

자세한 dispatch 코드는 [[30_코드_워크스루/05_tools_layer]].

## Shallow 모드와 Deep 모드가 부르는 tool 이 다르다

```python
# vitalagent/tools/registry.py

SHALLOW_TOOL_NAMES: Final[tuple[str, ...]] = (
    "predict_hypotension",
    "predict_cardiac_arrest",
    "assess_signal_quality",
    "cross_modal_consistency",
    "anomaly_score",
)
```

| Mode | 호출되는 tool |
|------|---|
| Shallow (30초 tick) | 위 5개 빠른 tool |
| Deep (event-triggered) | **21개 전체** |

ADR-016 에는 "Shallow 에 Signal Access 17 (current vitals) + 20 (baseline 비교) 도 넣자" 는 follow-up 권고가 있다. brief 의 `[Signal status]` 섹션 정량 source 가 더 풍부해지기 때문. 후속 작업.

자세한 건 [[Dual_mode_architecture]].

## "LLM 이 tool 을 직접 고르지 않는다" 정책

21개 tool 은 LLM 이 매번 골라서 부르지 않는다. **어떤 tool 을 부를지는 규칙이 정한다**.

- Shallow tick → 5개 quick tool 을 무조건 모두 호출
- Deep mode → 21개 전체를 무조건 모두 호출

LLM 은 받은 결과를 *해석* 만 한다. 이유는 세 가지:

- **안전** — LLM 이 "이번엔 vasoactive 안 불러도 돼" 라고 환각하면 brief 가 잘못된다
- **Latency 예측 가능** — 어떤 tool 이 불릴지 미리 정해져 있으니 시간 예산이 짜진다
- **검증 가능** — trace 에 tool 호출 sequence 가 deterministic 으로 찍힌다

자세한 건 [[10_기초/Tool_calling_과_Function_calling]] + [[Dual_mode_architecture]].

## 9 섹션 brief 에서 어느 tool 이 어디로 들어가나

각 섹션의 정량 source 가 어떤 tool 들인지 매핑되어 있다. Heavy LLM prompt v2 의 worked-through 예시도 이 매핑을 따른다.

| Brief 섹션 | 주 source tool | 보조 |
|---|---|---|
| `[Surgery context]` | 11 `query_surgery_progress` + **21 `summarize_current_state`** | 15 `surgery_context_awareness` |
| `[Signal status]` | **17 `get_current_vitals`** + **18 `describe_signal`** + 3 `assess_signal_quality` | 4 `cross_modal_consistency` |
| `[Assessment confidence]` | 3 + 4 | — |
| `[Risk evaluation]` | 1 `predict_hypotension` + 2 `predict_cardiac_arrest` | — |
| `[Evidence]` | 5 + 6 + 7 + **19 `assess_variability`** + **20 `compare_to_baseline`** | — |
| `[Intraoperative context]` | 8 + 9 + 10 | 11 |
| `[Similar trajectory]` | 13 `find_similar_cases` | — |
| `[Recommendations]` | (LLM 합성) | 14 `intervention_response_prediction` |
| `[Limitations]` | (LLM 합성) | 모든 tool 의 `quality_meta` |

## Tool description — LLM 이 결과를 *해석* 하는 데 쓴다

LLM 이 tool 을 *부르지는* 않지만, 결과를 *해석* 할 때는 description 의 도움을 받는다. 예:

```
Tool: predict_hypotension
Description: Probability of hypotension (MAP < 65 mmHg sustained ≥ 1 min)
             within horizon_min minutes. Returns risk in [0, 1] and
             uncertainty in [0, 1]. Higher uncertainty = less reliable.
```

이 description 덕분에 LLM 이 brief 작성 시 "risk 0.42 (uncertainty 0.18)" 이 무슨 의미인지 정확히 쓴다. 정식 tone guide 는 `prompts/v1_tool_description_style.md` 에 있다.

전체 21 tool 의 정식 description spec:
- 1–16 : `docs/tool_envelope.md` + `docs/tool_spec/{fm,emr,knowledge,auxiliary}_tools.md`
- 17–21 : `docs/tool_spec/signal_access_tools.md`

## 다음 노트

- [[9_Section_Brief]] — 21 tool 결과가 어떻게 9 섹션짜리 brief 가 되는가
- [[30_코드_워크스루/05_tools_layer]] — tool 레이어 코드 한 줄씩
- [[데이터_누수_방지]] — leakage guard 의 의미
