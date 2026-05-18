"""Train / val / test split for baselines (plan_1.4 task 1).
Baseline train / val / test split (plan_1.4 task 1).

Stratified by surgery type (department + optype) when possible.
Surgery type (department + optype) 기준 stratified.

Real cohort split lands when plan_1.2 manifest is finalized. The function
below works on any DataFrame with ``caseid`` (+ optional ``department`` +
``optype``) columns — so it can be re-run later with no API change.

실 cohort split 는 plan_1.2 manifest 확정 후 적용. 본 함수는 ``caseid``
(+ optional ``department`` + ``optype``) column 의 DataFrame 에 작동하므로
plan_1.2 합류 후 그대로 재실행 가능.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def make_splits(
    cases: Any,
    *,
    seed: int = 42,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    stratify_by: list[str] | None = None,
) -> Any:
    """Create reproducible train / val / test split per case.
    재현 가능한 case 별 train / val / test split.

    Args:
        cases: pandas DataFrame with at minimum ``caseid`` column.
            최소 ``caseid`` column 을 가진 pandas DataFrame.
        seed: random seed / random seed.
        val_frac: validation fraction / val 비율.
        test_frac: test fraction / test 비율.
        stratify_by: list of column names to stratify on
            (e.g., ``["department"]``). None → simple random split.
            stratify 기준 column list. None 시 random split.

    Returns:
        DataFrame with ``caseid``, ``split`` columns.
        ``caseid``, ``split`` column 의 DataFrame.
    """
    import pandas as pd

    df = cases[["caseid"] + (stratify_by or [])].copy()
    if not (0.0 < val_frac < 1.0) or not (0.0 < test_frac < 1.0):
        raise ValueError(f"val_frac / test_frac must be in (0, 1), got {val_frac}, {test_frac}")
    if val_frac + test_frac >= 1.0:
        raise ValueError(f"val_frac + test_frac must be < 1, got {val_frac + test_frac}")

    rng = np.random.default_rng(seed)
    df["split"] = "train"

    if stratify_by:
        # stratified within each group / 각 group 안에서 stratified
        for _gkey, gdf in df.groupby(stratify_by):
            idx = gdf.index.to_numpy().copy()
            rng.shuffle(idx)
            n = len(idx)
            n_val = int(round(n * val_frac))
            n_test = int(round(n * test_frac))
            val_idx = idx[:n_val]
            test_idx = idx[n_val : n_val + n_test]
            df.loc[val_idx, "split"] = "val"
            df.loc[test_idx, "split"] = "test"
    else:
        idx = df.index.to_numpy().copy()
        rng.shuffle(idx)
        n = len(idx)
        n_val = int(round(n * val_frac))
        n_test = int(round(n * test_frac))
        df.loc[idx[:n_val], "split"] = "val"
        df.loc[idx[n_val : n_val + n_test], "split"] = "test"

    return df[["caseid", "split"]].reset_index(drop=True)


__all__ = ["make_splits"]
