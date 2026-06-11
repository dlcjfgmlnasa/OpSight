"""Multi-tick real-cohort benchmark (Sprint 7 follow-up).
Sprint 7 follow-up — 다중 tick × 실 cohort × Mock FM Tier 2 벤치.

Bridges the gap between:
  - smoke_llm.py (single sim-time snapshot, with real LLM)
  - test_e2e_100cases_tier2 (multi-tick, synthetic signals)
  - test_real_cohort_10cases_e2e (multi-tick, real signals, 5-tick × 60s = 5min)

This script: real signals × 5 diverse cases × 20 ticks × 30s = **10 min sim** per
case. Long enough for trigger 7 (periodic 5-min) to fire ≥ 1× per case and for
risk_history / quality_history to accumulate meaningful trajectory.

Goal: answer "do the 7 trigger rules fire meaningfully on REAL VitalDB data,
or does NaN burden in the induction phase kill trigger 4 (cross-modal)?"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

# Repo root on sys.path so `opsight.*` imports resolve when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opsight.graph import build_graph
from opsight.preprocessing import preprocess_signal_dict
from opsight.signal_stream import stream_from_full_signal
from opsight.sim_clock import SimClock
from opsight.state import AgentState
from opsight.trace import TraceWriter


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data" / "cohort" / "manifest.parquet"
REPORTS_DIR = REPO_ROOT / "reports"

PRIORITY_TRACKS = [
    "Solar8000/HR",
    "Solar8000/ART_MBP",
    "Solar8000/NIBP_MBP",
    "Solar8000/PLETH_SPO2",
    "Solar8000/ETCO2",
    "Solar8000/BT",
    "BIS/BIS",
]
TRACK_TO_ALIAS = {
    "Solar8000/HR": "HR",
    "Solar8000/ART_MBP": "ABP",
    "Solar8000/NIBP_MBP": "Solar8000/NIBP_MBP",
    "Solar8000/PLETH_SPO2": "SpO2",
    "Solar8000/ETCO2": "EtCO2",
    "Solar8000/BT": "BT",
    "BIS/BIS": "BIS",
}

# Yesterday's 5 diverse cases (see Sprint 7).
DEFAULT_CASES = [3, 4, 13, 66, 53]


def _load_real_case(case_id: int, interval_sec: float = 1.0) -> tuple[
    dict[str, torch.Tensor], list[str], float
]:
    import vitaldb

    vf = vitaldb.VitalFile(case_id, track_names=PRIORITY_TRACKS)
    df = vf.to_pandas(PRIORITY_TRACKS, interval=interval_sec)

    signal: dict[str, torch.Tensor] = {}
    modalities: list[str] = []
    for col in df.columns:
        arr = df[col].to_numpy(dtype=np.float64)
        if np.isnan(arr).all():
            continue
        alias = TRACK_TO_ALIAS.get(col, col)
        signal[alias] = torch.from_numpy(arr.astype(np.float32))
        modalities.append(alias)
    return signal, modalities, 1.0 / interval_sec


def _case_meta(case_id: int) -> dict[str, Any]:
    """Pull manifest metadata for a case (surgery_type / duration / age / asa)."""
    if not MANIFEST_PATH.exists():
        return {}
    m = pd.read_parquet(MANIFEST_PATH)
    row = m[m["case_id"] == case_id]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "surgery_type": str(r.get("surgery_type", "unknown")),
        "duration_min": float(r.get("op_duration_min", 0.0)),
        "age": float(r.get("age", 0.0)),
        "asa": float(r.get("asa", 0.0)),
    }


def _run_case(
    case_id: int,
    *,
    max_ticks: int,
    tick_sim_advance_s: float,
    trace_dir: Path,
) -> dict[str, Any]:
    meta = _case_meta(case_id)
    print(f"\n========== CASE {case_id}  ({meta.get('surgery_type','?')}, "
          f"{meta.get('duration_min',0):.0f}min, ASA{meta.get('asa',0):.0f}) "
          f"==========")

    t_load = time.perf_counter()
    signal, modalities, sr_hz = _load_real_case(case_id)
    print(f"[load] {len(next(iter(signal.values())))} samples × {len(signal)} "
          f"tracks in {time.perf_counter() - t_load:.1f}s")

    signal, prep_report = preprocess_signal_dict(signal, sampling_rate_hz=sr_hz)
    rates = {
        mod: float(rep["output_sampling_rate_hz"])
        for mod, rep in prep_report.per_modality.items()
    }
    stream = stream_from_full_signal(
        signal, sampling_rates_hz=rates, default_sampling_rate_hz=sr_hz
    )

    clock = SimClock(start_s=0.0)
    initial = AgentState(case_id=f"vitaldb-{case_id}", trace_id=f"multitick-{case_id}")

    trace_path = trace_dir / f"case_{case_id}.jsonl"
    t0 = time.perf_counter()
    with TraceWriter(trace_path, trace_id=initial.trace_id, case_id=initial.case_id) as tw:
        graph = build_graph(
            clock=clock, signal_stream=stream, modalities=modalities,
            max_ticks=max_ticks, tick_sim_advance_s=tick_sim_advance_s, trace=tw,
        )
        final = graph.invoke(initial, {"recursion_limit": 200})
    wall_s = time.perf_counter() - t0

    final_state = (
        final if isinstance(final, AgentState) else AgentState.model_validate(final)
    )

    # ── Aggregate per-case statistics ──
    hypo_risks = [s.risk for s in final_state.risk_history
                  if s.risk_type.startswith("hypotension")]
    arrest_risks = [s.risk for s in final_state.risk_history
                    if s.risk_type.startswith("arrest")]
    quality_by_mod: dict[str, list[float]] = {}
    for s in final_state.quality_history:
        quality_by_mod.setdefault(s.modality, []).append(s.score)

    trigger_counter: Counter[str] = Counter()
    for record in final_state.brief_history:
        # reason format: "hypotension_risk_gt_0.7 (risk=0.83)" — strip parenthetical
        key = record.trigger_reason.split(" ", 1)[0]
        trigger_counter[key] += 1

    tick_count = final_state.scratch.get("tick_count", 0)
    per_tick_ms = (wall_s * 1000.0 / tick_count) if tick_count else 0.0

    summary = {
        "case_id": case_id,
        "meta": meta,
        "modalities": modalities,
        "tick_count": int(tick_count),
        "sim_minutes_covered": float(final_state.sim_time_s / 60.0),
        "wall_s": round(wall_s, 2),
        "per_tick_ms": round(per_tick_ms, 1),
        "brief_count": len(final_state.brief_history),
        "trigger_reasons": dict(trigger_counter),
        "risk_hypo": _risk_stats(hypo_risks),
        "risk_arrest": _risk_stats(arrest_risks),
        "quality_by_modality": {
            mod: _risk_stats(scores) for mod, scores in quality_by_mod.items()
        },
    }
    _print_case(summary)
    return summary


def _risk_stats(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {"n": 0}
    arr = np.array(xs, dtype=float)
    return {
        "n": int(arr.size),
        "min": round(float(arr.min()), 3),
        "max": round(float(arr.max()), 3),
        "mean": round(float(arr.mean()), 3),
        "std": round(float(arr.std()), 3),
    }


def _print_case(s: dict[str, Any]) -> None:
    print(f"  ticks={s['tick_count']:>2}  "
          f"sim={s['sim_minutes_covered']:.1f}min  "
          f"wall={s['wall_s']:.1f}s  per-tick={s['per_tick_ms']:.0f}ms  "
          f"briefs={s['brief_count']}")
    if s["trigger_reasons"]:
        for k, v in sorted(s["trigger_reasons"].items(), key=lambda x: -x[1]):
            print(f"    · {k}: {v}")
    else:
        print(f"    · (no triggers fired)")
    hr = s["risk_hypo"]
    if hr["n"]:
        print(f"  hypo  : min={hr['min']} max={hr['max']} "
              f"mean={hr['mean']} std={hr['std']}  (n={hr['n']})")
    ar = s["risk_arrest"]
    if ar["n"]:
        print(f"  arrest: min={ar['min']} max={ar['max']} "
              f"mean={ar['mean']} std={ar['std']}  (n={ar['n']})")


def _aggregate(per_case: list[dict[str, Any]]) -> dict[str, Any]:
    total_briefs = sum(c["brief_count"] for c in per_case)
    total_ticks = sum(c["tick_count"] for c in per_case)
    trigger_total: Counter[str] = Counter()
    for c in per_case:
        trigger_total.update(c["trigger_reasons"])
    per_tick_ms_list = [c["per_tick_ms"] for c in per_case if c["per_tick_ms"]]
    p95 = float(np.percentile(per_tick_ms_list, 95)) if per_tick_ms_list else 0.0
    return {
        "n_cases": len(per_case),
        "total_ticks": total_ticks,
        "total_briefs": total_briefs,
        "p95_per_tick_ms": round(p95, 1),
        "trigger_reasons_total": dict(trigger_total),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-ids", type=int, nargs="+", default=DEFAULT_CASES,
                        help=f"case ids (default: {DEFAULT_CASES})")
    parser.add_argument("--max-ticks", type=int, default=20,
                        help="ticks per case (default 20)")
    parser.add_argument("--tick-sec", type=float, default=30.0,
                        help="sim seconds per tick (default 30)")
    args = parser.parse_args()

    # UTF-8 console on Windows for Korean output.
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace_dir = REPORTS_DIR / f"multitick_{stamp}_traces"
    trace_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== OpSight multi-tick real-cohort benchmark ===")
    print(f"cases     = {args.case_ids}")
    print(f"max_ticks = {args.max_ticks}")
    print(f"tick_sec  = {args.tick_sec}  → sim ≈ "
          f"{args.max_ticks * args.tick_sec / 60.0:.1f} min/case")
    print(f"trace dir = {trace_dir}")

    per_case: list[dict[str, Any]] = []
    for cid in args.case_ids:
        try:
            s = _run_case(
                cid,
                max_ticks=args.max_ticks,
                tick_sim_advance_s=args.tick_sec,
                trace_dir=trace_dir,
            )
            per_case.append(s)
        except Exception as exc:
            print(f"  !! case {cid} failed: {exc!r}")

    agg = _aggregate(per_case)

    print(f"\n========== AGGREGATE ({agg['n_cases']} case) ==========")
    print(f"  total ticks       : {agg['total_ticks']}")
    print(f"  total briefs      : {agg['total_briefs']}")
    print(f"  p95 per-tick ms   : {agg['p95_per_tick_ms']}")
    print(f"  trigger reasons   :")
    for k, v in sorted(agg["trigger_reasons_total"].items(), key=lambda x: -x[1]):
        print(f"    · {k}: {v}")
    if not agg["trigger_reasons_total"]:
        print(f"    · (none)")

    report = {
        "schema": "opsight.multitick_real_cohort.v1",
        "generated_at": stamp,
        "params": {
            "case_ids": list(args.case_ids),
            "max_ticks": args.max_ticks,
            "tick_sim_advance_s": args.tick_sec,
        },
        "aggregate": agg,
        "per_case": per_case,
    }
    report_path = REPORTS_DIR / f"multitick_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"\nreport written: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
