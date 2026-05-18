# Stage 2 — FM 통합 (FM Integration, Month 3–4)

**상태 (Status)**: PLACEHOLDER
**개요 (Overview)**: 가중치 동결된 (frozen) Biosignal Foundation Model을 agent의 7개 FM-based tool backend로 연결한다. Stage 1의 stub을 대체한다.

## 잠정 범위 (Tentative scope — 3–5 bullets)

- Frozen FM checkpoint (K-MIMIC ICU pretrained, 6 modality)를 thin Python wrapper로 serve한다.
- 7개 FM tool 연결 (`predict_hypotension`, `predict_cardiac_arrest`, `assess_signal_quality`, `cross_modal_consistency`, `temporal_trend_analysis`, `forecast_signal`, `anomaly_score`).
- FM tool 출력이 `plan_1.7_tool_spec.md`의 JSON schema와 일치하는지 검증 (schema drift 없음).
- Real FM으로 50–100 case sample에 대해 shallow loop end-to-end 실행. 2× L40S에서 latency 기록.
- `docs/project_brief.md §3`의 TODO 해결: FM 학습 완료 시점에 누락된 4개 downstream task를 enumerate.

## 선행 stage 의존성 (Dependencies on prior stages)

- **Stage 1.7** — 16-tool spec이 계약이다. FM tool은 반드시 일치해야 한다.
- **Stage 1.8** — LangGraph skeleton. FM tool은 graph 재설계 없이 drop in된다.
- **외부 (External)** — FM 학습 완료 (≈ Month 2 종료. `master_plan.md §8 Risk Register`에서 추적).

## 상세 작성 시점 (Will be detailed when)

`master_plan.md §5 Stage 1 Acceptance Criteria`가 ≥ 80% 완료된 시점 (`master_plan.md §6 Change Rule 3` 기준). 이후 `project-planner` agent가 본 디렉토리에 `plan_2.{1..N}_*.md` 파일을 materialize한다.
