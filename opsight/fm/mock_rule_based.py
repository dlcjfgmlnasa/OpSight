"""RuleBasedBiosignalFM (Mock FM Tier 2, ADR-011) / Tier 2 rule-based mock.

============================================================================
⚠️ HARD CAVEAT — DO NOT USE TIER-2 OUTPUT FOR CLINICAL DECISIONS.
⚠️ 강제 주의 — Tier 2 출력을 임상 결정에 사용하지 않는다.
----------------------------------------------------------------------------
Tier 2 produces *plausible* but rule-based outputs to validate agent reasoning
before the real FM arrives. Thresholds are heuristics, NOT clinical decision
rules. Every threshold below carries an implicit
``[CLINICIAN-REVIEW: 의료진 검토 필요]`` mark.
Tier 2는 real FM 도착 전 agent reasoning 검증을 위해 *plausible*하지만 rule
기반 출력을 생성한다. Threshold는 휴리스틱이며 임상 결정 규칙이 아니다.
아래 모든 threshold는 암묵적으로
``[CLINICIAN-REVIEW: 의료진 검토 필요]`` marker가 적용된다.

Every Result carries ``meta["mock_tier"] == "rule_based"`` so downstream
consumers can detect (and refuse) Tier-2 output where clinical certainty is
required.
모든 Result는 ``meta["mock_tier"] == "rule_based"``를 갖는다. 임상 확정성이
필요한 downstream consumer는 본 marker로 Tier-2 출력을 감지·거부할 수 있다.
============================================================================

Rule design / Rule 설계 (high level):

1. ``predict_hypotension``       : MAP proxy (mean of ABP) + slope → risk.
2. ``predict_cardiac_arrest``    : composite of HR / MAP / anomaly.
3. ``assess_signal_quality``     : NaN ratio + flatline (std) heuristic.
4. ``cross_modal_consistency``   : |Pearson r| on quality-filtered windows.
5. ``temporal_trend``            : windowed least-squares slope + label rule.
6. ``forecast_signal``           : linear extrapolation + heteroscedastic
                                   uncertainty from recent residuals.
7. ``anomaly_score``             : rolling z-score on the modality window.
8. ``encode``                    : simple feature vector (mean / std / slope /
                                   modality count) padded/truncated to latent_dim.

Configurable noise injection (sprint Risk #1 mitigation):
``noise_pct`` per method or global. Independent ``noise_seed`` keeps
reproducibility while exposing agent reasoning to mock-vs-real variance.
설정 가능 noise injection: method별 또는 전역 ``noise_pct``. 독립적인
``noise_seed``로 재현성 + agent reasoning이 mock-vs-real 분산에 노출되도록 보장.

Spec: ``docs/fm_interface_guide.md §2``, ADR-011 §"3 tiers", plan_1.6.5.
"""
from __future__ import annotations

from typing import Iterable, Literal

import numpy as np
import torch

from opsight.fm.result_types import (
    AnomalyResult,
    ArrestResult,
    ConsistencyResult,
    ForecastResult,
    HypotensionResult,
    QualityResult,
    TrendResult,
)


# ── Threshold constants (clinical heuristics — all CLINICIAN-REVIEW) ──
# Threshold 상수 (임상 휴리스틱 — 모두 CLINICIAN-REVIEW 적용)
#
# `[CLINICIAN-REVIEW: 의료진 검토 필요]` for every threshold below.

# Hypotension rule / 저혈압 규칙
MAP_TARGET: float = 75.0          # MAP at which risk approaches 0 / risk≈0인 MAP
MAP_RISK_FLOOR: float = 55.0      # MAP at/below which map_score saturates / map_score 포화
SLOPE_RISK_FLOOR: float = -5.0    # mmHg/min at which slope_score saturates

# HR-based hypotension fallback (Scope 2 — ABP-less proxy chain)
# HR 기반 저혈압 fallback (Scope 2 — ABP 없을 때 proxy chain)
# Used ONLY when ABP/MAP unavailable or low-quality. Lower confidence by design.
# ABP/MAP 가용 X 또는 품질 낮을 때만 사용. 설계상 신뢰도 낮음.
HR_TACHY_THRESHOLD: float = 100.0  # tachycardia signal → compensatory hypotension proxy
HR_TACHY_SATURATE: float = 140.0   # HR at which tachy_score saturates to 1
HR_BRADY_THRESHOLD: float = 50.0   # bradycardia → less-specific hypotension proxy
HR_SLOPE_RISK_FLOOR: float = 10.0  # bpm/min rise rate → compensatory rise proxy

# Cardiac arrest rule / 심정지 규칙
ARREST_HR_LOW: float = 40.0
ARREST_HR_HIGH: float = 180.0
ARREST_MAP_LOW: float = 50.0
# Proxy-ensemble extensions (Scope 2 — arrest fallback when HR/ABP only)
# Proxy ensemble 확장 (Scope 2 — HR/ABP 만 있을 때 보조 신호)
ARREST_SPO2_LOW: float = 85.0     # SpO2 < this → perfusion-collapse proxy
ARREST_ETCO2_LOW: float = 10.0    # EtCO2 < this → no-pulmonary-perfusion proxy

