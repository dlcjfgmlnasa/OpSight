# 05. Tools Layer — 21개 tool 이 한 envelope 안에서 같은 형식으로 호출된다

> 21개의 tool 이 카테고리는 다 다르지만 **입출력 모양은 동일** 하다. 그 동일성을 강제하는 envelope, 7개의 FM wrapper, 5개의 EMR stub, 그리고 dispatch 역할을 하는 registry 가 이 layer 의 전부다.

## 파일 구조

```
vitalagent/tools/
├── __init__.py
├── envelope.py             ← ToolRequest / ToolResponse / ToolError
├── fm_tools.py             ← FM 7개를 부르는 thin wrapper
├── emr_tools_stub.py       ← EMR 5개의 fake data stub
├── knowledge_aux_tools.py  ← Knowledge 2 + Auxiliary 2
├── signal_access_tools.py  ← Signal Access 5개 (ADR-016)
└── registry.py             ← TOOLS dict + call_tool dispatch
```

## `envelope.py` — 21개 tool 이 공유하는 입출력 모양

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

### 왜 모든 envelope 이 frozen 인가

이 객체들은 trace JSONL 에 기록되고, LangGraph state 의 buffer 에도 들어간다. 도중에 누가 수정하면 trace 의 의미가 달라진다. 그래서 immutable 강제. 자세한 건 [[10_기초/Pydantic_과_typed_state]].

### `quality_meta` — 모든 tool 이 의무적으로 채우는 field

quality-aware claim 의 근거가 되는 dict 다. 카테고리마다 다른 내용이 들어간다.

- FM tool: `{"fm_meta": result.meta, "modality": ...}`
- EMR stub: `{"emr_stub": True, "clinical_review_required": True}`

Brief 를 생성하는 LLM 이 이걸 보고 "이 정보는 stub 이라 신뢰도 낮음" 같은 한계를 자동으로 적을 수 있다.

## `fm_tools.py` — 7개 FM wrapper

각 wrapper 는 세 단계만 한다.

1. **Leakage guard 검사** — 시뮬레이션 시간 위반인지 확인
2. **FM 의 해당 method 호출** — `BiosignalFMInterface` 의 한 method 를 부른다
3. **결과를 dict 로 변환** — `ToolResponse` 의 `result` 자리에 넣을 수 있도록

`tool_predict_hypotension` 이 패턴을 보여준다.

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

### Concrete FM class 를 *import 하지 않는다*

```python
if TYPE_CHECKING:
    from vitalagent.fm.interface import BiosignalFMInterface  # ← type hint 만
```

이 한 줄이 swap mechanism 의 안전장치다. tool layer 의 어떤 파일도 `StubBiosignalFM` 이나 `RuleBasedBiosignalFM` 같은 concrete class 를 import 하지 않는다. FM 인스턴스는 호출자가 주입한다. 그래서 tool layer 는 "지금 FM 자리에 누가 들어와 있는지" 를 모른다.

자세한 건 [[10_기초/Python_Protocol_과_runtime_checkable]] 과 [[01_fm_layer]].

### 7개 wrapper 가 다 같은 패턴

| Tool | FM method | wrapper 가 추가로 하는 일 |
|------|-----------|------------|
| `tool_predict_hypotension` | `fm.predict_hypotension` | leakage 검사 + horizon_min 파싱 |
| `tool_predict_cardiac_arrest` | `fm.predict_cardiac_arrest` | 동일 |
| `tool_assess_signal_quality` | `fm.assess_signal_quality` | modality 파싱 |
| `tool_cross_modal_consistency` | `fm.cross_modal_consistency` | modality_pair tuple 검증 |
| `tool_temporal_trend_analysis` | `fm.temporal_trend` | window_min 파싱 |
| `tool_forecast_signal` | `fm.forecast_signal` | horizon_min 파싱 |
| `tool_anomaly_score` | `fm.anomaly_score` | modality 파싱 |

자세한 FM Result 의 모양은 [[01_fm_layer]].

## `emr_tools_stub.py` — 아직 EMR 데이터를 안 붙였기 때문에 stub

⚠️ 모든 EMR tool 은 지금 **하드코딩된 fake data** 를 반환한다. VitalDB 의 `intraop_*` 컬럼 한계 (per-event timestamp 없음) 때문에 prototype 단계에서는 stub 으로 유지될 가능성도 높다.

### Tool 8 의 stub — `query_anesthesia_drugs`

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

지금은 모든 case 가 같은 3개의 fake drug 를 받는다. real EMR 이 도착하면 case 별로 실제 약물 administration 이 반환된다.

### Tool 11 의 stub — `query_surgery_progress`

```python
def tool_query_surgery_progress(request, clock):
    current_time = float(request.args.get("current_time", clock.now_s))
    total = 7200.0  # 2시간으로 가정
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

수술 시간 비율로 phase 를 휴리스틱하게 추정한다. 처음 15분은 induction, 마지막 10분은 emergence, 그 사이는 maintenance.

### `clinical_review_required` marker — 모든 stub 응답에 박힘

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

EMR stub 응답에는 `clinical_review_required: True` 가 항상 들어가 있다. brief 생성하는 LLM 이 이걸 보고 "이 데이터는 stub 이라서 임상의 검토 필요" 라는 한계를 자동으로 명시한다.

## `registry.py` — 21개 tool 의 중앙 카탈로그 + dispatch

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
    # ... 그리고 20개 더
}


SHALLOW_TOOL_NAMES: Final = (
    "predict_hypotension",
    "predict_cardiac_arrest",
    "assess_signal_quality",
    "cross_modal_consistency",
    "anomaly_score",
)
```

`ToolSpec` 의 `needs_fm` / `needs_signal` flag 가 dispatch 의 분기 기준이 된다.

### `call_tool` — 이름으로 적절한 함수에 전달

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

FM tool 은 `(request, fm, clock, signal)` 4개 인자, EMR tool 은 `(request, clock)` 2개 인자를 받는다. registry 의 spec 을 보고 알아서 분기한다.

## 실제로 어떻게 호출되는가 — Shallow loop 안에서

```python
# vitalagent/nodes/shallow_loop.py 일부

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

`SHALLOW_TOOL_NAMES` 5개를 순회하며 각각을 `call_tool` 로 호출. 결과는 `state.last_tool_results` 에 누적된다. 자세한 node 코드는 [[06_nodes_graph]].

## Test

tool 자체의 별도 unit test 파일은 따로 두지 않았다 — tool 들은 모두 *thin wrapper* 라서 wrapping 대상 (FM, EMR stub) 의 test 와 통합 test 로 충분하다. 검증은 다음 두 곳에서.

| Test | 검증 |
|------|------|
| `tests/integration/test_smoke_single_case.py` | 5개 shallow + 12개 deep tool 정상 호출 |
| `tests/integration/test_e2e_100cases_tier2.py` | 100 case × 6 tick × ~8 tool ≈ 4,800+ tool 호출, leakage 0건 |

## 다음 노트

- [[06_nodes_graph]] — node 가 어떻게 이 tool 들을 호출하는가
- [[01_fm_layer]] — FM interface (이 layer 가 의존하는 추상)
- [[20_아키텍처/21_Tool_Suite]] — 21개 tool 의 카테고리별 의미
- [[20_아키텍처/데이터_누수_방지]] — leakage guard 의 정책
