"""Streaming signal slicer (Sprint 6 — real_case_run_findings Issue #2).
Streaming signal slicer (Sprint 6 — real_case_run_findings Issue #2).

`build_graph(signal=...)` 가 전체 trajectory 를 한 번에 받던 prototype 의
limitation 을 해결한다. 본 module 의 ``SignalStream`` 은 *원본 전체 signal* 을
보유하되, tool 이 보는 ``view`` 는 ``clock.now_s`` 까지 slice 한 dict.

Issue #2 (whole-signal injection) — strict real-time framing:
- 이전: tool 의 `_to_numpy(signal[k])` 가 전체 array → 미래 sample 포함
- 이후: tool 이 받는 signal 은 ``stream.view_until(sim_time_s)`` — 시점 t 까지만

Design choices:
- Stream 은 modality 별 sampling rate 를 안다 (또는 추정).
- View 는 *얕은* slice (zero-copy where possible) — `torch.Tensor` 의 narrow.
- 미래 호출의 cache 일관성을 위해 ``frozen=True`` Pydantic 외부 인터페이스.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import torch

from opsight.preprocessing.signal_config import config_for_modality

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class SignalStream:
    """Holds full signal + per-modality sampling rates, exposes time-aware views.
    전체 signal + modality 별 sampling rate 보유, 시간 인지 view 제공.

    Args:
        signal: dict mapping modality alias → 1-D torch.Tensor (full trajectory).
        sampling_rates_hz: dict mapping modality alias → Hz. If missing,
            inferred from ``config_for_modality(name).typical_sampling_rate_hz``;
            fallback 1.0 Hz.
        start_offset_s: time of ``signal[*][0]`` in sim_time. Default 0.0.

    Args:
        signal: modality alias → 1-D tensor (전체 trajectory) dict.
        sampling_rates_hz: modality alias → Hz dict. 누락 시 SignalConfig 의
            typical_sampling_rate_hz; 그것도 없으면 1.0 Hz.
        start_offset_s: ``signal[*][0]`` 의 sim_time. 기본 0.0.
    """

    signal: dict[str, torch.Tensor]
    sampling_rates_hz: dict[str, float] = field(default_factory=dict)
    start_offset_s: float = 0.0

    def __post_init__(self) -> None:
        # Validate / 검증
        for name, tensor in self.signal.items():
            if not isinstance(tensor, torch.Tensor):
                raise TypeError(f"signal[{name!r}] must be torch.Tensor, got {type(tensor)}")
            if tensor.dim() != 1:
                raise ValueError(f"signal[{name!r}] must be 1-D, got shape {tuple(tensor.shape)}")

    def sampling_rate_hz_for(self, modality: str) -> float:
        """Resolve sampling rate for a modality.
        Modality 의 sampling rate 해석.
        """
        if modality in self.sampling_rates_hz:
            return float(self.sampling_rates_hz[modality])
        cfg = config_for_modality(modality)
        if cfg is not None:
            return float(cfg.typical_sampling_rate_hz)
        return 1.0  # conservative fallback

    def n_samples_until(self, modality: str, sim_time_s: float) -> int:
        """How many samples from start_offset_s to sim_time_s for this modality.
        Modality 의 start_offset_s ~ sim_time_s 까지 sample 수.
        """
        elapsed = max(0.0, sim_time_s - self.start_offset_s)
        sr_hz = self.sampling_rate_hz_for(modality)
        n_target = int(round(elapsed * sr_hz))
        # Clamp to actual signal length / 실제 signal 길이로 clamp
        return min(n_target, int(self.signal[modality].numel()))

    def view_until(self, sim_time_s: float) -> dict[str, torch.Tensor]:
        """Return a new signal dict containing only samples up to sim_time_s.
        sim_time_s 까지의 sample 만 포함하는 새 signal dict 반환.

        ``narrow`` views are zero-copy 동일 underlying storage. 별도 copy 없음
        (read-only assumption — tool 들이 mutate 하지 않음, 이미 verified).

        Edge cases:
        - sim_time_s < start_offset_s → 모든 modality 가 empty tensor
        - sim_time_s >= 전체 duration → 전체 signal (no slicing)
        """
        out: dict[str, torch.Tensor] = {}
        for name, tensor in self.signal.items():
            n = self.n_samples_until(name, sim_time_s)
            if n == 0:
                out[name] = tensor.new_empty(0)
            elif n >= tensor.numel():
                out[name] = tensor  # no slice needed
            else:
                out[name] = tensor.narrow(0, 0, n)
        return out

    def total_duration_s(self) -> float:
        """Longest modality duration in seconds.
        가장 긴 modality 의 duration (초).
        """
        max_dur = 0.0
        for name, tensor in self.signal.items():
            sr = self.sampling_rate_hz_for(name)
            if sr > 0:
                dur = tensor.numel() / sr
                max_dur = max(max_dur, dur)
        return max_dur


def stream_from_full_signal(
    signal: dict[str, torch.Tensor],
    *,
    sampling_rates_hz: dict[str, float] | None = None,
    default_sampling_rate_hz: float | None = None,
    start_offset_s: float = 0.0,
) -> SignalStream:
    """Build a SignalStream from a full signal dict.
    전체 signal dict 에서 SignalStream 생성.

    Args:
        signal: full trajectory signal dict.
        sampling_rates_hz: per-modality override. 누락된 modality 는
            ``config_for_modality(name).typical_sampling_rate_hz`` fallback.
        default_sampling_rate_hz: if set, used for *all* modalities that don't
            have an entry in ``sampling_rates_hz`` (overrides config-based default).
            모든 modality 의 default. 설정 시 config-based 보다 우선.
        start_offset_s: ``signal[*][0]`` 의 sim_time offset.
    """
    rates = dict(sampling_rates_hz or {})
    if default_sampling_rate_hz is not None:
        for name in signal:
            rates.setdefault(name, float(default_sampling_rate_hz))
    return SignalStream(
        signal=signal,
        sampling_rates_hz=rates,
        start_offset_s=start_offset_s,
    )


__all__ = ["SignalStream", "stream_from_full_signal"]
