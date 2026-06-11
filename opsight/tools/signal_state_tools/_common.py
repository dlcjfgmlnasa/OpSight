"""Shared internals for the signal-state tools package.
signal-state tool 패키지의 공용 내부 모듈.

Defaults, numpy helpers, and the envelope helpers (leakage guard / ok / error)
live here so every tool module imports a single source — no duplication. The
modality alias maps (the signal-type taxonomy) live in ``signal_families``.
기본값, numpy 헬퍼, envelope 헬퍼(leakage guard / ok / error)를 여기 한 곳에
모은다. modality alias 맵(신호 분류 taxonomy)은 ``signal_families`` 에 위치한다.

Sampling-rate note / 샘플링 레이트 주의:
    tool 은 timestamp 없는 raw array 를 받으므로 window 길이에 modality 별 rate 가
    필요하다. 해석 순서: ``sampling_rates_hz[mod]`` → ``sampling_rate_hz`` →
    ``DEFAULT_SAMPLING_RATE_HZ``. streaming layer 가 실제 rate 를 전달한다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from opsight.envelope import (
    ToolRequest,
    ToolResponse,
    error_response as _shared_error_response,
    ok as _shared_ok,
)
from opsight.leakage_guard import leakage_guard as _shared_leakage_guard

if TYPE_CHECKING:
    from opsight.sim_clock import SimClock


# ── Defaults / 기본값 ──
# 수치 vital 은 저속(~0.5–1Hz). waveform 은 args 로 override. 1Hz 가 정직한 기본.
DEFAULT_SAMPLING_RATE_HZ: float = 1.0
DEFAULT_CURRENT_WINDOW_S: float = 10.0
DEFAULT_TREND_WINDOW_S: float = 300.0  # 5 min
DEFAULT_STABLE_PCT: float = 5.0        # |delta%| below this → "stable"


# ── numpy helpers / numpy 헬퍼 ──
def _to_numpy(arr: Any) -> np.ndarray:
    """torch.Tensor / list / ndarray → 1-D float64 numpy."""
    try:
        return arr.detach().cpu().numpy().astype(np.float64).ravel()
    except AttributeError:
        return np.asarray(arr, dtype=np.float64).ravel()


def _nanmean_or_none(arr: np.ndarray) -> float | None:
    """NaN-safe mean; ``None`` when empty or all-NaN."""
    if arr.size == 0:
        return None
    mask = ~np.isnan(arr)
    if not mask.any():
        return None
    return float(np.mean(arr[mask]))


def _find_first(signal: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str, np.ndarray] | None:
    """First present alias → (track_key, array). ``None`` if no alias present."""
    for key in aliases:
        if key in signal:
            return key, _to_numpy(signal[key])
    return None


def _resolve_rate(track_key: str, args: dict[str, Any]) -> float:
    """Per-modality sampling rate from args, else single rate, else default."""
    rates = args.get("sampling_rates_hz")
    if isinstance(rates, dict) and track_key in rates:
        try:
            return float(rates[track_key])
        except (TypeError, ValueError):
            pass
    single = args.get("sampling_rate_hz")
    if single is not None:
        try:
            return float(single)
        except (TypeError, ValueError):
            pass
    return DEFAULT_SAMPLING_RATE_HZ


def _trailing(arr: np.ndarray, window_s: float, rate_hz: float) -> np.ndarray:
    """Last ``window_s`` seconds of ``arr`` given ``rate_hz`` (whole array if shorter)."""
    n = int(round(window_s * rate_hz))
    if n <= 0 or n >= arr.size:
        return arr
    return arr[-n:]


# ── envelope helpers / envelope 헬퍼 ──


def _leakage_guard(
    request: ToolRequest, clock: SimClock, query_window_end_s: float | None = None
) -> ToolResponse | None:
    """Refuse queries whose window extends past ``clock.now_s``.
    ``clock.now_s`` 이후를 포함하는 window 조회 거부.

    Thin wrapper over the shared ``opsight.leakage_guard`` primitive that
    tags the ``{"category": "signal_state"}`` quality_meta marker. Window end
    defaults to ``request.sim_time_s`` (current sim-time).
    공유 leakage guard primitive 의 thin wrapper — signal_state marker.
    """
    end = float(request.sim_time_s) if query_window_end_s is None else query_window_end_s
    return _shared_leakage_guard(
        request, clock, end,
        quality_meta={"category": "signal_state"},
        include_extra=True,
    )


def _ok(request: ToolRequest, result: dict[str, Any], latency_ms: float,
        *, quality_meta: dict[str, Any] | None = None) -> ToolResponse:
    """signal_state-tagged wrapper over ``opsight.envelope.ok``."""
    return _shared_ok(
        request, result, latency_ms,
        category="signal_state", quality_meta=quality_meta,
    )


def _error_response(
    request: ToolRequest, err_type: str, message: str, latency_ms: float,
    *, extra: dict[str, Any] | None = None,
) -> ToolResponse:
    """signal_state-tagged wrapper over ``opsight.envelope.error_response``."""
    return _shared_error_response(
        request, err_type, message, latency_ms,
        category="signal_state", extra=extra,
    )
