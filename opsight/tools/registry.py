"""Tool registry — central catalog of all 16 tools (plan_1.8 task 5).
Tool registry — 16개 tool 중앙 카탈로그 (plan_1.8 task 5).

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
- FM tools 1–7 (FM-backed)        — opsight/tools/fm_tools.py
- EMR tools 8–12 (stub for now)   — opsight/tools/emr_tools_stub.py
- Knowledge tools 13–14           — TODO (post-plan_1.6.5)
- Auxiliary tools 15–16           — TODO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Final

from opsight.tools.auxiliary_tools import (
    tool_quality_aware_synthesis,
    tool_surgery_context_awareness,
)
from opsight.tools.emr_tools_stub import (
    tool_query_anesthesia_drugs,
    tool_query_fluid_blood,
    tool_query_patient_baseline,
    tool_query_surgery_progress,
    tool_query_vasoactive_drugs,
)
from opsight.tools.envelope import ToolRequest, ToolResponse
from opsight.tools.fm_tools import (
    tool_anomaly_score,
    tool_assess_signal_quality,
    tool_cross_modal_consistency,
    tool_forecast_signal,
    tool_predict_cardiac_arrest,
    tool_predict_hypotension,
    tool_temporal_trend_analysis,
)
from opsight.tools.knowledge_tools_stub import (
    tool_find_similar_cases,
    tool_intervention_response_prediction,
)
from opsight.tools.signal_access_tools import (
    tool_assess_variability,
    tool_compare_to_baseline,
    tool_describe_signal,
    tool_get_current_vitals,
    tool_summarize_current_state,
)

if TYPE_CHECKING:
    import torch

    from opsight.fm.interface import BiosignalFMInterface
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
    category: str  # "fm" | "emr" | "knowledge" | "auxiliary"
    description: str
    # Callable signature differs between FM (needs ``fm`` + ``signal``) and EMR
    # (clock-only). The registry stores the raw callable; dispatch logic in
    # the LangGraph node handles the difference.
    # FM은 ``fm`` + ``signal`` 필요, EMR은 clock-only — registry는 raw callable
    # 보관, dispatch logic은 LangGraph node에서 처리.
    fn: Callable[..., ToolResponse] = field(repr=False)
    needs_fm: bool = False    # True → call with (request, fm, clock, signal)
    needs_signal: bool = False


# ── 16-tool registry (FM 7 + EMR 5 implemented; Knowledge / Auxiliary TODO) ──

TOOLS: Final[dict[str, ToolSpec]] = {
    # FM-based tools / FM 기반 tool
    "predict_hypotension": ToolSpec(
        name="predict_hypotension",
        category="fm",
        description="Predict hypotension risk within horizon_min.",
        fn=tool_predict_hypotension,
        needs_fm=True,
        needs_signal=True,
    ),
    "predict_cardiac_arrest": ToolSpec(
        name="predict_cardiac_arrest",
        category="fm",
        description="Predict cardiac arrest risk within horizon_min.",
        fn=tool_predict_cardiac_arrest,
        needs_fm=True,
        needs_signal=True,
    ),
    "assess_signal_quality": ToolSpec(
        name="assess_signal_quality",
        category="fm",
        description="Assess single-modality signal quality.",
        fn=tool_assess_signal_quality,
        needs_fm=True,
        needs_signal=True,
    ),
    "cross_modal_consistency": ToolSpec(
        name="cross_modal_consistency",
        category="fm",
        description="Cross-modal consistency for a modality pair.",
        fn=tool_cross_modal_consistency,
        needs_fm=True,
        needs_signal=True,
    ),
    "temporal_trend_analysis": ToolSpec(
        name="temporal_trend_analysis",
        category="fm",
        description="Temporal trend (slope / label) over a window.",
        fn=tool_temporal_trend_analysis,
        needs_fm=True,
        needs_signal=True,
    ),
    "forecast_signal": ToolSpec(
        name="forecast_signal",
        category="fm",
        description="Forecast modality trajectory.",
        fn=tool_forecast_signal,
        needs_fm=True,
        needs_signal=True,
    ),
    "anomaly_score": ToolSpec(
        name="anomaly_score",
        category="fm",
        description="Anomaly score for a modality window.",
        fn=tool_anomaly_score,
        needs_fm=True,
        needs_signal=True,
    ),
    # EMR-based tools (STUB until plan_1.3) / EMR tool (plan_1.3 전 stub)
    "query_anesthesia_drugs": ToolSpec(
        name="query_anesthesia_drugs",
        category="emr",
        description=(
            "Query main anesthetic drugs (remifentanil / propofol / sevoflurane) "
            "in a time window from Orchestra/Primus tracks."
        ),
        fn=tool_query_anesthesia_drugs,
        needs_signal=True,
    ),
    "query_vasoactive_drugs": ToolSpec(
        name="query_vasoactive_drugs",
        category="emr",
        description=(
            "Query vasoactive drugs in a time window (hybrid — ADR-021). "
            "Orchestra/* infusion channels report track-based `events`; when no "
            "infusion is active, `unobservable_bolus_window=true` flags that "
            "manual bolus push is unobservable (empty events != confirmed-absent)."
        ),
        fn=tool_query_vasoactive_drugs,
        needs_signal=True,
    ),
    "query_fluid_blood": ToolSpec(
        name="query_fluid_blood",
        category="emr",
        description=(
            "Query fluids / blood products — *not streamable* in VitalDB "
            "(per-event timestamps absent; case-end aggregates only). "
            "Returns empty result with honest reason marker."
        ),
        fn=tool_query_fluid_blood,
    ),
    "query_surgery_progress": ToolSpec(
        name="query_surgery_progress",
        category="emr",
        description="Estimate surgery phase / elapsed / remaining (STUB heuristic).",
        fn=tool_query_surgery_progress,
    ),
    "query_patient_baseline": ToolSpec(
        name="query_patient_baseline",
        category="emr",
        description="Case-level patient baseline metadata (STUB).",
        fn=tool_query_patient_baseline,
    ),
    # Knowledge / Comparative tools / Knowledge 비교 tool (plan_1.7 — STUB)
    "find_similar_cases": ToolSpec(
        name="find_similar_cases",
        category="knowledge",
        description="Retrieve up to k similar cohort cases (STUB — pending plan_1.2).",
        fn=tool_find_similar_cases,
    ),
    "intervention_response_prediction": ToolSpec(
        name="intervention_response_prediction",
        category="knowledge",
        description=(
            "Statistical response distribution for an intervention "
            "(NOT a dose recommendation; STUB — pending ADR-013)."
        ),
        fn=tool_intervention_response_prediction,
    ),
    # Auxiliary tools / Auxiliary tool (plan_1.7 — 15 STUB, 16 FULL)
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
    # Signal Access tools (ADR-016) — plan_1.3.5
    # Signal Access tool (ADR-016) — plan_1.3.5
    "get_current_vitals": ToolSpec(
        name="get_current_vitals",
        category="signal_access",
        description=(
            "Current vital values dict (MAP/SBP/DBP/HR/RR/SpO2/EtCO2/BIS/temp). "
            "Brief §[Signal status] 의 정량 source."
        ),
        fn=tool_get_current_vitals,
        needs_signal=True,
    ),
    "describe_signal": ToolSpec(
        name="describe_signal",
        category="signal_access",
        description=(
            "NaN-safe statistical summary of a modality window "
            "(mean/std/min/max/median/IQR/missing_ratio/n_samples)."
        ),
        fn=tool_describe_signal,
        needs_signal=True,
    ),
    "assess_variability": ToolSpec(
        name="assess_variability",
        category="signal_access",
        description=(
            "Variability metrics per modality — HRV (SDNN/RMSSD/LF-HF) for HR, "
            "BPV (SD/ARV) for MAP, amplitude/SVV for PPG."
        ),
        fn=tool_assess_variability,
        needs_signal=True,
    ),
    "compare_to_baseline": ToolSpec(
        name="compare_to_baseline",
        category="signal_access",
        description=(
            "Compare current modality mean to baseline (preop or intraop early "
            "10 min). Returns absolute / percent change + direction."
        ),
        fn=tool_compare_to_baseline,
        needs_signal=True,
    ),
    "summarize_current_state": ToolSpec(
        name="summarize_current_state",
        category="signal_access",
        description=(
            "Integrated current state assessment (rule-based threshold path). "
            "ADR-018: rule-based is the accepted Phase 1 implementation; "
            "ADR-014 Tier 0 supervised head deferred. Mandatory conditional "
            "phrasing + [CLINICIAN-REVIEW] marker."
        ),
        fn=tool_summarize_current_state,
        needs_signal=True,
    ),
}


SHALLOW_TOOL_NAMES: Final[tuple[str, ...]] = (
    # FM-based risk forecast (light)
    "predict_hypotension",
    "predict_cardiac_arrest",
    "assess_signal_quality",
    "cross_modal_consistency",
    "anomaly_score",
    # ADR-018 — Current-state assessment (rule-based, deterministic)
    "summarize_current_state",
    # ADR-018 — Cheap EMR context for narration grounding
    "query_surgery_progress",
    "query_vasoactive_drugs",
)
"""Shallow-loop tool sweep (project_brief §6.1; ADR-018 expanded 5 → 8).

