# OpSight — Claude Code 진입점 (Entrypoint)

> 이 repo에서 작업을 시작하는 모든 Claude (또는 사람)을 위한 짧은 안내.
> 전체 프로젝트 맥락은 **`docs/project_brief.md`를 먼저 읽는다**.

## 1. 본 프로젝트 (What this project is)

**OpSight**는 multimodal biosignal Foundation Model (K-MIMIC ICU pretrained, frozen backend로 활용)을 기반으로 한 tool-using LLM agent다. 술중 (intraoperative) 혈역학 (hemodynamics) 추론을 시뮬레이션된 실시간 (simulated real-time)으로 수행한다.

- 비심장 주요 수술 (non-cardiac major surgery; general / thoracic / urologic / gynecologic) 전반에 대해 Universal
- 모달리티 비의존 (modality-agnostic), 신호 품질 인지 (quality-aware), 수술 인지 (surgery-aware)
- 이중 모드 (dual-mode): Shallow 30초 loop + Deep on-demand 브리프 (brief)
- 목표 venue: **npj Digital Medicine**

→ 정체성, 데이터셋, tool suite, 브리프 형식, 평가, 기술 스택 등 상세는
**`docs/project_brief.md`** (단일 진실 원천, Single Source of Truth, SoT)에 위치한다.

## 2. 어디를 보는가 (Where to look)

| 필요한 정보 | 경로 |
|-------------|------|
| 프로젝트 정체성 + 모든 수치 | `docs/project_brief.md` |
| Master plan (5 stage, agent 담당) | `.plans/master_plan.md` |
| Stage 1 작업 분해 | `.plans/stage1_preparation/plan_1.{1..8}_*.md` |
| Stage 2–5 (현재 placeholder) | `.plans/stage{2..5}_*/README.md` |
| Agent별 정체성 | `.claude/agents/*.md` |
| Agent별 persistent memory | `.claude/agent-memory/<agent>/MEMORY.md` |
| 용어집 (translation ground truth) | `docs/terminology.md` |
| 주요 설계 결정 (ADR) | `docs/decisions/ADR-*.md` |
| Tool 레지스트리 (등록된 tool 카탈로그) | `opsight/registry.py` |

## 3. Agent 라인업 (Agent roster, 7명)

| Agent | 호출 시점 |
|-------|-----------|
| `project-planner` | 진행 상황 파악, 다음 작업 계획, master_plan 갱신, sub-agent 작업 할당 |
| `signal-ingest-engineer` | VitalDB streaming, 30초 window feature, simulated real-time, FM 입력 준비 |
| `langgraph-engineer` | StateGraph / Node / Edge 구현, tool registry, dual-mode 분기 |
| `llm-prompt-engineer` | System prompt, tool description, 브리프 생성 prompt, hallucination 가드 |
| `clinical-evaluator` | 임상 시나리오 평가, false-alarm / latency / hallucination 측정, clinician review hook |
| `vitaldb-domain-expert` | VitalDB schema / API / channel / sampling rate / EMR data structure 지식 (텍스트 출력만) |
| `biomedical-ai-paper-writer` | 논문 작성 / 수정 (npj DM 타겟; write 경로 제한 — agent charter 참조) |

## 4. 프로젝트 전반 강제 규칙 (Project-wide hard rules)

본 규칙은 모든 agent의 system prompt에 강제된다. 전문은 `docs/project_brief.md §13`에 위치한다. 요약:

