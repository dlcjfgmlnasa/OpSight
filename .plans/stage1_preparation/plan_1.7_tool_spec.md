# plan_1.7 — 16-Tool Specification (Schemas + LLM Descriptions)

**Owner**: `langgraph-engineer`
**Assist**: `llm-prompt-engineer` (description text), `vitaldb-domain-expert` (EMR field 의미)
**Status**: ✅ done (Sprint 4 continuation, 2026-05-17)
**Scope note (2026-05-17, ADR-016 Accepted)**: 본 plan 은 tool **1–16** 의 spec 만 다룬다. ADR-016 으로 추가된 **Signal Access tool 17–21** 의 spec / description / failure mode 는 `plan_1.3.5_signal_access_tools.md` + `docs/tool_spec/signal_access_tools.md` 에 위치한다. 본 plan 의 alignment 표 / audit / data contract 는 1–16 에만 적용된다.
**Goal**: `docs/project_brief.md §7.1–§7.4` 에 열거된 16개 tool 각각의 authoritative JSON-schema spec과 LLM-facing description을 작성한다. FM tool (1–7)은 stub 구현을 받고, EMR tool (8–12)은 `plan_1.3`을 참조한다.

---

## Tasks

- [x] **[Priority: High]** 공통 tool envelope (request / response / error contract) 정의.
  - 입력: LangGraph state schema 초안 (`plan_1.8` 초기 산출물), brief §13.2 leakage rule
  - 출력: `docs/tool_envelope.md` — `ToolRequest` / `ToolResponse` / `ToolError` Pydantic / JSON schema. 필수 필드: `case_id`, `sim_time_s`, `tool_name`, `args`, `result`, `quality_meta`, `latency_ms`
  - 의존성: `plan_1.3` leakage guard, `plan_1.8` state schema 초안
  - 참고: `quality_meta` 필드는 quality-aware claim의 근거. 모든 tool이 이 필드를 채워야 한다.

- [x] **[Priority: High]** **7개 FM-based tool** (tool 1–7)의 schema + description.
  - 입력: `docs/project_brief.md §7.1` signature
  - 출력: `docs/tool_spec/fm_tools.md` — tool별: input JSON schema, output JSON schema, LLM description (한글 + 영문), failure mode, Stage 1 테스트용 **stub return**
  - 의존성: tool envelope
  - 참고: 본 stage에서는 stub만 작성한다. 실제 FM forward는 Stage 2에서 `signal-ingest-engineer` + `langgraph-engineer` 합작으로 wire up.

- [x] **[Priority: High]** **5개 EMR tool** (tool 8–12)의 schema + description.
  - 입력: `plan_1.3` 실 구현
  - 출력: `docs/tool_spec/emr_tools.md` — tool별: schema, description, failure mode
  - 의존성: `plan_1.3`
  - 참고: 실제 코드와 schema의 1:1 일치는 pytest로 검증 (`plan_1.3` test에 포함).

- [x] **[Priority: High]** **2개 Knowledge / Comparative tool** (tool 13–14)의 schema + description.
  - 입력: `docs/project_brief.md §7.3`
  - 출력: `docs/tool_spec/knowledge_tools.md`
  - 의존성: tool envelope, 코호트 manifest
  - 참고: tool 14 `intervention_response_prediction`은 dose 권고가 아니라 *통계적 response distribution*만 반환한다. `[CLINICIAN-REVIEW]` mark.

- [x] **[Priority: High]** **2개 Auxiliary tool** (tool 15–16)의 schema + description.
  - 입력: `docs/project_brief.md §7.4`, `plan_1.5`의 `surgery_context.yaml`
  - 출력: `docs/tool_spec/auxiliary_tools.md`
  - 의존성: `plan_1.5`
  - 참고: tool 16 `quality_aware_synthesis`는 LLM 호출 없는 deterministic fusion 함수임을 명시.

- [x] **[Priority: Medium]** Tool registry module.
  - 입력: 위 spec
  - 출력: `opsight/tools/registry.py` — `TOOLS: dict[str, ToolSpec]` central registry. LangGraph에서 한 줄로 import 가능.
  - 의존성: 위 task 모두
  - 참고: stub 구현도 동일 module에서 import한다. Stage 2의 swap path를 깨끗하게 유지하기 위함.

- [x] **[Priority: Medium]** `llm-prompt-engineer`의 description style audit.
  - 입력: 위 16개 description
  - 출력: 본 plan 파일의 audit note — `plan_1.6_tool_description_style.md`와의 부합 여부, failure mode 누락 여부
  - 의존성: 위 spec
  - 참고: LLM tool-calling 정확도에 직결되는 가장 민감한 부분.

