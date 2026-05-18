"""Baseline 3 — LSTM on ABP waveform (plan_1.4 task 4).
Baseline 3 — ABP waveform 위에 LSTM (plan_1.4 task 4).

Raw ABP waveform window → 1-layer LSTM → sigmoid → P(hypotension).
MC-dropout 으로 uncertainty 근사.

Raw ABP waveform window → 1-layer LSTM → sigmoid → P(hypotension).
MC-dropout for uncertainty approximation.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch

from opsight.baselines.features import _ABP_ALIASES, _find_first, _to_numpy
from opsight.baselines.types import BaselineConfig, BaselineResult


class _LSTMHead(torch.nn.Module):
    def __init__(self, input_size: int = 1, hidden_size: int = 32, dropout: float = 0.2) -> None:
        super().__init__()
        self.lstm = torch.nn.LSTM(
            input_size=input_size, hidden_size=hidden_size, batch_first=True, num_layers=1
        )
        self.dropout = torch.nn.Dropout(dropout)
        self.head = torch.nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, T, 1) / x: (batch, T, 1)
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        last = self.dropout(last)
        return self.head(last)


class LSTMABPBaseline:
    """LSTM 1-layer on downsampled ABP waveform.
    Downsampled ABP waveform 위에 1-layer LSTM.
    """

    name: str = "lstm_abp"

    def __init__(
        self,
        config: BaselineConfig | None = None,
        *,
        downsample_hz: float = 4.0,
        hidden_size: int = 32,
        dropout: float = 0.2,
    ) -> None:
        self.config = config or BaselineConfig(name=self.name)
        self._downsample_hz = float(downsample_hz)
        self._hidden_size = int(hidden_size)
        self._dropout = float(dropout)
        self._net = _LSTMHead(input_size=1, hidden_size=hidden_size, dropout=dropout)
        self._fitted: bool = False
        # normalization stats / 정규화 통계
        self._x_mean: float = 0.0
        self._x_std: float = 1.0

    # ── Helpers / 헬퍼 ──

    def _downsample(self, abp_window: np.ndarray) -> np.ndarray:
        """Decimate raw ABP at config.sampling_rate_hz → ``downsample_hz``.
        raw ABP (config.sampling_rate_hz) 를 ``downsample_hz`` 로 decimate.
        """
        step = max(1, int(round(self.config.sampling_rate_hz / self._downsample_hz)))
        return abp_window[::step]

    def _to_input_tensor(self, abp: np.ndarray) -> torch.Tensor:
        """ABP array → (1, T, 1) tensor with NaN-impute + standardize.
        ABP array → (1, T, 1) tensor (NaN-impute + 표준화).
        """
        ds = self._downsample(abp)
        mean = self._x_mean if self._fitted else float(np.nanmean(ds))
        if not np.isfinite(mean):
            mean = 70.0  # nominal MAP fallback / 표준 MAP fallback
        ds = np.where(np.isnan(ds), mean, ds)
        if self._fitted:
            ds = (ds - self._x_mean) / max(self._x_std, 1e-6)
        return torch.from_numpy(ds).float().reshape(1, -1, 1)

    # ── Training / 학습 ──

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int = 10,
        lr: float = 0.01,
        batch_size: int = 16,
    ) -> dict[str, Any]:
        """Train on (n, T) ABP windows + (n,) labels.
        (n, T) ABP window + (n,) label 로 학습.
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if X.ndim != 2:
            raise ValueError(f"X must be 2-D (n_samples × T); got {X.shape}")
        if X.shape[0] != y.shape[0]:
            raise ValueError(f"X / y length mismatch: {X.shape[0]} vs {y.shape[0]}")

        # NaN-impute with global mean / 전역 mean 으로 NaN-impute
        col_mean = float(np.nanmean(X))
        if not np.isfinite(col_mean):
            col_mean = 70.0
        X_filled = np.where(np.isnan(X), col_mean, X)
        self._x_mean = col_mean
        self._x_std = float(np.std(X_filled)) or 1.0

        # downsample each row / 각 row downsample
        ds_step = max(1, int(round(self.config.sampling_rate_hz / self._downsample_hz)))
        Xds = X_filled[:, ::ds_step]
        Xnorm = (Xds - self._x_mean) / self._x_std

        Xt = torch.from_numpy(Xnorm).float().unsqueeze(-1)  # (n, T_ds, 1)
        yt = torch.from_numpy(y).float().unsqueeze(-1)

        opt = torch.optim.Adam(self._net.parameters(), lr=lr)
        bce = torch.nn.BCEWithLogitsLoss()
        self._net.train()

        losses: list[float] = []
        n = Xt.shape[0]
        for _ep in range(epochs):
            perm = torch.randperm(n)
            ep_loss = 0.0
            for i in range(0, n, batch_size):
                idx = perm[i : i + batch_size]
                opt.zero_grad()
                logit = self._net(Xt[idx])
                loss = bce(logit, yt[idx])
                loss.backward()
                opt.step()
                ep_loss += float(loss.detach()) * idx.numel()
            losses.append(ep_loss / max(1, n))

        self._fitted = True
        return {"final_loss": losses[-1], "n_samples": int(n)}

    # ── Inference / 추론 ──

    def predict(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> BaselineResult:
        abp = _find_first(signal, _ABP_ALIASES)
        if abp is None or len(abp) == 0 or np.isnan(abp).all():
            return BaselineResult(
                risk=0.4, uncertainty=0.7, horizon_min=horizon_min,
                meta={"model_name": self.name, "fallback": "no_abp"},
            )
        if not self._fitted:
            return BaselineResult(
                risk=0.5, uncertainty=0.9, horizon_min=horizon_min,
                meta={"model_name": self.name, "fallback": "untrained"},
            )

        x = self._to_input_tensor(np.asarray(abp, dtype=np.float64))
        # MC-dropout — N forward pass with dropout enabled for uncertainty
        # MC-dropout — dropout 활성 상태로 N forward (uncertainty 근사)
        self._net.train()
        n_mc = 8
        probs: list[float] = []
        with torch.no_grad():
            for _ in range(n_mc):
                logit = self._net(x)
                probs.append(float(torch.sigmoid(logit).squeeze()))
        mean_p = float(np.mean(probs))
        # MC variance → uncertainty in [0, 1] / MC variance → [0, 1] 정규화
        var_p = float(np.var(probs))
        uncertainty = float(min(1.0, var_p * 4.0))  # rescale roughly
        return BaselineResult(
            risk=mean_p,
            uncertainty=uncertainty,
            horizon_min=horizon_min,
            meta={
                "model_name": self.name,
                "mc_dropout_n": n_mc,
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
                "state_dict": self._net.state_dict(),
                "x_mean": self._x_mean,
                "x_std": self._x_std,
                "downsample_hz": self._downsample_hz,
                "hidden_size": self._hidden_size,
                "dropout": self._dropout,
                "config": self.config.__dict__,
            },
            path,
        )

    def load(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        if ckpt.get("name") != self.name:
            raise ValueError(f"checkpoint name mismatch: {ckpt.get('name')!r} vs {self.name!r}")
        self._downsample_hz = float(ckpt["downsample_hz"])
        self._hidden_size = int(ckpt["hidden_size"])
        self._dropout = float(ckpt["dropout"])
        self._net = _LSTMHead(input_size=1, hidden_size=self._hidden_size, dropout=self._dropout)
        self._net.load_state_dict(ckpt["state_dict"])
        self._x_mean = float(ckpt["x_mean"])
        self._x_std = float(ckpt["x_std"])
        self._fitted = True


__all__ = ["LSTMABPBaseline"]
