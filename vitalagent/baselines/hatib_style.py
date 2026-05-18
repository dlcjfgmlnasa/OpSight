"""Baseline 4 — Hatib HPI-style approximation (plan_1.4 task 5).
Baseline 4 — Hatib HPI 스타일 근사 (plan_1.4 task 5).

⚠️ Hatib HPI (Hypotension Prediction Index) 는 **commercial proprietary
   알고리즘** 으로 직접 재구현 불가. 본 baseline 은 **공개 문헌** 의
   feature set 만으로 구성한 **open-source approximation** 이다. Paper
   작성 시 본 차이를 명시한다 (plan_1.4 task 5 의 참고 사항).

⚠️ Hatib HPI is a **proprietary commercial algorithm** and cannot be
   reimplemented directly. This is an **open-source approximation** built
   only from publicly described features. The paper must explicitly disclose
   this gap (per plan_1.4 task 5 note).

Reference (paper to cite when reporting): Hatib et al. *Anesthesiology* 2018.
참고 (보고 시 인용): Hatib et al. *Anesthesiology* 2018.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch

from vitalagent.baselines.features import _ABP_ALIASES, _find_first
from vitalagent.baselines.types import BaselineConfig, BaselineResult


# Open-described feature axes / 공개 문헌에 기술된 feature 축
# Per Hatib 2018: 분 단위 ABP 형태 특성, derivative, 분포 등 ~3,022 feature.
# Per Hatib 2018: minute-scale ABP morphology, derivatives, distribution stats — ~3,022 features.
# 본 구현은 **간소화 21 feature** 로 *근사* 한다 (paper 에서 한계 명시 의무).
# This implementation **approximates** with **21 reduced features** (must
# disclose limitation in paper).

HATIB_LIKE_FEATURE_NAMES: tuple[str, ...] = (
    # Distribution stats / 분포 통계 (5)
    "abp_mean", "abp_std", "abp_skew", "abp_kurtosis", "abp_iqr",
    # Pressure quantiles / 압력 quantile (5)
    "abp_p5", "abp_p25", "abp_p50", "abp_p75", "abp_p95",
    # Time-domain / 시간 도메인 (4)
    "abp_slope", "abp_slope_abs", "abp_zero_crossings", "abp_range",
    # Hypotension exposure / 저혈압 노출 (3)
    "frac_below_65", "frac_below_70", "frac_below_55",
    # Derivative-based / derivative 기반 (4)
    "dabp_mean", "dabp_std", "dabp_max", "dabp_min",
)


def _safe_skew(arr: np.ndarray) -> float:
    if len(arr) < 3:
        return 0.0
    m = float(np.mean(arr))
    s = float(np.std(arr))
    if s < 1e-6:
        return 0.0
    return float(np.mean(((arr - m) / s) ** 3))


def _safe_kurtosis(arr: np.ndarray) -> float:
    if len(arr) < 4:
        return 0.0
    m = float(np.mean(arr))
    s = float(np.std(arr))
    if s < 1e-6:
        return 0.0
    return float(np.mean(((arr - m) / s) ** 4) - 3.0)


def extract_hatib_like_features(
    signal: dict[str, Any], sampling_rate_hz: float = 500.0
) -> np.ndarray:
    """Extract 21 Hatib-style approximation features from ABP window.
    ABP window 에서 21 가지 Hatib-style 근사 feature 추출.
    """
    abp = _find_first(signal, _ABP_ALIASES)
    if abp is None or len(abp) == 0:
        return np.full(len(HATIB_LIKE_FEATURE_NAMES), np.nan, dtype=np.float64)
    arr = np.asarray(abp, dtype=np.float64)
    mask = ~np.isnan(arr)
    if not mask.any():
        return np.full(len(HATIB_LIKE_FEATURE_NAMES), np.nan, dtype=np.float64)
    valid = arr[mask]

    # Distribution stats / 분포
    mean = float(np.mean(valid))
    std = float(np.std(valid))
    skew = _safe_skew(valid)
    kurt = _safe_kurtosis(valid)
    iqr = float(np.percentile(valid, 75) - np.percentile(valid, 25))

    # Quantiles
    p5 = float(np.percentile(valid, 5))
    p25 = float(np.percentile(valid, 25))
    p50 = float(np.percentile(valid, 50))
    p75 = float(np.percentile(valid, 75))
    p95 = float(np.percentile(valid, 95))

    # Time-domain
    if len(arr) >= 2:
        x = np.arange(len(arr), dtype=np.float64)
        try:
            slope, _ = np.polyfit(x[mask], valid, 1)
        except (np.linalg.LinAlgError, ValueError):
            slope = 0.0
    else:
        slope = 0.0
    slope_per_min = float(slope * sampling_rate_hz * 60.0)
    slope_abs = abs(slope_per_min)
    # zero crossings of deviation from mean / mean 편차의 zero-crossing
    dev = valid - mean
    zc = int(np.sum(np.diff(np.signbit(dev).astype(int)) != 0))
    rng = float(np.max(valid) - np.min(valid))

    # Hypotension exposure
    frac_below_65 = float(np.mean(valid < 65.0))
    frac_below_70 = float(np.mean(valid < 70.0))
    frac_below_55 = float(np.mean(valid < 55.0))

    # Derivative-based / derivative 기반
    if len(valid) >= 2:
        dabp = np.diff(valid)
        dabp_mean = float(np.mean(dabp))
        dabp_std = float(np.std(dabp))
        dabp_max = float(np.max(dabp))
        dabp_min = float(np.min(dabp))
    else:
        dabp_mean = dabp_std = dabp_max = dabp_min = 0.0

    return np.array(
        [
            mean, std, skew, kurt, iqr,
            p5, p25, p50, p75, p95,
            slope_per_min, slope_abs, float(zc), rng,
            frac_below_65, frac_below_70, frac_below_55,
            dabp_mean, dabp_std, dabp_max, dabp_min,
        ],
        dtype=np.float64,
    )


class HatibStyleBaseline:
    """Open-source Hatib-style approximation — logistic head on 21 features.
    Open-source Hatib 스타일 근사 — 21 feature 위 logistic head.

    Same training pipeline as ``LogRegABPBaseline``, differing only in the
    feature set. Documented as a *limited approximation* of HPI.
    학습 pipeline 은 ``LogRegABPBaseline`` 과 동일, feature set 만 상이.
    HPI 의 *제한된 근사* 임을 명시.
    """

    name: str = "hatib_style"

    def __init__(self, config: BaselineConfig | None = None) -> None:
        self.config = config or BaselineConfig(name=self.name)
        self.n_features = len(HATIB_LIKE_FEATURE_NAMES)
        self._linear = torch.nn.Linear(self.n_features, 1)
        self._fitted: bool = False
        self._x_mean: torch.Tensor | None = None
        self._x_std: torch.Tensor | None = None

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int = 200,
        lr: float = 0.05,
        l2: float = 1e-3,
    ) -> dict[str, Any]:
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(f"X must be (n, {self.n_features}); got {X.shape}")
        if X.shape[0] != y.shape[0]:
            raise ValueError("X / y length mismatch")

        col_mean = np.nanmean(X, axis=0)
        col_mean = np.where(np.isnan(col_mean), 0.0, col_mean)
        X_filled = np.where(np.isnan(X), col_mean, X)

        x_mean = X_filled.mean(axis=0)
        x_std = X_filled.std(axis=0)
        x_std = np.where(x_std < 1e-6, 1.0, x_std)
        X_std = (X_filled - x_mean) / x_std

        Xt = torch.from_numpy(X_std).float()
        yt = torch.from_numpy(y).float().unsqueeze(1)

        opt = torch.optim.Adam(self._linear.parameters(), lr=lr, weight_decay=l2)
        bce = torch.nn.BCEWithLogitsLoss()
        losses: list[float] = []
        for _ in range(epochs):
            opt.zero_grad()
            logit = self._linear(Xt)
            loss = bce(logit, yt)
            loss.backward()
            opt.step()
            losses.append(float(loss.detach()))

        self._x_mean = torch.from_numpy(x_mean).float()
        self._x_std = torch.from_numpy(x_std).float()
        self._fitted = True
        return {"final_loss": losses[-1], "n_samples": int(X.shape[0])}

    def predict(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> BaselineResult:
        features = extract_hatib_like_features(
            signal, sampling_rate_hz=self.config.sampling_rate_hz
        )
        if np.isnan(features).all():
            return BaselineResult(
                risk=0.4, uncertainty=0.7, horizon_min=horizon_min,
                meta={"model_name": self.name, "fallback": "no_abp",
                      "open_source_approximation": True},
            )
        if not self._fitted:
            return BaselineResult(
                risk=0.5, uncertainty=0.9, horizon_min=horizon_min,
                meta={"model_name": self.name, "fallback": "untrained",
                      "open_source_approximation": True},
            )

        col_mean_np = self._x_mean.detach().cpu().numpy() if self._x_mean is not None else np.zeros(self.n_features)
        X_filled = np.where(np.isnan(features), col_mean_np, features)
        Xt = torch.from_numpy(X_filled[None, :]).float()
        x_mean = self._x_mean if self._x_mean is not None else torch.zeros(self.n_features)
        x_std = self._x_std if self._x_std is not None else torch.ones(self.n_features)
        Xt_std = (Xt - x_mean) / x_std
        with torch.no_grad():
            prob = float(torch.sigmoid(self._linear(Xt_std)).squeeze())
        uncertainty = 1.0 - 2.0 * abs(prob - 0.5)
        return BaselineResult(
            risk=prob,
            uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={
                "model_name": self.name,
                "n_features": self.n_features,
                "open_source_approximation": True,
                "clinical_review_required": True,
                "available_modalities": list(available_modalities),
            },
        )

    def save(self, path: str) -> None:
        if not self._fitted:
            raise RuntimeError("cannot save an unfitted model")
        torch.save(
            {
                "name": self.name,
                "state_dict": self._linear.state_dict(),
                "x_mean": self._x_mean,
                "x_std": self._x_std,
                "config": self.config.__dict__,
            },
            path,
        )

    def load(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        if ckpt.get("name") != self.name:
            raise ValueError("checkpoint name mismatch")
        self._linear.load_state_dict(ckpt["state_dict"])
        self._x_mean = ckpt["x_mean"]
        self._x_std = ckpt["x_std"]
        self._fitted = True


__all__ = ["HatibStyleBaseline", "extract_hatib_like_features", "HATIB_LIKE_FEATURE_NAMES"]
