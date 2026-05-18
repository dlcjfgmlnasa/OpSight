# plan_1.3 — EMR Tools (tools 8–12)

**Owner**: `langgraph-engineer`
**Assist**: `vitaldb-domain-expert` (schema), `signal-ingest-engineer` (time-window slicing)
**Status**: not started
**Goal**: 21-tool suite 중 EMR 기반 5개 tool (`docs/project_brief.md §7.2`)을 엄격한 **time-leakage guard** 와 함께 구현한다. 본 plan 은 EMR 5 개만 다룬다 — *현재 신호 상태 access tool* (17–21) 은 별도 `plan_1.3.5` 가 담당하며 본 plan 과 병렬 실행 가능 (ADR-016 Accepted 2026-05-17).

---

## Tasks

- [ ] **[Priority: High]** 모든 EMR tool이 공유하는 **time-leakage guard** primitive를 정의한다.
  - 입력: LangGraph state로부터의 시뮬레이션 clock 값 `t`
  - 출력: `opsight/tools/_leakage_guard.py` — `query_window_end > t`이면 명시적으로 실패하는 `assert_le(t, query_window_end)` 함수
  - 의존성: 없음
  - 참고: §13.2 No-data-leakage rule의 실효성 확보. 모든 EMR tool은 본 guard로 wrap.

- [ ] **[Priority: High]** Tool 8 — `query_anesthesia_drugs(case_id, time_window)` 구현.
  - 입력: `case_id: str`, `time_window: (start_s, end_s)` (surgery start 기준 상대 시간, sim-clock-safe)
  - 출력: `{"drugs": [{"name": str, "amount": float, "unit": str, "timestamp_s": float, "channel": str}, ...]}` — `channel`은 source VitalDB track (예: `Orchestra/RFTN20_CE`)
  - 의존성: leakage guard, `plan_1.1` API ref, `docs/project_brief.md §4.3` priority table
  - 참고: **First-class channels** (brief §4.3): `Orchestra/RFTN20_*` (remifentanil, 74.7% — 가장 가용), `Orchestra/PPF20_*` (propofol, 55.0%), `Primus/EXP_SEVO` / `INSP_SEVO` (sevoflurane, 57.7%). Tool은 가용한 모든 first-class channel을 반환하며 임의로 하나를 선택하지 않는다. Secondary channel (`Orchestra/ROC_*` 등)도 존재 시 포함한다.

- [ ] **[Priority: High]** Tool 9 — `query_vasoactive_drugs(case_id, time_window)` 구현.
  - 입력: tool 8과 동일
  - 출력: tool 8과 동일 형식. norepinephrine / phenylephrine / ephedrine 등 vasoactive 분류 — `[CLINICIAN-REVIEW]`로 분류 확인
  - 의존성: leakage guard, `plan_1.1`
  - 참고: drug list는 vitaldb-domain-expert가 `plan_1.1` catalog 작성 후 확정한다.

- [ ] **[Priority: High]** Tool 10 — `query_fluid_blood(case_id, time_window)` 구현.
  - 입력: tool 8과 동일
  - 출력: `{"fluids": [...], "blood_products": [...]}` (volume 포함)
  - 의존성: leakage guard
  - 참고: 데이터 소스 명시 (manual entry vs device feed).

- [ ] **[Priority: High]** Tool 11 — `query_surgery_progress(case_id, current_time)` 구현.
  - 입력: `case_id`, `current_time: float (s)`
  - 출력: `{"phase": enum, "elapsed_min": float, "estimated_remaining_min": float}`
  - 의존성: `plan_1.5` (phase 정의)
  - 참고: phase 추정은 시간 비율 기반 휴리스틱이며 임상 단정 아님. `[CLINICIAN-REVIEW]` 주석을 코드에 포함한다.

- [ ] **[Priority: High]** Tool 12 — `query_patient_baseline(case_id)` 구현.
  - 입력: `case_id`
  - 출력: `{"age": int, "sex": str, "asa": int, "comorbidities": [...], "baseline_bp": float?, "labs": {...}}`
  - 의존성: 없음
  - 참고: `baseline_bp` 부재 case 처리 (`None`) 명시.

- [ ] **[Priority: Medium]** Leakage guard + 5 tool을 3개 sample case로 검증하는 pytest suite.
  - 입력: cohort sample
  - 출력: `tests/tools/test_emr_tools.py`
  - 의존성: 위 모든 task
  - 참고: `t < query_window_end`로 호출 시 반드시 fail하는 negative test 포함.

---

## Definition of done

- 5개 EMR tool 구현 완료 + pytest 통과 (green)
- Leakage guard primitive 구현 + 5 tool 모두에서 사용
- LLM tool-calling용 tool description 초안이 `plan_1.7_tool_spec.md`에 작성됨

## Data contracts established here

- **EMR tool I/O JSON schema** (`plan_1.7_tool_spec.md`로 mirror)
- **Leakage guard signature** (Stage 2 FM tool에서도 동일하게 소비됨; `plan_1.3.5` Signal Access tool 도 동일 guard 재사용)

## Cross-references

- ADR-016 신규 (`docs/decisions/ADR-016-signal-access-tools.md`): EMR 5 와 Signal Access 5 의 경계 명시
- plan_1.3.5 (`./plan_1.3.5_signal_access_tools.md`): 현재 vital / 통계 / 변동성 / baseline 비교 / 통합 상태 5 tool (17–21) — 본 plan 과 병렬
