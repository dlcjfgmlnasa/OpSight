"""Tool: get_signal_trend — per-vital temporal trend (least-squares slope).
vital 별 시간적 추세 (least-squares slope / 방향 / delta / R²).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import numpy as np

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    DEFAULT_STABLE_PCT,
    DEFAULT_TREND_WINDOW_S,
    _error_response,
    _find_first,
    _leakage_guard,
    _ok,
    _resolve_rate,
    _trailing,
)
from opsight.tools.signal_state_tools.signal_families import _VITAL_ALIASES

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def _trend_one(arr: np.ndarray, rate_hz: float, stable_pct: float) -> dict[str, Any]:
    """Linear-fit trend for one modality window.
    단일 modality window 의 선형 추세.

    Uses least-squares slope over valid samples (robust to endpoint noise) plus
    sub-window means for start/end (first / last 20 %). Direction is decided by
    the percent change band.
    유효 sample 에 대한 least-squares slope + 시작/끝 sub-window 평균(앞/뒤 20%).
    """
    valid_mask = ~np.isnan(arr)
    n_valid = int(valid_mask.sum())
    if n_valid < 2:
        return {"direction": "unknown", "slope_per_min": None,
                "start_value": None, "end_value": None, "delta": None,
                "delta_pct": None, "r_squared": None, "n_samples": int(arr.size),
                "note": "insufficient valid samples"}

    idx = np.arange(arr.size, dtype=np.float64)
    t_s = idx[valid_mask] / rate_hz          # seconds within window
    y = arr[valid_mask]

    # Least-squares line y = a*t + b.
    a, b = np.polyfit(t_s, y, 1)
    slope_per_min = float(a * 60.0)

    # R² of the fit (confidence the trend is linear, not noise).
    yhat = a * t_s + b
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else None

    # Robust start / end via 20 % sub-window means.
    k = max(1, n_valid // 5)
    start_value = float(np.mean(y[:k]))
    end_value = float(np.mean(y[-k:]))
    delta = end_value - start_value
    delta_pct = (delta / start_value * 100.0) if abs(start_value) > 1e-9 else None

    if delta_pct is None:
        direction = "rising" if delta > 0 else "falling" if delta < 0 else "stable"
    elif abs(delta_pct) < stable_pct:
        direction = "stable"
    else:
        direction = "rising" if delta > 0 else "falling"

    return {
        "direction": direction,
        "slope_per_min": round(slope_per_min, 4),
        "start_value": round(start_value, 3),
        "end_value": round(end_value, 3),
        "delta": round(delta, 3),
        "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
        "r_squared": round(r_squared, 3) if r_squared is not None else None,
        "n_samples": int(arr.size),
    }


def _field_for(name: str) -> str | None:
    """Resolve a vital field from a field name or a track alias.
    field 이름 또는 track alias 로부터 vital field 해석.
    """
    if name in _VITAL_ALIASES:
        return name
    for field, aliases in _VITAL_ALIASES.items():
        if name in aliases:
            return field
    return None


def tool_get_signal_trend(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Temporal trend per vital over a trailing window.
    최근 window 동안 vital 별 시간적 추세.

    Args (``request.args``):
        modality: optional single vital field (e.g. "map_mmHg") or track key.
            When omitted, every available known vital is analysed.
        window_s: trailing window length in seconds (default 300 = 5 min).
        stable_pct: |delta%| below this is reported "stable" (default 5).
        sampling_rate_hz / sampling_rates_hz: rate resolution (see _common docs).

    Result:
        ``trends`` — {field: {direction, slope_per_min, start_value, end_value,
        delta, delta_pct, r_squared, n_samples}}.
        ``window_s``, ``meta.source_tracks``.
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock)
    if err is not None:
        return err

    window_s = float(request.args.get("window_s", DEFAULT_TREND_WINDOW_S))
    if window_s <= 0:
        return _error_response(request, "invalid_args",
                               f"window_s must be positive (got {window_s})",
                               (time.perf_counter() - t0) * 1000.0)
    stable_pct = float(request.args.get("stable_pct", DEFAULT_STABLE_PCT))

    # Resolve which fields to analyse.
    requested = request.args.get("modality")
    if requested is not None:
        if not isinstance(requested, str):
            return _error_response(request, "invalid_args", "modality must be a string",
                                   (time.perf_counter() - t0) * 1000.0)
        field = _field_for(requested)
        if field is None:
            return _error_response(request, "invalid_args",
                                   f"modality {requested!r} not a known vital "
                                   f"(known: {sorted(_VITAL_ALIASES)})",
                                   (time.perf_counter() - t0) * 1000.0)
        fields = [field]
    else:
        fields = list(_VITAL_ALIASES)

    trends: dict[str, Any] = {}
    source_tracks: dict[str, str] = {}
    for field in fields:
        found = _find_first(signal, _VITAL_ALIASES[field])
        if found is None:
            continue  # only report vitals actually present
        track_key, arr = found
        rate = _resolve_rate(track_key, request.args)
        window = _trailing(arr, window_s, rate)
        trends[field] = _trend_one(window, rate, stable_pct)
        source_tracks[field] = track_key

    if requested is not None and not trends:
        return _error_response(request, "invalid_args",
                               f"modality {requested!r} resolved to field "
                               f"{fields[0]!r} but no matching track in signal",
                               (time.perf_counter() - t0) * 1000.0)

    result: dict[str, Any] = {
        "trends": trends,
        "window_s": window_s,
        "meta": {"source_tracks": source_tracks, "stable_pct": stable_pct},
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0,
               quality_meta={"source_tracks": source_tracks})
