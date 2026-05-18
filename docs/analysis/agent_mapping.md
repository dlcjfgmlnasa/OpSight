# Biosignal-FM Agents → VitalAgent 매핑 (Agent Mapping)

> VitalAgent 핵심 특성 요약:
> - Tool-using LLM agent for intraoperative monitoring
> - VitalDB 오픈데이터 활용
> - Multimodal biosignal + LLM 통합
> - 이중 모드 (dual-mode): Shallow 30초 loop + Deep on-demand
> - LangGraph 기반 orchestration
> - 마취과 임상의 평가 필수 (이형철 교수님 그룹)
> - npj Digital Medicine 투고 목표

## 1. 핵심 차이 (Decision Rationale)

| 축 | Biosignal-FM | VitalAgent |
|----|--------------|------------|
| 산출물 | PyTorch foundation model (pretraining) | Tool-using LLM agent (inference-time orchestration) |
| 코드 비중 | `module/`, `model/`, `data/` PyTorch | LangGraph node, LLM prompt, tool schema |
| 데이터 흐름 | offline batch → DataLoader → train | online stream (VitalDB) → feature → LLM context |
| 평가 주체 | 정량 metric (AUROC, MSE) | 마취과 임상의 (이형철 교수님 그룹) + 시나리오 평가 |
| 출력 목표 | top-tier ML venue | npj Digital Medicine (임상 venue) |

→ **결론**: data 처리 + 논문 + planning + 평가는 재사용 가치가 크다. 그러나 `model-architect`의 "PyTorch foundation model 빌더" 정체성은 VitalAgent에 그대로는 들어맞지 않는다.

## 2. 매핑 결정 (Mapping Decisions)

### (A) 그대로 재사용 — 1개

| Agent | 근거 |
|-------|------|
| (없음) | BFM 5개 중 VitalAgent 환경에서 *전혀 수정 없이* 100% 들어맞는 것은 없다. paper-writer가 가장 가깝지만 venue / 톤 가이드를 npj DM에 맞춰 미세 조정해야 함 → (B)로 분류 |

### (B) 수정해서 재사용 — 4개

| 원본 | 새 이름 (제안) | 수정 포인트 |
|------|----------------|-------------|
| **project-planner** | **project-planner** (유지) | (1) `master_plan.md` 구조를 LangGraph 기반 workflow용으로 재작성. (2) 하위 plan 파일 라인업 변경: `plan_data.md` → `plan_signal_ingest.md`, `plan_model.md` → `plan_langgraph.md` + `plan_prompts.md`, `plan_eval.md` → `plan_clinical_eval.md`. (3) sub-agent 호출 예시를 새 라인업으로 갱신. (4) 데이터 컨트랙트 항목에 "tool schema", "LangGraph state shape", "LLM context budget" 추가. |
| **data-engineer** | **signal-ingest-engineer** | (1) PyTorch Dataset / Collate 중심에서 **VitalDB streaming + 30초 window feature extraction** 중심으로 재정의. (2) "lazy-loading sliding window" 컨셉은 유지 (VitalDB client와 잘 맞음). (3) tensor shape 강제 → "LLM-readable summary" 및 tool input JSON schema 강제. (4) Shallow loop용 가벼운 numerical feature와 Deep loop용 raw window 둘을 구분 출력하도록 명시. |
| **estimator** | **clinical-evaluator** | (1) 코드 quality 평가 → **임상 시나리오 / false-alarm / latency** 평가로 축 이동. (2) 마취과 evaluation rubric (정확도 · 지연시간 · hallucination · 환자 안전) 도입. (3) evidence 형식: 파일 : line + 시나리오 transcript + LLM 응답 예시. (4) 기존 critical / warning / suggestion 3-tier 분류 골격은 유지. |
| **biomedical-ai-paper-writer** | **biomedical-ai-paper-writer** (유지) | (1) 기본 target venue를 **npj Digital Medicine**으로. JAMA / NEJM AI 같은 임상 venue 톤 가이드 추가. (2) Clinical reporting standard (CONSORT-AI, SPIRIT-AI, TRIPOD-AI) 인지. (3) read-only 정책 유지 (write tool 부여 X — 사용자에게 텍스트 반환). |

### (C) 폐기 — 1개

