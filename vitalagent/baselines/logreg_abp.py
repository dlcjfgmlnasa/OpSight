"""Baseline 1 — Logistic regression on ABP features (plan_1.4 task 2).
Baseline 1 — ABP feature 위에 logistic regression (plan_1.4 task 2).

10 lit-standard ABP feature → sigmoid → P(hypotension within horizon).
torch 의 ``nn.Linear`` + BCE loss 로 학습.

10 lit-standard ABP features → sigmoid → P(hypotension within horizon).
Trained with torch ``nn.Linear`` + BCE loss.

⚠️ Stage 1 prototype: 실 cohort 학습은 plan_1.2 manifest 확정 후. 본 구현
은 synthetic data 로 sanity-check 가능하며 ``BaselineFMAdapter`` 가
``BiosignalFMInterface.predict_hypotension`` 으로 wrap 한다.
⚠️ Stage 1 prototype: Real cohort training awaits plan_1.2 manifest. This
implementation is sanity-checkable on synthetic data and is wrapped by
``BaselineFMAdapter`` as ``BiosignalFMInterface.predict_hypotension``.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch

from vitalagent.baselines.features import ABP_FEATURE_NAMES, extract_abp_features
from vitalagent.baselines.types import BaselineConfig, BaselineResult


class LogRegABPBaseline:
    """Sigmoid(w·x + b) 로 hypotension risk 예측.
    Sigmoid(w·x + b) for hypotension risk prediction.
    """

    name: str = "logreg_abp"

    def __init__(self, config: BaselineConfig | None = None) -> None:
        self.config = config or BaselineConfig(name=self.name)
        self.n_features = len(ABP_FEATURE_NAMES)
        # nn.Linear with sigmoid in forward / nn.Linear + forward 에 sigmoid
        self._linear = torch.nn.Linear(self.n_features, 1)
        self._fitted: bool = False
        # Feature mean / std for normalization (set during fit).
        # 정규화용 feature mean / std (fit 중 설정).
        self._x_mean: torch.Tensor | None = None
        self._x_std: torch.Tensor | None = None

    # ── Training / 학습 ──

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int = 200,
        lr: float = 0.05,
        l2: float = 1e-3,
    ) -> dict[str, Any]:
        """Train on ``X`` (n_samples × n_features) and ``y`` (n_samples,).
        ``X`` (n_sample × n_feature), ``y`` (n_sample,) 로 학습.

        NaN-safe — features with NaN are mean-imputed before training.
        NaN-safe — NaN feature 는 학습 전 평균 대치.
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(
                f"X must be (n, {self.n_features}); got {X.shape}"
            )
        if X.shape[0] != y.shape[0]:
            raise ValueError(f"X / y length mismatch: {X.shape[0]} vs {y.shape[0]}")

        # NaN imputation with column means / column mean 으로 NaN 대치
        col_mean = np.nanmean(X, axis=0)
        col_mean = np.where(np.isnan(col_mean), 0.0, col_mean)
        nan_mask = np.isnan(X)
        X_filled = np.where(nan_mask, col_mean, X)

        # Standardize / 표준화
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

    # ── Inference / 추론 ──

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Batch sigmoid probabilities / Batch sigmoid 확률."""
        if not self._fitted:
            raise RuntimeError("model not fitted; call .fit() first")
        X = np.asarray(X, dtype=np.float64)
        col_mean_np = self._x_mean.detach().cpu().numpy() if self._x_mean is not None else np.zeros(self.n_features)
        nan_mask = np.isnan(X)
        X_filled = np.where(nan_mask, col_mean_np, X)
        Xt = torch.from_numpy(X_filled).float()
        x_mean = self._x_mean if self._x_mean is not None else torch.zeros(self.n_features)
        x_std = self._x_std if self._x_std is not None else torch.ones(self.n_features)
        Xt_std = (Xt - x_mean) / x_std
        with torch.no_grad():
            prob = torch.sigmoid(self._linear(Xt_std)).squeeze(-1)
        return prob.detach().cpu().numpy()

    def predict(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> BaselineResult:
        """Single-case inference matching ``BiosignalFMInterface`` signature.
        ``BiosignalFMInterface`` signature 와 일치하는 단일 case 추론.
        """
        features = extract_abp_features(signal, sampling_rate_hz=self.config.sampling_rate_hz)
        if np.isnan(features).all():
            # ABP fully absent → fallback risk = 0.4, uncertainty = 0.7
            # ABP 완전 부재 → fallback risk = 0.4, uncertainty = 0.7
            return BaselineResult(
                risk=0.4,
                uncertainty=0.7,
                horizon_min=horizon_min,
                meta={
                    "model_name": self.name,
                    "fallback": "no_abp",
                    "available_modalities": list(available_modalities),
                },
            )
        if not self._fitted:
            # Untrained model: zero-init sigmoid ≈ 0.5; uncertainty = high
            # Untrained: zero-init sigmoid ≈ 0.5; uncertainty high
            return BaselineResult(
                risk=0.5,
                uncertainty=0.9,
                horizon_min=horizon_min,
                meta={"model_name": self.name, "fallback": "untrained"},
            )

        prob = float(self.predict_proba(features[None, :])[0])
        # Calibration distance from 0.5 as uncertainty proxy.
        # 0.5 기준 거리를 uncertainty 근사로 사용.
        uncertainty = 1.0 - 2.0 * abs(prob - 0.5)
        return BaselineResult(
            risk=prob,
            uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={
                "model_name": self.name,
                "n_features": self.n_features,
                "available_modalities": list(available_modalities),
            },
        )

    # ── Persistence / 저장 ──

    def save(self, path: str) -> None:
        if not self._fitted:
            raise RuntimeError("cannot save an unfitted model")
        torch.save(
            {
                "name": self.name,
                "n_features": self.n_features,
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
            raise ValueError(f"checkpoint name mismatch: {ckpt.get('name')!r} vs {self.name!r}")
        self._linear.load_state_dict(ckpt["state_dict"])
        self._x_mean = ckpt["x_mean"]
        self._x_std = ckpt["x_std"]
        self._fitted = True


__all__ = ["LogRegABPBaseline"]
