"""Tool: get_current_state — current vital snapshot (trailing-window mean).
현재 vital 스냅샷 (최근 window 평균).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    DEFAULT_CURRENT_WINDOW_S,
    _error_response,
    _find_first,
    _leakage_guard,
    _nanmean_or_none,
    _ok,
    _resolve_rate,
    _trailing,
)
from opsight.tools.signal_state_tools.signal_families import _VITAL_ALIASES

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_get_current_state(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Current vital snapshot — trailing-window mean per available vital.
    현재 vital 스냅샷 — 가용 vital 별 최근 window 평균.

    Args (``request.args``):
        window_s: trailing window length in seconds (default 10).
            최근 window 길이 (초, 기본 10).
        sampling_rate_hz / sampling_rates_hz: rate resolution (see _common docs).

    Result:
        ``vitals``  — {field: value|None} for every known vital field.
        ``available`` / ``missing`` — field names with / without a present track.
        ``window_s``, ``meta.source_tracks``, ``meta.n_samples``.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock)
    if err is not None:
        return err

    window_s = float(request.args.get("window_s", DEFAULT_CURRENT_WINDOW_S))
    if window_s <= 0:
        return _error_response(request, "invalid_args",
                               f"window_s must be positive (got {window_s})",
                               (time.perf_counter() - t0) * 1000.0)

    vitals: dict[str, float | None] = {}
    source_tracks: dict[str, str] = {}
    n_samples: dict[str, int] = {}
    available: list[str] = []
    missing: list[str] = []

    for field, aliases in _VITAL_ALIASES.items():
        found = _find_first(signal, aliases)
        if found is None:
            vitals[field] = None
            missing.append(field)
            continue
        track_key, arr = found
        rate = _resolve_rate(track_key, request.args)
        window = _trailing(arr, window_s, rate)
        value = _nanmean_or_none(window)
        vitals[field] = value
        source_tracks[field] = track_key
        n_samples[field] = int(window.size)
        (available if value is not None else missing).append(field)

    result: dict[str, Any] = {
        "vitals": vitals,
        "window_s": window_s,
        "available": available,
        "missing": missing,
        "meta": {"source_tracks": source_tracks, "n_samples": n_samples},
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"source_tracks": source_tracks})
