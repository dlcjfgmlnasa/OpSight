"""Audit preprocessing impact per modality on a real VitalDB case.
실 VitalDB case 의 modality 별 preprocessing 영향 audit.

Shows for each modality:
  - raw finite ratio (from VitalDB load)
  - post-preprocessing finite ratio
  - source/output sampling rate
  - whether preprocessing rejected/skipped/clipped/filled/resampled it
  - alias resolution (live_view alias → signal_config canonical key)

Usage::

    python scripts/preprocess_audit.py --case-id 13
    python scripts/preprocess_audit.py --case-id 3 4 13 20 53 66
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

from opsight.preprocessing import preprocess_signal_dict
from opsight.preprocessing.signal_config import config_for_modality
from scripts.live_view import _load_real_case


def audit_case(case_id: int) -> None:
    signal_raw, modalities, sr_hz = _load_real_case(case_id)
    n_raw_samples = next(iter(signal_raw.values())).shape[0]
    print(f"\n===== case {case_id}  ({n_raw_samples} samples × {len(modalities)} tracks @ {sr_hz} Hz) =====")
    print(f"{'modality':<25} {'cfg key':<12} {'is_wave':<7} "
          f"{'raw fin%':>9} {'clip%':>6} {'gap_max':>8} "
          f"{'out fin%':>9} {'out Hz':>7}")
    print("-" * 100)

    # Pre-compute raw finite ratios on RAW signal (before preprocess)
    raw_finite = {}
    for name, t in signal_raw.items():
        arr = t.detach().cpu().numpy()
        raw_finite[name] = float(np.isfinite(arr).mean()) * 100

    # Now preprocess (this mutates a copy)
    signal_pp, report = preprocess_signal_dict(signal_raw, sampling_rate_hz=sr_hz)

    for name in modalities:
        cfg = config_for_modality(name)
        if cfg is None:
            print(f"{name:<25} {'(none)':<12} {'-':<7} "
                  f"{raw_finite[name]:>8.1f}% {'SKIP':>6} {'SKIP':>8} "
                  f"{raw_finite[name]:>8.1f}% {sr_hz:>6.1f}")
            continue
        rep = report.per_modality[name]
        # Compute post-preprocessing finite
        out_arr = signal_pp[name].detach().cpu().numpy()
        out_fin_pct = float(np.isfinite(out_arr).mean()) * 100
        print(f"{name:<25} {cfg.name:<12} "
              f"{('Y' if cfg.is_waveform else 'n'):<7} "
              f"{raw_finite[name]:>8.1f}% "
              f"{rep['ratio_clipped']*100:>5.2f}% "
              f"{rep['max_gap_samples']:>8} "
              f"{out_fin_pct:>8.1f}% "
              f"{rep['output_sampling_rate_hz']:>6.1f}")

    if report.skipped_modalities:
        print(f"  ⚠ skipped (no config): {report.skipped_modalities}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", type=int, nargs="+", default=[3, 4, 13, 20, 53, 66])
    args = parser.parse_args()
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    for cid in args.case_id:
        audit_case(cid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
