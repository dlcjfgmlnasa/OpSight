"""Build OpSight cohort manifest (plan_1.2 산출물).
OpSight cohort manifest 빌드 스크립트 (plan_1.2 산출물).

End-to-end pipeline:
  1. Read cases.csv + trks.csv (cache 우선, fallback to VitalDB CSV endpoint)
  2. Apply minimal-filter exclusions (`docs/project_brief.md §4.1`)
  3. Emit `data/cohort/exclusions.parquet` (full 6,388 rows + reason)
  4. Emit `data/cohort/manifest.parquet` (included rows + 9 columns)
  5. Emit `docs/cohort_stats.md` (department-stratified modality availability)

Pre-task blocker defaults (`[DECISION PENDING]`):
  - Pediatric inclusion (age < 18): **INCLUDE** (default, brief §4.1)
  - ASA = 6 inclusion: **INCLUDE** (default, preserves transplant cases)

본 default 는 임상의 그룹 회의에서 변경 가능 — `--exclude-pediatric` /
`--exclude-asa6` flag 로 sensitivity 분석 가능.

Usage:
  python scripts/build_cohort.py [--cache-only]
  python scripts/build_cohort.py --exclude-pediatric --exclude-asa6
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ── Paths / 경로 ──

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "docs" / "notebooks" / "_cache"
DATA_COHORT_DIR = REPO_ROOT / "data" / "cohort"
COHORT_STATS_PATH = REPO_ROOT / "docs" / "cohort_stats.md"

CASES_URL = "https://api.vitaldb.net/cases"
TRKS_URL = "https://api.vitaldb.net/trks"

# ── Filter thresholds / 필터 임계 ──

OP_TIME_MIN_SEC = 30 * 60  # 30 min

# Modality alias for cohort manifest abp_* columns
# Mirror of `opsight/fm/mock_rule_based.py::_ABP_ALIASES`.
_ABP_INVASIVE_TRACKS = {"SNUADC/ART"}
_ABP_PRIMARY_EXTRA = {"Solar8000/ART_MBP"}
_ABP_EXTENDED_EXTRA = {"EV1000/ART_MBP", "Solar8000/FEM_MBP"}


# ── Loaders / 로더 ──


def load_cases(cache_only: bool = False) -> pd.DataFrame:
    """Load case-level metadata (6,388 row × 74 col).
    Case 수준 metadata 로드.
    """
    cache_path = CACHE_DIR / "cases.csv"
    if cache_path.exists():
        return pd.read_csv(cache_path)
    if cache_only:
        raise FileNotFoundError(f"cache 부재 + --cache-only: {cache_path}")
    print(f"[fetch] {CASES_URL}")
    df = pd.read_csv(CASES_URL)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return df


def load_trks(cache_only: bool = False) -> pd.DataFrame:
    """Load track listing (486k row × 3 col: caseid, tname, tid).
    Track listing 로드.
    """
    cache_path = CACHE_DIR / "trks.csv"
    if cache_path.exists():
        return pd.read_csv(cache_path)
    if cache_only:
        raise FileNotFoundError(f"cache 부재 + --cache-only: {cache_path}")
    print(f"[fetch] {TRKS_URL}")
    df = pd.read_csv(TRKS_URL)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return df


# ── Exclusion logic / 제외 로직 ──


def compute_exclusions(
    cases: pd.DataFrame,
    *,
    exclude_pediatric: bool = False,
    exclude_asa6: bool = False,
) -> pd.DataFrame:
    """Compute per-case exclusion reason. Returns DataFrame with case_id +
    excluded (bool) + reason (str).
    Case 별 exclusion reason 계산.
    """
    out_rows: list[dict[str, Any]] = []
    for _, row in cases.iterrows():
        cid = int(row["caseid"])
        # op_duration in seconds
        op_dur = float(row["opend"]) - float(row["opstart"])
        if op_dur < OP_TIME_MIN_SEC:
            out_rows.append({"case_id": cid, "excluded": True, "reason": "op_time_lt_30min"})
            continue
        # Patient info — height / weight / age 모두 NaN 이면 제외
        # 본 dataset 은 age/weight/height 모두 100% → 보통 trigger 안 됨
        if (
            pd.isna(row.get("age"))
            and pd.isna(row.get("weight"))
            and pd.isna(row.get("height"))
        ):
            out_rows.append(
                {"case_id": cid, "excluded": True, "reason": "patient_info_missing"}
            )
            continue
        if exclude_pediatric and float(row["age"]) < 18.0:
            out_rows.append(
                {"case_id": cid, "excluded": True, "reason": "pediatric_age_lt_18"}
            )
            continue
        if exclude_asa6 and not pd.isna(row.get("asa")) and int(row["asa"]) == 6:
            out_rows.append(
                {"case_id": cid, "excluded": True, "reason": "asa_eq_6"}
            )
            continue
        out_rows.append({"case_id": cid, "excluded": False, "reason": "included"})
    return pd.DataFrame(out_rows)


# ── Manifest build / Manifest 빌드 ──


def _case_to_track_set(trks: pd.DataFrame) -> dict[int, set[str]]:
    """Return dict mapping caseid → set of tname.
    """
    return trks.groupby("caseid")["tname"].apply(set).to_dict()


def build_manifest(
    cases: pd.DataFrame, trks: pd.DataFrame, exclusions: pd.DataFrame,
) -> pd.DataFrame:
    """Build final manifest from cases + trks + exclusions.
    Cases + trks + exclusions 에서 manifest 빌드.
    """
    included = exclusions[~exclusions["excluded"]]["case_id"].tolist()
    cases_included = cases[cases["caseid"].isin(included)].copy()
    case_tracks = _case_to_track_set(trks)

    # surgery_type mapping (VitalDB `department` → enum)
    # surgery_type 매핑
    _DEPT_TO_TYPE = {
        "General surgery": "general",
        "Thoracic surgery": "thoracic",
        "Urology": "urology",
        "Gynecology": "gynecology",
    }

    rows: list[dict[str, Any]] = []
    for _, row in cases_included.iterrows():
        cid = int(row["caseid"])
        tracks = case_tracks.get(cid, set())
        abp_invasive = bool(tracks & _ABP_INVASIVE_TRACKS)
        abp_primary = abp_invasive or bool(tracks & _ABP_PRIMARY_EXTRA)
        abp_any = abp_primary or bool(tracks & _ABP_EXTENDED_EXTRA)
        op_min = (float(row["opend"]) - float(row["opstart"])) / 60.0
        surgery_type = _DEPT_TO_TYPE.get(row["department"], "other")
        rows.append({
            "case_id": cid,
            "surgery_type": surgery_type,
            "op_duration_min": op_min,
            "age": float(row["age"]),
            "asa": int(row["asa"]) if not pd.isna(row["asa"]) else None,
            "abp_invasive": abp_invasive,
            "abp_primary": abp_primary,
            "abp_any": abp_any,
            "included": True,
        })
    return pd.DataFrame(rows)


# ── Modality availability stats / Modality 가용성 통계 ──


_PRIORITY_MODALITIES = {
    "ABP_any (Extended)":
        _ABP_INVASIVE_TRACKS | _ABP_PRIMARY_EXTRA | _ABP_EXTENDED_EXTRA,
    "SNUADC/ART (invasive)": _ABP_INVASIVE_TRACKS,
    "Solar8000/NIBP_MBP (NIBP)": {"Solar8000/NIBP_MBP"},
    "SNUADC/PLETH (PPG)": {"SNUADC/PLETH"},
    "SNUADC/ECG_II": {"SNUADC/ECG_II"},
    "BIS/BIS": {"BIS/BIS"},
    "BIS/EEG1_WAV (EEG)": {"BIS/EEG1_WAV"},
    "Primus/EXP_SEVO (Sevo)": {"Primus/EXP_SEVO"},
    "Orchestra/RFTN20_CE (Remi)": {"Orchestra/RFTN20_CE"},
    "Orchestra/PPF20_CE (Prop)": {"Orchestra/PPF20_CE"},
    "Solar8000/HR": {"Solar8000/HR"},
    "Primus/CO2 (Capno)": {"Primus/CO2"},
}


def compute_modality_stats(
    manifest: pd.DataFrame, trks: pd.DataFrame,
) -> pd.DataFrame:
    """Department-stratified modality availability table.
    Department 별 stratified modality 가용성 표.
    """
    case_tracks = _case_to_track_set(trks)
    surgery_types = ["general", "thoracic", "urology", "gynecology"]

    rows: list[dict[str, Any]] = []
    for mod_name, candidate_tracks in _PRIORITY_MODALITIES.items():
        row: dict[str, Any] = {"modality": mod_name}
        # Overall
        n_all = len(manifest)
        present_all = sum(
            1 for cid in manifest["case_id"]
            if cid in case_tracks and (case_tracks[cid] & candidate_tracks)
        )
        row["All"] = f"{100 * present_all / max(1, n_all):.1f}%"
        row["All_n"] = n_all
        for st in surgery_types:
            sub = manifest[manifest["surgery_type"] == st]
            n_sub = len(sub)
            if n_sub == 0:
                row[st] = "—"
                row[f"{st}_n"] = 0
                continue
            present = sum(
                1 for cid in sub["case_id"]
                if cid in case_tracks and (case_tracks[cid] & candidate_tracks)
            )
            pct = 100 * present / n_sub
            row[st] = f"{pct:.1f}%"
            if pct < 50.0:
                row[st] += " [CAVEAT]"
            row[f"{st}_n"] = n_sub
        rows.append(row)
    return pd.DataFrame(rows)


# ── Markdown writer / Markdown writer ──


def compute_artifact_stats(
    manifest: pd.DataFrame, max_cases: int = 50,
) -> pd.DataFrame:
    """Sample artifact rate per modality for the first ``max_cases`` cases.
    첫 ``max_cases`` case 에 대한 modality 별 artifact 비율.

    `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` — physiological range 임계.

    Loads each case via vitaldb at interval=1.0s; counts samples outside the
    physiological range defined in opsight.preprocessing.SIGNAL_CONFIGS
    + counts NaN ratio. Network-dependent (graceful skip on error).

    Args:
        manifest: cohort manifest DataFrame.
        max_cases: sample size cap (network cost).
    """
    import sys as _sys
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in _sys.path:
        _sys.path.insert(0, str(repo_root))
    try:
        import vitaldb as _vdb
        from opsight.preprocessing.signal_config import config_for_modality
    except Exception as exc:
        print(f"  [artifact-stats] skip (import failed): {exc}")
        return pd.DataFrame()

    TRACKS = {
        "Solar8000/HR": "HR",
        "Solar8000/ART_MBP": "ABP",  # MAP config used via alias
        "Solar8000/NIBP_MBP": "Solar8000/NIBP_MBP",
        "Solar8000/PLETH_SPO2": "SpO2",
        "Solar8000/ETCO2": "EtCO2",
        "BIS/BIS": "BIS",
    }
    sample_ids = manifest["case_id"].head(max_cases).tolist()
    stats: dict[str, dict[str, list[float]]] = {
        alias: {"nan_ratio": [], "out_of_range_ratio": []} for alias in TRACKS.values()
    }
    n_processed = 0
    for cid in sample_ids:
        try:
            vf = _vdb.VitalFile(int(cid), track_names=list(TRACKS))
            df = vf.to_pandas(list(TRACKS), interval=1.0)
        except Exception:
            continue
        n_processed += 1
        for col in df.columns:
            arr = df[col].to_numpy(dtype=np.float64)
            alias = TRACKS.get(col, col)
            nan_ratio = float(np.mean(np.isnan(arr)))
            cfg = config_for_modality(alias)
            if cfg is None:
                continue
            valid = arr[~np.isnan(arr)]
            if len(valid) == 0:
                oor_ratio = 0.0
            else:
                oor = (valid < cfg.physiological_min) | (valid > cfg.physiological_max)
                oor_ratio = float(np.mean(oor))
            stats[alias]["nan_ratio"].append(nan_ratio)
            stats[alias]["out_of_range_ratio"].append(oor_ratio)

    rows: list[dict[str, Any]] = []
    for alias, m in stats.items():
        if not m["nan_ratio"]:
            continue
        rows.append({
            "modality": alias,
            "n_cases_sampled": len(m["nan_ratio"]),
            "nan_ratio_mean": float(np.mean(m["nan_ratio"])),
            "nan_ratio_p50": float(np.median(m["nan_ratio"])),
            "nan_ratio_p95": float(np.percentile(m["nan_ratio"], 95)),
            "out_of_range_ratio_mean": float(np.mean(m["out_of_range_ratio"])),
            "out_of_range_ratio_p95": float(np.percentile(m["out_of_range_ratio"], 95)),
            "out_of_range_ratio_max": float(np.max(m["out_of_range_ratio"])),
        })
    print(f"  [artifact-stats] processed {n_processed}/{len(sample_ids)} cases")
    return pd.DataFrame(rows)


def write_cohort_stats_md(
    manifest: pd.DataFrame, modality_stats: pd.DataFrame, exclusions: pd.DataFrame,
    *, exclude_pediatric: bool, exclude_asa6: bool,
    artifact_stats: pd.DataFrame | None = None,
) -> None:
    """Write `docs/cohort_stats.md`.
    `docs/cohort_stats.md` 작성.
    """
    surgery_types = ["general", "thoracic", "urology", "gynecology"]
    lines: list[str] = []
    lines.append("# Cohort Stats — plan_1.2 산출물")
    lines.append("")
    lines.append("> 자동 생성: `python scripts/build_cohort.py`. 매번 갱신.")
    lines.append("> Source: `data/cohort/manifest.parquet` + `data/cohort/exclusions.parquet`.")
    lines.append("")
    lines.append("## 0. 빌드 정책 (Build policy)")
    lines.append("")
    lines.append("| 항목 | 값 |")
    lines.append("|------|----|")
    lines.append(f"| 데이터 source | `docs/notebooks/_cache/cases.csv` + `trks.csv` (2026-05-16 snapshot) |")
    lines.append(f"| 최소 수술시간 | ≥ {OP_TIME_MIN_SEC // 60} 분 |")
    lines.append(f"| Pediatric (`age < 18`) | {'EXCLUDED' if exclude_pediatric else 'INCLUDED (default)'} |")
    lines.append(f"| `ASA = 6` | {'EXCLUDED' if exclude_asa6 else 'INCLUDED (default)'} |")
    lines.append("")
    lines.append("`[DECISION PENDING]` `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` —")
    lines.append("Pediatric / ASA=6 inclusion 은 회의 후 결정. 본 manifest 는 *default (둘 다 INCLUDE)* 기반.")
    lines.append("")
    lines.append("## 1. Cohort 규모")
    lines.append("")
    lines.append("| Stratum | n |")
    lines.append("|---------|---|")
    lines.append(f"| Raw (cases.csv) | {len(exclusions)} |")
    excl_counts = exclusions["reason"].value_counts().to_dict()
    for reason, count in sorted(excl_counts.items()):
        if reason == "included":
            continue
        lines.append(f"| Excluded — {reason} | {count} |")
    lines.append(f"| **Included (manifest.parquet)** | **{len(manifest)}** |")
    lines.append("")
    lines.append("### Surgery type 분포")
    lines.append("")
    lines.append("| surgery_type | n | % of included |")
    lines.append("|--------------|---|---------------|")
    n_total = len(manifest)
    for st in surgery_types + ["other"]:
        sub = manifest[manifest["surgery_type"] == st]
        if len(sub) == 0:
            continue
        pct = 100 * len(sub) / max(1, n_total)
        lines.append(f"| {st} | {len(sub)} | {pct:.1f}% |")
    lines.append("")
    lines.append("## 2. Department-stratified modality 가용성")
    lines.append("")
    header_n = {
        "all": f"All (n={n_total})",
        "general": f"general (n={modality_stats.iloc[0].get('general_n', 0)})",
        "thoracic": f"thoracic (n={modality_stats.iloc[0].get('thoracic_n', 0)})",
        "urology": f"urology (n={modality_stats.iloc[0].get('urology_n', 0)})",
        "gynecology": f"gynecology (n={modality_stats.iloc[0].get('gynecology_n', 0)})",
    }
    lines.append(f"| modality | {header_n['all']} | {header_n['general']} | {header_n['thoracic']} | {header_n['urology']} | {header_n['gynecology']} |")
    lines.append("|----------|---|---|---|---|---|")
    for _, r in modality_stats.iterrows():
        lines.append(
            f"| `{r['modality']}` | {r['All']} | {r['general']} | "
            f"{r['thoracic']} | {r['urology']} | {r['gynecology']} |"
        )
    lines.append("")
    lines.append("`[CAVEAT]` mark = 가용성 < 50% (department 안).")
    lines.append("")
    lines.append("## 3. Manifest schema")
    lines.append("")
    lines.append("```")
    lines.append("case_id: int")
    lines.append("surgery_type: enum {general, thoracic, urology, gynecology, other}")
    lines.append("op_duration_min: float")
    lines.append("age: float")
    lines.append("asa: int | null")
    lines.append("abp_invasive: bool      # SNUADC/ART present")
    lines.append("abp_primary: bool       # ART OR Solar8000/ART_MBP (brief §4.2 Primary)")
    lines.append("abp_any: bool           # Primary OR EV1000/ART_MBP OR Solar8000/FEM_MBP (brief §4.2 Extended, default)")
    lines.append("included: bool          # always True in manifest.parquet")
    lines.append("```")
    lines.append("")
    lines.append("## 4. Clinical-evaluator review note (자동)")
    lines.append("")
    lines.append("아래는 *자동 sanity check* 결과. 실제 임상 검토는 `[CLINICIAN-REVIEW]` marker.")
    lines.append("")
    if "general" in modality_stats.columns:
        general_abp = modality_stats[modality_stats["modality"] == "ABP_any (Extended)"]["general"].iloc[0]
        thoracic_abp = modality_stats[modality_stats["modality"] == "ABP_any (Extended)"]["thoracic"].iloc[0]
        lines.append(f"- ABP 가용성 department 별 편차 — General: {general_abp}, Thoracic: {thoracic_abp}. brief §1 의 modality-agnostic 정책의 empirical 근거.")
    lines.append("- Pediatric / ASA=6 default 적용 — 회의 결정 후 본 stats 재생성 필요 시 `--exclude-pediatric` / `--exclude-asa6` flag 사용.")
    lines.append("- `surgery_type == 'other'` 비율 — VitalDB `department` 가 4 표준 외 값을 가지면 발생. 본 dataset (2026-05-16 snapshot) 은 4 department 만.")
    lines.append("")
    lines.append("[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — surgery_type 분포의 임상적 타당성, ABP 가용성 편차 해석.")

    # ── Artifact stats (Sprint 6 Task D) ──
    if artifact_stats is not None and len(artifact_stats) > 0:
        lines.append("")
        lines.append("## 5. Modality 별 artifact / NaN ratio (Sprint 6 추가)")
        lines.append("")
        lines.append(f"> 첫 {int(artifact_stats['n_cases_sampled'].max())} case sample 기반. "
                     "Physiological range 임계는 `opsight/preprocessing/signal_config.py` 의 `SIGNAL_CONFIGS`.")
        lines.append("> `out_of_range_ratio` = valid sample 중 physiological_min/max 범위 밖 비율.")
        lines.append("> `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` — range 임계의 임상 적절성.")
        lines.append("")
        lines.append("| modality | n_cases | nan_ratio mean | nan p95 | OOR ratio mean | OOR p95 | OOR max |")
        lines.append("|----------|---------|----------------|---------|----------------|---------|---------|")
        for _, r in artifact_stats.iterrows():
            lines.append(
                f"| `{r['modality']}` | {int(r['n_cases_sampled'])} | "
                f"{r['nan_ratio_mean']:.1%} | {r['nan_ratio_p95']:.1%} | "
                f"{r['out_of_range_ratio_mean']:.2%} | {r['out_of_range_ratio_p95']:.2%} | "
                f"{r['out_of_range_ratio_max']:.2%} |"
            )
        lines.append("")
        lines.append("### 해석 hint")
        lines.append("")
        lines.append("- **NaN ratio 가 50%+ 인 modality** (HR / ABP / SpO2 등) — Solar8000 native rate (~0.5Hz) "
                     "가 1Hz resample 와 mismatch. 정상.")
        lines.append("- **NaN ratio 가 95%+** (NIBP) — cuff 측정 주기 (~5분 1회). 정상.")
        lines.append("- **OOR (out-of-range) 비율 > 1%** — sensor artifact 비율 추정. preprocessing 의 "
                     "`clip_to_physiological` 가 자동 처리.")
        lines.append("- **OOR max** 가 큰 case — *문제 case*. cohort filtering 또는 manual review 후보.")

    COHORT_STATS_PATH.write_text("\n".join(lines), encoding="utf-8")


# ── Entry point / 진입점 ──


def main() -> None:
    ap = argparse.ArgumentParser(description="Build OpSight cohort manifest")
    ap.add_argument("--cache-only", action="store_true",
                    help="cache 만 사용 (network fetch 안 함)")
    ap.add_argument("--exclude-pediatric", action="store_true",
                    help="age < 18 case 제외 (default: include — brief §4.1)")
    ap.add_argument("--exclude-asa6", action="store_true",
                    help="ASA = 6 case 제외 (default: include)")
    ap.add_argument("--artifact-stats-cases", type=int, default=0,
                    help="N>0 시 첫 N case sample 로 modality 별 artifact/NaN 비율 계산 + "
                         "cohort_stats.md 에 추가 (network 의존). 기본 0 (skip).")
    args = ap.parse_args()

    DATA_COHORT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] Loading cases + trks ...")
    cases = load_cases(cache_only=args.cache_only)
    trks = load_trks(cache_only=args.cache_only)
    print(f"  raw cases: {len(cases)} | trks: {len(trks)}")

    print("[2/5] Computing exclusions ...")
    exclusions = compute_exclusions(
        cases,
        exclude_pediatric=args.exclude_pediatric,
        exclude_asa6=args.exclude_asa6,
    )
    excl_path = DATA_COHORT_DIR / "exclusions.parquet"
    exclusions.to_parquet(excl_path, index=False)
    print(f"  → {excl_path} ({len(exclusions)} rows)")

    print("[3/5] Building manifest ...")
    manifest = build_manifest(cases, trks, exclusions)
    manifest_path = DATA_COHORT_DIR / "manifest.parquet"
    manifest.to_parquet(manifest_path, index=False)
    print(f"  → {manifest_path} ({len(manifest)} rows)")

    print("[4/5] Computing modality stats ...")
    modality_stats = compute_modality_stats(manifest, trks)

    artifact_stats: pd.DataFrame | None = None
    if args.artifact_stats_cases > 0:
        print(f"[4b/5] Computing artifact stats (sample {args.artifact_stats_cases} cases) ...")
        artifact_stats = compute_artifact_stats(manifest, max_cases=args.artifact_stats_cases)

    print("[5/5] Writing docs/cohort_stats.md ...")
    write_cohort_stats_md(
        manifest, modality_stats, exclusions,
        exclude_pediatric=args.exclude_pediatric,
        exclude_asa6=args.exclude_asa6,
        artifact_stats=artifact_stats,
    )
    print(f"  → {COHORT_STATS_PATH}")
    print("")
    print(f"DONE. {len(manifest)} cases included.")


if __name__ == "__main__":
    main()
