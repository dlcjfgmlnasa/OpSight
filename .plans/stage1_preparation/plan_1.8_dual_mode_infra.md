# plan_1.8 — Dual-Mode LangGraph Skeleton

**Owner**: `langgraph-engineer`
**Assist**: `signal-ingest-engineer` (sim clock, streaming tick), `llm-prompt-engineer` (prompt injection 지점)
**Status**: 완료 (2026-05-16) — 9/9 task. 단일 case smoke + 100-case Tier 2 e2e 모두 PASSED.
**Goal**: LangGraph dual-mode skeleton (Shallow 30초 loop + Deep on-demand)을 stub FM tool과 함께 end-to-end로 구동한다. Stage 2에서 real FM 호출을 재설계 없이 drop-in할 수 있게 한다.

> Project brief: `docs/project_brief.md §6`.

---

## Tasks

- [x] **[Priority: High]** LangGraph `AgentState` schema 정의. (2026-05-16)
  - 입력: `docs/project_brief.md §6`, `plan_1.7` tool envelope
  - 출력: `opsight/state.py` — Pydantic `AgentState`. field: `case_id`, `sim_time_s`, `mode` (`shallow` / `deep`), `last_tool_results` (list[ToolResponse]), `last_deep_trigger_time_s`, `risk_history`, `quality_history`, `brief_history`, `trace_id`
  - 의존성: `plan_1.7` envelope 초안
  - 참고: typed (Pydantic). state는 직렬화 가능해야 한다 (trace 저장용).

- [x] **[Priority: High]** **시뮬레이션된 실시간 (simulated real-time) clock** 구현. (2026-05-16)
  - 입력: VitalDB case timeline
  - 출력: `opsight/sim_clock.py` — `SimClock` class. 1초 또는 30초 tick으로 진행 + wall-clock 측정 hook 보유.
  - 의존성: 없음
  - 참고: `t` 시점 이후 데이터는 절대 노출되지 않는다 (brief §13.2). 위반 시 leakage guard가 fail한다.

- [x] **[Priority: High]** Shallow-loop node 구현 (30초 tick마다). (2026-05-16, placeholder LLM 사용 — plan_1.6 도착 시 vLLM 대체)
  - 입력: `AgentState`, `SimClock`, tool registry
  - 출력: `opsight/nodes/shallow_loop.py` — quick tool 5–6개 병렬 실행, Light LLM 호출, narration 출력
  - 의존성: `plan_1.7` (stub FM tool callable), `plan_1.6` Light prompt v1
  - 참고: latency 목표 < 15초로 측정.
  - **Follow-up (ADR-016 Signal Access)**: Shallow tool set 에 **17 `get_current_vitals` + 20 `compare_to_baseline`** 추가 — light/빠름, 브리프 §[Signal status] 의 정량 source. `plan_1.3.5` 도착 시 `SHALLOW_TOOL_NAMES` registry constant 확장.

- [x] **[Priority: High]** Deep-mode node 구현 (event-triggered). (2026-05-16, placeholder LLM 사용 — plan_1.6 도착 시 vLLM 대체)
  - 입력: `AgentState`, full tool registry, Heavy LLM
  - 출력: `opsight/nodes/deep_brief.py` — tool suite 전체 실행 (현재 16; `plan_1.3.5` 합류 시 21), Heavy LLM 호출, 9-section 한글 브리프 생성
  - 의존성: `plan_1.6` Heavy prompt v1, `plan_1.7` tool registry
  - 참고: latency 목표 < 60초로 측정. Heavy LLM 미배포 상태이면 mock으로 대체.
  - **Follow-up (ADR-016 Signal Access)**: Deep tool set 을 21-tool 로 확장. `_deep_args` 에 17–21 호출 인자 추가. 브리프 §[Surgery context]/§[Signal status]/§[Evidence] 의 정량 claim 이 17–21 출력으로 grounded 됨. `plan_1.3.5` 도착 시 `_deep_args` patch.

- [x] **[Priority: High]** **rule-based** deep-mode trigger engine 구현 (7개 trigger + 60초 cooldown). (2026-05-16, 19 unit test 통과)
  - 입력: brief §6.3 trigger
  - 출력: `opsight/triggers.py` — pure function `should_escalate(state) → (bool, reason)`. **LLM 사용 절대 금지** (brief §13.3).
  - 의존성: shallow loop output schema
  - 참고: 각 trigger를 unit test로 (negative + positive case).

- [x] **[Priority: High]** StateGraph wiring. (2026-05-16, `build_graph()` 작동)
  - 입력: 위 모든 node + trigger
  - 출력: `opsight/graph.py` — `build_graph() → CompiledGraph`. Edge: `shallow_loop → (trigger?) → deep_brief → shallow_loop`
  - 의존성: 위
  - 참고: trace logging은 LangSmith 또는 local JSONL 결정 필요. 일단 local JSONL.

- [x] **[Priority: Medium]** 단일 코호트 case에 대한 end-to-end smoke test. (2026-05-16, synthetic case, 3 integration test 통과)
  - 입력: 코호트 manifest sample (1 case), 빌드된 graph
  - 출력: `tests/integration/test_smoke_single_case.py` — assertion: shallow가 30초마다 실행, 최소 1개 trigger에서 deep 발화, leakage error 없음
  - 의존성: 위 모든 task, `plan_1.1.5` Mock FM Tier 1
  - 참고: Tier 1 Stub FM으로 실행. 인프라 검증용.

- [x] **[Priority: High]** **Mock FM Tier 2 (rule-based)**에 대한 100-case end-to-end test. (2026-05-16 — 100/100 case PASSED, p95 per-tick=4.8ms, 300 deep fires, leakage 0)
  - 입력: 코호트 manifest sample (100 case), 빌드된 graph, `plan_1.6.5`의 rule-based mock
  - 출력: `tests/integration/test_e2e_100cases_tier2.py` — assertion: shallow latency budget 충족 (p95 < 15초), deep trigger가 plausible하게 발화, leakage 없음, 9-section 브리프 template이 end-to-end로 렌더링됨
  - 의존성: 위 + `plan_1.6.5`
  - 참고: 본 test가 Stage 1 done의 "Mock FM Tier 1 + Tier 2가 end-to-end agent loop를 구동" criterion (`master_plan.md §5`) 충족의 근거다.

- [x] **[Priority: Medium]** Trace 영속화 (persistence) + viewer note. (2026-05-16, `opsight/trace.py` + `docs/trace_format.md`)
  - 입력: trace JSONL
  - 출력: `docs/trace_format.md` + 최소 trace dump tool
  - 의존성: graph 동작
  - 참고: Stage 4 임상의 평가에서 브리프 + trace pair가 필요하다.

---

## Definition of done

- `opsight/graph.py::build_graph()`가 동작하는 graph를 반환
- 단일 코호트 case에 대해 smoke test 통과 (Mock FM Tier 1)
- 100-case integration test가 **Mock FM Tier 2**에 대해 shallow latency budget 안에서 통과
- Shallow loop tick = 30초 측정. 최소 1개 rule이 deep brief를 trigger
- Trace JSONL 캡처됨
- FM은 `BiosignalFMInterface`를 통해서만 소비된다 (`opsight/nodes/`와 `opsight/graph.py`에 concrete-class import 없음 — static check로 검증)

## Data contracts established here

- **`AgentState` schema** (Stage 2+ 모든 node에서 소비됨)
- **Trigger interface** (`should_escalate`) — stage 전반에 걸쳐 안정 signature
- **Trace JSONL schema** (Stage 4 임상의 평가 workflow에서 소비됨)
