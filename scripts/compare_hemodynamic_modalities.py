"""Compare hemodynamic modality availability (ABP vs PPG vs ECG) per case.
모달리티 가용성 비교: ABP (invasive) vs PPG (PLETH) vs ECG.

Answers: "When ABP is missing, do we have PPG/ECG to fall back on?"
"ABP 없을 때 PPG/ECG 가 실제로 존재하는가?"

Usage::
    python scripts/compare_hemodynamic_modalities.py
    python scripts/compare_hemodynamic_modalities.py --case-ids 3 4 13 20 53 66
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.live_view import _load_real_case, _window_finite_ratio

DEFAULT_CASES = [3, 4, 13, 20, 53, 66, 100, 200, 500, 1000]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-ids", type=int, nargs="+", default=DEFAULT_CASES)
    args = parser.parse_args()
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    rows = []
    for cid in args.case_ids:
        try:
            signal, modalities, sr_hz = _load_real_case(cid)
        except Exception as e:
            print(f"case {cid}: load failed ({e!r})")
            continue

        row = {"case_id": cid}
        for proxy in ("ABP", "PPG", "ECG"):
            if proxy not in signal:
                row[f"{proxy}_first_s"] = None
                row[f"{proxy}_pct"] = 0.0
                row[f"{proxy}_t30s_r"] = 0.0
                row[f"{proxy}_t300s_r"] = 0.0
                continue
            arr = signal[proxy]
            fin = torch.isfinite(arr)
            if not fin.any():
                row[f"{proxy}_first_s"] = None
                row[f"{proxy}_pct"] = 0.0
                row[f"{proxy}_t30s_r"] = 0.0
                row[f"{proxy}_t300s_r"] = 0.0
                continue
            row[f"{proxy}_first_s"] = int(fin.nonzero()[0].item())
            row[f"{proxy}_pct"] = float(fin.float().mean()) * 100
            row[f"{proxy}_t30s_r"] = _window_finite_ratio(arr, 30.0, sr_hz)
            row[f"{proxy}_t300s_r"] = _window_finite_ratio(arr, 300.0, sr_hz)
        rows.append(row)

    # Pretty print
    print(f"\n{'='*120}")
    print(f"{'case':>6}  "
          f"{'ABP first':>11}  {'ABP %':>6}  {'@30s':>5}  {'@5min':>6}  | "
          f"{'PPG first':>11}  {'PPG %':>6}  {'@30s':>5}  {'@5min':>6}  | "
          f"{'ECG first':>11}  {'ECG %':>6}")
    print(f"{'-'*120}")
    for r in rows:
        def fmt_time(s: int | None) -> str:
            if s is None:
                return "MISSING"
            return f"{s//60:>3}:{s%60:02d}"
        def fmt_pct(p: float) -> str:
            return f"{p:>5.1f}%"
        def fmt_r(r: float) -> str:
            return f"{r:.2f}"
        print(
            f"{r['case_id']:>6}  "
            f"{fmt_time(r['ABP_first_s']):>11}  "
            f"{fmt_pct(r['ABP_pct']):>6}  "
            f"{fmt_r(r['ABP_t30s_r']):>5}  "
            f"{fmt_r(r['ABP_t300s_r']):>6}  | "
            f"{fmt_time(r['PPG_first_s']):>11}  "
            f"{fmt_pct(r['PPG_pct']):>6}  "
            f"{fmt_r(r['PPG_t30s_r']):>5}  "
            f"{fmt_r(r['PPG_t300s_r']):>6}  | "
            f"{fmt_time(r['ECG_first_s']):>11}  "
            f"{fmt_pct(r['ECG_pct']):>6}"
        )

    print(f"\n{'='*120}")
    print("Interpretation:")
    print("  @30s   = window finite ratio at sim_time=30s  (very early induction)")
    print("  @5min  = window finite ratio at sim_time=5min (typical post-induction)")
    print("  MISSING = modality not in case at all (or all-NaN — usually means no sensor)")
    print()
    # Aggregate: how many cases have PPG when ABP is missing/late?
    abp_late = sum(1 for r in rows
                   if r["ABP_first_s"] is None or r["ABP_first_s"] > 30)
    ppg_present_early = sum(
        1 for r in rows
        if r["PPG_first_s"] is not None and r["PPG_first_s"] <= 30
        and (r["ABP_first_s"] is None or r["ABP_first_s"] > 30)
    )
    ecg_present_early = sum(
        1 for r in rows
        if r["ECG_first_s"] is not None and r["ECG_first_s"] <= 30
        and (r["ABP_first_s"] is None or r["ABP_first_s"] > 30)
    )
    print(f"Cases with ABP missing or late (>30s):  {abp_late} / {len(rows)}")
    print(f"   ...of which PPG present at ≤30s:    {ppg_present_early}")
    print(f"   ...of which ECG present at ≤30s:    {ecg_present_early}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