- [x] **[Priority: High]** FM-tool spec이 `BiosignalFMInterface`와 일치하는지 검증.
  - 입력: 위 FM-tool schema, `plan_1.2.5` Protocol + `plan_1.1.5` Result dataclass
  - 출력: 본 plan 파일의 alignment 표 (tool → Protocol method → Result dataclass); 7개 FM tool이 Protocol method만 호출하고 tool layer가 concrete-mock을 import하지 않는지 pytest로 확인
  - 의존성: `plan_1.1.5`, `plan_1.2.5`
  - 참고: ADR-011의 swap mechanism이 코드 수정 없이 작동하려면 tool layer가 절대 concrete class를 import하면 안 된다.

- [x] **[Priority: High]** Tool description은 mock과 real FM 양쪽에 대해 동일하게 읽혀야 한다.
  - 입력: tool description style guide (`plan_1.6`), Protocol 의미
  - 출력: `docs/tool_spec/*.md`의 tool별 description audit note — phrasing이 "mock 전용" 또는 "real 전용" 행동을 가정하지 않는지, uncertainty 필드가 일반적으로 기술되는지, failure mode가 양쪽을 cover하는지 확인
  - 의존성: 위 task
  - 참고: LLM이 mock 출력에 의존된 phrasing을 학습하는 것을 방지.

---

## Definition of done

- 16개 tool 모두 보유: JSON input schema, JSON output schema, 한글 + 영문 description, failure mode 목록
- 7개 FM tool의 stub 구현이 end-to-end callable (placeholder 반환)
- 5개 EMR tool schema가 `plan_1.3` 구현과 일치 (pytest 검증)
- `opsight/tools/registry.py` importable

## Data contracts established here

- **`ToolRequest` / `ToolResponse` / `ToolError` envelope** (`plan_1.8`의 LangGraph node, Stage 2 FM wiring, Stage 3 full agent에서 소비됨; `plan_1.3.5` Signal Access tool 도 동일 envelope 사용)
- **16-tool name registry (1–16)** (모든 downstream stage에서 소비됨). 17–21 의 추가는 `plan_1.3.5` 가 같은 registry 에 등록.

---

## Sprint 4 산출물 요약 (2026-05-17)

### 작성된 문서

- `docs/tool_envelope.md` — Pydantic + JSON Schema 정식 spec, leakage guard, quality_meta 컨벤션
- `docs/tool_spec/fm_tools.md` — FM tool 1–7 (Protocol method 별 정렬)
- `docs/tool_spec/emr_tools.md` — EMR tool 8–12 (STUB 단계, schema 는 real 합류 후 그대로 적용)
- `docs/tool_spec/knowledge_tools.md` — Knowledge tool 13–14 (STUB; intervention 14 의 phrasing rule 강제)
- `docs/tool_spec/auxiliary_tools.md` — Auxiliary tool 15 (STUB priors) + 16 (정식 deterministic 구현)

### 구현된 코드

- `opsight/tools/knowledge_tools_stub.py` — tool 13 + 14 STUB
- `opsight/tools/auxiliary_tools.py` — tool 15 STUB + tool 16 정식 구현 (3 method: weighted_mean / max_quality / min_uncertainty)
- `opsight/tools/registry.py` — TOOLS dict 가 16 entry 모두 보유; 카테고리 (fm/emr/knowledge/auxiliary)
- `opsight/nodes/deep_brief.py::_deep_args` — 13–16 호출 args 추가

### Test

- `tests/test_tools_knowledge_auxiliary.py` — 23 test (전체 통과)
  - Tool 13: stub empty / k 범위 / leakage
  - Tool 14: stub empty / invalid intervention / missing name / leakage
  - Tool 15: general+maintenance / unknown type / missing type
  - Tool 16: weighted_mean / max_quality / min_uncertainty / all-zero / empty / invalid method / range / missing / single-passthrough
  - Registry: 16 tool 모두 존재 + 카테고리 분포 + call_tool dispatch

- 전체 test suite: **132 통과** (109 → 132, +23)

---

## Alignment 표 — FM Tool ↔ Protocol Method ↔ Result Dataclass

| Tool # | Tool name | `BiosignalFMInterface` method | Result dataclass |
|--------|-----------|-------------------------------|------------------|
| 1 | `predict_hypotension` | `predict_hypotension` | `HypotensionResult` |
| 2 | `predict_cardiac_arrest` | `predict_cardiac_arrest` | `ArrestResult` |
| 3 | `assess_signal_quality` | `assess_signal_quality` | `QualityResult` |
| 4 | `cross_modal_consistency` | `cross_modal_consistency` | `ConsistencyResult` |
| 5 | `temporal_trend_analysis` | `temporal_trend` | `TrendResult` |
| 6 | `forecast_signal` | `forecast_signal` | `ForecastResult` |
| 7 | `anomaly_score` | `anomaly_score` | `AnomalyResult` |

Protocol method `encode()` 는 tool 로 노출되지 않음 — 내부 latent representation.

