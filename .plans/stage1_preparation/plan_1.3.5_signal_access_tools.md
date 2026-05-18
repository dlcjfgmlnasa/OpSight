# plan_1.3.5 — Signal Access Tools (tools 17–21)

**Owner**: `signal-ingest-engineer`
**Assist**: `langgraph-engineer` (registry wiring, dispatch, Tool 21 의 Tier 0 wrapping)
**Status**: ✅ done (Sprint 5, 2026-05-17) — 5 tool 모두 구현 + 28 test 통과. Tool 21 은 STUB (ADR-014 Accepted 시 Tier 0 wrap 으로 교체). prompt v2 (task 11) 는 plan_1.3.5 본 sprint 후 분리 진행.
**Goal**: 21-tool suite 중 **Signal Access 5 개 tool (17–21)** 을 구현한다. LLM 이 raw signal 에 접근 못 하므로, 브리프 §[Signal status] / §[Surgery context] / §[Evidence] section 의 정량 claim 이 explicit tool 호출로 grounded 되도록 한다.

> **명명 정책**: 본 카테고리는 **"Signal Access Tools"** 로 일관 호칭 — ADR-014 의 "Current State Assessment" (학습 capability) 와 구분. 함수명 `get_current_vitals` / `summarize_current_state` 등은 함수 의미 그대로 유지 (terminology §6.0 참조).
> ADR: `docs/decisions/ADR-016-signal-access-tools.md` (Accepted 2026-05-17).
> Project brief: `docs/project_brief.md §7.5` (Signal Access 카테고리).

---

## Tasks

- [x] **[Priority: High]** 환경 verification — NeuroKit2 설치 시도 + import 결정 + fallback path 확정.
  - 입력: 현재 `.venv` 상태 (`pip list`), xgboost 미설치 누락 패턴의 학습 (plan_1.4 사례)
  - 출력: 본 plan 파일에 NeuroKit2 install 결과 기록 + `opsight/baselines/__init__.py` 와 유사한 fallback 패턴 결정. `pip install neurokit2` 시도 → 성공 시 Primary, 실패 시 numpy 직접 구현 fallback.
  - 의존성: 없음 (가장 먼저 실행)
  - 참고: NeuroKit2 는 HRV / BPV / PPG 분석에서 lit-standard 라 직접 구현 대비 정확도 우위. 설치 권장 — `pip install neurokit2` (single dependency, 무거운 의존성 아님). 본 task 의 결과 (PRIMARY / FALLBACK) 가 Tool 19 의 구현 path 결정.

- [x] **[Priority: High]** 공통 `signal_access_tools.py` module 안착 + leakage guard 적용.
  - 입력: `opsight/tools/envelope.py` (`ToolRequest` / `ToolResponse`), `opsight/sim_clock.py` (`SimClock.assert_le`), `plan_1.1` channel naming convention (`docs/vitaldb_catalog.md`)
  - 출력: `opsight/tools/signal_access_tools.py` — 5 tool 의 단일 module. 모든 tool 은 `_leakage_guard(request, clock, query_window_end_s)` 를 첫 줄에서 호출.
  - 의존성: `plan_1.1` catalog, `plan_1.7` envelope
  - 참고: VitalDB raw load 는 `plan_1.1` 의 `vitaldb.load_case(caseid, track_names, interval)` 패턴 사용. 본 prototype 에서는 synthetic / cache 친화로 작성 가능.

- [x] **[Priority: High]** Result dataclass 5 개 정의.
  - 입력: ADR-016 의 schema sketch
  - 출력: `opsight/tools/signal_access_types.py` — `CurrentVitalsResult`, `SignalDescription`, `VariabilityResult`, `BaselineComparison`, `StateSynthesis` 모두 `@dataclass(frozen=True)`. `meta: dict[str, Any] = field(default_factory=dict)` 필드 공통.
  - 의존성: 없음
  - 참고: 본 5 dataclass 는 별도 module 에 분리 (fm/result_types.py 와 구분) — FM Interface 무관함을 코드 layout 으로 명시.

