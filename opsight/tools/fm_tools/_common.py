"""Shared internals for the fm_tools package (deferred — Stage 2).
fm_tools 패키지 공용 내부 (deferred — Stage 2).

Holds the deferred-stub helper + the restoration plan so every FM tool module
imports a single source. Each tool lives in its own module (one tool = one file,
mirroring ``signal_state_tools``) so Stage-2 FM-head implementations land
independently.
deferred stub 헬퍼 + 복원 plan 을 한 곳에 모아 모든 FM tool 모듈이 단일 source 를
import 한다. tool 별 모듈 (한 tool = 한 파일, ``signal_state_tools`` 와 동일) 로
Stage-2 FM-head 구현이 독립적으로 도착하게 한다.
"""
from __future__ import annotations

import time

from opsight.envelope import ToolRequest, ToolResponse, error_response


# Planned FM-based tools (name → one-line intent). Restored at Stage 2.
# 복원 예정 FM 기반 tool (이름 → 한 줄 의도). Stage 2 복원.
FM_TOOL_PLAN: dict[str, str] = {
    "predict_hypotension": "Forecast hypotension risk over a horizon (FM head).",
    "predict_cardiac_arrest": "Forecast cardiac-arrest risk over a horizon (FM head).",
    "assess_signal_quality": "Per-modality signal-quality score from the FM encoder.",
    "cross_modal_consistency": "Agreement score across modalities (FM latent) — feeds trigger #4.",
    "temporal_trend_analysis": "FM-derived temporal trend / change-point over a window.",
    "forecast_signal": "Forecast a modality's near-future trajectory (FM decoder).",
    "anomaly_score": "Reconstruction-based anomaly score from the FM.",
}

_FM_DEFERRED_MSG = (
    "FM-based tool is deferred to Stage 2 (FM integration); not yet implemented "
    "(project_brief §7.6, ADR-011)."
)


def _deferred(request: ToolRequest, t0: float) -> ToolResponse:
    """Uniform ``not_implemented`` envelope for every FM stub.
    모든 FM stub 의 공통 ``not_implemented`` envelope.
    """
    return error_response(
        request,
        "not_implemented",
        _FM_DEFERRED_MSG,
        (time.perf_counter() - t0) * 1000.0,
        category="fm",
        extra={"deferred_until": "stage_2_fm_integration"},
    )