### Static check — concrete FM class import 금지

`tests/integration/test_smoke_single_case.py::test_no_concrete_fm_import_in_node_or_graph_module` 가 `opsight/nodes/` + `opsight/graph.py` + (extension) `opsight/tools/` 에서 `StubBiosignalFM` / `RuleBasedBiosignalFM` / `LightMLBiosignalFM` / `RealBiosignalFM` 어느 것도 import 하지 않음을 검증. ADR-011 swap mechanism 보존.

---

## Description style audit — `prompts/v1_tool_description_style.md` 준수

본 audit 는 16 tool 각각이 `v1_tool_description_style.md` 의 4-line skeleton 을 지키는지 확인.

### Skeleton 준수 점검

| 항목 | FM 1–7 | EMR 8–12 | Knowledge 13–14 | Auxiliary 15–16 |
|------|--------|----------|-----------------|-----------------|
| Purpose 1 문장 | ✅ | ✅ | ✅ | ✅ |
| Input 인자 + 의미 + 단위 | ✅ | ✅ | ✅ | ✅ |
| Output 키 + 범위 + 단위 | ✅ | ✅ | ✅ | ✅ |
| Caveats (failure mode + 신뢰도 한계) | ✅ | ✅ | ✅ | ✅ |
| Leakage guard 메모 | ✅ | ✅ | ✅ | ⛔ N/A for 16 (deterministic, no time data) |
| Quality-aware 메모 | ✅ | ✅ | ✅ | ✅ |
| 한·영 병기 | ✅ | ✅ | ✅ | ✅ |
| Token budget (70–200) | ✅ | ✅ | ⚠️ (intervention 14 는 phrasing rule 추가로 다소 길어짐) | ✅ |

### Mock-vs-real description universality audit

본 description 이 mock_tier 와 real FM 양쪽에 동일 적용되는지 확인 (plan_1.7 task 9):

- FM 1–7 description: ✅ "mock_tier == 'stub' 출력은 random — 임상 추론 금지" 처럼 mock 한계 *언급* 만 — 별도 mock-전용 phrasing 강제 안 함
- Uncertainty 필드: 7 FM tool 중 6 개에 명시 (예외: `anomaly_score`, `temporal_trend` 는 magnitude/label 로 대체); 양 mock_tier 와 real 에서 모두 적용
- EMR 8–12 description: `emr_stub` marker 가 quality_meta 에 있을 때와 없을 때 모두 적용 가능; real 합류 후 동일 schema
- Knowledge 13–14 description: `unimplemented_in_prototype` marker 가 있을 때와 없을 때 (real 합류 후) 모두 적용 가능
- Auxiliary 15: stub priors vs surgery_context.yaml priors 모두 동일 phrasing
- Auxiliary 16: deterministic — mock/real 구분 자체가 N/A

### Failure mode coverage audit

| Tool | Leakage | Invalid args | Missing dep | Internal exc | Fallback success |
|------|---------|--------------|-------------|--------------|------------------|
| 1–7 (FM) | ✅ | ✅ | ✅ | ✅ | ✅ (modality absent, flatline) |
| 8–11 (EMR with window) | ✅ | ✅ | ✅ (post-plan_1.3) | ✅ | ✅ (default 5-min window) |
| 12 (baseline static) | N/A | ✅ | ✅ | ✅ | N/A |
| 13 (similar cases) | ✅ | ✅ (k range) | ✅ (post-plan_1.2) | ✅ | ✅ (empty list) |
| 14 (intervention) | ✅ | ✅ (intervention shape) | ✅ (post-ADR-013) | ✅ | ✅ (empty distribution) |
| 15 (surgery context) | N/A | ✅ | ✅ (post-plan_1.5) | ✅ | ✅ (unknown type → empty) |
| 16 (synthesis) | N/A | ✅ (5가지 검증) | N/A | N/A | ✅ (single-pred passthrough, all-zero NaN) |

→ 모든 tool 이 5 가지 failure axis 중 적용 가능한 모든 case 를 cover.

---

## 추후 review 필요 항목 (post-real 합류)

1. **Tool 14 phrasing rule 강화** — `[Recommendations]` section 의 phrasing 이 dose 권고로 새지 않는지 임상의 그룹 검토 (`[CLINICIAN-REVIEW]`)
2. **Tool 15 priors 검토** — `_PHASE_PRIORS` 의 hardcoded event list 가 임상 reality 와 정합한지 plan_1.5 합류 시 검토
3. **Token budget 실측** — Heavy LLM prompt + 16 tool description 전체가 system message context window 안에 들어가는지 vLLM tokenizer 로 측정
4. **Description audit 자동화** — `v1_tool_description_style.md` 4-line skeleton 준수를 자동 검증하는 lint test 추가 (plan_1.7 의 description 만 manual audit; 향후 description 변경 시 regression 방지)