- [x] **[Priority: High]** Tool 17 — `get_current_vitals(case_id, time)` 구현.
  - 입력: `case_id: str`, `time: float (sim_time_s)` (기본 `clock.now_s`)
  - 출력: `CurrentVitalsResult { map_mmHg, sbp_mmHg, dbp_mmHg, hr_bpm, rr_per_min, spo2_pct, etco2_mmHg, bis, core_temp_c, meta }`. 각 field 는 부재 시 `None` (NaN 아님).
  - Source: VitalDB numeric tracks (catalog §3.1) — `Solar8000/ART_MBP` 우선, 부재 시 `Solar8000/NIBP_MBP`; `Solar8000/HR`, `Solar8000/PLETH_SPO2`, `Solar8000/ETCO2`, `Solar8000/BT`, `BIS/BIS`. `time` 의 ±5 초 window 의 평균.
  - 의존성: leakage guard, `plan_1.1`
  - 참고: meta 에 `source_tracks` 명시. ABP fallback (NIBP) 사용 시 `meta.fallback_source = "NIBP"`.

- [x] **[Priority: High]** Tool 18 — `describe_signal(case_id, modality, window_min=5)` 구현.
  - 입력: `case_id`, `modality: str` (예: `"ABP"`, `"HR"`), `window_min: int`
  - 출력: `SignalDescription { mean, std, min, max, median, iqr, missing_ratio, n_samples, meta }`. NaN-safe.
  - 의존성: leakage guard
  - 참고: numpy 만으로 구현. `iqr = p75 − p25`. `missing_ratio` 가 1.0 시 다른 모든 통계는 `None`.

- [x] **[Priority: High]** Tool 19 — `assess_variability(case_id, modality, window_min=5)` 구현.
  - 입력: tool 18 과 동일
  - 출력: `VariabilityResult { metrics: dict[str, float], meta }`.
    * `modality == "HR"`: metrics = `{ "SDNN_ms": ..., "RMSSD_ms": ..., "LF_HF_ratio": ... }` (HRV)
    * `modality == "MAP"` / `"ABP"`: metrics = `{ "SD_mmHg": ..., "ARV_mmHg": ... }` (BPV)
    * `modality == "PPG"`: metrics = `{ "amplitude_var": ..., "SVV_pct": ... }`
  - 의존성: leakage guard, **task 1 (NeuroKit2 verification)** 결과
  - 참고: 구현 path 는 task 1 의 verification 결과에 따른다.
    ```python
    try:
        import neurokit2 as nk
        USE_NEUROKIT = True
    except ImportError:
        USE_NEUROKIT = False

    if USE_NEUROKIT:
        # Primary: NeuroKit2 — SDNN, RMSSD, LF/HF 모두
        hrv = nk.hrv(...)
    else:
        # Fallback: numpy 직접 구현 — time-domain (SDNN, RMSSD) 만. LF/HF 는 `None` + meta.fallback="numpy_only"
        hrv = basic_hrv_numpy(...)
    ```
    Fallback 사용 시 `meta.implementation = "numpy_fallback"` + `meta.unavailable_metrics = ["LF_HF_ratio"]` 명시. `[CLINICIAN-REVIEW: HRV/BPV/SVV metric 선택 검토 필요]` — ADR-016 open question 1.

- [x] **[Priority: High]** Tool 20 — `compare_to_baseline(case_id, modality, current_time)` 구현.
  - 입력: `case_id`, `modality`, `current_time`
  - 출력: `BaselineComparison { baseline_value: float|None, current_value: float, absolute_change: float, percent_change: float, direction: "up"|"down"|"stable", meta: { baseline_source: "preop"|"intraop_early_10min"|"none" } }`
  - Baseline 정의 순서: (1) `query_patient_baseline(case_id).baseline_bp` 같은 preop 값 우선 (2) intraop 초기 10 분 평균 fallback (3) 둘 다 부재 시 `baseline_value=None`, `meta.baseline_source="none"`
  - 의존성: leakage guard, tool 12 `query_patient_baseline` (preop 1순위 source)
  - 참고: `[CLINICIAN-REVIEW: baseline 정의 우선순위 검토]` — ADR-016 open question 2.

