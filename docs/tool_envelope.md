# Tool Envelope — Authoritative Spec (plan_1.7 산출물)

> 모든 16 tool 의 공통 입출력 schema.
> 본 문서는 `vitalagent/tools/envelope.py` 코드와 1:1 일치하며, **본 문서가 정식 spec**이다.
> 의존성: `docs/project_brief.md §7 / §13.2`, `vitalagent/state.py` (LangGraph state schema).

---

## 1. Envelope 3 모델

```
ToolRequest  ─────► call_tool ─────► ToolResponse
                                          │
                                          ├── result (success)
                                          └── error  (failure: ToolError)
```

### 1.1 `ToolRequest`

| Field | Type | Required | 의미 |
|-------|------|----------|------|
| `case_id` | `str` | ✅ | VitalDB case 식별자 |
| `sim_time_s` | `float` | ✅ | 시뮬레이션 시간 (초). Leakage guard 기준점. |
| `tool_name` | `str` | ✅ | 호출할 tool 이름 (`TOOLS` registry key) |
| `args` | `dict[str, Any]` | optional (default `{}`) | tool-specific 인자 |

Constraint: `model_config = ConfigDict(extra="forbid", frozen=True)`. Unknown field 거부 + immutable.

### 1.2 `ToolResponse`

| Field | Type | Required | 의미 |
|-------|------|----------|------|
| `case_id` | `str` | ✅ | request 의 case_id echo |
| `sim_time_s` | `float` | ✅ | request 의 sim_time_s echo |
| `tool_name` | `str` | ✅ | request 의 tool_name echo |
| `args` | `dict[str, Any]` | optional | request args echo (debugging) |
| `result` | `dict[str, Any] \| None` | conditional | 성공 시 채워짐 |
| `error` | `ToolError \| None` | conditional | 실패 시 채워짐 |
| `quality_meta` | `dict[str, Any]` | ✅ | quality-aware claim 출처 — 모든 tool 의무 채움 |
| `latency_ms` | `float` | optional (default 0) | wall-clock 측정 |

Invariant: `result` 와 `error` 중 정확히 하나만 채워진다. `.ok` property 가 `error is None` 을 반환.

### 1.3 `ToolError`

| Field | Type | 의미 |
|-------|------|------|
| `type` | `str` | error class (다음 표) |
| `message` | `str` | 사람이 읽을 수 있는 메시지 |
| `extra` | `dict[str, Any]` | 추가 진단 정보 |

#### 표준 `error.type` 값

| Type | 의미 | 누가 raise |
|------|------|------------|
| `"leakage_violation"` | `query_window_end_s > clock.now_s` | 모든 tool 의 `_leakage_guard` |
| `"invalid_args"` | 인자 검증 실패 (예: 잘못된 modality 이름) | tool body |
| `"missing_dependency"` | FM / signal 미주입 | dispatch layer |
| `"tool_internal_error"` | tool 내부 예외 (예: FM forward fail) | tool body try/except |
| `"unimplemented"` | tool 13–14 등 stub 단계 명시적 미구현 호출 | tool body |

## 2. Leakage guard (brief §13.2 강제)

```python
def _leakage_guard(request, clock, query_window_end_s=None):
    end_s = query_window_end_s if query_window_end_s is not None else request.sim_time_s
    if end_s > clock.now_s:
        return ToolResponse(
            ...,
            error=ToolError(
                type="leakage_violation",
                message=f"query_window_end_s={end_s} exceeds clock.now_s={clock.now_s}",
                extra={"query_window_end_s": end_s, "clock_now_s": clock.now_s},
            ),
        )
    return None
```

모든 tool 의 첫 줄에서 호출. fail 시 `ToolResponse(error=ToolError(type="leakage_violation"))` 반환 — exception 으로 propagate 하지 않음 (trace 에 명시적 기록).

## 3. `quality_meta` 컨벤션

모든 tool 이 다음 중 적용 가능한 key 를 채운다.

