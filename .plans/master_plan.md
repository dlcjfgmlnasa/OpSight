# VitalAgent — Master Plan

> 5개 stage 전체에 걸친 프로젝트 방향의 **단일 진실 원천 (Single Source of Truth, SoT)**.
> 본 파일은 `project-planner` agent만 편집한다. 다른 agent는 각자에게 할당된
> sub-plan만 갱신한다.
>
> 프로젝트 정체성, 데이터셋, tool suite, 브리프 (brief) 형식, 평가는
> `docs/project_brief.md` (canonical brief) 참조.

마지막 갱신: 2026-05-16 — Stage 1 active.

---

## 1. 미션 (Mission)

multimodal biosignal Foundation Model을 backend로 활용한 **술중 (intraoperative) 혈역학 (hemodynamics) 추론용 tool-using LLM agent**를 구축한다. 실무 anesthesiologist 평가를 거쳐 **10개월 이내**에 **npj Digital Medicine**에 보고한다.

본 agent는 **universal**, **modality-agnostic**, **quality-aware**, **surgery-aware**의 특성을 모두 갖추어야 하며 자신의 불확실성 (uncertainty)에 정직해야 한다.

---

## 2. 5-Stage 로드맵 (Roadmap)

| Stage | 기간 (months) | 핵심 산출물 | 담당 agent (lead) | Plan 파일 |
|-------|---------------|-------------|-------------------|-----------|
| **1. Preparation** | 1–2 | VitalDB cohort, EMR tool stub, baselines, dual-mode skeleton | vitaldb-domain-expert, signal-ingest-engineer, langgraph-engineer, llm-prompt-engineer | `stage1_preparation/plan_1.{1..8}_*.md` |
| **2. FM integration** | 3–4 | FM을 backend로 소비; 7개 FM tool 연결 | langgraph-engineer, signal-ingest-engineer | `stage2_fm_integration/README.md` → 상세 TBD |
| **3. Full agent** | 5–6 | End-to-end shallow + deep mode, 내부 validation | langgraph-engineer, llm-prompt-engineer, clinical-evaluator | `stage3_full_agent/README.md` → 상세 TBD |
| **4. Clinician eval** | 7–8 | 5–7명 anesthesiologists가 200–300 브리프를 blinded 평가 | clinical-evaluator, project-planner | `stage4_clinician_eval/README.md` → 상세 TBD |
| **5. Paper** | 9–10 | npj DM 제출 | biomedical-ai-paper-writer | `stage5_paper/README.md` → 상세 TBD |

---

## 3. Critical Path — Stage 1 주간 일정 (Mock FM track 포함)

Mock FM track (ADR-011)은 data/agent track과 **병렬**로 진행되며 critical path를 막지 않도록 설계된다. 아래 주차는 명목적이다. 실제 slippage는 본 헤더가 아닌 §9 Status Log에 기록된다.

| Week | Data / Agent track | Mock FM track |
|------|--------------------|---------------|
| 1 | `plan_1.1` VitalDB exploration | `plan_1.1.5` mock FM stub |
| 2 | `plan_1.2` cohort definition | `plan_1.2.5` FM interface spec |
| 3 | `plan_1.3` EMR tools + `plan_1.3.5` signal access tools (병렬) | — |
| 4 | `plan_1.4` baselines (시작) | `plan_1.6.5` mock FM rule-based |
| 5 | `plan_1.4` baselines (완료) | — |
| 6 | `plan_1.5` surgery context | `plan_1.7.5` mock FM light ML *(optional)* |
| 7 | `plan_1.6` system prompt + end-to-end mock 통합 시작 | — |
| 8 | `plan_1.7` tool spec + `plan_1.8` dual-mode infra + 100-case mock test | — |

**Blocker chain (Data/Agent)**: 1.1 → 1.2 → 1.3 → 1.7 → 1.8 (선형).
**Track 내 병렬 가능**: 1.4, 1.5, 1.6, **1.3.5** 는 1.1 이 부분 진행되면 critical chain 과 병행 실행 가능. plan_1.3.5 는 ADR-016 (Accepted) 산출물로 plan_1.3 과 독립.
**Mock FM track 게이팅**: 1.1.5 → 1.2.5 → 1.6.5 → (1.7.5). Mock track은 Data/Agent track을 절대 막지 않으며, agent code는 Mock을 Protocol을 통해서만 소비한다.

---

## 4. Stage 1 — Plan 담당 (Plan Ownership)

