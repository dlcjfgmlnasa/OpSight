# 05. Tools Layer — envelope + fm_tools + emr_tools_stub + registry + signal_access_tools

> 21 tool 의 공통 envelope + 7 FM wrapper + 5 EMR stub + 2 Knowledge stub + 2 Auxiliary + 5 Signal Access (ADR-016) + central registry.

## 파일 구조

```
opsight/tools/
├── __init__.py
├── envelope.py             ← ToolRequest / ToolResponse / ToolError
├── fm_tools.py             ← 7 FM wrapper
├── emr_tools_stub.py       ← 5 EMR stub
├── knowledge_aux_tools.py  ← Knowledge 2 + Auxiliary 2
├── signal_access_tools.py  ← Signal Access 5 (ADR-016)
└── registry.py             ← TOOLS dict + call_tool dispatch
```

## `envelope.py` — 공통 schema

```python
class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    sim_time_s: float
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: str               # "leakage_violation", "invalid_args", ...
    message: str
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    sim_time_s: float
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: ToolError | None = None
    quality_meta: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None
```

### 모든 envelope frozen — 이유

Trace JSONL + state buffer 에 들어가는 값. 변경되면 안전 X. [[10_기초/Pydantic_과_typed_state]].

### `quality_meta` — 모든 tool 의무 field

quality-aware claim 의 근거:
- FM tool: `{"fm_meta": result.meta, "modality": ...}`
- EMR stub: `{"emr_stub": True, "clinical_review_required": True}`

Brief LLM 이 quality_meta 보고 "이 정보는 stub 이라 신뢰도 낮음" 한계 명시.

## `fm_tools.py` — 7 FM wrapper

각 wrapper 의 3-step:
1. Leakage guard
2. `BiosignalFMInterface` method 호출
3. Result → dict 변환 후 `ToolResponse`

```python
def tool_predict_hypotension(
    request: ToolRequest,
    fm: BiosignalFMInterface,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    err = _leakage_guard(request, clock)
    if err is not None:
        return err

    t0 = time.perf_counter()
    horizon_min = int(request.args.get("horizon_min", 5))
    available_modalities = list(request.args.get("available_modalities", list(signal)))

    r = fm.predict_hypotension(signal, horizon_min, available_modalities)
    latency_ms = (time.perf_counter() - t0) * 1000

    return _build_response(request, asdict(r), {"fm_meta": r.meta}, latency_ms)
```

### Concrete FM class import 금지

```python
if TYPE_CHECKING:
    from opsight.fm.interface import BiosignalFMInterface  # type hint 만
```

FM 은 호출자가 주입. Tool layer 는 concrete class 모름 → **ADR-011 swap mechanism 보존**.

[[10_기초/Python_Protocol_과_runtime_checkable]], [[01_fm_layer]] 참조.

### 7 FM wrapper

| Tool | FM method | 핵심 logic |
|------|-----------|------------|
| `tool_predict_hypotension` | `fm.predict_hypotension` | horizon_min 파싱 |
| `tool_predict_cardiac_arrest` | `fm.predict_cardiac_arrest` | 동일 |
| `tool_assess_signal_quality` | `fm.assess_signal_quality` | modality 파싱 |
| `tool_cross_modal_consistency` | `fm.cross_modal_consistency` | modality_pair 검증 |
| `tool_temporal_trend_analysis` | `fm.temporal_trend` | window_min 파싱 |
| `tool_forecast_signal` | `fm.forecast_signal` | horizon_min 파싱 |
| `tool_anomaly_score` | `fm.anomaly_score` | modality 파싱 |

## `emr_tools_stub.py` — 5 EMR placeholder

⚠️ STUB: hard-coded fake. VitalDB `intraop_*` 의 per-event timestamp 부재로 prototype 단계 stub 유지 가능성.

### Tool 8 — `query_anesthesia_drugs` (fake)