| Key | 값 | 의미 |
|-----|-----|------|
| `fm_meta` | dict | FM tool 의 `Result.meta` 전체. mock_tier 포함. |
| `mock_tier` | `"stub" \| "rule_based" \| "light_ml" \| "real"` | FM tier (FM tool 만) |
| `modality` | `str` | 단일 modality tool (assess_signal_quality 등) |
| `modality_pair` | `[str, str]` | cross-modal tool |
| `emr_stub` | `True` | EMR stub 단계 (plan_1.3 전) |
| `clinical_review_required` | `bool` | LLM 이 `[Limitations]` 에 명시해야 함을 표시 |
| `unimplemented_in_prototype` | `True` | tool 13–16 stub 단계 |
| `deterministic` | `True` | quality_aware_synthesis (auxiliary 16) 처럼 LLM 호출 없는 deterministic fusion |
| `cohort_index_version` | `str` | similar-case tool (13) — 사용한 cohort index 버전 |

Brief LLM 은 `quality_meta` 를 `[Limitations]` / `[Assessment confidence]` section 작성 시 참조.

## 4. JSON Schema (machine-readable)

### 4.1 ToolRequest

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ToolRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["case_id", "sim_time_s", "tool_name"],
  "properties": {
    "case_id":    {"type": "string"},
    "sim_time_s": {"type": "number", "minimum": 0},
    "tool_name":  {"type": "string"},
    "args":       {"type": "object", "additionalProperties": true}
  }
}
```

### 4.2 ToolResponse

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ToolResponse",
  "type": "object",
  "additionalProperties": false,
  "required": ["case_id", "sim_time_s", "tool_name", "quality_meta", "latency_ms"],
  "properties": {
    "case_id":    {"type": "string"},
    "sim_time_s": {"type": "number", "minimum": 0},
    "tool_name":  {"type": "string"},
    "args":       {"type": "object", "additionalProperties": true},
    "result":     {"type": ["object", "null"]},
    "error":      {"$ref": "#/definitions/ToolError"},
    "quality_meta": {"type": "object", "additionalProperties": true},
    "latency_ms": {"type": "number", "minimum": 0}
  },
  "definitions": {
    "ToolError": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "required": ["type", "message"],
      "properties": {
        "type":    {"type": "string"},
        "message": {"type": "string"},
        "extra":   {"type": "object", "additionalProperties": true}
      }
    }
  }
}
```

### 4.3 Constraint — `result` xor `error`

JSON Schema 로 표현하면:
```json
"oneOf": [
  {"required": ["result"], "properties": {"error": {"type": "null"}}},
  {"required": ["error"],  "properties": {"result": {"type": "null"}}}
]
```

`ToolResponse.ok` property 가 invariant 보장.

## 5. Trace JSONL 와의 관계

매 tool 호출은 trace 에 2 개 event:
- `"tool_call"` payload: `{"tool": name, "args": dict}` (request 의 sanitized 버전)
- `"tool_result"` payload: `{"tool": name, "ok": bool, "latency_ms": float, "result": dict | null, "error": dict | null}`

자세한 trace schema 는 `docs/trace_format.md`.

## 6. Pydantic ↔ JSON 직렬화

```python
req = ToolRequest(case_id="c1", sim_time_s=30.0, tool_name="predict_hypotension", args={...})
req.model_dump_json()                 # JSON string
ToolRequest.model_validate(json_dict) # 역방향

resp = ToolResponse(...)
resp.model_dump()                      # dict (trace 에 기록할 때 사용)
```

## 7. 코드 ↔ 본 문서 정합성 검증

`tests/integration/test_smoke_single_case.py` 는 본 envelope 의 invariant 를 검증:
- 모든 tool_result event 가 `ok=True`
- `quality_meta` 가 비어있지 않음 (모든 tool 이 채움)
- `latency_ms` 가 양수

자세한 건 [[../obsidian/30_코드_워크스루/05_tools_layer]].

## 8. Versioning

| Version | Date | Change |
|---------|------|--------|
| v1 (minimal) | plan_1.8 초기 | inline `envelope.py` 에 작성 |
| **v1 정식** | 2026-05-17 (plan_1.7) | 본 문서 작성 — 코드와 1:1 일치 |
