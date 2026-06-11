"""Shared internals for the fm_tools package (deferred — Stage 2).
fm_tools 패키지 공용 내부 (deferred — Stage 2).

Holds the deferred-stub helper + the (scoped-down) tool plan. Scoped to a single
flagship tool, ``predict_hypotension``; the deferred-candidate names are kept as
documentation so they can be re-added one file at a time when needed.
deferred stub 헬퍼 + (축소된) tool plan. 플래그십 단일 tool ``predict_hypotension``
로 좁혔고, 나머지 후보 이름은 필요 시 한 파일씩 재추가하도록 문서로만 남긴다.
"""
from __future__ import annotations

import time

from opsight.envelope import ToolRequest, ToolResponse, error_response


# Active FM-based tool (name → one-line intent). Single flagship for v1.
# 현재 FM 기반 tool (이름 → 한 줄 의도). v1 은 플래그십 1개.
FM_TOOL_PLAN: dict[str, str] = {
    "predict_hypotension": "Forecast hypotension risk over a horizon (FM head).",
}

# Deferred candidates (NOT implemented; re-add one file at a time if needed).
# brady/tachy intentionally absent — rule-tier, not an FM target.
# 보류 후보 (미구현; 필요 시 한 파일씩 재추가). 서맥/빈맥은 rule-tier 라 의도적 제외.
FM_DEFERRED_CANDIDATES: dict[str, str] = {
    "predict_cardiac_arrest": "Forecast cardiac-arrest risk over a horizon (FM head).",
    "assess_signal_quality": "Per-modality signal-quality score from the FM encoder.",
    "cross_modal_consistency": "Agreement score across modalities (FM latent).",
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