```python
def tool_query_anesthesia_drugs(request, clock):
    start_s, end_s = _resolve_window(request.args)
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err

    fake = {
        "drugs": [
            {"name": "remifentanil",   "amount": 0.10, "unit": "mcg/kg/min",
             "timestamp_s": (start_s + end_s) / 2, "channel": "Orchestra/RFTN20_CE"},
            {"name": "propofol",       "amount": 3.0,  "unit": "mcg/mL",
             "timestamp_s": (start_s + end_s) / 2, "channel": "Orchestra/PPF20_CE"},
            {"name": "sevoflurane",    "amount": 1.8,  "unit": "%",
             "timestamp_s": (start_s + end_s) / 2, "channel": "Primus/EXP_SEVO"},
        ]
    }
    return _ok(request, fake, ...)
```

모든 case 가 같은 fake 3 drug.

### Tool 11 — `query_surgery_progress` (heuristic stub)

```python
def tool_query_surgery_progress(request, clock):
    current_time = float(request.args.get("current_time", clock.now_s))
    total = 7200.0  # 2h 가정
    elapsed_min = current_time / 60.0
    if elapsed_min < 15:
        phase = "induction"
    elif elapsed_min > (total / 60.0) - 10:
        phase = "emergence"
    else:
        phase = "maintenance"
    fake = {"phase": phase, "elapsed_min": elapsed_min, ...}
    return _ok(request, fake, ...)
```

시간 비율 기반 heuristic.

### `clinical_review_required` marker

```python
def _ok(request, result, latency_ms, *, clinician_review=True):
    return ToolResponse(
        ...
        quality_meta={
            "emr_stub": True,
            "clinical_review_required": clinician_review,
        },
    )
```

모든 EMR stub 응답에 `clinical_review_required: True` 박힘.

## `registry.py` — central catalog + dispatch

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    category: str                              # "fm" | "emr" | "knowledge" | "auxiliary" | "signal_access"
    description: str
    fn: Callable[..., ToolResponse] = field(repr=False)
    needs_fm: bool = False
    needs_signal: bool = False


TOOLS: Final[dict[str, ToolSpec]] = {
    "predict_hypotension": ToolSpec(
        name="predict_hypotension",
        category="fm",
        description="Predict hypotension risk within horizon_min.",
        fn=tool_predict_hypotension,
        needs_fm=True,
        needs_signal=True,
    ),
    # ... 20개 더
}


SHALLOW_TOOL_NAMES: Final = (
    "predict_hypotension",
    "predict_cardiac_arrest",
    "assess_signal_quality",
    "cross_modal_consistency",
    "anomaly_score",
)
```

### `call_tool` — dispatch

```python
def call_tool(
    name: str,
    request: ToolRequest,
    *, fm: BiosignalFMInterface | None = None,
    clock: SimClock,
    signal: dict[str, torch.Tensor] | None = None,
) -> ToolResponse:
    spec = TOOLS.get(name)
    if spec is None:
        raise KeyError(f"unknown tool: {name!r}. known: {sorted(TOOLS)}")
    if spec.needs_fm:
        if fm is None:
            raise ValueError(f"tool {name!r} requires fm but none provided")
        return spec.fn(request, fm, clock, signal or {})
    return spec.fn(request, clock)
```

FM tool: `(request, fm, clock, signal)`, EMR tool: `(request, clock)`. registry 가 분기.

## 사용 흐름 — shallow loop

```python
for tool_name in SHALLOW_TOOL_NAMES:
    args = _shallow_tool_args(tool_name, modalities)
    req = ToolRequest(
        case_id=state.case_id,
        sim_time_s=state.sim_time_s,
        tool_name=tool_name,
        args=args,
    )
    resp = call_tool(tool_name, req, fm=fm, clock=clock, signal=signal)
    tool_results.append(resp)
```

자세한 node 코드: [[06_nodes_graph]].

## Tests

Tool 별 unit test 는 없음 (thin wrapper). 통합 test 로 검증.

| Test | 검증 |
|------|------|
| `tests/integration/test_smoke_single_case.py` | 5 shallow + 12 deep tool |
| `tests/integration/test_e2e_100cases_tier2.py` | 100 case × 6 tick × ~8 tool = 4,800+ call, leakage 0 |

## 다음 노트

- [[06_nodes_graph]] — node 에서 어떻게 호출되는가
- [[01_fm_layer]] — FM interface
- [[20_아키텍처/21_Tool_Suite]] — 21 tool 카테고리 + Signal Access
- [[20_아키텍처/데이터_누수_방지]] — leakage guard
