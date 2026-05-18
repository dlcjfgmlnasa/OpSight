# Biosignal-FM Team Agent 분석 (Existing Agents Analysis)

> 원본 위치: `C:\Projects\Biosignal-Foundation-Model\.claude\`
> 분석일: 2026-05-16
> 발견한 subagent: **5개** (+ 흔적 디렉토리 `plan-eval/` 1개)

## 1. 디렉토리 구조 (Directory Structure)

```
.claude/
├── agents/                              # 5 subagent 정의
│   ├── biomedical-ai-paper-writer.md
│   ├── data-engineer.md
│   ├── estimator.md
│   ├── model-architect.md
│   └── project-planner.md
├── agent-memory/                        # per-agent persistent memory
│   ├── biomedical-ai-paper-writer/      (비어있음)
│   ├── data-engineer/                   (3 files)
│   ├── estimator/                       (4 files)
│   ├── model-architect/                 (2 files)
│   ├── plan-eval/                       (흔적 디렉토리, agent .md 없음 — estimator로 rename된 것으로 추정)
│   └── project-planner/                 (12 files, status log 다수 — 운영 허브 역할)
├── settings.local.json
└── scheduled_tasks.lock
```

**참고**: CLAUDE.md, `commands/` 디렉토리는 존재하지 않는다.

## 2. Agent별 요약 표 (Agent Summary Table)

| Name | Role | Model | Tools | 호출 trigger | Style / Personality | BFM에서의 활용 |
|------|------|-------|-------|--------------|---------------------|----------------|
| **project-planner** | AI Project Manager / Chief Orchestrator. `master_plan.md` 기반으로 모든 workstream을 조율하고 sub-agent에 작업 할당 | opus | Skill, TaskCreate / Get / Update / List, Worktree, Cron, Glob, Grep, Read, Edit, Write, NotebookEdit, WebFetch / Search, mcp__ide__getDiagnostics | "프로젝트 진행 상황 파악", "다음 작업 계획", "`master_plan.md` 업데이트", "EEG 지원 추가 계획" | **No Code 원칙** — `.md` 파일만 읽고 쓴다. `master_plan.md` = single source of truth. 작업을 atomic하게 분해, 데이터 컨트랙트 (tensor shape, file format)를 명시. 한글 보고서. | 12개 status 로그 (2026-03 ~ 05) — 사실상 프로젝트 운영 허브. Data / Model / Eval 진척도 % 추적, V1 / V2 실험 전략 결정, K-MIMIC 합류 같은 마일스톤 기록 |
| **data-engineer** | 생체신호 (ECG / EEG / PPG / ABP / ICP) PyTorch 데이터 파이프라인 전문가. dataset, collate, parser 구현 | opus | (frontmatter에 tools 미명시 → 기본 전체) | "`plan_data.md` 다음 태스크", "데이터 파이프라인 구현", "새 parser 추가" | `.plans/.agent_plan/plan_data.md` 절대 우선. tensor shape 인라인 주석 의무, `jaxtyping` 금지, Channel-Independent + lazy-loading + sliding window 패턴 | Sleep-EDF parser, BiosignalDataset, PackCollate (FFD bin-packing), Multi-Resolution patch, EEG 제외 결정 (2026-04-08), 13 downstream task modality spec |
| **model-architect** | PyTorch Foundation Model 아키텍처 전문가. Transformer (GQA / MHA / MQA), MoE, RMSNorm, RoPE, PatchEmbedding | opus | (전체) | "`plan_model.md` 다음 단계", "새 head 추가", "MoE 적용" | `module/` (primitive) → `model/` (composition) 계층. 모든 `nn.Module`에 shape 주석 docstring. plan 파일 갱신 의무. | BiosignalFoundationModel (Scaler → Patch → Transformer → Head), Switch Transformer MoE, V1 / V2 실험 (raw 복원 vs CNN stem 복원) |
| **estimator** | 코드 / 아키텍처 / 완성도 평가 agent. `plan_eval.md` 기준 evidence-based 평가 | opus | (전체) | "eval 진행", "지금까지 작업 평가", "plan eval 기준 체크" | critical / warning / suggestion 3-tier 분류, 파일 : line 인용 필수. `plan_eval.md` 매 호출마다 fresh read. | Train pipeline review (`clone()` 버그 발견), `CSVLogger` `eeg_loss` 누락, `static_graph` 미설정, 9-task downstream 평가 |
| **biomedical-ai-paper-writer** | Biomedical Engineering × AI 시니어 연구자. 논문 작성 / 수정 (KR / EN) | opus | Glob, Grep, Read, WebFetch, WebSearch (편집 도구 없음 — read-only + 텍스트 출력) | "Introduction 작성", "Results / Discussion 작성", "abstract 다듬어", "Related Work 정리" | `[CITATION NEEDED]` placeholder 강제. fake citation 절대 금지. Nature BME / IEEE TBME / NeurIPS 톤. 한글 본문 + 영문 기술 용어 in parentheses. | 메모리는 비어 있음 — 사용 빈도는 낮았던 것으로 추정 |

## 3. 공통 패턴 (Common Patterns — 5개 agent 공유)

- **Model**: 전원 `opus`
- **Memory**: 전원 `memory: project` (project-scope persistent memory)
- **Plan-file-driven workflow**: `.plans/.agent_plan/plan_*.md`를 호출마다 fresh read → 작업 → 완료 마킹. project-planner는 plan 작성 측, 나머지 3개 (data / model / eval)는 plan 소비 측.
- **Persistent Memory block**: 모든 agent가 동일한 약 150 line memory system prompt를 frontmatter 뒤에 포함. user / feedback / project / reference 4 type, `MEMORY.md` 인덱스 패턴.
- **한글 친화**: trigger 예시 · 보고 포맷이 한글 우선

## 4. 흔적 관찰 (Vestigial Observations)

- `agent-memory/plan-eval/`은 디렉토리만 존재하고 안에 파일이 없다. 과거에 `plan-eval`이라는 agent가 있다가 `estimator`로 rename된 흔적으로 추정.
- `project-planner`의 status log가 매우 풍부 (2026-03-21 ~ 2026-05-13). 실제로 가장 많이 호출된 agent다.
- `data-engineer`의 memory 파일이 사용자 path (`C:\Users\SNUH_VitalLab_LEGION\.claude\agent-memory\data-engineer\`)로 적혀 있다. 프로젝트 path와 불일치. **재이식 시 path 일관성 점검 필요**.
