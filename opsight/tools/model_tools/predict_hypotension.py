"""Tool: predict_hypotension — near-future hypotension risk (Mock FM, rule_based tier).
근미래 저혈압 위험 예측 (Mock FM, rule_based tier — ADR-011).

⚠️ Mock, NOT the real FM. The real Biosignal FM (Stage 2) consumes raw waveforms
through ``BiosignalFMInterface``; this rule_based mock stands in so the tiered
escalation runs end-to-end now. ``mock_tier="rule_based"`` is surfaced so nothing
mistakes it for a validated model. [CLINICIAN-REVIEW] for threshold/horizon.
실제 FM 아님. real FM(Stage 2)이 도착하면 인터페이스 그대로 교체된다.

Method — level + trend, distinct from the router's *current-state* view:
project MAP to the horizon by its recent slope, then a logistic on the projected
MAP vs the 65 mmHg threshold. MAP 를 최근 기울기로 horizon 까지 외삽 → projected MAP
에 logistic. (현재 상태 분류인 router 와 달리 *근미래* 예측이라는 다른 역할.)
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.model_tools._common import _error, _leakage_guard, _ok
from opsight.tools.signal_state_tools.extractors.get_current_state import (
    tool_get_current_state,
)
from opsight.tools.signal_state_tools.extractors.get_signal_trend import (
    tool_get_signal_trend,
)

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# Threshold + logistic steepness [CLINICIAN-REVIEW: 의료진 검토 필요].
_MAP_THRESHOLD: float = 65.0     # hypotension threshold (lit-standard; same as router)
_LOGISTIC_K: float = 0.15        # risk transitions over ~±15 mmHg around threshold
_DEFAULT_HORIZON_MIN: float = 5.0


def _risk(projected_map: float) -> float:
    """Logistic risk from projected MAP — 1 well below threshold, 0 well above.
    projected MAP 의 logistic 위험 — 임계 한참 아래면 1, 위면 0.
    """
    return 1.0 / (1.0 + math.exp(_LOGISTIC_K * (projected_map - _MAP_THRESHOLD)))


def tool_predict_hypotension(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Forecast hypotension risk over a horizon (Mock FM, rule_based).
    horizon 동안의 저혈압 위험 예측 (Mock FM, rule_based).

    Args (``request.args``): ``horizon_min`` (default 5).
    Reuses ``get_current_state`` (MAP now) + ``get_signal_trend`` (MAP slope).
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    horizon_min = float(request.args.get("horizon_min", _DEFAULT_HORIZON_MIN))

    # Current MAP (reuse the signal-state extractor — DRY; the real FM would
    # encode raw waveforms instead).
    cur = tool_get_current_state(
        ToolRequest(case_id=request.case_id, sim_time_s=request.sim_time_s,
                    tool_name="get_current_state", args={}),
        clock, signal,
    )
    if not cur.ok or cur.result is None:
        return _error(request, "tool_internal_error",
                      "internal: get_current_state failed",
                      (time.perf_counter() - t0) * 1000.0)
    map_now = cur.result.get("vitals", {}).get("map_mmHg")
    if map_now is None:
        # Graceful: this tool is swept unconditionally, so "no MAP this window" is
        # a no-prediction outcome (risk None), NOT a tool failure/error.
        # 무조건 swept 되므로 MAP 부재는 error 가 아니라 예측 불가(risk None) 결과.
        return _ok(
            request,
            {"hypotension_risk": None, "horizon_min": horizon_min,
             "current_map_mmHg": None, "map_slope_per_min": None,
             "projected_map_mmHg": None,
             "meta": {"mock_tier": "rule_based", "note": "MAP unavailable"}},
            (time.perf_counter() - t0) * 1000.0,
            quality_meta={"mock_tier": "rule_based", "clinical_review_required": True},
        )

    # MAP slope (per minute); default 0 (stable) when trend is unavailable.
    slope = 0.0
    tr = tool_get_signal_trend(
        ToolRequest(case_id=request.case_id, sim_time_s=request.sim_time_s,
                    tool_name="get_signal_trend", args={"modality": "map_mmHg"}),
        clock, signal,
    )
    if tr.ok and tr.result is not None:
        t_map = tr.result.get("trends", {}).get("map_mmHg")
        if t_map and t_map.get("slope_per_min") is not None:
            slope = float(t_map["slope_per_min"])

    projected = float(map_now) + slope * horizon_min
    risk = round(_risk(projected), 3)

    result = {
        "hypotension_risk": risk,
        "horizon_min": horizon_min,
        "current_map_mmHg": round(float(map_now), 1),
        "map_slope_per_min": round(slope, 3),
        "projected_map_mmHg": round(projected, 1),
        "meta": {
            "mock_tier": "rule_based",
            "method": "logistic_on_projected_map",
            "threshold_mmHg": _MAP_THRESHOLD,
        },
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"mock_tier": "rule_based", "clinical_review_required": True})
