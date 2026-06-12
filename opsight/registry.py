"""Tool registry — central catalog of tools (plan_1.8 task 5).
Tool registry — tool 중앙 카탈로그 (plan_1.8 task 5).

⚠️ Ownership / 소유권:
   This is the **minimal** registry for the dual-mode skeleton. The
   authoritative spec (JSON schemas, LLM-facing descriptions, failure modes)
   lives in ``plan_1.7_tool_spec.md`` and ``docs/tool_spec/``. When plan_1.7
   lands, the registry below is superseded.
   본 module은 dual-mode skeleton용 **최소** registry다. JSON schema / LLM
   description / failure mode 정식 spec은 ``plan_1.7_tool_spec.md``와
   ``docs/tool_spec/``에 위치하며, plan_1.7 도착 시 본 registry는 대체된다.

Tool category map (project_brief §7):
Tool 카테고리 (project_brief §7):
- Auxiliary tools                 — opsight/tools/auxiliary_tools.py
- Signal-state tools (ADR-016, amended 2026-06-10) — opsight/tools/signal_state_tools/ (package)
- EMR tools (preop patient context) — opsight/tools/emr_tools/ (package)

NOTE: FM-backed tools, the EMR/drug-lookup group, knowledge stubs, and the
mock/placeholder LLM were removed during the false-alarm-agent rebuild.
``get_patient_context`` (preop-safe, leakage-free) is the first revived EMR
member; the rest stay deferred to Stage 2.
주: FM 기반 tool, EMR/약물 lookup 그룹, knowledge stub, mock/placeholder LLM 은
false-alarm-agent 재작성에서 제거됨. ``get_patient_context`` (preop-safe·누수 0) 만
먼저 부활했고 나머지 EMR tool 은 Stage 2 로 deferred.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Final

from opsight.tools.auxiliary_tools import (
    tool_quality_aware_synthesis,
    tool_surgery_context_awareness,
)
from opsight.tools.emr_tools import tool_get_patient_context
from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools import (
    tool_assess_signal_quality,
    tool_assess_variability,
    tool_compare_to_baseline,
    tool_describe_signal,
    tool_get_current_state,
    tool_get_signal_trend,
    tool_summarize_current_state,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# ── Tool spec dataclass / Tool spec 데이터클래스 ──


@dataclass(frozen=True)
class ToolSpec:
    """Minimal tool spec for the dual-mode skeleton.
    Dual-mode skeleton용 최소 tool spec.

    The full spec (input / output JSON schema, LLM description, failure
    modes) will live in ``docs/tool_spec/*.md`` per plan_1.7.
    전체 spec (input / output JSON schema, LLM description, failure mode)은
    plan_1.7에 따라 ``docs/tool_spec/*.md``에 위치한다.
    """

    name: str
    category: str  # "emr" | "knowledge" | "auxiliary" | "signal_state"
    description: str
    # Callable signature differs between signal-reading tools (need ``signal``)
    # and clock-only EMR tools. The registry stores the raw callable; dispatch
    # logic below handles the difference via ``needs_signal``.
    # signal-reading tool 은 ``signal`` 필요, EMR 은 clock-only — registry 는 raw
    # callable 보관, dispatch logic 이 ``needs_signal`` 로 분기.
    fn: Callable[..., ToolResponse] = field(repr=False)
    needs_signal: bool = False


# ── Tool registry (EMR + Knowledge + Auxiliary + Signal Access) ──
# FM-backed tools removed (Biosignal Foundation Model decoupled).

TOOLS: Final[dict[str, ToolSpec]] = {
    # Auxiliary tools / Auxiliary tool (15 yaml-backed, 16 FULL)
    "surgery_context_awareness": ToolSpec(
        name="surgery_context_awareness",
        category="auxiliary",
        description=(
            "Reasoning priors for surgery type + phase "
            "(STUB minimal priors — pending plan_1.5 surgery_context.yaml)."
        ),
        fn=tool_surgery_context_awareness,
    ),
    "quality_aware_synthesis": ToolSpec(
        name="quality_aware_synthesis",
        category="auxiliary",
        description=(
            "Deterministic quality-weighted fusion of multiple predictions. "
            "No LLM call inside."
        ),
        fn=tool_quality_aware_synthesis,
    ),
    # EMR tools — preop patient context (first revived member; rest Stage 2)
    "get_patient_context": ToolSpec(
        name="get_patient_context",
        category="emr",
        description=(
            "Preoperative patient context from VitalDB cases metadata — "
            "age/sex/bmi, ASA, department/opname/diagnosis. Leakage-free "
            "(preop-safe whitelist; never reads postop/outcome/intraop_* "
            "columns). Returns values only; clinical interpretation deferred "
            "to the brief LLM with [CLINICIAN-REVIEW]. Brief §[Surgery context] source."
        ),
        fn=tool_get_patient_context,
    ),
    # Signal Access tools (ADR-016) — plan_1.3.5
    # Signal Access tool (ADR-016) — plan_1.3.5
    "get_current_state": ToolSpec(
        name="get_current_state",
        category="signal_state",
        description=(
            "Current vital snapshot — trailing-window mean per vital "
            "(MAP/SBP/DBP/HR/RR/SpO2/EtCO2/BIS/temp). Reports available / "
            "missing vitals. Brief §[Signal status] 의 정량 source."
        ),
        fn=tool_get_current_state,
        needs_signal=True,
    ),
    "get_signal_trend": ToolSpec(
        name="get_signal_trend",
        category="signal_state",
        description=(
            "Per-vital temporal trend over a trailing window — least-squares "
            "slope, direction (rising/falling/stable), delta, R². Distinguishes "
            "sustained change from transient artifact for alarm triage."
        ),
        fn=tool_get_signal_trend,
        needs_signal=True,
    ),
    "describe_signal": ToolSpec(
        name="describe_signal",
        category="signal_state",
        description=(
            "NaN-safe statistical summary of a modality window "
            "(mean/std/min/max/median/IQR/missing_ratio/n_samples)."
        ),
        fn=tool_describe_signal,
        needs_signal=True,
    ),
    "assess_variability": ToolSpec(
        name="assess_variability",
        category="signal_state",
        description=(
            "Variability metrics per modality — HRV (SDNN/RMSSD/LF-HF) for HR, "
            "BPV (SD/ARV) for MAP, amplitude/SVV for PPG."
        ),
        fn=tool_assess_variability,
        needs_signal=True,
    ),
    "compare_to_baseline": ToolSpec(
        name="compare_to_baseline",
        category="signal_state",
        description=(
            "Compare current modality mean to baseline (preop or intraop early "
            "10 min). Returns absolute / percent change + direction."
        ),
        fn=tool_compare_to_baseline,
        needs_signal=True,
    ),
    "assess_signal_quality": ToolSpec(
        name="assess_signal_quality",
        category="signal_state",
        description=(
            "Rule-based per-modality signal quality (SQI) in [0,1] from "
            "missing-ratio + sensor-range violation + waveform flatline. "
            "Quality-aware producer — feeds the triage router's quality gate so "
            "a clear breach on a low-quality signal routes to investigation "
            "(possible artifact) instead of an immediate alarm."
        ),
        fn=tool_assess_signal_quality,
        needs_signal=True,
    ),
    "summarize_current_state": ToolSpec(
        name="summarize_current_state",
        category="signal_state",
        description=(
            "Integrated current state assessment (rule-based threshold path) — "
            "synthesizes get_current_state snapshot + get_signal_trend direction "
            "so a threshold breach reports whether the vital is falling/rising. "
            "ADR-018: rule-based is the accepted Phase 1 implementation; "
            "ADR-014 Tier 0 supervised head deferred. Mandatory conditional "
            "phrasing + [CLINICIAN-REVIEW] marker."
        ),
        fn=tool_summarize_current_state,
        needs_signal=True,
    ),
}


SHALLOW_TOOL_NAMES: Final[tuple[str, ...]] = (
    # Rule-based current-state assessment (deterministic) + signal access
    "summarize_current_state",
    "get_current_state",
    # Quality-aware producer — feeds the triage router's quality gate (ADR-023).
    "assess_signal_quality",
)
"""Shallow-loop tool sweep (project_brief §6.1).

Shallow loop 가 호출하는 tool.
- Rule-based 현재 상태: summarize_current_state, get_current_state
- 신호 품질(SQI): assess_signal_quality → router quality gate (애매한 noise 감지)
"""


# ── Dispatch / 디스패치 ──


def call_tool(
    name: str,
    request: ToolRequest,
    *,
    clock: SimClock,
    signal: dict[str, torch.Tensor] | None = None,
) -> ToolResponse:
    """Dispatch a tool by name with the right argument set.
    Tool 이름으로 적절한 인자 set과 함께 디스패치.

    Raises:
        KeyError: unknown tool name.
            알 수 없는 tool 이름.
    """
    spec = TOOLS.get(name)
    if spec is None:
        raise KeyError(f"unknown tool: {name!r}. known: {sorted(TOOLS)}")
    # Signal-reading tools take ``signal``; clock-only tools (auxiliary) don't.
    # signal-reading tool 은 ``signal`` 사용, clock-only tool (auxiliary) 은 미사용.
    if spec.needs_signal:
        return spec.fn(request, clock, signal or {})
    return spec.fn(request, clock)


__all__ = ["ToolSpec", "TOOLS", "SHALLOW_TOOL_NAMES", "call_tool"]