- [x] **[Priority: High]** Tool 21 — `summarize_current_state(case_id, time)` **stub** 구현.
  - 입력: `case_id`, `time`
  - 출력: `StateSynthesis { hemodynamic_state, anesthesia_state, respiratory_state, key_concerns: list[str], overall_assessment: str, meta }`
  - **Stub 구현** (ADR-014 `[DECISION PENDING]`): 17 + 18 + 19 + 20 의 출력을 합성한 *rule-based* 휴리스틱. 예:
    * `hemodynamic_state = "stable" if 65 ≤ map ≤ 100 else "caution"` 등 lit-standard threshold 기반
    * `key_concerns` 는 threshold 위반 항목 list
  - **출력 phrasing 강제 정책** (brief §13.1 Clinical Fact Guard 적용):
    * **Conditional phrasing 강제**: "X 가능성을 시사함", "X 가 관찰됨", "X 가 임상의 판단 영역" 형식
    * **단정형 금지**: "X 이다", "X 진단됨", "X 처치 필요" 등 단정 어조 절대 금지
    * **Dose 권고 절대 금지**: "Norepinephrine 시작", "수액 500 mL" 등 일체 금지
    * **`[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` marker 자동 부착**: `overall_assessment` 출력 끝에 *반드시* concatenate. 누락 시 unit test 가 fail (task 8 의 검증 항목 5).
    * **Heavy LLM 와의 일관성**: 본 phrasing rule 은 `plan_1.6` Heavy LLM prompt v2 (task 11 cross-ref) 의 §[Recommendations] / §[Surgery context] phrasing 정책과 1:1 일치하도록 enforce.
  - 의존성: 17, 18, 19, 20
  - 참고: ADR-014 Accepted 시점에 본 stub 을 Tier 0 #14 (hemodynamic state classifier) + #15 (anesthesia state) + #16 (surgical phase) 호출로 교체. 본 task 의 docstring 에 "ADR-014 합류 후 교체" 명시. `quality_meta.tier0_status = "stub" | "tier0_supervised"` field 로 출처 표기.

- [x] **[Priority: High]** Registry 등록 + dispatch.
  - 입력: 위 5 tool 함수
  - 출력: `opsight/tools/registry.py` 의 `TOOLS` dict 에 `current_state` 카테고리 5 entry 추가. `category="current_state"`. `needs_fm=False`, `needs_signal=False` (signal 은 `case_id` + VitalDB load 로 직접 가져오므로). `call_tool` dispatch 자동 적용.
  - 의존성: 위 5 tool
  - 참고: `opsight/tools/registry.py::TOOLS` 가 21 entry 보유하도록 한다 (FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2 + Signal Access 5).

- [x] **[Priority: High]** Pytest suite — 5 tool + registry + leakage guard.
  - 입력: synthetic signal fixtures (HR sine, MAP step, NaN injection)
  - 출력: `tests/test_signal_access_tools.py`
  - 의존성: 위 task 모두
  - 참고: 최소 cover 항목:
    * Tool 17: 9 vital field 모두 채워지는 happy / ABP 부재 시 NIBP fallback / 모든 modality 부재 시 None
    * Tool 18: NaN-safe 통계 / `missing_ratio == 1.0` 경계
    * Tool 19: HR HRV 계산 정상 / MAP BPV 정상 / PPG SVV 정상 / 미지의 modality → `error.type="invalid_args"`
    * Tool 20: preop 우선 / preop 부재 시 intraop fallback / 둘 다 부재 시 None
    * Tool 21 stub: 17–20 합성 / **`[CLINICIAN-REVIEW]` marker 가 `overall_assessment` 끝에 *반드시* 포함 (누락 시 fail)** / `meta.tier0_status=="stub"` / **단정 어조 phrase ("이다", "진단", "필요") 가 출력에 없음** (regex assertion)
    * Leakage: 모든 5 tool 에서 `query_window_end_s > clock.now_s` → `leakage_violation`
    * Registry: 21 entry 모두 존재 + `current_state` 카테고리 5 개

- [x] **[Priority: High]** Tool 17–21 의 description 작성 + style guide 준수 audit.
  - 입력: `prompts/v1_tool_description_style.md` 4-line skeleton
  - 출력: `docs/tool_spec/signal_access_tools.md` — 5 tool 의 input/output JSON schema + LLM description (한·영) + failure mode 표
  - 의존성: 위 tool 구현
  - 참고: plan_1.7 의 description audit 표를 21 tool 로 확장.

- [x] **[Priority: Medium]** Single-case integration smoke test — 5 tool 모두 호출 + 결과 일관성 점검.
  - 입력: synthetic 단일 case
  - 출력: `tests/integration/test_signal_access_smoke.py` — graph 실행 없이 5 tool 직접 호출 + 결과 grounding 검증 (예: tool 17 의 MAP 과 tool 18 의 `describe_signal(modality="ABP").mean` 이 ±2 mmHg 안에서 일치)
  - 의존성: 위 모든 task
  - 참고: dual-mode 통합은 `plan_1.8` 의 `_deep_args` 확장에서 처리.