| Plan | 담당 (Lead) | 보조 / 검토 (Reviewer / Assist) | 상태 |
|------|-------------|--------------------------------|------|
| `plan_1.1_vitaldb_exploration` | vitaldb-domain-expert | signal-ingest-engineer | not started |
| `plan_1.1.5_mock_fm_stub` | signal-ingest-engineer | langgraph-engineer | not started |
| `plan_1.2_cohort_definition` | vitaldb-domain-expert | clinical-evaluator | not started |
| `plan_1.2.5_fm_interface_spec` | langgraph-engineer | signal-ingest-engineer | not started |
| `plan_1.3_emr_tools` | langgraph-engineer | vitaldb-domain-expert | not started |
| `plan_1.3.5_signal_access_tools` | signal-ingest-engineer | langgraph-engineer | not started (ADR-016 Accepted 2026-05-17) |
| `plan_1.4_baselines` | signal-ingest-engineer | clinical-evaluator | not started |
| `plan_1.5_surgery_context` | vitaldb-domain-expert | llm-prompt-engineer | not started |
| `plan_1.6_system_prompt` | llm-prompt-engineer | paper-writer (tone) | not started |
| `plan_1.6.5_mock_fm_rule_based` | signal-ingest-engineer | vitaldb-domain-expert | not started |
| `plan_1.7_tool_spec` | langgraph-engineer | llm-prompt-engineer | not started |
| `plan_1.7.5_mock_fm_light_ml` *(optional)* | signal-ingest-engineer | clinical-evaluator | not started |
| `plan_1.8_dual_mode_infra` | langgraph-engineer | signal-ingest-engineer | not started |

---

## 5. Stage별 완료 기준 (Acceptance Criteria per Stage)

### Stage 1 — 완료 조건
- [ ] VitalDB channel + numeric track 카탈로그 commit 완료 (`docs/vitaldb_catalog.md` 또는 동등 문서)
- [ ] 코호트 manifest (~5,800–6,000 cases) parquet/sqlite로 저장 + 스크립트로 재현 가능
- [ ] 5개 EMR tool (tool 8–12) 구현 + leakage-guard test 통과
- [ ] **5개 Signal Access tool (tool 17–21)** 구현 + leakage-guard test 통과 — `plan_1.3.5` (ADR-016). Tool 21 은 stub 까지 (`[DECISION PENDING ADR-014]`)
- [ ] 최소 3개 baseline end-to-end 실행 가능 (Logistic, XGBoost, LSTM)
- [ ] LangGraph dual-mode skeleton이 stub FM tool로 단일 case에서 동작
- [ ] Light + Heavy LLM system prompt v1 작성 + 검토 완료
- [ ] **21-tool spec** (JSON schema + LLM description) commit 완료 — `plan_1.7` (1–16) + `plan_1.3.5` (17–21 addendum)
- [ ] **Mock FM Tier 1 + Tier 2**가 end-to-end agent loop를 구동 (`plan_1.1.5`, `plan_1.6.5`)
- [ ] **Tier 1 ↔ Tier 2 swap**이 config만으로 가능 (agent / tool layer 코드 변경 없음) (`plan_1.2.5` factory)
- [ ] **`BiosignalFMInterface` Protocol**이 모든 기존 implementation에 대해 `runtime_checkable` 준수 test를 통과; swap 시 real FM이 변경 없이 들어맞도록 설계됨

### Stage 2 — 완료 조건
- [ ] FM checkpoint를 backend로 로드 (frozen)
- [ ] 7개 FM tool (tool 1–7)이 코호트 case에서 실 출력 반환
- [ ] Tool 21 `summarize_current_state` 가 ADR-014 Accepted 시 Tier 0 #14–16 호출로 stub→full 전환 (`plan_1.3.5` follow-up)
- [ ] Shallow loop가 real FM과 함께 시뮬레이션 case에서 end-to-end 실행
<!-- TODO: detail in stage2_fm_integration/ when Stage 1 closes -->

### Stage 3 — 완료 조건
- [ ] End-to-end shallow + deep mode 통합 완료
- [ ] 내부 validation set 평가 완료 (자동 metric + LLM-as-judge)
- [ ] Latency 목표 (shallow < 15s, deep < 60s) 목표 hardware에서 측정 완료
<!-- TODO: detail in stage3_full_agent/ -->

### Stage 4 — 완료 조건
- [ ] 5–7명 anesthesiologist onboarding 완료
- [ ] 200–300 브리프 평가 완료 (baseline과 blinded 비교)
- [ ] Cohen's κ 계산 완료; 결과를 paper용으로 freeze
<!-- TODO: detail in stage4_clinician_eval/ -->

### Stage 5 — 완료 조건
- [ ] npj DM에 draft 제출 완료
- [ ] Supplementary materials, code release, data reference freeze 완료
<!-- TODO: detail in stage5_paper/ -->

---

## 6. 변경 규칙 (Change Rules)

1. **`project-planner`만** `master_plan.md`를 작성한다. 다른 agent는 planner 호출을 통해 변경을 요청한다.
2. **단일 진실 원천**: 모든 spec은 `docs/project_brief.md` 또는 해당 stage plan에 위치한다. 중복 절대 금지 — 상호 참조 (cross-reference)로 연결한다.
3. **Stage rollover**: stage의 `README.md` placeholder는 **선행 stage가 ≥ 80% 완료된 시점**에만 `plan_<stage>.<n>_*.md` 파일로 확장된다.
4. **원자성 (Atomicity)**: sub-plan의 모든 `- [ ]` 작업은 단일 agent가 추가 분해 없이 수행 가능한 크기여야 한다.
5. **데이터 컨트랙트 (Data contract)** (tool I/O JSON schema, LangGraph state shape, LLM context budget, VitalDB API params)는 해당 plan 파일 내에서 versioning되며 추론으로 채우지 않는다.