1. **⚠️ Clinical Fact Guard (임상 사실 가드)** — 어떤 agent도 임상 사실을 단독으로 단정하지 않는다. 임상 사실은 `[CLINICIAN-REVIEW: 의료진 검토 필요]` marker를 붙이거나 조건문 (conditional)으로 재서술한다.
2. **데이터 누수 (data leakage) 금지** — 시뮬레이션 시점 t에서는 t 이하의 데이터만 읽을 수 있다.
3. **Trigger(알람) 결정은 rule-based** — *알람을 울릴지*의 결정은 LLM-driven이 아니다. 단 (ADR-023, tiered escalation): rule router가 **애매 (ambiguous)**로 분류한 케이스에 한해, LLM이 deep 조사에서 적절한 tool을 선택 (ReAct)할 수 있다. 이때도 **최종 알람 발화는 rule gate를 통과**하며 LLM은 정보 (예측치)만 제공한다 — 즉 규칙이 묶는 것은 *알람 결정*이지 *조사 중 tool 선택*이 아니다.
4. **언어 정책 (language policy)** — [ADR-PENDING: brief language] 2026-05-19 부터 **영문 우선 (English-first)** 로 전환 검토 중. 결정 시점까지 다음을 따른다:
   - **Agent 출력 (브리프 / shallow narration / LLM-generated text)**: 영문 prompt 가 default (`prompts/*.en.md`). 한글 변형 (`prompts/*.md`) 도 유지하여 `--lang ko` 로 선택 가능. 모델 선택: 영문 Heavy slot = OpenBioLLM-70B 후보, 한글 Heavy slot = Llama-3.3-70B.
   - **Planner / project 보고 / 회의 자료 / 옵시디언 노트 / commit message**: 한글이 default (project 운영 효율).
   - **코드 식별자, tool I/O JSON, paper draft, github PR description**: 영문이 default.
   - 임상 deployment 시점의 한글 brief variant 는 별도 fine-tune 후 결정 (Stage 4+ ADR).

## 5. 코딩 컨벤션 (Coding conventions)

- Python (LangGraph + vLLM + PyTorch + `vitaldb`)
- LangGraph state는 typed (TypedDict / Pydantic)
- Tool I/O 계약은 JSON schema로 정의하고 `plan_1.7_tool_spec.md`에 문서화한다
- Tensor shape은 등장 시 인라인 주석으로 표기 (Deep 모드 FM 입력 준비)
- `.plans/`와 `docs/`에는 코드를 두지 않는다 — 모두 markdown 전용
- `project-planner` agent는 Python을 작성하지 않으며 `.md`만 작성한다

## 6. Plan 파일 작업 흐름 (Plan-file workflow — BFM pattern, kept)

1. 작업 agent는 호출 시점마다 자신의 plan 파일을 **다시 읽는다** (매번 새로 읽으며 캐시하지 않는다).
2. 다음 미완료 작업을 식별한다.
3. 작업을 수행하고 plan 파일을 갱신한다 (`[x]`로 완료 표시, 필요한 메모 추가).
4. 비자명한 맥락을 발견한 경우 해당 agent의 `agent-memory/<agent>/MEMORY.md` 인덱스를 갱신한다.

## 7. 현재 상태 (Status)

**Stage 1 (Month 1–2) — Preparation**이 현재 active stage다.
FM 학습은 병행 진행되며 Stage 2 시작 시점 (약 2개월 후)에 도착한다. 그 사이 agent system 개발은 **Mock FM** (`docs/decisions/ADR-011-mock-fm-strategy.md`)을 활용하여 중단 없이 진행된다.

**제어 구조 방향 (ADR-023, Proposed)** — rule이 뻔한 케이스를 즉시 처리 (알람)하고, 애매한 케이스만 LLM+FM 조사로 escalation하는 **tiered triage**로 전환 검토 중. 이로써 "agent" 자율성을 patient-safety를 해치지 않는 bounded place에 두고, rule-vs-LLM ablation을 평가에 내장한다.

**Tool 레이어 현황** (`opsight/registry.py` 가 authoritative):
- `opsight/tools/signal_state_tools/` — leaf extractor 5개 (`extractors/`) + 합성 apex `summarize.py` (rule-based 현재상태 평가; snapshot + trend).
- `opsight/tools/emr_tools/` — `get_patient_context` (수술 전 환자 컨텍스트, 누수-0 화이트리스트). 구 EMR 그룹 중 먼저 부활한 멤버.
- `opsight/tools/fm_tools/` — 플래그십 단일 `predict_hypotension` (저혈압 조기 예측). 아직 deferred stub; 나머지 FM 후보는 `FM_DEFERRED_CANDIDATES`로 보류 (ADR-023).
- `opsight/tools/auxiliary_tools.py` — `surgery_context_awareness`, `quality_aware_synthesis`.