# Quality rule / 품질 규칙
QUALITY_NAN_CUTOFF: float = 0.10            # NaN ratio > this → degraded
QUALITY_FLATLINE_STD_EPS: float = 1e-3      # std < this → flatline
QUALITY_BASE_SCORE: float = 0.95            # clean signal default
QUALITY_DEGRADED_NAN: float = 0.3           # heavy-NaN score
QUALITY_DEGRADED_FLATLINE: float = 0.2      # flatline score

# Consistency rule / 일관성 규칙
CONSISTENCY_QUALITY_GATE: float = 0.7       # below this, fallback to 0.5

# Trend rule / Trend 규칙
TREND_STABLE_BAND: float = 1.0              # |slope| < this → "stable"

# NaN-burden guard (Scope 2 audit — all signal-statistic methods)
# NaN-burden 가드 (Scope 2 audit — 모든 signal-statistic method)
# Reject downstream rule firing when more than half the window is NaN —
# avoids false flags from sparse-finite signal stripes during sensor
# induction / position-change artifacts.
# Window 의 절반 이상이 NaN 일 때 downstream rule 발화 거부 — sensor induction
# / position-change artifact 의 sparse-finite signal stripe 로 인한 false flag
# 방지.
NAN_BURDEN_REJECT_THRESHOLD: float = 0.5


# ── Helpers (private) / 헬퍼 (private) ──


def _to_numpy(t: torch.Tensor | np.ndarray) -> np.ndarray:
    """Convert tensor / array to a 1-D float numpy array.
    Tensor / array를 1-D float numpy array로 변환.
    """
    if isinstance(t, torch.Tensor):
        arr = t.detach().cpu().numpy()
    else:
        arr = np.asarray(t)
    return arr.astype(np.float64, copy=False).ravel()


def _find_first(
    signal: dict[str, torch.Tensor], candidate_keys: Iterable[str]
) -> tuple[str, np.ndarray] | None:
    """Return ``(name, arr)`` of the first candidate present in ``signal``.
    ``signal``에 존재하는 첫 candidate의 ``(name, arr)`` 반환.
    """
    for k in candidate_keys:
        if k in signal:
            arr = _to_numpy(signal[k])
            if arr.size > 0:
                return k, arr
    return None


def _safe_stats(arr: np.ndarray) -> tuple[float, float, float, float]:
    """Return ``(mean, std, nan_ratio, slope_per_step)``.
    ``(mean, std, nan_ratio, slope_per_step)``을 반환.

    ``slope_per_step`` is the least-squares slope per sample (caller can convert
    to per-minute given the sampling rate).
    ``slope_per_step``은 sample당 least-squares slope (호출자가 sampling rate를
    적용하여 per-minute로 변환).
    """
    n = arr.size
    if n == 0:
        return 0.0, 0.0, 1.0, 0.0
    finite = np.isfinite(arr)
    nan_ratio = float(1.0 - finite.mean())
    arr_clean = arr[finite] if nan_ratio > 0 else arr
    if arr_clean.size == 0:
        return 0.0, 0.0, 1.0, 0.0
    mean = float(np.mean(arr_clean))
    std = float(np.std(arr_clean))
    # least-squares slope via polyfit on indices / index 기준 폴리핏 slope
    if arr_clean.size >= 2:
        slope_per_step = float(np.polyfit(np.arange(arr_clean.size), arr_clean, 1)[0])
    else:
        slope_per_step = 0.0
    return mean, std, nan_ratio, slope_per_step


# ── Class ──


