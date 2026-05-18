"""
00 — VitalDB Quick Exploration (Pre-Phase 3)

Purpose: validate VitalAgent design assumptions against real VitalDB metadata.
Scope: 5 quick analyses (cases, surgery types, demographics, duration, modality).
Out of scope: deep statistics — that lives in plan_1.1 (Stage 1).

Outputs:
- Markdown findings file at docs/findings/pre_phase3_findings.md (rebuilt each run)
- Cached CSV at docs/notebooks/_cache/cases.csv and trks.csv so the notebook companion
  can read them without re-hitting the network.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vitaldb

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / "_cache"
CACHE.mkdir(exist_ok=True)
FINDINGS = ROOT / "findings" / "pre_phase3_findings.md"


# Modalities the project plan explicitly lists as priority (project_brief §4)
PRIORITY_TRACKS = [
    "SNUADC/ART",
    "SNUADC/PLETH",
    "SNUADC/ECG_II",
    "Solar8000/ART_MBP",
    "Solar8000/NIBP_MBP",
    "BIS/EEG1_WAV",
    "Primus/SEVOFLURANE_VOL",
    "Orchestra/PPF20_CE",
]


def fmt_pct(n: int, total: int) -> str:
    return f"{n:,} ({100*n/total:.1f}%)" if total else f"{n:,} (n/a)"


def load_metadata() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull case-level clinical data + track listing. Cache to CSV."""
    cases_csv = CACHE / "cases.csv"
    trks_csv = CACHE / "trks.csv"

    if cases_csv.exists():
        cases = pd.read_csv(cases_csv)
    else:
        cases = vitaldb.load_clinical_data()
        cases.to_csv(cases_csv, index=False)

    if trks_csv.exists():
        trks = pd.read_csv(trks_csv)
    else:
        # vitaldb.tracklist holds the (caseid, tname) pairs;
        # we prefer the official API endpoint for trks.
        try:
            trks = pd.read_csv("https://api.vitaldb.net/trks")
        except Exception as e:
            print(f"WARN: trks endpoint failed ({e}); using vitaldb.tracklist", file=sys.stderr)
            trks = pd.DataFrame(vitaldb.tracklist, columns=["caseid", "tname"])
        trks.to_csv(trks_csv, index=False)

    return cases, trks


def analysis_1_total(cases: pd.DataFrame) -> dict[str, Any]:
    n = len(cases)
    cols = list(cases.columns)
    return {
        "n_cases": n,
        "n_columns": len(cols),
        "columns": cols,
        "first5": cases.head(5).to_dict(orient="records"),
    }


