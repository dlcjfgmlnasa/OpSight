"""Auxiliary tools 15–16 (plan_1.7).
Auxiliary tool 15–16 (plan_1.7).

- Tool 15 ``surgery_context_awareness``: STUB (depends on plan_1.5
  ``surgery_context.yaml``). Minimal hardcoded priors for prototype.
- Tool 16 ``quality_aware_synthesis``: **Full implementation** —
  deterministic mathematical fusion, no LLM call, no external dependency.

- Tool 15: STUB — plan_1.5 의 ``surgery_context.yaml`` 의존. 본 prototype 에서는
  최소 hardcoded priors.
- Tool 16: **정식 구현** — deterministic 수학적 fusion, LLM 호출 없음, 외부 의존 없음.

Schema 정식 spec / Schema authoritative spec: ``docs/tool_spec/auxiliary_tools.md``.
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from opsight.envelope import (
    ToolRequest,
    ToolResponse,
    error_response as _error_response,
)

if TYPE_CHECKING:
    from opsight.sim_clock import SimClock


# ── Tool 15 — surgery_context_awareness (yaml-backed, plan_1.5 완료) ──
# Source: docs/surgery_context.yaml (plan_1.5 산출물).
# YAML 부재 시 minimal hardcoded fallback 으로 graceful degradation.


_SURGERY_CONTEXT_CACHE: dict[str, Any] | None = None


def _load_surgery_context_yaml() -> dict[str, Any] | None:
    """Load docs/surgery_context.yaml (cached). Returns None on failure.
    docs/surgery_context.yaml 로드 (cache). 실패 시 None.
    """
    global _SURGERY_CONTEXT_CACHE
    if _SURGERY_CONTEXT_CACHE is not None:
        return _SURGERY_CONTEXT_CACHE
    try:
        import yaml as _yaml  # PyYAML
        from pathlib import Path as _Path
        repo_root = _Path(__file__).resolve().parents[2]
        yaml_path = repo_root / "docs" / "surgery_context.yaml"
        if not yaml_path.exists():
            return None
        with open(yaml_path, encoding="utf-8") as f:
            _SURGERY_CONTEXT_CACHE = _yaml.safe_load(f)
        return _SURGERY_CONTEXT_CACHE
    except Exception:
        return None


# Fallback minimal hardcoded priors — YAML 부재 시 graceful degradation.
_FALLBACK_PRIORS: dict[str, dict[str, list[str]]] = {
    "general": {
        "induction":   ["induction hypotension", "intubation_response"],
        "maintenance": ["maintenance hypotension", "blood loss related changes"],
        "emergence":   ["emergence hypertension", "extubation response"],
        "unknown":     [],
    },
    "thoracic": {
        "induction":   ["induction hypotension", "one_lung_ventilation_onset"],
        "maintenance": ["hypoxemia during OLV", "fluid management challenges"],
        "emergence":   ["emergence hypertension", "respiratory recovery"],
        "unknown":     [],
    },
}


def tool_surgery_context_awareness(
    request: ToolRequest, clock: SimClock
) -> ToolResponse:
    """Surgery-aware reasoning priors per (surgery_type, phase).
    수술 (surgery) 인지 reasoning priors.

    yaml-backed via ``docs/surgery_context.yaml`` (plan_1.5). YAML 부재 시
    minimal hardcoded fallback.
    yaml-backed (`docs/surgery_context.yaml`, plan_1.5). YAML absent →
    minimal hardcoded fallback.
    """
    t0 = time.perf_counter()

    surgery_type = request.args.get("surgery_type")
    if not isinstance(surgery_type, str):
        return _error_response(
            request, "invalid_args", "surgery_type must be a string",
            (time.perf_counter() - t0) * 1000.0,
            quality_meta={"source": "yaml_or_fallback"},
        )

    phase = str(request.args.get("phase", "unknown"))

    yaml_data = _load_surgery_context_yaml()
    common_events: list[str] = []
    phase_hint = f"surgery_type ({surgery_type}) / phase ({phase}) 에 대한 prior 미정의."
    source = "fallback_hardcoded"
    yaml_version = None
    clinical_review_marker = None

    if yaml_data is not None:
        source = "yaml"
        yaml_version = yaml_data.get("version")
        # surgery_types validation
        if surgery_type not in yaml_data.get("surgery_types", {}):
            common_events = []
        else:
            # phase events
            phase_def = yaml_data.get("phases", {}).get(phase, {})
            common_events = list(phase_def.get("typical_hemodynamic_events", []))
            # hint
            hint_cell = (
                yaml_data.get("hints", {}).get(surgery_type, {}).get(phase, {})
            )
            if hint_cell:
                phase_hint = hint_cell.get("hint", phase_hint)
                clinical_review_marker = hint_cell.get("clinical_review")
    else:
        # fallback path
        type_priors = _FALLBACK_PRIORS.get(surgery_type, {})
        common_events = type_priors.get(phase, [])
        if common_events:
            phase_hint = (
                f"본 phase ({phase}) 에서 흔한 hemodynamic 변동을 임상의가 확인할 수 있다."
            )
            clinical_review_marker = "[CLINICIAN-REVIEW: 의료진 검토 필요]"

    # Always append clinical_review_marker to phase_hint if present.
    if clinical_review_marker and clinical_review_marker not in phase_hint:
        phase_hint = phase_hint + " " + clinical_review_marker

    result: dict[str, Any] = {
        "common_events": common_events,
        "phase_hint": phase_hint,
        "reasoning_priors": {evt: 0.0 for evt in common_events},  # informative-only
        "meta": {
            "source": source,
            "yaml_version": yaml_version,
            "note": (
                "plan_1.5 yaml-backed" if source == "yaml"
                else "fallback hardcoded — surgery_context.yaml not loadable"
            ),
        },
    }
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result,
        quality_meta={
            "clinical_review_required": True,
            "source": source,
        },
        latency_ms=(time.perf_counter() - t0) * 1000.0,
    )


# ── Tool 16 — quality_aware_synthesis (FULL implementation) ──


_FUSION_METHODS = ("weighted_mean", "max_quality", "min_uncertainty")


def tool_quality_aware_synthesis(
    request: ToolRequest, clock: SimClock
) -> ToolResponse:
    """Deterministic quality-weighted fusion of multiple predictions.
    여러 prediction 의 quality-weighted deterministic fusion.

    No LLM call. No external dependency. Pure math.
    LLM 호출 없음. 외부 의존 없음. 순수 수학.
    """
    t0 = time.perf_counter()

    predictions = request.args.get("predictions")
    if not isinstance(predictions, list) or len(predictions) == 0:
        return _error_response(
            request, "invalid_args",
            "predictions must be a non-empty list",
            (time.perf_counter() - t0) * 1000.0,
            quality_meta={"deterministic": True},
        )

    method = str(request.args.get("method", "weighted_mean"))
    if method not in _FUSION_METHODS:
        return _error_response(
            request, "invalid_args",
            f"method must be one of {_FUSION_METHODS}, got {method!r}",
            (time.perf_counter() - t0) * 1000.0,
            quality_meta={"deterministic": True},
        )

    # Validate each prediction / 각 prediction 검증
    items: list[tuple[float, float, str]] = []
    for i, p in enumerate(predictions):
        if not isinstance(p, dict):
            return _error_response(
                request, "invalid_args",
                f"predictions[{i}] must be an object",
                (time.perf_counter() - t0) * 1000.0,
                quality_meta={"deterministic": True},
            )
        try:
            value = float(p["value"])
            quality = float(p["quality"])
        except (KeyError, TypeError, ValueError):
            return _error_response(
                request, "invalid_args",
                f"predictions[{i}] missing/invalid 'value' or 'quality'",
                (time.perf_counter() - t0) * 1000.0,
                quality_meta={"deterministic": True},
            )
        if not (0.0 <= quality <= 1.0):
            return _error_response(
                request, "invalid_args",
                f"predictions[{i}].quality must be in [0, 1], got {quality}",
                (time.perf_counter() - t0) * 1000.0,
                quality_meta={"deterministic": True},
            )
        source = str(p.get("source", f"pred_{i}"))
        items.append((value, quality, source))

    # Compute fused_value per method / method 별 fused_value 계산
    if method == "weighted_mean":
        sum_q = sum(q for _, q, _ in items)
        if sum_q == 0.0:
            fused_value = float("nan")
            effective_quality = 0.0
            contributors: list[str] = []
        else:
            fused_value = sum(v * q for v, q, _ in items) / sum_q
            effective_quality = sum_q / len(items)
            contributors = [s for _, q, s in items if q > 0]
    elif method == "max_quality":
        best = max(items, key=lambda t: t[1])
        fused_value = best[0]
        effective_quality = best[1]
        contributors = [best[2]]
    else:  # min_uncertainty (= max_quality, but explicit)
        best = max(items, key=lambda t: t[1])
        fused_value = best[0]
        effective_quality = best[1]
        contributors = [best[2]]

    result: dict[str, Any] = {
        "fused_value": fused_value,
        "effective_quality": effective_quality,
        "contributors": contributors,
        "meta": {
            "method": method,
            "n_inputs": len(items),
            "formula": {
                "weighted_mean":     "sum(v_i * q_i) / sum(q_i)",
                "max_quality":       "v_i where q_i = max(q)",
                "min_uncertainty":   "v_i where (1-q_i) = min, equivalent to max_quality",
            }[method],
        },
    }
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result,
        quality_meta={
            "deterministic": True,
            "effective_quality": effective_quality,
        },
        latency_ms=(time.perf_counter() - t0) * 1000.0,
    )


__all__ = [
    "tool_surgery_context_awareness",
    "tool_quality_aware_synthesis",
]