class RuleBasedBiosignalFM:
    """Tier 2 Rule-based Mock — signal-statistic-driven plausible outputs.
    Tier 2 Rule-based Mock — 신호 통계 기반 plausible 출력.

    Satisfies :class:`opsight.fm.interface.BiosignalFMInterface`. Used by
    LangGraph nodes via the factory + Protocol indirection (ADR-011).
    :class:`opsight.fm.interface.BiosignalFMInterface`를 만족. LangGraph
    node는 factory + Protocol indirection으로 사용 (ADR-011).
    """

    # Modality aliases — synthetic key → real VitalDB track names.
    # Modality alias — synthetic key → 실제 VitalDB track 이름.
    # ``MAP`` first — preferred for hypotension prediction (numeric parameter,
    # native 1Hz, already represents mean arterial pressure). live_view
    # aliases Solar8000/ART_MBP → MAP (Fix #4 of preprocessing audit).
    # ``ABP`` is a waveform source; mean(waveform) ≈ MAP but with more
    # noise / NaN-burden, so used only when MAP unavailable.
    # MAP 우선 — 저혈압 예측에 가장 적합 (numeric parameter, 1Hz, MAP 값
    # 자체). live_view 가 Solar8000/ART_MBP 를 MAP alias 로 라우팅 (preprocess
    # audit Fix #4). ABP 는 waveform — MAP 부재 시에만 사용.
    _ABP_ALIASES = (
        "MAP", "ABP",
        "SNUADC/ART", "Solar8000/ART_MBP", "EV1000/ART_MBP",
    )
    _ECG_ALIASES = ("ECG", "ECG_II", "SNUADC/ECG_II")
    _PPG_ALIASES = ("PPG", "SNUADC/PLETH")
    _HR_ALIASES = ("HR", "Solar8000/HR", "Solar8000/PLETH_HR")
    _BIS_ALIASES = ("BIS", "BIS/EEG1_WAV", "BIS/BIS")
    # Arrest proxy-ensemble extensions (Scope 2)
    # Arrest proxy ensemble 확장 (Scope 2)
    _SPO2_ALIASES = ("SpO2", "Solar8000/PLETH_SPO2", "Solar8000/SPO2")
    _ETCO2_ALIASES = ("EtCO2", "Solar8000/ETCO2", "Primus/ETCO2")
    # brief §1 6 modality 중 CVP / PAP — Tier 2 rule 미정 (placeholder).
    # 현재 rule 출력에는 사용하지 않지만, encode/embed 경로에서 alias 인식
    # 가능하도록 보존. [CLINICIAN-REVIEW] 추후 fluid-status / RV-strain rule 추가.
    _CVP_ALIASES = ("CVP", "CVP_MEAN", "SNUADC/CVP", "Solar8000/CVP", "EV1000/CVP")
    _PAP_ALIASES = (
        "PAP_MBP", "PAP_SBP", "PAP_DBP",
        "Solar8000/PA_MBP", "Solar8000/PA_SBP", "Solar8000/PA_DBP",
    )

    def __init__(
        self,
        seed: int = 42,
        latent_dim: int = 128,
        sampling_rate_hz: float = 500.0,
        noise_pct: float = 0.0,
        noise_per_method: dict[str, float] | None = None,
        noise_seed: int | None = None,
    ) -> None:
        """Initialize the rule-based mock.
        Rule-based mock 초기화.

        Args:
            seed: deterministic seed for downstream RNG (currently unused —
                rule outputs are deterministic given the signal).
                downstream RNG의 결정적 seed. (현재 미사용 — rule 출력은
                signal이 주어지면 결정적.)
            latent_dim: dimension of ``encode`` output.
                ``encode`` 출력 차원.
            sampling_rate_hz: assumed sampling rate when converting slope
                from per-step to per-minute (default 500 Hz).
                Per-step slope를 per-minute로 변환 시 사용하는 sampling rate
                (기본 500 Hz).
            noise_pct: global ±jitter as a fraction of each numeric output
                (e.g. 0.2 = ±20%). ``0`` (default) means no injection.
                각 numeric 출력에 적용되는 전역 ±jitter 비율. ``0`` (기본)은 미적용.
            noise_per_method: per-method overrides; keys are method names.
                method별 override; key는 method 이름.
            noise_seed: independent seed for the noise RNG. Defaults to
                ``seed`` if ``None``.
                noise RNG용 독립 seed. ``None``이면 ``seed`` 사용.
        """
        self._seed = seed
        self._latent_dim = latent_dim
        self._sampling_rate_hz = float(sampling_rate_hz)
        self._noise_pct = float(noise_pct)
        self._noise_per_method = dict(noise_per_method or {})
        self._noise_rng = np.random.default_rng(noise_seed if noise_seed is not None else seed)

    # ── Noise injection / Noise 주입 ──

    def _apply_noise(self, method: str, value: float) -> float:
        """Apply ±jitter to a scalar output per method config.
        Method 구성에 따라 scalar 출력에 ±jitter 적용.

        Returns the jittered value, optionally clipped by the caller.
        Jittered 값 반환. 호출자가 clip할 수 있다.
        """
        pct = self._noise_per_method.get(method, self._noise_pct)
        if pct <= 0:
            return value
        delta = float(self._noise_rng.uniform(-pct, pct)) * value
        return value + delta

    @staticmethod
    def _clip01(value: float) -> float:
        """Clip to ``[0, 1]`` / ``[0, 1]``로 clip."""
        return max(0.0, min(1.0, value))

    # ── 8 Protocol methods / 8 Protocol 메서드 ──

    def encode(
        self,
        signal: dict[str, torch.Tensor],
        available_modalities: list[str],
    ) -> torch.Tensor:
        """Simple feature vector: per-modality (mean, std, slope) padded/truncated.
        단순 feature 벡터: modality별 (mean, std, slope)를 pad/truncate.

        Deterministic given the same signal. Acts as a tiny "encoder" for
        agent code that consumes a latent vector.
        동일 signal에 대해 결정적. agent code가 소비하는 작은 "encoder" 역할.
        """
        feats: list[float] = [float(len(available_modalities))]
        for k in available_modalities:
            if k not in signal:
                feats.extend([0.0, 0.0, 0.0])
                continue
            mean, std, _nan, slope = _safe_stats(_to_numpy(signal[k]))
            feats.extend([mean, std, slope])
        # Pad / truncate to latent_dim / latent_dim에 맞춰 pad / truncate.
        arr = np.zeros(self._latent_dim, dtype=np.float32)
        n = min(len(feats), self._latent_dim)
        arr[:n] = np.asarray(feats[:n], dtype=np.float32)
        return torch.from_numpy(arr)

    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult:
        """Risk rises with low MAP and falling slope.
        Risk는 낮은 MAP과 falling slope에서 상승.

        Fallback chain (Scope 2, ADR-modality-agnostic / 작업 18):
        1. ABP (invasive or NIBP MAP) — primary, best confidence.
        2. HR — tachycardia / rising-HR proxy when ABP missing or low-quality.
        3. PPG/ECG presence only (rule-based Tier 2 cannot exploit waveform at
           1Hz; presence is recorded so prompt/clinician sees what was available).
        4. None — flat 0.4 with very high uncertainty.

        ``[CLINICIAN-REVIEW]`` — all thresholds are heuristic. HR-based proxy
        is *less specific* than ABP. Tier 3 / real FM will replace this chain.
        ``[CLINICIAN-REVIEW]`` — 모든 threshold 는 휴리스틱. HR fallback 은
        ABP 대비 *덜 specific*. Tier 3 / 진짜 FM 도착 후 이 chain 교체.
        """
        chain: list[dict] = []  # what we tried, in order
        abp_found = _find_first(signal, self._ABP_ALIASES)
        ppg_present = _find_first(signal, self._PPG_ALIASES) is not None
        ecg_present = _find_first(signal, self._ECG_ALIASES) is not None

        # ── Path 1 — ABP (primary) / ABP 1차 경로 ──
        if abp_found is not None:
            key, arr = abp_found
            mean, std, nan_ratio, slope_step = _safe_stats(arr)
            if std >= QUALITY_FLATLINE_STD_EPS and nan_ratio <= 0.5:
                # ABP quality OK — use it / ABP 품질 OK — 사용.
                denom = MAP_TARGET - MAP_RISK_FLOOR
                map_score = self._clip01((MAP_TARGET - mean) / denom) if denom > 0 else 0.0
                slope_per_min = slope_step * self._sampling_rate_hz * 60.0
                slope_score = (
                    self._clip01(-slope_per_min / -SLOPE_RISK_FLOOR)
                    if slope_per_min < 0 else 0.0
                )
                risk = 0.4 * map_score + 0.6 * slope_score
                risk = self._clip01(self._apply_noise("predict_hypotension", risk))
                uncertainty = self._clip01(
                    0.2 + 0.3 * (1.0 - min(map_score + slope_score, 1.0))
                    + nan_ratio * 0.5
                )
                return HypotensionResult(
                    risk=risk, uncertainty=uncertainty, horizon_min=horizon_min,
                    meta={
                        "mock_tier": "rule_based",
                        "predicted_from": "abp",
                        "abp_key": key,
                        "map_proxy": mean,
                        "slope_mmhg_per_min": slope_per_min,
                        "map_score": map_score,
                        "slope_score": slope_score,
                        "nan_ratio": nan_ratio,
                        "ppg_present": ppg_present,
                        "ecg_present": ecg_present,
                    },
                )
            # ABP found but low-quality — fall through to HR proxy.
            # ABP 찾았지만 품질 낮음 — HR proxy 로 fall through.
            chain.append({
                "tried": "abp", "status": "rejected_low_quality",
                "key": key, "std": std, "nan_ratio": nan_ratio,
            })
        else:
            chain.append({"tried": "abp", "status": "missing"})

        # ── Path 2 — HR proxy (tachycardia / rising HR) ──
        hr_found = _find_first(signal, self._HR_ALIASES)
        if hr_found is not None:
            hr_key, hr_arr = hr_found
            hr_mean, hr_std, hr_nan, hr_slope_step = _safe_stats(hr_arr)
            if hr_std >= QUALITY_FLATLINE_STD_EPS and hr_nan <= 0.5:
                # Tachy score: 0 at HR_TACHY_THRESHOLD, 1 at HR_TACHY_SATURATE.
                denom = HR_TACHY_SATURATE - HR_TACHY_THRESHOLD
                tachy_score = (
                    self._clip01((hr_mean - HR_TACHY_THRESHOLD) / denom)
                    if denom > 0 else 0.0
                )
                # Bradycardia (HR < 50) — less specific, half-weight.
                brady_score = (
                    self._clip01((HR_BRADY_THRESHOLD - hr_mean) / HR_BRADY_THRESHOLD)
                    if hr_mean < HR_BRADY_THRESHOLD else 0.0
                ) * 0.5
                # Rising-HR slope (bpm/min).
                hr_slope_per_min = hr_slope_step * self._sampling_rate_hz * 60.0
                slope_score = (
                    self._clip01(hr_slope_per_min / HR_SLOPE_RISK_FLOOR)
                    if hr_slope_per_min > 0 else 0.0
                )
                # Combine — HR proxy is less direct than ABP; cap at 0.7 to avoid
                # over-confident predictions from indirect signal.
                # HR proxy 는 ABP 보다 간접적 — 0.7 로 cap (간접 신호의 과신 방지).
                raw = 0.4 * tachy_score + 0.2 * brady_score + 0.4 * slope_score
                risk = min(0.7, raw)
                risk = self._clip01(self._apply_noise("predict_hypotension", risk))
                # Uncertainty higher than ABP path: floor 0.5.
                uncertainty = self._clip01(
                    0.5 + 0.2 * (1.0 - min(tachy_score + slope_score, 1.0))
                    + hr_nan * 0.3
                )
                chain.append({"tried": "hr", "status": "used", "key": hr_key})
                return HypotensionResult(
                    risk=risk, uncertainty=uncertainty, horizon_min=horizon_min,
                    meta={
                        "mock_tier": "rule_based",
                        "predicted_from": "hr_compensation_proxy",
                        "hr_key": hr_key,
                        "hr_mean": hr_mean,
                        "hr_slope_bpm_per_min": hr_slope_per_min,
                        "tachy_score": tachy_score,
                        "brady_score": brady_score,
                        "slope_score": slope_score,
                        "nan_ratio": hr_nan,
                        "ppg_present": ppg_present,
                        "ecg_present": ecg_present,
                        "fallback_chain": chain,
                    },
                )
            chain.append({
                "tried": "hr", "status": "rejected_low_quality",
                "key": hr_key, "std": hr_std, "nan_ratio": hr_nan,
            })
        else:
            chain.append({"tried": "hr", "status": "missing"})

        # ── Path 3 — no usable proxy / 가용 proxy 없음 ──
        # Tier 2 cannot exploit raw PPG/ECG waveform at the sampling rates used
        # by current preprocessing. Their *presence* is reported so downstream
        # prompts can hedge appropriately ("PPG available but Tier-2 cannot
        # derive hemodynamic estimate"); real prediction awaits Tier 3 / Bio-FM.
        # Tier 2 는 현재 preprocess sampling rate 의 raw PPG/ECG waveform 활용 불가.
        # presence 만 보고하여 downstream prompt 가 hedge — 실제 예측은 Tier 3 /
        # Bio-FM 도착 후.
        return HypotensionResult(
            risk=0.4,
            uncertainty=0.9 if not (ppg_present or ecg_present) else 0.85,
            horizon_min=horizon_min,
            meta={
                "mock_tier": "rule_based",
                "predicted_from": None,
                "reason": "no_hemodynamic_proxy",
                "ppg_present": ppg_present,
                "ecg_present": ecg_present,
                "available_modalities": list(available_modalities),
                "fallback_chain": chain,
            },
        )

    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult:
        """Proxy-ensemble composite — HR / MAP / SpO2 / EtCO2 thresholds.
        Proxy ensemble 합성 — HR / MAP / SpO2 / EtCO2 threshold.

        Proxy ensemble (Scope 2, ADR-modality-agnostic / 작업 18):
        - HR < 40 / > 180  → score += 0.5  (rhythm extreme)
        - MAP < 50         → score += 0.5  (perfusion collapse)
        - SpO2 < 85        → score += 0.4  (peripheral perfusion loss)
        - EtCO2 < 10       → score += 0.5  (no pulmonary perfusion — strong)

        Multiple confirming proxies → lower uncertainty. ECG/PPG presence is
        recorded but not exploited (Tier 2 cannot analyze rhythm at 1Hz).
        다중 proxy 확인 → uncertainty 하향. ECG/PPG presence 는 meta 에만
        기록 (Tier 2 가 1Hz 에서 rhythm 분석 불가).

        ``[CLINICIAN-REVIEW]`` — all thresholds heuristic, NOT clinical decision
        rules. Tier 3 / real FM replaces this composite with learned proxy.
        ``[CLINICIAN-REVIEW]`` — 모든 threshold 휴리스틱. Tier 3 / 진짜 FM 이
        learned proxy 로 본 composite 교체.
        """
        flags: list[str] = []
        predicted_from: list[str] = []
        score = 0.0
        nan_acc = 0.0
        present = 0

        # Indirect proxies — Tier 2 cannot exploit at 1Hz; reported for prompt.
        # 간접 proxy — Tier 2 1Hz 활용 불가; prompt 용 meta 만 기록.
        ecg_present = _find_first(signal, self._ECG_ALIASES) is not None
        ppg_present = _find_first(signal, self._PPG_ALIASES) is not None

        # ── HR check ──
        hr_found = _find_first(signal, self._HR_ALIASES)
        if hr_found is not None:
            _, hr_arr = hr_found
            hr_mean, _, hr_nan, _ = _safe_stats(hr_arr)
            if hr_nan <= 0.5:
                nan_acc += hr_nan
                present += 1
                predicted_from.append("hr")
                if hr_mean < ARREST_HR_LOW:
                    score += 0.5
                    flags.append(f"hr_low_{hr_mean:.0f}")
                elif hr_mean > ARREST_HR_HIGH:
                    score += 0.5
                    flags.append(f"hr_high_{hr_mean:.0f}")

        # ── ABP / MAP check ──
        abp_found = _find_first(signal, self._ABP_ALIASES)
        if abp_found is not None:
            _, abp_arr = abp_found
            abp_mean, _, abp_nan, _ = _safe_stats(abp_arr)
            if abp_nan <= 0.5:
                nan_acc += abp_nan
                present += 1
                predicted_from.append("abp")
                if abp_mean < ARREST_MAP_LOW:
                    score += 0.5
                    flags.append(f"map_low_{abp_mean:.0f}")

        # ── SpO2 check (proxy-ensemble) ──
        spo2_found = _find_first(signal, self._SPO2_ALIASES)
        if spo2_found is not None:
            _, spo2_arr = spo2_found
            spo2_mean, _, spo2_nan, _ = _safe_stats(spo2_arr)
            if spo2_nan <= 0.5:
                nan_acc += spo2_nan
                present += 1
                predicted_from.append("spo2")
                if spo2_mean < ARREST_SPO2_LOW:
                    score += 0.4
                    flags.append(f"spo2_low_{spo2_mean:.0f}")

        # ── EtCO2 check (strong arrest indicator) ──
        etco2_found = _find_first(signal, self._ETCO2_ALIASES)
        if etco2_found is not None:
            _, etco2_arr = etco2_found
            etco2_mean, _, etco2_nan, _ = _safe_stats(etco2_arr)
            if etco2_nan <= 0.5:
                nan_acc += etco2_nan
                present += 1
                predicted_from.append("etco2")
                if etco2_mean < ARREST_ETCO2_LOW:
                    score += 0.5
                    flags.append(f"etco2_low_{etco2_mean:.1f}")

        # ── No usable proxy / 가용 proxy 없음 ──
        if present == 0:
            return ArrestResult(
                risk=0.05, uncertainty=0.9, horizon_min=horizon_min,
                meta={
                    "mock_tier": "rule_based",
                    "reason": "no_usable_proxy",
                    "predicted_from": [],
                    "flags": [],
                    "ppg_present": ppg_present,
                    "ecg_present": ecg_present,
                    "available_modalities": list(available_modalities),
                },
            )

        risk_raw = min(1.0, score)
        risk = 0.02 + 0.6 * risk_raw
        risk = self._clip01(self._apply_noise("predict_cardiac_arrest", risk))

        nan_avg = nan_acc / present if present else 0.0
        # Base uncertainty drops as more proxies confirm. Each extra proxy
        # beyond the first contributes a small confidence bonus.
        # 기본 uncertainty 는 confirming proxy 가 많을수록 하락. 첫 proxy 이후
        # 각각 작은 confidence bonus.
        base_uncertainty = 0.3 + 0.5 * (1.0 - risk_raw)
        proxy_bonus = min(present - 1, 3) * 0.05   # cap at 4 proxies
        uncertainty = self._clip01(base_uncertainty - proxy_bonus + nan_avg * 0.3)

        return ArrestResult(
            risk=risk,
            uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={
                "mock_tier": "rule_based",
                "flags": flags,
                "predicted_from": predicted_from,
                "modalities_used": present,
                "nan_ratio_avg": nan_avg,
                "ppg_present": ppg_present,
                "ecg_present": ecg_present,
            },
        )

    def assess_signal_quality(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> QualityResult:
        """NaN ratio + flatline detection.
        NaN 비율 + flatline 감지.
        """
        if modality not in signal:
            return QualityResult(
                score=0.0, reason="modality_absent",
                meta={"mock_tier": "rule_based", "modality": modality},
            )
        arr = _to_numpy(signal[modality])
        if arr.size == 0:
            return QualityResult(
                score=0.0, reason="empty_signal",
                meta={"mock_tier": "rule_based", "modality": modality},
            )
        _, std, nan_ratio, _ = _safe_stats(arr)
        if nan_ratio > QUALITY_NAN_CUTOFF:
            score = QUALITY_DEGRADED_NAN
            reason: str | None = f"nan_ratio={nan_ratio:.2f}"
        elif std < QUALITY_FLATLINE_STD_EPS:
            score = QUALITY_DEGRADED_FLATLINE
            reason = "flatline_detected"
        else:
            score = QUALITY_BASE_SCORE
            reason = None
        score = self._clip01(self._apply_noise("assess_signal_quality", score))
        return QualityResult(
            score=score, reason=reason,
            meta={
                "mock_tier": "rule_based", "modality": modality,
                "std": std, "nan_ratio": nan_ratio,
            },
        )

    def cross_modal_consistency(
        self,
        signal: dict[str, torch.Tensor],
        modality_pair: tuple[str, str],
    ) -> ConsistencyResult:
        """|Pearson r| on quality-filtered windows.
        품질 필터된 window의 |Pearson r|.
        """
        a_name, b_name = modality_pair
        if a_name not in signal or b_name not in signal:
            return ConsistencyResult(
                score=0.5, reason="modality_missing",
                meta={"mock_tier": "rule_based", "modality_pair": list(modality_pair)},
            )
        a = _to_numpy(signal[a_name])
        b = _to_numpy(signal[b_name])
        if a.size == 0 or b.size == 0:
            return ConsistencyResult(
                score=0.5, reason="empty_signal",
                meta={"mock_tier": "rule_based", "modality_pair": list(modality_pair)},
            )

        # Resample to common length / 공통 길이로 resample.
        n = min(a.size, b.size)
        a, b = a[:n], b[:n]

        # Filter joint-NaN / 양쪽 NaN 동시 필터.
        finite = np.isfinite(a) & np.isfinite(b)
        if finite.sum() < 8:
            return ConsistencyResult(
                score=0.5, reason="too_few_finite_samples",
                meta={"mock_tier": "rule_based", "modality_pair": list(modality_pair)},
            )
        a, b = a[finite], b[finite]

        # Constant arrays → consistency is undefined; treat as low.
        # 상수 array → consistency 미정; 낮음으로.
        if np.std(a) < QUALITY_FLATLINE_STD_EPS or np.std(b) < QUALITY_FLATLINE_STD_EPS:
            return ConsistencyResult(
                score=0.3, reason="flatline_modality",
                meta={"mock_tier": "rule_based", "modality_pair": list(modality_pair)},
            )

        r = float(np.corrcoef(a, b)[0, 1])
        score = self._clip01(self._apply_noise("cross_modal_consistency", abs(r)))
        return ConsistencyResult(
            score=score,
            reason=None,
            meta={
                "mock_tier": "rule_based",
                "modality_pair": list(modality_pair),
                "pearson_r": r,
                "n_finite": int(finite.sum()),
            },
        )

    def temporal_trend(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        window_min: int,
    ) -> TrendResult:
        """Windowed least-squares slope + label rule.
        Window least-squares slope + label 규칙.
        """
        if modality not in signal or _to_numpy(signal[modality]).size == 0:
            return TrendResult(
                slope=0.0, magnitude=0.0, label="stable",
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "modality_missing", "window_min": window_min,
                },
            )
        arr = _to_numpy(signal[modality])
        _, _, nan_ratio, slope_step = _safe_stats(arr)
        # NaN-burden guard — sparse finite samples make slope unreliable.
        # NaN-burden 가드 — sparse finite sample 은 slope 신뢰도 낮음.
        if nan_ratio > NAN_BURDEN_REJECT_THRESHOLD:
            return TrendResult(
                slope=0.0, magnitude=0.0, label="stable",
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "nan_burden_rejected", "nan_ratio": nan_ratio,
                    "window_min": window_min,
                },
            )
        # Per-step → per-minute (sampling-rate aware).
        slope_per_min = slope_step * self._sampling_rate_hz * 60.0
        slope_per_min = self._apply_noise("temporal_trend", slope_per_min)
        label: Literal["rising", "falling", "stable"]
        if abs(slope_per_min) < TREND_STABLE_BAND:
            label = "stable"
        elif slope_per_min > 0:
            label = "rising"
        else:
            label = "falling"
        return TrendResult(
            slope=slope_per_min,
            magnitude=abs(slope_per_min),
            label=label,
            meta={
                "mock_tier": "rule_based",
                "modality": modality,
                "window_min": window_min,
                "sampling_rate_hz": self._sampling_rate_hz,
                "nan_ratio": nan_ratio,
            },
        )

    def forecast_signal(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        horizon_min: int,
    ) -> ForecastResult:
        """Linear extrapolation + heteroscedastic uncertainty from residuals.
        선형 외삽 + residual 기반 heteroscedastic uncertainty.
        """
        if modality not in signal or _to_numpy(signal[modality]).size == 0:
            zeros = [0.0] * horizon_min
            return ForecastResult(
                forecast=zeros, uncertainty=[10.0] * horizon_min,
                horizon_min=horizon_min,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "modality_missing",
                    "sampling_rate_hz": 1.0 / 60.0,
                },
            )
        arr = _to_numpy(signal[modality])
        if arr.size < 2:
            mean = float(np.nanmean(arr)) if arr.size else 0.0
            return ForecastResult(
                forecast=[mean] * horizon_min,
                uncertainty=[10.0] * horizon_min,
                horizon_min=horizon_min,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "insufficient_samples",
                    "sampling_rate_hz": 1.0 / 60.0,
                },
            )
        # Fit y = a + b*x; extrapolate one sample per minute.
        # y = a + b*x 적합; 분당 한 sample로 외삽.
        x = np.arange(arr.size, dtype=np.float64)
        finite = np.isfinite(arr)
        nan_ratio = float(1.0 - finite.mean())
        if finite.sum() < 2:
            mean = float(np.nanmean(arr)) if arr.size else 0.0
            return ForecastResult(
                forecast=[mean] * horizon_min,
                uncertainty=[10.0] * horizon_min,
                horizon_min=horizon_min,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "too_few_finite", "sampling_rate_hz": 1.0 / 60.0,
                },
            )
        # NaN-burden guard — sparse finite makes the polyfit unreliable.
        # Return flat (mean of finite) forecast with high uncertainty.
        # NaN-burden 가드 — sparse finite 는 polyfit 신뢰도 낮음.
        # finite 평균으로 flat forecast + 높은 uncertainty.
        if nan_ratio > NAN_BURDEN_REJECT_THRESHOLD:
            mean = float(np.mean(arr[finite]))
            return ForecastResult(
                forecast=[mean] * horizon_min,
                uncertainty=[15.0] * horizon_min,  # higher than insufficient_samples
                horizon_min=horizon_min,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "nan_burden_rejected", "nan_ratio": nan_ratio,
                    "sampling_rate_hz": 1.0 / 60.0,
                },
            )
        b, a = np.polyfit(x[finite], arr[finite], 1)
        residuals = arr[finite] - (a + b * x[finite])
        residual_std = float(np.std(residuals))

        # Each forecast sample is 1 minute ahead; in samples that's
        # ``sampling_rate_hz * 60`` per minute. Step the predictor accordingly.
        # 각 forecast sample은 1분 후; sample 단위로 sampling_rate_hz * 60 step.
        step = self._sampling_rate_hz * 60.0
        last_x = float(x[-1])
        forecast: list[float] = []
        uncertainty: list[float] = []
        for i in range(1, horizon_min + 1):
            xi = last_x + step * i
            yi = a + b * xi
            yi = self._apply_noise("forecast_signal", yi)
            forecast.append(float(yi))
            # Uncertainty grows with horizon — sqrt(i) heuristic on residual std.
            # Uncertainty는 horizon과 함께 증가 — residual std의 sqrt(i) heuristic.
            uncertainty.append(float(residual_std * np.sqrt(i) + 1.0))

        return ForecastResult(
            forecast=forecast,
            uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={
                "mock_tier": "rule_based",
                "modality": modality,
                "sampling_rate_hz": 1.0 / 60.0,   # 1 sample / min in the output
                "fit_intercept": float(a),
                "fit_slope": float(b),
                "residual_std": residual_std,
            },
        )

    def anomaly_score(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> AnomalyResult:
        """Rolling z-score magnitude → score in [0, 1].
        Rolling z-score 크기 → score ∈ [0, 1].
        """
        if modality not in signal or _to_numpy(signal[modality]).size == 0:
            return AnomalyResult(
                score=0.0,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "modality_missing",
                },
            )
        arr = _to_numpy(signal[modality])
        finite_mask = np.isfinite(arr)
        nan_ratio = float(1.0 - finite_mask.mean()) if arr.size else 1.0
        finite = arr[finite_mask]
        if finite.size < 2:
            return AnomalyResult(
                score=0.0,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "too_few_finite",
                },
            )
        # NaN-burden guard — sparse finite samples can produce spurious z-score
        # outliers that look like anomalies. Conservative score 0 with reason.
        # NaN-burden 가드 — sparse finite sample 은 z-score outlier 생성하여
        # false anomaly. 보수적으로 score 0 + reason.
        if nan_ratio > NAN_BURDEN_REJECT_THRESHOLD:
            return AnomalyResult(
                score=0.0,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "nan_burden_rejected", "nan_ratio": nan_ratio,
                },
            )
        mean = float(np.mean(finite))
        std = float(np.std(finite))
        if std < QUALITY_FLATLINE_STD_EPS:
            return AnomalyResult(
                score=0.05,
                meta={
                    "mock_tier": "rule_based", "modality": modality,
                    "reason": "flatline", "std": std,
                },
            )
        # Worst (max) |z| in the last 10% of the window — anomaly proxy.
        # Window 마지막 10%의 최대 |z| — anomaly proxy.
        tail = finite[max(1, int(0.9 * finite.size)) :]
        worst_z = float(np.max(np.abs((tail - mean) / std)))
        # Map |z|=0 → 0; |z|=6 → 1 (saturate). The /6 normalizer keeps a
        # stationary normal-noise tail (worst |z| ≈ 2–3 for n≈200) below 0.5,
        # while large spikes (|z| > 6) still saturate to 1.
        # |z|=0 → 0; |z|=6 → 1로 매핑 (포화). /6 normalizer는 정상 정규 잡음 tail
        # (n≈200일 때 worst |z| ≈ 2–3)을 0.5 아래로 유지하면서, 큰 spike (|z| > 6)는
        # 여전히 1로 포화.
        raw = min(1.0, worst_z / 6.0)
        score = self._clip01(self._apply_noise("anomaly_score", raw))
        return AnomalyResult(
            score=score,
            meta={
                "mock_tier": "rule_based",
                "modality": modality,
                "worst_z_tail": worst_z,
                "tail_n": int(tail.size),
            },
        )


__all__ = ["RuleBasedBiosignalFM"]