def analysis_2_surgery(cases: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "opname" in cases.columns:
        s = cases["opname"].dropna()
        out["opname_unique"] = int(s.nunique())
        out["opname_top20"] = s.value_counts().head(20).to_dict()
    if "department" in cases.columns:
        s = cases["department"].dropna()
        out["department_dist"] = s.value_counts().to_dict()
    if "optype" in cases.columns:
        s = cases["optype"].dropna()
        out["optype_dist"] = s.value_counts().to_dict()
    if "approach" in cases.columns:
        s = cases["approach"].dropna()
        out["approach_dist"] = s.value_counts().head(10).to_dict()
    return out


def analysis_3_demographics(cases: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in ["age", "sex", "weight", "height", "bmi", "asa"]:
        if col not in cases.columns:
            continue
        s = cases[col]
        if pd.api.types.is_numeric_dtype(s):
            d = s.dropna()
            out[col] = {
                "n": int(len(d)),
                "missing": int(s.isna().sum()),
                "mean": float(d.mean()) if len(d) else None,
                "std": float(d.std()) if len(d) else None,
                "p5": float(d.quantile(0.05)) if len(d) else None,
                "p50": float(d.quantile(0.50)) if len(d) else None,
                "p95": float(d.quantile(0.95)) if len(d) else None,
                "min": float(d.min()) if len(d) else None,
                "max": float(d.max()) if len(d) else None,
            }
        else:
            out[col] = s.value_counts(dropna=False).to_dict()
    # BMI computed if not present and we have weight+height
    if "bmi" not in cases.columns and {"weight", "height"} <= set(cases.columns):
        h = cases["height"] / 100.0  # cm → m
        bmi = cases["weight"] / (h * h)
        d = bmi.replace([np.inf, -np.inf], np.nan).dropna()
        out["bmi_computed"] = {
            "n": int(len(d)),
            "mean": float(d.mean()),
            "std": float(d.std()),
            "p5": float(d.quantile(0.05)),
            "p50": float(d.quantile(0.50)),
            "p95": float(d.quantile(0.95)),
        }
    return out


def analysis_4_duration(cases: pd.DataFrame) -> dict[str, Any]:
    """Surgery duration based on opstart/opend (seconds)."""
    cols = set(cases.columns)
    if not {"opstart", "opend"}.issubset(cols):
        return {"note": "opstart/opend not present", "available_cols": sorted(cols)}
    dur_sec = cases["opend"] - cases["opstart"]
    dur_min = dur_sec / 60.0
    d = dur_min.replace([np.inf, -np.inf], np.nan).dropna()
    out = {
        "n_with_duration": int(len(d)),
        "missing": int(dur_min.isna().sum()),
        "mean_min": float(d.mean()),
        "std_min": float(d.std()),
        "p5_min": float(d.quantile(0.05)),
        "p25_min": float(d.quantile(0.25)),
        "p50_min": float(d.quantile(0.50)),
        "p75_min": float(d.quantile(0.75)),
        "p95_min": float(d.quantile(0.95)),
        "min_min": float(d.min()),
        "max_min": float(d.max()),
        "bin_lt30": int((d < 30).sum()),
        "bin_30_60": int(((d >= 30) & (d < 60)).sum()),
        "bin_60_120": int(((d >= 60) & (d < 120)).sum()),
        "bin_120_240": int(((d >= 120) & (d < 240)).sum()),
        "bin_ge240": int((d >= 240).sum()),
        "total_for_bins": int(len(d)),
    }
    # Optype intersection: non-cardiac filter
    if "optype" in cases.columns:
        for optype in cases["optype"].dropna().unique():
            sel = dur_min[cases["optype"] == optype].dropna()
            if len(sel) >= 50:
                out[f"by_optype__{optype}__median_min"] = float(sel.quantile(0.50))
                out[f"by_optype__{optype}__lt30_count"] = int((sel < 30).sum())
                out[f"by_optype__{optype}__n"] = int(len(sel))
    return out


def analysis_5_modalities(cases: pd.DataFrame, trks: pd.DataFrame) -> dict[str, Any]:
    """For each priority track, what fraction of cases have at least one occurrence?"""
    out: dict[str, Any] = {"priority_tracks": PRIORITY_TRACKS}
    n_total = len(cases)

    # Build set of caseids per track
    per_track = trks.groupby("tname")["caseid"].nunique()
    out["track_listing_size"] = int(len(per_track))
    out["track_total_caseids"] = int(trks["caseid"].nunique())

    # Priority availability
    avail = {}
    for t in PRIORITY_TRACKS:
        n = int(per_track.get(t, 0))
        avail[t] = {"n_cases": n, "pct_of_total_cases": (n / n_total * 100) if n_total else None}
    out["priority_availability"] = avail

    # Cross-tab: ABP presence (any of SNUADC/ART, Solar8000/ART_MBP) vs cohort
    case_to_tracks = trks.groupby("caseid")["tname"].agg(set)
    has_abp_invasive = case_to_tracks.apply(lambda s: "SNUADC/ART" in s)
    has_abp_numeric = case_to_tracks.apply(lambda s: "Solar8000/ART_MBP" in s)
    has_ppg = case_to_tracks.apply(lambda s: "SNUADC/PLETH" in s)
    has_ecg2 = case_to_tracks.apply(lambda s: "SNUADC/ECG_II" in s)
    has_nibp = case_to_tracks.apply(lambda s: "Solar8000/NIBP_MBP" in s)
    has_bis = case_to_tracks.apply(lambda s: "BIS/EEG1_WAV" in s)
    has_sevo = case_to_tracks.apply(lambda s: "Primus/SEVOFLURANE_VOL" in s)
    has_ppf = case_to_tracks.apply(lambda s: "Orchestra/PPF20_CE" in s)

    n_with_any_track = int(len(case_to_tracks))
    out["n_cases_in_trk_list"] = n_with_any_track
    out["abp_invasive_pct"] = float(has_abp_invasive.mean() * 100)
    out["abp_numeric_pct"] = float(has_abp_numeric.mean() * 100)
    out["ppg_pct"] = float(has_ppg.mean() * 100)
    out["ecg2_pct"] = float(has_ecg2.mean() * 100)
    out["nibp_pct"] = float(has_nibp.mean() * 100)
    out["bis_pct"] = float(has_bis.mean() * 100)
    out["sevo_pct"] = float(has_sevo.mean() * 100)
    out["ppf_pct"] = float(has_ppf.mean() * 100)

    # ABP absent (the modality-agnostic narrative)
    has_any_abp = has_abp_invasive | has_abp_numeric
    out["abp_any_pct"] = float(has_any_abp.mean() * 100)
    out["abp_absent_pct"] = float((~has_any_abp).mean() * 100)
    out["abp_absent_n"] = int((~has_any_abp).sum())

    # Modality combo: ECG II AND PLETH AND ABP-something
    triplet = has_ecg2 & has_ppg & has_any_abp
    out["triplet_ecg_ppg_abp_pct"] = float(triplet.mean() * 100)

    return out


def render(report: dict[str, Any]) -> str:
    """Render the findings report as Markdown."""
    lines: list[str] = []
    L = lines.append

    L("# Pre-Phase 3 — VitalDB Quick Exploration: Findings")
    L("")
    L(f"> Generated by `docs/notebooks/00_vitaldb_quick_exploration.py` on real VitalDB metadata.")
    L(f"> Cache directory: `docs/notebooks/_cache/`.")
    L(f"> vitaldb package: {report['env']['vitaldb_version']}, Python {report['env']['python']}.")
    L("")

    # 1. Total cases
    a = report["a1_total"]
    L("## 1. Total case loading")
    L("")
    L(f"- **n_cases**: {a['n_cases']:,}")
    L(f"- **n_columns**: {a['n_columns']}")
    L(f"- Brief §4 assumption: **6,388 cases** (non-cardiac surgery)")
    delta = a["n_cases"] - 6388
    L(f"- Δ vs brief: **{delta:+,}** ({'matches' if delta == 0 else 'differs'})")
    L(f"- Columns: `{', '.join(a['columns'])}`")
    L("")

    # 2. Surgery types
    a = report["a2_surgery"]
    L("## 2. Surgery type distribution")
    L("")
    if "optype_dist" in a:
        L("### `optype` distribution")
        L("| optype | n |")
        L("|--------|---|")
        for k, v in a["optype_dist"].items():
            L(f"| {k} | {int(v):,} |")
        L("")
    if "department_dist" in a:
        L("### `department` distribution")
        L("| department | n |")
        L("|------------|---|")
        for k, v in a["department_dist"].items():
            L(f"| {k} | {int(v):,} |")
        L("")
    if "opname_unique" in a:
        L(f"### `opname` — unique procedures: **{a['opname_unique']:,}**")
        L("")
        L("Top 20 by frequency:")
        L("")
        L("| opname | n |")
        L("|--------|---|")
        for k, v in a["opname_top20"].items():
            L(f"| {k} | {int(v):,} |")
        L("")
    if "approach_dist" in a:
        L("### `approach` (top 10)")
        L("| approach | n |")
        L("|----------|---|")
        for k, v in a["approach_dist"].items():
            L(f"| {k} | {int(v):,} |")
        L("")

    # 3. Demographics
    a = report["a3_demographics"]
    L("## 3. Demographics")
    L("")
    L("| field | n | missing | mean ± std | p5 / p50 / p95 | min / max |")
    L("|-------|---|---------|------------|----------------|-----------|")
    for field in ["age", "weight", "height", "bmi", "bmi_computed", "asa"]:
        d = a.get(field)
        if not isinstance(d, dict) or "mean" not in d:
            continue
        mean = d.get("mean"); std = d.get("std")
        p5 = d.get("p5"); p50 = d.get("p50"); p95 = d.get("p95")
        mn = d.get("min"); mx = d.get("max")
        L(f"| {field} | {d.get('n')} | {d.get('missing','-')} | "
          f"{mean:.1f} ± {std:.1f} | "
          f"{p5:.1f} / {p50:.1f} / {p95:.1f} | "
          f"{mn:.1f} / {mx:.1f} |")
    L("")
    if "sex" in a and isinstance(a["sex"], dict):
        L("### `sex` counts")
        L("| sex | n |")
        L("|-----|---|")
        for k, v in a["sex"].items():
            L(f"| {k} | {int(v):,} |")
        L("")

    # 4. Duration
    a = report["a4_duration"]
    L("## 4. Surgery duration")
    L("")
    if "note" in a:
        L(f"> {a['note']}")
        L("")
    else:
        n = a["n_with_duration"]
        L(f"- **n with duration**: {n:,} (missing: {a['missing']:,})")
        L(f"- **mean ± std**: {a['mean_min']:.1f} ± {a['std_min']:.1f} min")
        L(f"- **percentiles** (min): p5={a['p5_min']:.1f}, p25={a['p25_min']:.1f}, "
          f"p50={a['p50_min']:.1f}, p75={a['p75_min']:.1f}, p95={a['p95_min']:.1f}")
        L(f"- **range**: {a['min_min']:.1f} – {a['max_min']:.1f} min")
        L("")
        L("### Duration bins")
        L("| bin | n | pct |")
        L("|-----|---|-----|")
        for label, key in [
            ("< 30 min", "bin_lt30"),
            ("30–60 min", "bin_30_60"),
            ("60–120 min", "bin_60_120"),
            ("120–240 min", "bin_120_240"),
            ("≥ 240 min", "bin_ge240"),
        ]:
            v = a[key]; total = a["total_for_bins"]
            L(f"| {label} | {v:,} | {fmt_pct(v, total).split(' ')[1]} |")
        L("")
        L(f"- Cohort exclusion rule **수술시간 < 30분 exclude** would drop **{a['bin_lt30']:,} cases**.")
        L("")

    # 5. Modality
    a = report["a5_modality"]
    L("## 5. Modality availability matrix (priority tracks)")
    L("")
    L(f"- Total cases in metadata: {report['a1_total']['n_cases']:,}")
    L(f"- Cases that appear in `trks` listing: {a['n_cases_in_trk_list']:,}")
    L(f"- Unique track names in DB: {a['track_listing_size']:,}")
    L("")
    L("### Priority track availability (% of cases with at least one occurrence in trks)")
    L("| track | n_cases | pct |")
    L("|-------|---------|-----|")
    for t, d in a["priority_availability"].items():
        n = d["n_cases"]; pct = d["pct_of_total_cases"]
        pct_s = f"{pct:.1f}%" if pct is not None else "n/a"
        L(f"| {t} | {n:,} | {pct_s} |")
    L("")
    L("### Key derived availability")
    L("| modality | % cases |")
    L("|----------|---------|")
    L(f"| ABP (invasive, `SNUADC/ART`) | {a['abp_invasive_pct']:.1f}% |")
    L(f"| ABP (numeric, `Solar8000/ART_MBP`) | {a['abp_numeric_pct']:.1f}% |")
    L(f"| ABP (any of the two) | {a['abp_any_pct']:.1f}% |")
    L(f"| **ABP absent (both missing)** | **{a['abp_absent_pct']:.1f}%** ({a['abp_absent_n']:,} cases) |")
    L(f"| PPG (`SNUADC/PLETH`) | {a['ppg_pct']:.1f}% |")
    L(f"| ECG II (`SNUADC/ECG_II`) | {a['ecg2_pct']:.1f}% |")
    L(f"| NIBP (`Solar8000/NIBP_MBP`) | {a['nibp_pct']:.1f}% |")
    L(f"| BIS EEG (`BIS/EEG1_WAV`) | {a['bis_pct']:.1f}% |")
    L(f"| Sevoflurane (`Primus/SEVOFLURANE_VOL`) | {a['sevo_pct']:.1f}% |")
    L(f"| Propofol Ce (`Orchestra/PPF20_CE`) | {a['ppf_pct']:.1f}% |")
    L(f"| Triplet (ECG II + PLETH + ABP) | {a['triplet_ecg_ppg_abp_pct']:.1f}% |")
    L("")

    # 6. Design-assumption reconciliation
    L("## 6. Design assumption vs reality")
    L("")
    L("| assumption (project_brief / master_plan) | observed | verdict |")
    L("|------------------------------------------|----------|---------|")
    L(f"| 6,388 cases (non-cardiac surgery, SNUH, Aug 2016 – Jun 2017) | {report['a1_total']['n_cases']:,} cases in `load_clinical_data()` | "
      f"{'**match**' if report['a1_total']['n_cases'] == 6388 else '**review required**'} |")
    if "bin_lt30" in report["a4_duration"]:
        n = report["a4_duration"]["bin_lt30"]
        L(f"| Cohort exclusion: 수술시간 < 30분 drop | {n:,} cases under 30 min | confirms exclusion would actually drop a meaningful slice |")
    if "abp_any_pct" in report["a5_modality"]:
        v = report["a5_modality"]["abp_any_pct"]
        v_abs = report["a5_modality"]["abp_absent_pct"]
        L(f"| Modality-agnostic claim depends on ABP-absent fraction being non-trivial | ABP-any in **{v:.1f}%**; ABP-absent in **{v_abs:.1f}%** | "
          f"{'reasonable — modality-agnostic story holds' if v_abs >= 5 else 'review — ABP-absent fraction may be too small for a strong narrative'} |")
    L(f"| Expected final cohort ~5,800–6,000 after minimal filter | starting set {report['a1_total']['n_cases']:,}; subtract <30-min ({report['a4_duration'].get('bin_lt30', 'n/a')}) | gross check only — full exclusion logic lives in `plan_1.2` |")
    L("")

    # 7. Issues / open questions
    L("## 7. Open questions / things to verify in `plan_1.1`")
    L("")
    L("- The 12 waveform modalities listed in `docs/project_brief.md §4` need to be cross-checked against the `trks` track listing — some priority tracks above may have different official names per VitalDB version.")
    L("- ABP-absent fraction (above) drives the modality-agnostic story; if it lands above ~10%, that is a clean talking point — if it is essentially zero, the framing should shift to robustness rather than 'agnostic'.")
    L("- `opstart` / `opend` interpretation: confirm units (seconds vs minutes vs HH:MM) before relying on duration bins for cohort code.")
    L("- `optype` taxonomy here vs the 4-bucket taxonomy (general / thoracic / urologic / gynecologic) in `plan_1.5_surgery_context.md` — likely needs a mapping table.")
    L("- The track listing size and the case count in `trks` vs `cases` should agree on which cases are reachable end-to-end; small gaps usually mean uploaded vs analyzed splits.")
    L("- `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` for any clinical interpretation of these counts.")
    L("")

    L("## 8. Reproducibility")
    L("")
    L("```bash")
    L(".venv/Scripts/python.exe docs/notebooks/00_vitaldb_quick_exploration.py")
    L("# CSV cache: docs/notebooks/_cache/{cases,trks}.csv (delete to force re-fetch)")
    L("```")
    L("")

    return "\n".join(lines) + "\n"


def main() -> None:
    print("Loading metadata...", flush=True)
    cases, trks = load_metadata()
    print(f"  cases: {len(cases):,} rows, {cases.shape[1]} cols", flush=True)
    print(f"  trks:  {len(trks):,} rows", flush=True)

    print("Running analyses...", flush=True)
    report = {
        "env": {
            "vitaldb_version": getattr(vitaldb, "__version__", "1.6.0"),
            "python": sys.version.split()[0],
        },
        "a1_total": analysis_1_total(cases),
        "a2_surgery": analysis_2_surgery(cases),
        "a3_demographics": analysis_3_demographics(cases),
        "a4_duration": analysis_4_duration(cases),
        "a5_modality": analysis_5_modalities(cases, trks),
    }

    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS.write_text(render(report), encoding="utf-8")
    (CACHE / "report.json").write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")
    print(f"Wrote {FINDINGS}", flush=True)
    print(f"Wrote {CACHE / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
