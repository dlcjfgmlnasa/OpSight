# Stage 4 — 임상의 평가 (Clinician Evaluation, Month 7–8)

**상태 (Status)**: PLACEHOLDER
**개요 (Overview)**: 이형철 교수님 그룹의 5–7명 anesthesiologist가 200–300개 Deep 모드 브리프 (brief)를 baseline과 blinded 비교 평가한다.

## 잠정 범위 (Tentative scope — 3–5 bullets)

- 5–7명 anesthesiologist 평가자 onboarding. `docs/project_brief.md §11.1`의 정확한 N에 대한 TODO 해결.
- 200–300 브리프 case를 surgery type / risk level / signal-quality regime에 대해 stratified sampling.
- OpSight 브리프 vs ≥ 1개 baseline 브리프의 blinded rating UI / spreadsheet workflow 구축.
- 5-point Likert × 5 차원. Cohen's κ inter-rater agreement 계산.
- 결과를 `results/clinician_eval/`에 freeze (Stage 5 paper에 포함).

## 선행 stage 의존성 (Dependencies on prior stages)

- **Stage 3 완료** — agent가 안정된 브리프를 end-to-end로 생성한다.
- **Stage 1.4** — comparator 브리프를 위한 baseline이 가용하다.
- **외부 (External)** — 임상의 스케줄링 가용성, IRB / consent posture (TBD).

## 상세 작성 시점 (Will be detailed when)

Stage 3가 ≥ 80% 완료된 시점. 이후 `project-planner`가 본 디렉토리에 `plan_4.{1..N}_*.md`를 작성한다.
