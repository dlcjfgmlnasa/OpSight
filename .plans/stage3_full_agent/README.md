# Stage 3 — Full Agent 통합 (Full Agent Integration, Month 5–6)

**상태 (Status)**: PLACEHOLDER
**개요 (Overview)**: Shallow + Deep 모드를 end-to-end로 완성하고 내부 validation (자동 metric + LLM-as-judge)을 수행한다.

## 잠정 범위 (Tentative scope — 3–5 bullets)

- Shallow + Deep 모드를 7-trigger rule engine 아래 단일 deterministic dispatcher로 통합한다.
- 내부 validation harness 구축: AUPRC / AUROC / sens@spec, tool 선택 P / R, latency 분포, faithfulness (atomic-claim grounding).
- Held-out val split에 대해 LLM-as-judge (Claude가 Llama 출력을 판정) 연결.
- 목표 2× L40S 환경에서 shallow < 15초, deep < 60초가 되도록 profiling + tuning. `docs/project_brief.md §6` latency TODO 채움.
- Judge feedback을 활용하여 system prompt (`prompts/v2_*.md`) 반복 개선.

## 선행 stage 의존성 (Dependencies on prior stages)

- **Stage 2 완료** — 7개 FM tool이 real output을 반환한다.
- **Stage 1.6 / 1.7** — system prompt와 tool spec이 iteration의 baseline이다.

## 상세 작성 시점 (Will be detailed when)

Stage 2가 ≥ 80% 완료된 시점. 이후 `project-planner`가 본 디렉토리에 `plan_3.{1..N}_*.md`를 작성한다.