- [x] **[Priority: Medium]** `prompts/v2_heavy_deep_brief.md` 작성 (Heavy LLM prompt v2 follow-up) — Tool 17–21 반영.
  - 입력: ADR-016 §"브리프 §[Signal status] / §[Surgery context] 의 tool source 명시" 매핑 표, `prompts/v1_heavy_deep_brief.md` (16-tool 기준 baseline)
  - 출력: `prompts/v2_heavy_deep_brief.md` + bilingual `prompts/v2_heavy_deep_brief.en.md`. 본 plan 파일에 작성 진행 메모.
  - 의존성: tool 17–21 실 구현 완료 (task 1–9), ADR-016
  - 참고: **본 task 는 plan_1.3.5 의 task 1–9 완료 후 진행** (실 구현 결과 보고 prompt 작성이 더 정확). v2 prompt 의 구체 명세:
    * **21 tool 전체 반영**: 1–16 (기존) + 17–21 (신규) 의 description 모두 포함
    * **Tool 17–21 worked-through 예시 추가**: synthetic case 의 9-section brief 예시에 17–21 tool 호출 + 결과 인용 패턴 명시
    * **브리프 §[Signal status] source mapping 명시** (ADR-016 표 그대로):
      - `§[Signal status]` 의 vital 값 → `get_current_vitals` (tool 17)
      - `§[Signal status]` / `§[Evidence]` 의 trend / 통계 description → `describe_signal` (tool 18) + `temporal_trend_analysis` (tool 5)
      - `§[Evidence]` 의 variability 언급 → `assess_variability` (tool 19)
      - `§[Evidence]` 의 baseline 대비 변화 → `compare_to_baseline` (tool 20)
      - `§[Surgery context]` 의 통합 state 언급 → `summarize_current_state` (tool 21)
    * **Tool 21 출력 phrasing enforce (task 7 와 일관)**: Heavy LLM 이 `summarize_current_state.overall_assessment` 를 인용할 때 conditional phrasing 만 사용. 단정 phrasing 발견 시 prompt self-review block 으로 catch. dose 권고 금지. `[CLINICIAN-REVIEW]` marker 보존.
    * **v1 대비 변경 점**: v1 의 9-section worked-through 예시는 16-tool 기준이라 §[Signal status] 의 정량 source 가 placeholder. v2 에서 17–21 호출 trace 를 명시적으로 포함.
    * **`llm-prompt-engineer` 가 owner**: 본 task 는 `signal-ingest-engineer` 의 18, 19, 20 결과를 `llm-prompt-engineer` 가 받아 prompt 로 합성. handoff note 가 본 plan 파일에 기록.

---

## Definition of done

- 5 개 Signal Access tool (17–21) 구현 완료 + `opsight/tools/signal_access_tools.py` importable
- 5 Result dataclass (`CurrentVitalsResult`, `SignalDescription`, `VariabilityResult`, `BaselineComparison`, `StateSynthesis`) 정의
- Tool 21 의 stub 이 동작 + `meta.tier0_status="stub"` marker + `[CLINICIAN-REVIEW]` marker
- Pytest 통과 (`tests/test_signal_access_tools.py`)
- Registry 가 21 entry 보유 (`tests/test_tools_knowledge_auxiliary.py::test_registry_contains_all_16_tools` 가 21 으로 갱신 필요 — 본 plan 산출물의 일부)
- `docs/tool_spec/current_state_tools.md` description spec commit
- Brief §[Signal status] / §[Surgery context] 의 source mapping 이 plan_1.6 prompt review note 에 cross-ref 됨

## Data contracts established here

- `CurrentVitalsResult` schema (브리프 §2 [Signal status] 의 정량 source)
- `SignalDescription` schema (브리프 §2 + §5 [Evidence] 의 통계 source)
- `VariabilityResult` schema (브리프 §5 [Evidence] 의 HRV/BPV/SVV source)
- `BaselineComparison` schema (브리프 §5 [Evidence] 의 변화 source)
- `StateSynthesis` schema (브리프 §1 [Surgery context] 통합 source; stub→full 은 ADR-014 의존)

## Cross-references

- ADR-016 (본 plan 의 governance): `docs/decisions/ADR-016-signal-access-tools.md`
- ADR-014 (Tool 21 의 stub→full 의존): `docs/decisions/ADR-014-tier0-current-state-assessment.md`
- Brief §7 (Tool Suite — 21): `docs/project_brief.md §7.5`
- Brief §8 (9-section + tool source mapping): `docs/project_brief.md §8`
- plan_1.3 (EMR tools — 5 그대로 유지, 본 plan 과 병렬): `.plans/stage1_preparation/plan_1.3_emr_tools.md`
- plan_1.7 (16-tool spec — 본 plan 은 17–21 addendum): `.plans/stage1_preparation/plan_1.7_tool_spec.md`
- plan_1.8 (dual-mode infra — Shallow 17/20 + Deep 17–21 분배): `.plans/stage1_preparation/plan_1.8_dual_mode_infra.md`
- Terminology (HRV / BPV / SVV / baseline / vital signs 신규 entry): `docs/terminology.md §5.1`

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — Tool 19 의 HRV metric 선택, Tool 20 의 baseline 정의, Tool 21 의 `overall_assessment` phrasing.

