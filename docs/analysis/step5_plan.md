# Step 5 실행 계획 (Step 5 Execution Plan) — VitalAgent `.claude` 라인업 + Plan 구조 + Master Context

> 작성일: 2026-05-16
> 입력: `docs/analysis/existing_agents.md`, `docs/analysis/agent_mapping.md`, 사용자 결정 사항 (2026-05-16)
> 출력 대상: VitalAgent 프로젝트 루트 (`C:\Projects\VitalAgent\`)

본 문서는 **무엇을 만들 것인지에 대한 계약서**다. confirm 후 본 계획 그대로 파일 생성에 들어간다.

---

## 0. 핵심 결정 반영 체크리스트 (Decision Checklist)

- [x] 신설 agent 3개 한꺼번에 (langgraph / prompt / vitaldb)
- [x] `vitaldb-domain-expert` scope을 *technical* domain (VitalDB schema / API / signal 처리)으로 좁힘
- [x] 모든 agent에 "임상 fact 단정 금지 — 임상의 (이형철 교수님 그룹) review 필수" guard를 공통 규칙으로 명시
- [x] Plan 구조: BFM 골격 (`master_plan` + sub-plans + status log) + **Stage별 디렉토리**
- [x] Memory: project-scope으로 통일, `plan-eval/` 흔적 디렉토리는 이식 안 함
- [x] `paper-writer` memory는 비어있는 채로 재시작
- [x] `CLAUDE.md` = 짧은 entrypoint. 상세는 `docs/project_brief.md`에서 정리하고 reference

---

## 1. 생성할 파일 목록 (File Inventory)

```
VitalAgent/
├── CLAUDE.md                                                 # NEW: short entrypoint
├── docs/
│   └── project_brief.md                                      # NEW: master context (11 항목)
├── .claude/
│   ├── agents/
│   │   ├── project-planner.md                                # MOD from BFM
│   │   ├── signal-ingest-engineer.md                         # MOD from BFM data-engineer
│   │   ├── langgraph-engineer.md                             # NEW
│   │   ├── llm-prompt-engineer.md                            # NEW
│   │   ├── clinical-evaluator.md                             # MOD from BFM estimator
│   │   ├── vitaldb-domain-expert.md                          # NEW (scope-narrowed)
│   │   └── biomedical-ai-paper-writer.md                     # MOD from BFM (npj DM tone)
│   ├── agent-memory/
│   │   ├── project-planner/MEMORY.md                         # empty index
│   │   ├── signal-ingest-engineer/MEMORY.md                  # empty index
│   │   ├── langgraph-engineer/MEMORY.md                      # empty index
│   │   ├── llm-prompt-engineer/MEMORY.md                     # empty index
│   │   ├── clinical-evaluator/MEMORY.md                      # empty index
│   │   ├── vitaldb-domain-expert/MEMORY.md                   # empty index
│   │   └── biomedical-ai-paper-writer/MEMORY.md              # empty index
│   └── settings.local.json                                   # NEW: minimal permission scaffold (§6 참조)
└── .plans/
    ├── master_plan.md                                        # NEW: SoT
    ├── stage1_preparation/
    │   ├── plan_1.1_vitaldb_exploration.md
    │   ├── plan_1.2_cohort_definition.md
    │   ├── plan_1.3_emr_tools.md
    │   ├── plan_1.4_baselines.md
    │   ├── plan_1.5_surgery_context.md
    │   ├── plan_1.6_system_prompt.md
    │   ├── plan_1.7_tool_spec.md
    │   └── plan_1.8_dual_mode_infra.md
    ├── stage2_fm_integration/README.md                       # placeholder (skeleton + TBD)
    ├── stage3_full_agent/README.md                           # placeholder
    ├── stage4_clinician_eval/README.md                       # placeholder
    └── stage5_paper/README.md                                # placeholder
```

**총 파일 수: 30개** (디렉토리 자동 생성 별도)

---

## 2. 문서 layer outline (Document Layer Outline)

### 2.1 `CLAUDE.md` (entrypoint, 짧게)
- 한 줄 정체성 + tagline
- "상세는 `docs/project_brief.md` 참조" — 본 파일을 SoT로 지정
- Agent roster 1줄 요약 (7개 + 호출 trigger)
- Plan 구조 1줄 요약 (`.plans/master_plan.md` + `stage{1..5}_*/`)
- 코딩 / 문서 컨벤션 (Python 3.x + LangGraph + 한글 친화 보고)
- 공통 guard: **임상 fact 단정 금지 — 임상의 review marker 사용** 강조
- 길이 목표: 약 50 lines

### 2.2 `docs/project_brief.md` (Master Context, SoT)
사용자가 제시한 **11개 항목** 그대로 챕터화. 사용자가 이전 대화에서 가진 상세 값 (직접 접근 불가)은 `<!-- TODO: fill from prior session -->` 마커로 자리를 잡아둔다.

| # | Section | 채울 수 있는 부분 | TODO 마커 부분 |
|---|---------|------------------|----------------|
| 1 | Project identity & tagline | 골격 (tool-using LLM agent for intraoperative monitoring) | 정확한 tagline 문구 |
| 2 | Why now / problem statement | 골격 | 임상적 motivation 본문 |
| 3 | Foundation Model context | K-MIMIC ICU pretrained / 13 tasks / 2-month ETA 골격 | FM 정확한 이름, downstream 13 task 목록 |
| 4 | VitalDB 데이터 | 6,388 cases / non-cardiac surgery 골격 | filter criteria 상세 |
| 5 | Cohort 정책 | minimum filter / ~5,800–6,000 cases 골격 | 정확한 inclusion / exclusion |
| 6 | Dual-mode architecture | Shallow 30초 + Deep on-demand 골격 | Shallow loop trigger 조건, Deep escalation rule |
| 7 | Tool suite (16개) | 카테고리 분류 (FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2) | 16개 tool name + I/O signature |
| 8 | Brief 포맷 | 한글 / 9 sections / surgery-aware / quality-aware 골격 | 9 section header |
| 9 | 5-stage plan | Month 1–2 ~ 9–10 골격. Stage 1만 detail | Stage 2–5 상세 |
| 10 | Real-time = simulated real-time | 골격 (offline VitalDB → wall-clock simulation) | 시뮬레이터 정확한 매핑 |
| 11 | Target venue + evaluation | npj DM / 5–7 clinicians / 200–300 brief 골격 | scoring rubric 정확본 |

→ **사용자에게 요청**: 본 파일 1차 생성 후 TODO 마커 자리에 prior-session 정리본을 paste하면 SoT 완성. 그 전에는 agent들이 본 파일을 reference해도 placeholder임을 인지하도록 상단에 status banner 추가.

---

## 3. Plan layer outline

### 3.1 `.plans/master_plan.md`
- Project mission (1 단락)
- 5-stage roadmap 표 (stage / month / 핵심 산출물 / owner agent들)
- Critical path (graph-ish text)
- Stage 1 8개 sub-plan과 owner agent 매핑 표
- Acceptance criteria (stage별 done 정의)
- 변경 규칙: `project-planner`만 master를 수정 가능. 다른 agent는 sub-plan 갱신만.

### 3.2 `.plans/stage1_preparation/plan_1.*.md` (8개)
BFM `project-planner` format을 그대로 따른다.
```
# plan_1.X — <title>
Owner: <agent-name>
Status: in progress / blocked / done
Goal: <한 문장>

## Tasks
- [ ] **[Priority]** description
  - 입력: ...
  - 출력: ...
  - 의존성: ...
  - 참고: ...
```

8개 plan의 owner 매핑 (잠정):

| 파일 | 1차 담당 | 보조 |
|------|----------|------|
| `plan_1.1_vitaldb_exploration` | vitaldb-domain-expert | signal-ingest-engineer |
| `plan_1.2_cohort_definition` | vitaldb-domain-expert | clinical-evaluator (review) |
| `plan_1.3_emr_tools` | langgraph-engineer | vitaldb-domain-expert |
| `plan_1.4_baselines` | signal-ingest-engineer | clinical-evaluator |
| `plan_1.5_surgery_context` | vitaldb-domain-expert | llm-prompt-engineer |
| `plan_1.6_system_prompt` | llm-prompt-engineer | paper-writer (tone) |
| `plan_1.7_tool_spec` | langgraph-engineer | llm-prompt-engineer (description) |
| `plan_1.8_dual_mode_infra` | langgraph-engineer | signal-ingest-engineer |

각 파일은 **3 ~ 6개의 atomic task** 골격으로 시작한다. 사용자가 prior session에서 정한 구체 값이 있으면 채우고, 없으면 `<!-- TODO -->` 마킹.

### 3.3 `.plans/stage{2..5}_*/README.md` (4개, placeholder)
Skeleton만:
```
# Stage N — <title>
Status: not started
Predecessor: stage N-1
Goal (one-liner): ...
Sub-plans (TBD when stage approaches): ...
```

---

## 4. Agent layer outline (`.claude/agents/`)

모든 agent는 BFM 표준 골격을 유지한다.

- YAML frontmatter (`name`, `description` w/ trigger examples, `model: opus`, `memory: project`, color / tools as needed)
- Identity 단락
- Primary Directive (plan 파일 fresh read)
- Workflow (1. Read plan → 2. Identify task → 3. Execute → 4. Update plan + memory)
- Project Context (요약 + `docs/project_brief.md` reference)
- Quality Standards
- "Update your agent memory" 절
- **Persistent Agent Memory** 표준 block (4 type, `MEMORY.md` 패턴)
- **공통 guard 절** — 신설: "임상 사실 단정 금지, 임상의 review 필수, `[CLINICIAN-REVIEW]` marker 사용"

각 agent별 차이점만 정리:

### 4.1 `project-planner.md` (MOD)
- BFM 골격 그대로 + 다음 갱신:
  - Project context를 VitalAgent (LangGraph, dual-mode, npj DM)로 교체
  - Sub-agent roster 갱신: 6명 (signal-ingest / langgraph / prompt / clinical-eval / vitaldb-expert / paper-writer)
  - Plan 파일 경로 갱신: `.plans/master_plan.md` + `.plans/stage{1..5}_*/plan_*.md`
  - 데이터 컨트랙트 항목 확장: **(a) Tool I/O schema, (b) LangGraph state shape, (c) LLM context budget (tokens), (d) VitalDB API call signature** — tensor shape는 부수 항목으로 강등
  - "🛑 NO CODE" 원칙 유지
  - 한글 status report format 유지
  - tools 목록은 BFM 그대로 (Skill / Task* / Worktree / Cron / Glob / Grep / Read / Edit / Write / NotebookEdit / WebFetch / WebSearch + ide diagnostics)

### 4.2 `signal-ingest-engineer.md` (MOD from data-engineer)
- Identity 재정의: PyTorch dataset 빌더 → **VitalDB stream + 30초 window feature extractor**
- Plan 파일: `.plans/stage1_preparation/plan_1.1_vitaldb_exploration.md`, `plan_1.4_baselines.md`, `plan_1.8_dual_mode_infra.md`
- 책임:
  - VitalDB API 호출 (`vitaldb.find_cases`, `vitaldb.load_case`)
  - Channel selection (ECG, ABP, PPG, EEG 등) + sampling rate 처리
  - 30초 window slicing + simulated real-time tick generator
  - Shallow 출력: 수치 요약 (JSON serializable, LLM-readable)
  - Deep 출력: raw window tensor (FM 입력용)
- Conventions: tensor shape 인라인 주석은 유지 (Deep 모드). Shallow 모드는 JSON schema 명시.
- Stack: vitaldb, numpy, pandas, (옵션) torch
- **PyTorch Dataset / Collate는 부수**로만. main은 streaming임을 명시.

### 4.3 `langgraph-engineer.md` (NEW)
- Identity: LangGraph StateGraph / Node / Edge architect + tool registry 운영자
- Plan 파일: `plan_1.7_tool_spec.md`, `plan_1.8_dual_mode_infra.md`, `plan_1.3_emr_tools.md`
- 책임:
  - State schema (TypedDict / Pydantic) 설계
  - Node 함수 (shallow_loop, deep_analyze, brief_writer, tool_executor 등)
  - Conditional edge (Shallow → Deep escalation rule)
  - Tool registry: 16-tool suite 등록 + I/O 계약
  - Retry / fallback / timeout 정책
  - Trace / logging hook
- Stack: langgraph, langchain (tool integration), pydantic, structlog (logging)
- Conventions: typed state, node에서 implicit side effect 금지, deterministic edge logic.

### 4.4 `llm-prompt-engineer.md` (NEW)
- Identity: System prompt + tool description specialist
- Plan 파일: `plan_1.6_system_prompt.md`, `plan_1.7_tool_spec.md` (tool description 부분), `plan_1.5_surgery_context.md` (prompt embedding)
- 책임:
  - System prompt 초안 / 개정 (한글 우선, 영문 옵션)
  - Tool description writing (LLM이 정확히 호출하도록 계약 명시)
  - 브리프 generator prompt (9-section 한글 브리프, surgery-aware, quality-aware)
  - Hallucination guard: `[CLINICIAN-REVIEW]` marker 사용 강제
  - Prompt versioning (`prompts/v{N}_*.md` 권장 패턴 명시)
- Hard rule: 임상 fact 단정 절대 금지. 모든 진단성 문장은 marker 또는 조건문 (conditional) phrasing (예: "수치는 X이며 임상의 판단 필요").
- 출력 형식: markdown prompt 파일 (코드 X).

### 4.5 `clinical-evaluator.md` (MOD from estimator)
- Identity 재정의: 코드 평가 → **임상 시나리오 평가**
- Plan 파일: `.plans/stage4_clinician_eval/` 하위 plan (Stage 4 도달 시 생성)
- 평가 rubric (5 axis):
  1. Scenario accuracy (정답률)
  2. Latency (응답 시간, Shallow loop 기준)
  3. False-alarm rate (overcalling)
  4. Hallucination (근거 없는 임상 단정)
  5. Patient-safety severity (오류 발생 시 위해 등급)
- 출력 포맷:
  ```
  Scenario: <id>
  Transcript: <agent I/O excerpt>
  Score: accuracy=X/5, latency=Yms, hallucination=Z(count)
  Severity: critical/warning/suggestion
  Clinician review needed: yes/no
  ```
- 3-tier 분류 (critical / warning / suggestion) 골격은 유지
- **임상의 review workflow hook**: 본 agent가 1차 자동 평가 → 임상의 (이형철 교수님 그룹) 2차 review slot 마련

### 4.6 `vitaldb-domain-expert.md` (NEW, **scope 좁힘**)
- Identity: VitalDB **technical** domain expert (data structure / API / signal channel)
- **Scope IN**:
  - VitalDB database schema (cases, trks, signal hierarchy)
  - Python `vitaldb` package API
  - Wave / numeric 채널 naming convention (`SNUADC/ART`, `BIS/EEG`, EtCO2 등)
  - Channel별 sampling rate
  - EMR 컬럼 의미 (case-level metadata, drug administration timestamp의 데이터 구조 측면)
- **Scope OUT** (Hard rule):
  - 임상 진단 단정
  - 약물 dose 권고
  - 예후 판단
  - "이 신호 패턴이 X 상태를 의미한다" 식의 단정
- 위 항목은 항상 `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` marker로 출력
- Plan 파일: `plan_1.1_vitaldb_exploration.md`, `plan_1.2_cohort_definition.md`, `plan_1.3_emr_tools.md`, `plan_1.5_surgery_context.md`
- 출력 형식: markdown notes / schema spec / API reference card (코드는 `signal-ingest-engineer`가 작성)

### 4.7 `biomedical-ai-paper-writer.md` (MOD)
- BFM 골격 그대로 + 다음 갱신:
  - Target venue 기본값을 **npj Digital Medicine**으로
  - Tone: 임상 venue 친화 (clinical narrative + technical rigor)
  - 표준 참조: CONSORT-AI / SPIRIT-AI / TRIPOD-AI / DECIDE-AI / CONSORT-AI extension 인지
  - Read-only 유지 (tools: Glob, Grep, Read, WebFetch, WebSearch) — 결과는 텍스트 출력으로만
  - `[CITATION NEEDED]`, `[FIGURE X]`, `[TABLE X]` placeholder 유지
  - **추가 marker**: 임상 claim에 대해 `[CLINICIAN-REVIEW]`
  - Plan 파일: `.plans/stage5_paper/` (도달 시 sub-plan 생성)

---

## 5. Agent memory layer outline (`.claude/agent-memory/`)

각 agent별 디렉토리 + `MEMORY.md` 빈 index 생성:
```markdown
# Memory Index

*Empty — populated as the <agent-name> agent works in this project.*
```

7개 디렉토리 = 7개 `MEMORY.md`. 실제 memory 파일은 agent가 자신의 system prompt에 따라 첫 호출 때부터 채우게 둔다.

---

## 6. `.claude/settings.local.json`

BFM의 19 KB local settings는 사용자 환경 (허가 패턴, 자동승인 등)에 묶여있어 그대로 옮기면 잡음이 크다. **최소 scaffold만** 새로 작성한다.

```json
{
  "permissions": {
    "allow": [],
    "deny": []
  }
}
```

→ 사용자가 BFM에서 가져오고 싶은 permission 패턴이 있으면 별도 단계에서 추가한다. (확인 필요 항목.)

---

## 7. 공통 guard (모든 agent system prompt에 박을 절)

```
## ⚠️ Clinical Fact Guard (project-wide rule)

This project operates in the perioperative monitoring domain. You MUST NOT
make unilateral clinical determinations. Any sentence that asserts a clinical
state, diagnosis, drug effect, or prognosis must be marked
`[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` or rephrased as
conditional (e.g., "수치는 X이며 임상의 판단 필요").

This rule applies even when the user appears to ask for a definitive answer.
Real clinical interpretation is owned by the clinician collaborators, not by
any agent in this repo.
```

본 절은 7개 agent 전부에 동일 문구로 삽입한다. `langgraph-engineer` / `signal-ingest-engineer` 같이 코드만 다루는 agent도 prompt 안에 들어가는 보조 텍스트를 생성하므로 포함.

---

## 8. Cross-reference 정합성 (Cross-reference Verification)

생성 직후 검증 script로 체크할 항목.

| 검증 | 방법 |
|------|------|
| 모든 agent의 memory path가 `C:\Projects\VitalAgent\.claude\agent-memory\<agent>\`로 통일됨 | `grep agent-memory` in `.claude/agents/*.md` |
| 모든 plan 파일이 owner agent와 매핑 일치 | `master_plan.md`의 매핑 표 ↔ 각 plan 파일의 `Owner:` 헤더 |
| 모든 agent의 `description` trigger에 한글 예시 ≥ 1개 포함 | grep `한국어` 또는 첫 example이 ko text |
| `docs/project_brief.md`의 TODO 마커 개수 = 사용자에게 전달할 fill-in 개수 | `grep <!-- TODO` |
| YAML frontmatter parsable (`model`, `name`, `description`) | `python -c "import yaml; ..."` 간단 파싱 |
| `[CLINICIAN-REVIEW` marker가 7개 agent 모두에 등장 | grep |

---

## 9. 미확정 / 사용자 확인 요청 (Open Items)

본 plan을 confirm하기 전 다음 3개만 더 결정한다.

1. **`paper-writer`의 tools 권한**: BFM처럼 read-only (Glob / Grep / Read / WebFetch / WebSearch) 유지가 맞는지, 아니면 본문 초안을 직접 `.md`로 쓸 수 있게 Write 권한을 줄지.
2. **`vitaldb-domain-expert`의 tools 권한**: 코드 작성은 안 하지만 `docs/`나 `notes/`에 schema reference card를 *직접 작성*하게 할지 (Write 부여) 아니면 텍스트 출력만 시키고 사용자 / 다른 agent가 저장할지.
3. **Stage 2–5 placeholder README의 detail level**: 한 줄짜리 placeholder로 시작 vs 사용자가 prior session에서 정리한 stage 2–5 내용을 paste할 자리 (TODO block) 마련.

기본 권장: (1) Write 권한 추가 (실용성), (2) 텍스트 출력만 (역할 분업 명확), (3) TODO block 자리 마련 (확장성).

---

## 10. Confirm 후 진행 순서 (Execution Order)

1. `docs/project_brief.md` 생성 (TODO 마커 자리 잡기)
2. `CLAUDE.md` 생성 (`project_brief`를 reference)
3. `.plans/master_plan.md` + `stage1_preparation/plan_1.*.md` 8개 + Stage 2–5 README 4개
4. `.claude/agents/*.md` 7개
5. `.claude/agent-memory/<agent>/MEMORY.md` 7개
6. `.claude/settings.local.json` 최소본
7. **검증** (§8 cross-reference 체크)
8. 결과 보고 (생성 파일 트리 + TODO 마커 위치 목록)

---

위 계획대로 진행해도 되는지, 또는 어디 수정할지 알려주세요.