Shallow loop가 호출하는 8개 tool (ADR-018).
- FM forecast 5개: hypotension / arrest risk + signal quality / cross-modal / anomaly
- Rule-based 현재 상태 1개: summarize_current_state (Tool 21)
- Cheap EMR context 2개: surgery_progress (Tool 11) + vasoactive_drugs (Tool 9)
"""


# ── Dispatch / 디스패치 ──


def call_tool(
    name: str,
    request: ToolRequest,
    *,
    fm: BiosignalFMInterface | None = None,
    clock: SimClock,
    signal: dict[str, torch.Tensor] | None = None,
) -> ToolResponse:
    """Dispatch a tool by name with the right argument set.
    Tool 이름으로 적절한 인자 set과 함께 디스패치.

    Raises:
        KeyError: unknown tool name.
            알 수 없는 tool 이름.
        ValueError: missing dependencies (e.g. FM tool without ``fm``).
            의존성 누락 (예: ``fm`` 없이 FM tool).
    """
    spec = TOOLS.get(name)
    if spec is None:
        raise KeyError(f"unknown tool: {name!r}. known: {sorted(TOOLS)}")
    if spec.needs_fm:
        if fm is None:
            raise ValueError(f"tool {name!r} requires fm but none provided")
        return spec.fn(request, fm, clock, signal or {})
    # Signal Access (ADR-016): needs_signal=True without FM dependency.
    # Signal Access (ADR-016): needs_signal=True, FM 무관.
    if spec.needs_signal:
        return spec.fn(request, clock, signal or {})
    return spec.fn(request, clock)


__all__ = ["ToolSpec", "TOOLS", "SHALLOW_TOOL_NAMES", "call_tool"]
