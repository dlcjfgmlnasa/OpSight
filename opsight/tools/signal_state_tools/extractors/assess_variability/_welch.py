"""Welch PSD primitive — shared by the HRV frequency-domain path (pure numpy).
HRV 주파수 영역 경로가 공유하는 Welch PSD primitive (순수 numpy).
"""
from __future__ import annotations

import numpy as np


def welch_psd(x: np.ndarray, fs: float, nperseg: int) -> tuple[np.ndarray, np.ndarray] | None:
    """One-sided PSD via Welch's method (Hann window, 50% overlap, pure numpy).
    Welch 방법의 one-sided PSD (Hann 창, 50% overlap, 순수 numpy).

    Returns (freqs, psd) or ``None`` if the segment is too short. PSD is scaled
    to power spectral density (units²/Hz) using the window-power normalisation.
    """
    nperseg = int(min(nperseg, x.size))
    if nperseg < 8:
        return None
    win = np.hanning(nperseg)
    win_power = float(np.sum(win ** 2))
    step = max(1, nperseg // 2)
    segments = []
    start = 0
    while start + nperseg <= x.size:
        seg = (x[start:start + nperseg] - np.mean(x[start:start + nperseg])) * win
        spec = (np.abs(np.fft.rfft(seg)) ** 2) / (fs * win_power)
        segments.append(spec)
        start += step
    if not segments:
        return None
    psd = np.mean(segments, axis=0)
    freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)
    return freqs, psd