| Agent | 폐기 근거 |
|-------|-----------|
| **model-architect** | VitalAgent는 PyTorch foundation model을 새로 학습하지 않는다. Transformer / MoE / RoPE / PatchEmbedding 지식은 VitalAgent의 LangGraph + tool-using workflow와 직접 연결되는 책임 영역이 없다. 향후 VitalAgent가 BFM checkpoint를 *호출*해서 embedding을 쓴다면 그 wrapper 역할은 `signal-ingest-engineer` 또는 신설 agent가 흡수하면 충분. **이름과 페르소나를 그대로 가져오면 잘못된 코드 (PyTorch 학습 loop)를 작성하려 할 위험이 있어 폐기를 권한다.** |

### (D) 새로 추가 권장 — 3개

| 새 Agent | 책임 | 신설 근거 |
|----------|------|-----------|
| **langgraph-engineer** | LangGraph StateGraph / Node / Edge 구현, tool registry, 이중 모드 분기 (Shallow 30초 ↔ Deep on-demand) 구현, state schema 설계 | VitalAgent의 *심장*. BFM에는 동치 agent 없음. `plan_langgraph.md` 기반 workflow로 운영. |
| **llm-prompt-engineer** | System prompt 작성, tool description 정제, role / instruction 분리, hallucination 억제 가드 작성, 한 / 영 대응 | LLM agent의 품질은 prompt에서 결정된다. PyTorch project에는 없던 책임 — VitalAgent에서 별도 agent로 두면 paper-writer / clinical-evaluator와의 분업이 깨끗해진다. |
| **vitaldb-domain-expert** | VitalDB 데이터 schema, 마취 · 중환자 모니터링 임상 맥락 (vital sign 정상 범위, alarm threshold, 마취 단계, 약물 효과) 해석 | 임상 domain 지식을 코드 / prompt에 박는 단일 책임처가 필요. `signal-ingest-engineer`는 기술적 처리, `clinical-evaluator`는 평가, **`vitaldb-domain-expert`는 지식 base 역할**. |

> **선택지**: 위 3개를 모두 둘 수도 있고, 초기엔 `langgraph-engineer + clinical-evaluator + signal-ingest-engineer` 3개로 시작하고 prompt-engineer / domain-expert는 필요해질 때 분리하는 점진적 도입도 가능 — 사용자 의향 확인 필요.

## 3. 최종 권장 라인업 (`.claude/agents/`)

```
.claude/agents/
├── project-planner.md             ← 수정 재사용 (master_plan + plan_*.md 재정의)
├── signal-ingest-engineer.md      ← data-engineer 재구성 (VitalDB stream + feature)
├── langgraph-engineer.md          ← 신설 (workflow / node / tool 통합)
├── llm-prompt-engineer.md         ← 신설 (prompt / tool description 전담)
├── clinical-evaluator.md          ← estimator 재구성 (임상 시나리오 평가)
├── vitaldb-domain-expert.md       ← 신설 (마취 · 중환자 domain 지식)
└── biomedical-ai-paper-writer.md  ← 미세 수정 재사용 (npj DM 타겟)
```

총 **7개 agent**. BFM의 5개 중 1개 폐기 (model-architect), 4개 수정 재사용, 3개 신설.

## 4. 공통 패턴 보존 권장 (Common Patterns to Preserve)

BFM에서 효과적이었던 패턴은 유지한다.

- **Plan-file-driven workflow**: `.plans/master_plan.md` + `.plans/.agent_plan/plan_*.md` 구조 그대로 — agent 호출마다 fresh read → 작업 → 완료 마킹.
- **Persistent agent memory**: `.claude/agent-memory/<agent>/` per-agent 디렉토리 + `MEMORY.md` 인덱스 패턴 그대로 (path는 프로젝트 path로 통일 — BFM에서는 사용자 path와 프로젝트 path가 섞여 있었음).
- **한글 친화 보고 / trigger**: 동일 유지.
- **Model: `opus`**: 동일 유지 (Opus 4.7이 VitalAgent 기준 시점의 최신).

## 5. 이식 시 정리할 작은 부채 (Small Debts to Clean Up)

- BFM의 일부 agent가 memory path를 `C:\Users\SNUH_VitalLab_LEGION\.claude\agent-memory\` (user-scope)로 적어두고 frontmatter는 `memory: project`로 선언 → 불일치. VitalAgent에선 모두 `C:\Projects\VitalAgent\.claude\agent-memory\<agent>\` (project-scope)로 통일한다.
- `agent-memory/plan-eval/` 같은 흔적 디렉토리는 옮기지 않는다.
