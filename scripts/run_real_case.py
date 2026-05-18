"""Run dual-mode OpSight graph on a real VitalDB case (a-option script).
실제 VitalDB case 로 dual-mode OpSight graph 실행 (a-option).

End-to-end demo:
  1. manifest 에서 case_id 선택 (or CLI arg)
  2. vitaldb.VitalFile 로 priority track load
  3. pandas DataFrame → dict[str, torch.Tensor] 변환 + modality alias rename
  4. Mock FM (rule-based; matching sampling_rate_hz) 빌드
  5. dual-mode graph invoke (Shallow + Deep)
  6. summary 출력 + trace JSONL 저장

Usage:
  python scripts/run_real_case.py --case-id 1 --max-ticks 10
  python scripts/run_real_case.py --case-id 1 --interval 0.5 --max-ticks 20

Tested 2026-05-18 Sprint 5 — `docs/findings/real_case_run_findings.md` 참조.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch

# Force UTF-8 stdout on Windows (default cp949 chokes on '—' / 한글).
# Windows 콘솔 기본 cp949 가 한글 / em-dash 등에서 실패 → UTF-8 강제.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

# Repo root on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opsight.fm.factory import create_fm
from opsight.graph import build_graph
from opsight.preprocessing import preprocess_signal_dict
from opsight.signal_stream import stream_from_full_signal
from opsight.sim_clock import SimClock
from opsight.state import AgentState
from opsight.trace import TraceWriter


# ── Track selection — VitalDB priority subset (catalog §3.1) ──

# Solar8000 numerics — robust @ ~1Hz, almost universal across cohort.
DEFAULT_TRACKS = [
    "Solar8000/HR",            # → HR
    "Solar8000/ART_MBP",       # → ABP (primary)
    "Solar8000/NIBP_MBP",      # → ABP (fallback)
    "Solar8000/PLETH_SPO2",    # → SpO2
    "Solar8000/ETCO2",         # → EtCO2
    "Solar8000/BT",            # → core_temp
    "BIS/BIS",                 # → BIS (if available)
]

# VitalDB track name → opsight signal dict key (modality alias)
# opsight/fm/mock_rule_based.py::_*_ALIASES 와 일치
TRACK_TO_ALIAS = {
    "Solar8000/HR": "HR",
    "Solar8000/ART_MBP": "ABP",
    "Solar8000/NIBP_MBP": "Solar8000/NIBP_MBP",  # fallback path
    "Solar8000/PLETH_SPO2": "SpO2",
    "Solar8000/ETCO2": "EtCO2",
    "Solar8000/BT": "BT",
    "BIS/BIS": "BIS",
    "SNUADC/PLETH": "PPG",
    "SNUADC/ECG_II": "ECG_II",
    "SNUADC/ART": "SNUADC/ART",  # passthrough for ABP_INVASIVE
}


def load_vitaldb_case(
    case_id: int, tracks: list[str], interval_sec: float
) -> tuple[pd.DataFrame, float]:
    """Load a VitalDB case → DataFrame. Returns (df, effective_sampling_rate_hz).
    VitalDB case → DataFrame.
    """
    import vitaldb

    t0 = time.time()
    vf = vitaldb.VitalFile(case_id, track_names=tracks)
    df = vf.to_pandas(tracks, interval=interval_sec)
    elapsed = time.time() - t0
    print(f"[load] case {case_id}: {df.shape[0]} samples × {df.shape[1]} tracks "
          f"({elapsed:.1f}s, interval={interval_sec}s)")
    sr_hz = 1.0 / interval_sec
    return df, sr_hz


def df_to_signal_dict(df: pd.DataFrame) -> tuple[dict[str, torch.Tensor], list[str]]:
    """Convert VitalDB DataFrame → signal dict + modalities list.
    Filters out columns that are entirely NaN.
    Modality alias rename per TRACK_TO_ALIAS.
    """
    signal: dict[str, torch.Tensor] = {}
    modalities: list[str] = []
    for col in df.columns:
        arr = df[col].to_numpy(dtype=np.float64)
        if np.isnan(arr).all():
            continue  # skip fully-NaN tracks
        # NaN ratio diag
        nan_ratio = float(np.mean(np.isnan(arr)))
        alias = TRACK_TO_ALIAS.get(col, col)
        signal[alias] = torch.from_numpy(arr.astype(np.float32))
        modalities.append(alias)
        mean_val = float(np.nanmean(arr))
        mean_str = f"{mean_val:.2f}" if not np.isnan(mean_val) else "NaN"
        print(f"  [track] {col} → {alias!r}: "
              f"n={len(arr)}, nan={nan_ratio*100:.1f}%, mean={mean_str}")
    return signal, modalities


def run_case(args: argparse.Namespace) -> dict:
    """Main entry — return summary dict."""
    # 1. Load case
    print(f"\n=== Run real VitalDB case_id={args.case_id} ===")
    df, sr_hz = load_vitaldb_case(args.case_id, DEFAULT_TRACKS, args.interval)

    # 2. Convert to signal dict
    signal, modalities = df_to_signal_dict(df)
    if not signal:
        print(f"[error] all tracks fully NaN for case {args.case_id}")
        return {"case_id": args.case_id, "error": "all_nan"}

    print(f"\n[modalities loaded] {modalities}")
    print(f"[effective sampling rate] {sr_hz} Hz (interval={args.interval}s)")

    # 2.5 Preprocess — artifact clip + NaN-gap fill (Issue #1/#4)
    if args.preprocess:
        signal, prep_report = preprocess_signal_dict(signal, sampling_rate_hz=sr_hz)
        print(f"\n[preprocess] artifact clip + NaN-gap fill:")
        for mod_name, rep in prep_report.per_modality.items():
            clipped = rep["n_below_range"] + rep["n_above_range"]
            print(f"  {mod_name}: clipped={clipped} "
                  f"({rep['ratio_clipped']*100:.2f}%), "
                  f"gap_filled={rep['n_nan_gap_filled']}, "
                  f"left_nan={rep['n_nan_left']}")
        if prep_report.skipped_modalities:
            print(f"  [skipped no-config] {prep_report.skipped_modalities}")
    else:
        prep_report = None
        print(f"\n[preprocess] DISABLED (--no-preprocess). Raw signal used.")

    # 3. Build FM with matching sampling rate
    fm_cfg = {
        "fm": {
            "implementation": "mock_rule_based",
            "config": {
                "seed": 42,
                "sampling_rate_hz": sr_hz,  # CRITICAL: match real sampling
                "noise_pct": 0.0,
            },
        }
    }
    fm = create_fm(fm_cfg)
    print(f"[FM] mock_rule_based (sampling_rate_hz={sr_hz})")

    # 4. Build graph
    clock = SimClock(start_s=0.0)
    runs_dir = REPO_ROOT / "data" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_path = runs_dir / f"case{args.case_id}_{stamp}.jsonl"
    summary_path = runs_dir / f"case{args.case_id}_{stamp}.summary.json"

    initial = AgentState(
        case_id=f"vitaldb-{args.case_id}",
        trace_id=f"real-{args.case_id}-{stamp}",
    )

    # Streaming wiring (Sprint 6, Issue #2): graph sees signal up to clock.now_s only.
    # Per-modality output rate after preprocessing (waveform → 100Hz, numerics → native).
    # Preprocessing 후 modality 별 output rate (waveform→100Hz, numerics→native) 반영.
    rates_for_stream: dict[str, float] = {}
    if prep_report is not None:
        for mod, rep in prep_report.per_modality.items():
            rates_for_stream[mod] = float(rep["output_sampling_rate_hz"])
    stream = stream_from_full_signal(
        signal, sampling_rates_hz=rates_for_stream,
        default_sampling_rate_hz=sr_hz,
    )
    with TraceWriter(trace_path, trace_id=initial.trace_id, case_id=initial.case_id) as tw:
        graph = build_graph(
            fm=fm,
            clock=clock,
            signal_stream=stream,
            modalities=modalities,
            max_ticks=args.max_ticks,
            tick_sim_advance_s=args.tick_sim_advance_s,
            trace=tw,
        )
        print(f"\n[graph] invoke (max_ticks={args.max_ticks}, "
              f"tick={args.tick_sim_advance_s}s) ...")
        t0 = time.perf_counter()
        final = graph.invoke(initial, {"recursion_limit": 200})
        wall = time.perf_counter() - t0

    final_state = (
        final if isinstance(final, AgentState)
        else AgentState.model_validate(final)
    )

    # 5. Summary
    n_ticks = final_state.scratch.get("tick_count", 0)
    n_briefs = len(final_state.brief_history)
    trigger_reasons: dict[str, int] = {}
    for r in final_state.brief_history:
        key = r.trigger_reason.split(" ", 1)[0]
        trigger_reasons[key] = trigger_reasons.get(key, 0) + 1

    summary = {
        "case_id": args.case_id,
        "trace_path": str(trace_path),
        "interval_sec": args.interval,
        "sampling_rate_hz": sr_hz,
        "modalities": modalities,
        "case_duration_total_sec": float(df.shape[0] * args.interval),
        "n_ticks_executed": n_ticks,
        "sim_time_final_s": final_state.sim_time_s,
        "wall_clock_s": wall,
        "n_deep_briefs": n_briefs,
        "trigger_reasons": trigger_reasons,
        "shallow_narration_last": final_state.scratch.get("narration", ""),
        "brief_sample_first": (
            final_state.brief_history[0].sections if n_briefs else None
        ),
        "preprocess_enabled": args.preprocess,
        "preprocess_report": (
            {mod: rep for mod, rep in prep_report.per_modality.items()}
            if prep_report is not None else None
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\n=== Summary ===")
    print(f"  ticks executed     : {n_ticks}")
    print(f"  sim_time final     : {final_state.sim_time_s:.0f} s ({final_state.sim_time_s/60:.1f} min)")
    print(f"  wall clock         : {wall*1000:.0f} ms")
    print(f"  deep briefs fired  : {n_briefs}")
    for reason, count in trigger_reasons.items():
        print(f"    - {reason}: {count}")
    print(f"  trace              : {trace_path}")
    print(f"  summary JSON       : {summary_path}")

    if n_briefs and final_state.brief_history[0].sections:
        first_brief = final_state.brief_history[0]
        print(f"\n=== First deep brief (trigger: {first_brief.trigger_reason}) ===")
        for sec, body in first_brief.sections.items():
            short = body[:120] + ("..." if len(body) > 120 else "")
            print(f"  [{sec}] {short}")

    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Run dual-mode graph on a real VitalDB case")
    ap.add_argument("--case-id", type=int, default=1,
                    help="VitalDB caseid (must exist in manifest)")
    ap.add_argument("--max-ticks", type=int, default=10,
                    help="number of shallow ticks to run (default 10)")
    ap.add_argument("--tick-sim-advance-s", type=float, default=30.0,
                    help="seconds each tick advances (default 30)")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="vitaldb to_pandas interval seconds (default 1.0)")
    ap.add_argument("--no-preprocess", dest="preprocess", action="store_false",
                    help="disable preprocessing (artifact clip + NaN-gap fill)")
    ap.set_defaults(preprocess=True)
    args = ap.parse_args()

    # Validate caseid in manifest
    manifest_path = REPO_ROOT / "data" / "cohort" / "manifest.parquet"
    if manifest_path.exists():
        manifest = pd.read_parquet(manifest_path)
        if args.case_id not in manifest["case_id"].values:
            print(f"[warn] case_id={args.case_id} not in manifest "
                  f"(manifest has {len(manifest)} cases). Continuing anyway.")
        else:
            row = manifest[manifest["case_id"] == args.case_id].iloc[0]
            print(f"[manifest] case {args.case_id}: surgery_type={row['surgery_type']}, "
                  f"op_duration_min={row['op_duration_min']:.1f}, age={row['age']:.0f}, "
                  f"abp_invasive={row['abp_invasive']}, abp_primary={row['abp_primary']}")

    summary = run_case(args)
    if "error" in summary:
        sys.exit(1)


if __name__ == "__main__":
    main()
