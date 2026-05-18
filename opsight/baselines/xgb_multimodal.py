"""Baseline 2 — XGBoost multimodal (plan_1.4 task 3).
Baseline 2 — XGBoost multimodal (plan_1.4 task 3).

XGBoost 미설치 환경 (현재 prototype) 에서는 명시적 ``NotImplementedError`` 로
안내. 본 module 의 ``XGBMultimodalBaseline`` class skeleton 은 학습 / 추론
interface 만 유지하며 xgboost 설치 후 즉시 사용 가능하도록 한다.

XGBoost is not installed in the prototype environment, so this module raises
an explicit ``NotImplementedError`` with installation guidance. The class
skeleton preserves the training / inference interface so it becomes drop-in
once xgboost is installed.

Reason for the skeleton-first approach / Skeleton-first 이유:
- 본 sprint 의 핵심 unblocker 는 `BaselineFMAdapter` (plan_1.7.5 Tier 3
  Mock FM). XGBoost 의 부재가 본 unblocker 를 막지 않도록 *interface*
  만 안착시킨다. 실 학습은 plan_1.2 cohort + xgboost 설치 후 진행.
- The Sprint's main unblocker is ``BaselineFMAdapter`` (plan_1.7.5 Tier 3
  Mock FM). Lack of xgboost should not block it, so the *interface* is
  established now. Real training waits for plan_1.2 cohort + xgboost install.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import torch

from opsight.baselines.features import (
    MULTIMODAL_FEATURE_NAMES,
    extract_multimodal_features,
)
from opsight.baselines.types import BaselineConfig, BaselineResult


_XGB_INSTALL_HINT = (
    "XGBoost is not installed in the current environment. "
    "Install with: `pip install xgboost` (CPU build is sufficient). "
    "After install, this class becomes drop-in — interface is unchanged."
)


class XGBMultimodalBaseline:
    """Multimodal XGBoost classifier on ABP + HR + PPG summary features.
    ABP + HR + PPG 요약 feature 위에 multimodal XGBoost classifier.

    ⚠️ XGBoost 미설치 시 fit / predict 호출은 명시적 NotImplementedError.
       ``BaselineFMAdapter`` 가 본 baseline 을 wrap 할 때는 ``fitted=False``
       fallback path (risk=0.5, uncertainty=0.9) 가 사용된다.
    ⚠️ When xgboost is missing, fit / predict raise NotImplementedError.
       ``BaselineFMAdapter`` falls back to the unfitted-path
       (risk=0.5, uncertainty=0.9).
    """

    name: str = "xgb_multimodal"

    def __init__(self, config: BaselineConfig | None = None, **xgb_params: Any) -> None:
        self.config = config or BaselineConfig(name=self.name)
        self.n_features = len(MULTIMODAL_FEATURE_NAMES)
        self._xgb_params = xgb_params or {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
            "tree_method": "hist",
        }
        self._model: Any = None  # xgboost.XGBClassifier when fitted
        self._fitted: bool = False

    @staticmethod
    def _require_xgboost() -> Any:
        """Lazy import — raise with install hint when xgboost is absent.
        지연 import — xgboost 부재 시 install hint 와 함께 raise.
        """
        try:
            import xgboost  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in tests
            raise NotImplementedError(_XGB_INSTALL_HINT) from exc
        return xgboost

    def fit(self, X: np.ndarray, y: np.ndarray, **fit_kwargs: Any) -> dict[str, Any]:
        """Train on (n × 15) features and (n,) labels.
        (n × 15) feature, (n,) label 로 학습.
        """
        xgb = self._require_xgboost()
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(f"X must be (n, {self.n_features}); got {X.shape}")
        if X.shape[0] != y.shape[0]:
            raise ValueError(f"X / y length mismatch")

        # xgboost native NaN handling — no imputation needed
        # xgboost 가 NaN native 처리 — imputation 불필요
        self._model = xgb.XGBClassifier(**self._xgb_params)
        self._model.fit(X, y, **fit_kwargs)
        self._fitted = True
        return {"n_samples": int(X.shape[0])}

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("model not fitted")
        return self._model.predict_proba(np.asarray(X, dtype=np.float64))[:, 1]

    def predict(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> BaselineResult:
        if not self._fitted:
            # Either xgboost missing or untrained / xgboost 부재 또는 미학습
            return BaselineResult(
                risk=0.5,
                uncertainty=0.9,
                horizon_min=horizon_min,
                meta={
                    "model_name": self.name,
                    "fallback": "untrained_or_xgb_missing",
                    "install_hint": _XGB_INSTALL_HINT,
                },
            )

        features = extract_multimodal_features(
            signal, sampling_rate_hz=self.config.sampling_rate_hz
        )
        prob = float(self.predict_proba(features[None, :])[0])
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

    def save(self, path: str) -> None:
        if not self._fitted:
            raise RuntimeError("cannot save an unfitted model")
        self._model.save_model(path)

    def load(self, path: str) -> None:
        xgb = self._require_xgboost()
        self._model = xgb.XGBClassifier()
        self._model.load_model(path)
        self._fitted = True


__all__ = ["XGBMultimodalBaseline"]
