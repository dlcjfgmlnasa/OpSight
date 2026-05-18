# Stage 5 — 논문 작성 및 제출 (Paper Writing & Submission, Month 9–10)

**상태 (Status)**: PLACEHOLDER
**개요 (Overview)**: **npj Digital Medicine**에 manuscript를 작성하고 제출한다.

## 잠정 범위 (Tentative scope — 3–5 bullets)

- Introduction / Related Work / Methods / Results / Discussion / Conclusion 작성 (한글 draft는 선택, 최종은 영문).
- 임상 보고 표준 (CONSORT-AI, SPIRIT-AI, TRIPOD-AI, DECIDE-AI)을 구조 checklist로 참조.
- 주요 design 결정에 대한 ADR을 `docs/decisions/ADR-*.md`로 작성 — `docs/project_brief.md §14` TODO 해결. (ADR-011 Mock FM Strategy는 이미 존재. ADR-012 / -013 / -014는 `[DECISION PENDING]` 상태로 회의 후 확정 예정.)
- Figure, table, supplementary material, code-release 명세 준비.
- 제출 전 `biomedical-ai-paper-writer` + 임상 협력자 (이형철 교수님 그룹) 내부 review pass.

## 선행 stage 의존성 (Dependencies on prior stages)

- **Stage 4 결과 freeze 완료**.
- **Stage 1–3 log**가 Methods 재현성 (reproducibility)을 위해 가용해야 함.

## 상세 작성 시점 (Will be detailed when)

Stage 4가 ≥ 80% 완료된 시점. 이후 `project-planner`가 본 디렉토리에 `plan_5.{1..N}_*.md`를 작성한다. Stage 5 내에서는 `biomedical-ai-paper-writer`가 lead이다.

## Write 권한 범위 안내 (Write-permission scope reminder)

`biomedical-ai-paper-writer`는 다음 경로에만 write 권한을 가진다: `docs/paper/**`, `docs/design/10_paper_outline.md`, `results/figures/captions/**`. 그 외 경로는 다른 agent가 처리한다.
