"""HR family → heart-rate variability (HRV), self-implemented (pure numpy).
HR family → 심박 변이도 (HRV), 자체 구현 (순수 numpy, NeuroKit2 미사용).

Time-domain SDNN / RMSSD + frequency-domain LF/HF via Welch PSD on the
resampled RR tachogram.
시간 영역 SDNN / RMSSD + 주파수 영역 LF/HF (resample RR tachogram 의 Welch PSD).
"""
from __future__ import annotations

import numpy as np

from opsight.tools.signal_state_tools.assess_variability._welch import welch_psd


# Frequency-domain HRV constants (Task Force 1996 standard bands).
# 주파수 영역 HRV 상수 (Task Force 1996 표준 band). [CLINICIAN-REVIEW] — band/method.
_HRV_RESAMPLE_HZ = 4.0          # RR tachogram 균일 resample rate
_HRV_LF_BAND = (0.04, 0.15)     # Hz — low-frequency band
_HRV_HF_BAND = (0.15, 0.40)     # Hz — high-frequency band
_HRV_MIN_RR = 32                # LF/HF 추정 최소 RR 개수
_HRV_MIN_DURATION_S = 25.0      # LF(0.04Hz) 1주기(25s) 이상 필요


def _lf_hf_ratio(rr_ms: np.ndarray) -> float | None:
    """LF/HF ratio from an RR-interval series (Task Force 1996), pure numpy.
    RR interval series 의 LF/HF (Task Force 1996), 순수 numpy.

    Builds the RR tachogram at cumulative beat times, resamples to a uniform
    grid (4 Hz), detrends, and integrates Welch PSD over the LF / HF bands.
    Returns ``None`` when the series is too short or HF power is ~0 (no
    variability → ratio undefined).
    RR tachogram 을 누적 beat 시간에 놓고 균일 grid(4Hz) resample·detrend 후
    Welch PSD 를 LF/HF band 로 적분. series 가 짧거나 HF 전력이 ~0 이면 None.
    """
    if rr_ms.size < _HRV_MIN_RR:
        return None
    # Beat times (s) = cumulative RR; tachogram is irregularly sampled.
    t_beat = np.cumsum(rr_ms) / 1000.0
    t_beat -= t_beat[0]
    duration = float(t_beat[-1])
    if duration < _HRV_MIN_DURATION_S:
        return None
    n = int(duration * _HRV_RESAMPLE_HZ)
    if n < 16:
        return None
    t_uniform = np.arange(n) / _HRV_RESAMPLE_HZ
    rr_interp = np.interp(t_uniform, t_beat, rr_ms)

    res = welch_psd(rr_interp, _HRV_RESAMPLE_HZ, nperseg=min(256, rr_interp.size))
    if res is None:
        return None
    freqs, psd = res
    df = float(freqs[1] - freqs[0]) if freqs.size > 1 else 0.0
    if df <= 0:
        return None
    lf_mask = (freqs >= _HRV_LF_BAND[0]) & (freqs < _HRV_LF_BAND[1])
    hf_mask = (freqs >= _HRV_HF_BAND[0]) & (freqs < _HRV_HF_BAND[1])
    lf = float(np.sum(psd[lf_mask]) * df)
    hf = float(np.sum(psd[hf_mask]) * df)
    if hf <= 1e-12:
        return None
    return lf / hf


def hrv_metrics(hr_arr: np.ndarray) -> dict[str, float | None]:
    """Time- + frequency-domain HRV from an HR series (self-implemented, pure numpy).
    HR series 의 시간·주파수 영역 HRV (자체 구현, 순수 numpy. NeuroKit2 미사용).

    Treats HR samples as instantaneous; RR interval = 60_000 / HR (ms).
    SDNN = std(RR); RMSSD = sqrt(mean(diff(RR)^2)); LF/HF via Welch PSD on the
    resampled RR tachogram (see ``_lf_hf_ratio``).
    HR sample 을 instantaneous 로 간주; RR = 60_000/HR. LF/HF 는 Welch PSD.
    """
    valid = hr_arr[~np.isnan(hr_arr) & (hr_arr > 0)]
    if valid.size < 2:
        return {"SDNN_ms": None, "RMSSD_ms": None, "LF_HF_ratio": None}
    rr_ms = 60_000.0 / valid
    sdnn = float(np.std(rr_ms))
    diff = np.diff(rr_ms)
    rmssd = float(np.sqrt(np.mean(diff ** 2))) if diff.size > 0 else 0.0
    return {"SDNN_ms": sdnn, "RMSSD_ms": rmssd, "LF_HF_ratio": _lf_hf_ratio(rr_ms)}
