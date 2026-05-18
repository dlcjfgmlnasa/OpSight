# Trace JSONL Format (plan_1.8 task 9)

> Append-only JSONL captured by `vitalagent/trace.py::TraceWriter`. Consumed by Stage 4 임상의 평가 workflow as `(brief, trace)` pairs.
> Spec: `docs/project_brief.md §10` (real-time framing) + plan_1.8 task 9.

---

## 1. Per-line envelope (every event)

```json
{
  "trace_id": "smoke-run-1",
  "case_id": "synthetic-case-1",
  "sim_time_s": 30.0,
  "wall_time_ms": 1747460850123,
  "event": "tick",
  "payload": { /* event-specific dict */ }
}
```

| Field | Type | 의미 |
|-------|------|------|
| `trace_id` | str | Run-wide identifier (한 graph 실행 1개) |
| `case_id` | str | VitalDB case ID |
| `sim_time_s` | float | 이벤트 시점 simulated time (초) |
| `wall_time_ms` | int | Unix epoch ms — wall-clock |
| `event` | str | Event tag (아래 §2 참조) |
| `payload` | dict | Event-specific — JSON-serializable |

---

## 2. Event types

### `tick`
Payload: `{"tick_count": int}` — shallow-loop tick 카운터 (1부터).

### `tool_call`
Payload: `{"tool": str, "args": dict}` — 호출 시점 tool 이름 + 인자.

### `tool_result`
Payload:
```json
{
  "tool": "predict_hypotension",
  "ok": true,
  "latency_ms": 12.3,
  "result_keys": ["risk", "uncertainty", "horizon_min", "meta"]
}
```
실패 시 `ok=false`. `result_keys`는 result dict의 top-level keys만 (전체 result는 brief / state에서 별도 캡쳐).

### `narration`
Payload: `{"text": "[안정] 저혈압 risk 0.42, 심정지 risk 0.05."}` — shallow loop 1문장.

### `trigger`
Payload: `{"reason": "clinician_on_demand"}` — 발화한 trigger 사유 (project_brief §6.3 + clinician on-demand 등).

### `brief`
Payload:
```json
{
  "trigger_reason": "clinician_on_demand",
  "latency_ms": 245.7,
  "sections": {
    "Surgery context": "수술 유형: general. Phase: ...",
    "Signal status": "...",
    "Assessment confidence": "MEDIUM.",
    "Risk evaluation": "저혈압 risk: 0.42 (5분 horizon). ...",
    "Evidence": "...",
    "Intraoperative context": "...",
    "Similar trajectory": "...",
    "Recommendations": "임상적 고려사항은 ... [CLINICIAN-REVIEW: ...]",
    "Limitations": "본 브리프는 placeholder template LLM 출력이다. ..."
  }
}
```
9 section 모두 포함 (빈 문자열 가능). `[CLINICIAN-REVIEW]` marker 의무.

### `error`
Payload: `{"type": str, "message": str, "extra": dict}` — graph 또는 tool 단계의 error. 본 smoke test 단계에는 발생하지 않음 (leakage guard는 정상 reject로 처리).

---

## 3. 파일 명세

- Encoding: UTF-8 (`ensure_ascii=False` — 한글 가독성)
- 한 줄당 JSON 객체 1개. trailing newline.
- Append-only (기존 라인 수정 X).
- 파일 경로 컨벤션: `logs/traces/<trace_id>.jsonl` (권장; smoke test는 `tmp_path` 사용).

---

## 4. 사용 예 (Python)

```python
from vitalagent.trace import TraceWriter, read_trace

with TraceWriter("logs/traces/run-001.jsonl",
                 trace_id="run-001",
                 case_id="case-42") as tw:
    tw.event("tick", {"tick_count": 1}, sim_time_s=30.0)
    tw.event("narration", {"text": "[안정] ..."}, sim_time_s=30.0)

# Read back / 다시 읽기
events = read_trace("logs/traces/run-001.jsonl")
brief_events = [e for e in events if e["event"] == "brief"]
```

---

## 5. Stage 4 임상의 평가용 pair

```
(brief, trace) := (BriefRecord, JSONL run identified by trace_id)
```

임상의는 brief 본문 + trace의 `tool_result` / `narration` / `trigger` 시퀀스를 함께 보고 평가한다.

---

## 6. 미해결

- 후속 plan에서 정의될 추가 event: `state_snapshot` (주기적 state dump), `judge_score` (LLM-as-judge 결과) 등.
- JSON schema 정식 정의는 plan_3 (Full Agent stage)에서 작성.