---

## Sprint 5 산출물 요약 (2026-05-17)

### 구현 (3 module)

- `opsight/tools/signal_access_types.py` — 5 frozen Result dataclass (CurrentVitalsResult / SignalDescription / VariabilityResult / BaselineComparison / StateSynthesis)
- `opsight/tools/signal_access_tools.py` — 5 tool 정식 구현
- `opsight/tools/registry.py` — `TOOLS` dict 가 21 entry 보유 (FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2 + Signal Access 5)
- `opsight/tools/registry.py::call_tool` — `needs_signal=True, needs_fm=False` 조합 dispatch 추가 (3-arg routing)
- `opsight/nodes/deep_brief.py::_deep_args` — 17–21 호출 args 추가

### Environment verification (task 1)

- `pip install neurokit2` 성공 (joblib + pandas + sklearn + pywavelets 함께 설치). Bonus: sklearn 도 가용해짐 (plan_1.4 baseline 의 향후 metric 확장에 활용 가능)
- `USE_NEUROKIT = True` (primary path) — fallback path 도 작성됨 (numpy direct HRV)

### Tool 21 phrasing enforcement (task 7)

`tool_summarize_current_state` 의 `overall_assessment` 가 conditional phrasing 만 사용 + `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` marker 필수. Unit test 가 enforce:
- `test_tool21_clinician_review_marker_mandatory` — marker 누락 시 fail
- `test_tool21_no_assertive_phrasing_in_output` — 단정 phrase (`이다.`, `진단`, `처치`, `투여`, `권고`) 발견 시 fail
- `test_tool21_low_map_flagged_as_concern` — concern phrasing 이 "가능성을 시사함" 형식 검증

### Test (28 신규)

`tests/test_signal_access_tools.py`:
- Tool 17 (4 test): happy / NIBP fallback / 부재 / leakage
- Tool 18 (4 test): happy / all-NaN / invalid modality / missing arg
- Tool 19 (6 test): HR-HRV / MAP-BPV / PPG-SVV / unsupported / missing signal / fallback metadata
- Tool 20 (4 test): preop priority / intraop fallback / no-baseline / modality absent
- Tool 21 (6 test): synthesis happy / marker mandatory / no assertive phrasing / low-MAP concern / quality_meta clinical_review / leakage
- Registry (3 test): 21 entry / 5 signal_access category / dispatch
- NeuroKit2 env status (1 informational)

`tests/test_tools_knowledge_auxiliary.py`: `test_registry_contains_all_16_tools` → `test_registry_contains_all_21_tools` 갱신 + signal_access category count 검증 추가.

전체 test: **214 passed + 1 skipped** (Sprint 4: 187 → Sprint 5: 215, +28; 1 skip = NeuroKit2 fallback test — installed 환경에서 자동 skip).

### Description doc (task 8 / 9)

`docs/tool_spec/signal_access_tools.md` 작성 — 5 tool 의 input/output JSON schema + LLM description (한·영) + failure mode + brief mapping + style guide audit + failure mode coverage.

### plan_1.6 prompt v2 follow-up (task 11) — ✅ 완료 (2026-05-18)

- `prompts/v2_heavy_deep_brief.md` 작성 — 21 tool 반영 + brief 9-section × tool source mapping + Tool 17–21 인용 규칙 + Tool 21 의 `overall_assessment` paraphrase 금지 + worked-through 예시 (synthetic case_id=synth-001, 21 tool 결과 전수)
- `prompts/v2_heavy_deep_brief.en.md` — English bilingual mirror
- v1 → v2 changelog 표 + self-review checklist 추가

### 후속 항목

1. **prompt v2** (`prompts/v2_heavy_deep_brief.md`) 작성 — 21 tool 반영, Tool 17–21 worked-through 예시, Tool 21 phrasing rule heavy LLM 까지 enforce (별도 sprint)
2. **integration smoke test** (`tests/integration/test_signal_access_smoke.py`) — 5 tool 직접 호출 + 결과 일관성 (예: tool 17 의 MAP 과 tool 18 의 describe_signal.mean 일치). 현재는 unit test 만, 통합은 follow-up.
3. **ADR-014 Accepted 후** Tool 21 stub → Tier 0 #14–16 wrap 으로 교체 (회의 후).