---

## 7. 데이터 컨트랙트 (Data Contracts — project-wide)

기 확립된 contract는 해당 plan 파일로부터 mirror된다. 본 표는 stage 간 가시성을 위해 정리한 것이다.

| Contract | 정의 위치 | 상태 |
|----------|-----------|------|
| 21-tool JSON schema (1–16 + 17–21) | `plan_1.7_tool_spec.md` (1–16) + `plan_1.3.5_signal_access_tools.md` (17–21) | 1–16 ✅ (Sprint 4); 17–21 not started |
| `CurrentVitalsResult` (tool 17) | `plan_1.3.5_signal_access_tools.md` | not started |
| `SignalDescription` (tool 18) | `plan_1.3.5_signal_access_tools.md` | not started |
| `VariabilityResult` (tool 19) | `plan_1.3.5_signal_access_tools.md` | not started |
| `BaselineComparison` (tool 20) | `plan_1.3.5_signal_access_tools.md` | not started |
| `StateSynthesis` (tool 21) | `plan_1.3.5_signal_access_tools.md` | stub schema only; full schema gated on ADR-014 |
| LangGraph state shape | `plan_1.8_dual_mode_infra.md` | not started |
| Cohort manifest schema | `plan_1.2_cohort_definition.md` | not started |
| Surgery context taxonomy | `plan_1.5_surgery_context.md` | not started |
| Brief 9-section template | `docs/project_brief.md §8` | drafted |
| Light-mode narration template | `plan_1.6_system_prompt.md` | not started |
| `BiosignalFMInterface` Protocol | `plan_1.2.5_fm_interface_spec.md` (ADR-011 governance) | not started |
| FM Result dataclass | `plan_1.1.5_mock_fm_stub.md` (ADR-011 governance) | not started |
| Factory config (`configs/fm/*.yaml`) | `plan_1.2.5_fm_interface_spec.md` | not started |
| Mock noise-injection schema | `plan_1.6.5_mock_fm_rule_based.md` | not started |

---

## 8. 위험 등록부 (Risk Register)

| 위험 (Risk) | 영향 Stage | 대응 담당 | 상태 / 대응책 |
|-------------|-----------|-----------|---------------|
| FM 학습이 2개월을 초과 | 2 | project-planner | 모니터링 중 — Mock FM (ADR-011)이 Month-3 slippage를 흡수 |
| 70B heavy LLM이 GPU2 4-bit budget 초과 | 1.8 / 2 | langgraph-engineer | open |
| 200–300 브리프 평가를 위한 임상의 가용성 | 4 | project-planner + clinical-evaluator | open |
| ABP-absent 코호트 비율이 modality-agnostic 주장을 깸 | 1.2 | vitaldb-domain-expert | open |
| Time-window 슬라이싱에서 데이터 누수 (data leakage) 발생 | 1.3 / 1.7 | langgraph-engineer | open |
| Agent 설계가 Mock FM 행동에 과적합 (over-fits) | 1.6.5 / 2 | signal-ingest-engineer | Tier-2 noise injection + swap 시점 100-case mock-vs-real gap 분석으로 완화 (ADR-011) |
| Severe `department` imbalance (Urology n ≈ 94 post-filter; 2026-05-16 관찰)가 per-department subgroup 안정성을 깸 | 1.2 / 3 / 4 | clinical-evaluator | Urology를 wide CI로 보고하거나 subgroup-only 뷰에서만 다른 department와 pool. aggregate에서는 down-weight 금지 (`docs/project_brief.md §11.0`) |
| ABP-absent rate가 department와 상관 (Thoracic 2.5% vs General 51.9%); aggregate `modality-agnostic` 헤드라인이 오해를 부를 수 있음 | 1 / 11 | project-planner | brief §1 + §11.0가 stratified 보고를 요구; clinical-evaluator rubric이 강제; paper Results는 department별 `abp_absent`를 보고 (`docs/project_brief.md §1, §11.0`) |
| Pediatric / ASA = 6 inclusion 미결정; 코호트 크기 + baseline 성능에 영향 | 1.2 | project-planner | `[DECISION PENDING]`이 `docs/project_brief.md §4.1`과 `plan_1.2_cohort_definition.md`에 flag. 임상의 결정 전까지 manifest 확정 block |

---

## 9. 상태 로그 (Status Log)

세션별 상태 스냅샷은 `project-planner`가 agent memory `.claude/agent-memory/project-planner/project_status_<YYYY_MM_DD>.md`에 저장한다. 본 파일 (master_plan.md)은 최신 요약 한 줄만 보유한다.

> **2026-05-16 기준 상태**: Stage 1 시작. Agent 인프라 (`.claude/`, `.plans/`, `docs/project_brief.md`) 부트스트랩 중. Sub-plan 실행은 아직 시작되지 않았다.
