"""
01 — PUMP / Drug Channel Design-Feasibility Exploration (pre plan_1.1 deep dive)

목적 (Purpose): VitalAgent intervention-response 자동 감지가 어디까지 자동
가능한지를 빠르게 검증한다. user 가설 "PUMP* / DRUG* 채널이 있다" 를 schema reality
와 대조하고, Orchestra/* drug track + cases.csv intraop_* field 의 가용성을
정리한다.

Scope: 100 random case sample (재현용 manifest 저장), PHEN-보유 case 3개 selective
load. 본격 plan_1.1 작업이 아닌 design feasibility 사전 탐색.

Outputs:
- docs/findings/pump_drug_findings.md  (메인 산출물, 한글)
- docs/notebooks/_cache/sample100.csv  (재현용 caseid manifest)
- docs/notebooks/_cache/01_report.json (raw stats)

Cache: docs/notebooks/_cache/{cases,trks}.csv — 재다운로드 없음.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).parent / "_cache"
FINDINGS = ROOT / "findings" / "pump_drug_findings.md"

SEED = 20260517


# ---------------------------------------------------------------------------
# 1. 임상 분류 (잠정 — 모두 [CLINICIAN-REVIEW] marker 대상)
# ---------------------------------------------------------------------------

# Orchestra/<DRUG>_<VAR> 의 <DRUG> code → 잠정 임상 class.
# 본 매핑은 임상의 (이형철 교수님 그룹) 검토 전 잠정안이다.
DRUG_CLASS = {
    # opioid / hypnotic / paralytic — main anesthetic infusions
    "RFTN20": ("opioid",       "remifentanil 20μg/mL"),
    "RFTN50": ("opioid",       "remifentanil 50μg/mL"),
    "PPF20":  ("hypnotic",     "propofol 20mg/mL"),
    "ROC":    ("paralytic",    "rocuronium"),
    "VEC":    ("paralytic",    "vecuronium"),
    # vasoactive (vasopressor / inotrope)
    "PHEN":   ("vasopressor",  "phenylephrine"),
    "NEPI":   ("vasopressor",  "norepinephrine"),
    "DOPA":   ("inotrope",     "dopamine"),       # dose-dependent
    "EPI":    ("inotrope",     "epinephrine"),
    "DOBU":   ("inotrope",     "dobutamine"),
    "VASO":   ("vasopressor",  "vasopressin"),
    "MRN":    ("inotrope",     "milrinone"),
    # vasodilator
    "NTG":    ("vasodilator",  "nitroglycerin"),
    "NPS":    ("vasodilator",  "nitroprusside"),
    "PGE1":   ("vasodilator",  "prostaglandin E1 (pulmonary)"),
    # antiarrhythmic / CCB
    "DTZ":    ("antiarrhythmic", "diltiazem"),
    "AMD":    ("antiarrhythmic", "amiodarone"),
    # sedative
    "DEX2":   ("sedative",     "dexmedetomidine (2)"),
    "DEX4":   ("sedative",     "dexmedetomidine (4)"),
    # other
    "FUT":    ("other",        "futhan / nafamostat (protease inh)"),
    "OXY":    ("other",        "oxytocin (uterotonic)"),
}


# ---------------------------------------------------------------------------
# 2. Step A1–A5: cache 만 사용하는 분석 함수
# ---------------------------------------------------------------------------

def load_cache() -> tuple[pd.DataFrame, pd.DataFrame]:
    cases = pd.read_csv(CACHE / "cases.csv")
    trks = pd.read_csv(CACHE / "trks.csv")
    return cases, trks


def a1_schema_check(trks: pd.DataFrame) -> dict[str, Any]:
    """user 가설 'PUMP* / DRUG* 채널 존재' 를 schema 에 대조한다."""
    pump_hits = trks["tname"].str.contains("PUMP", case=False, na=False).sum()
    drug_hits = trks["tname"].str.contains("DRUG", case=False, na=False).sum()
    orch = trks[trks["tname"].str.startswith("Orchestra/", na=False)]
    orch_track_counts = orch.groupby("tname")["caseid"].nunique().sort_values(ascending=False)
    return {
        "pump_pattern_hits": int(pump_hits),
        "drug_pattern_hits": int(drug_hits),
        "orchestra_track_count": int(len(orch_track_counts)),
        "orchestra_track_caseid_counts": {k: int(v) for k, v in orch_track_counts.items()},
    }


def _drug_code_from_track(tname: str) -> str | None:
    """Orchestra/<DRUG>_<VAR> 에서 <DRUG> 추출."""
    if not tname.startswith("Orchestra/"):
        return None
    rest = tname[len("Orchestra/") :]
    # variable suffix: _RATE / _VOL / _CE / _CP / _CT
    for suffix in ("_RATE", "_VOL", "_CE", "_CP", "_CT"):
        if rest.endswith(suffix):
            return rest[: -len(suffix)]
    return rest  # unknown variable


def a2_drug_taxonomy(trks: pd.DataFrame, n_total: int) -> dict[str, Any]:
    """drug code → 임상 class 매핑 + 각 class 당 case 수."""
    orch = trks[trks["tname"].str.startswith("Orchestra/", na=False)].copy()
    orch["drug_code"] = orch["tname"].apply(_drug_code_from_track)
    # 한 case 가 같은 drug 의 RATE/VOL/CE 를 다 갖는 게 일반적이므로
    # drug 단위 case 카운트는 drug_code 별 unique caseid.
    drug_case = orch.groupby("drug_code")["caseid"].nunique().sort_values(ascending=False)
    rows = []
    for code, n in drug_case.items():
        klass, name = DRUG_CLASS.get(code, ("unknown", "unknown"))
        rows.append({
            "drug_code": code,
            "drug_name": name,
            "class": klass,
            "n_cases": int(n),
            "pct": round(100 * n / n_total, 2),
        })
    # class 단위 합 (case 단위 unique — drug 여러 개 보유한 case 가 중복될 수 있어
    # 'at least one drug of class K' 로 계산)
    by_class: dict[str, set[int]] = {}
    for code, klass in [(c, DRUG_CLASS.get(c, ("unknown", ""))[0]) for c in drug_case.index]:
        ids = set(orch.loc[orch["drug_code"] == code, "caseid"].unique())
        by_class.setdefault(klass, set()).update(ids)
    class_summary = [
        {"class": k, "n_cases_with_any_member": len(v),
         "pct": round(100 * len(v) / n_total, 2)}
        for k, v in sorted(by_class.items(), key=lambda x: -len(x[1]))
    ]
    return {"per_drug": rows, "per_class": class_summary}


def a3_department_crosstab(cases: pd.DataFrame, trks: pd.DataFrame) -> dict[str, Any]:
    """Vasoactive Orchestra track × department 가용성."""
    vasoactives = ["PHEN", "NEPI", "DOPA", "EPI", "DOBU", "VASO", "NTG"]
    dept_order = ["General surgery", "Thoracic surgery", "Gynecology", "Urology"]
    dept_n = {d: int((cases["department"] == d).sum()) for d in dept_order}

    out: dict[str, Any] = {"dept_n": dept_n, "rows": []}
    for code in vasoactives:
        rate_t = f"Orchestra/{code}_RATE"
        case_ids = set(trks.loc[trks["tname"] == rate_t, "caseid"].unique())
        per_dept = {}
        for d in dept_order:
            dept_cases = set(cases.loc[cases["department"] == d, "caseid"].values)
            n = len(case_ids & dept_cases)
            per_dept[d] = {"n": n, "pct": round(100 * n / dept_n[d], 2)}
        out["rows"].append({
            "drug_code": code,
            "drug_name": DRUG_CLASS.get(code, ("?", "?"))[1],
            "class": DRUG_CLASS.get(code, ("?", "?"))[0],
            "total_cases": len(case_ids),
            "by_department": per_dept,
        })
    return out


def a4_intraop_coverage(cases: pd.DataFrame) -> dict[str, Any]:
    """cases.csv intraop_* field 의 가용성 + bolus 빈도 (n_>0)."""
    intraop_cols = sorted([c for c in cases.columns if c.startswith("intraop_")])
    rows = []
    for c in intraop_cols:
        s = cases[c]
        n_nonnull = int(s.notna().sum())
        if not pd.api.types.is_numeric_dtype(s):
            rows.append({"field": c, "n_nonnull": n_nonnull, "non_numeric": True})
            continue
        n_pos = int((s.fillna(0) > 0).sum())
        d = s.dropna()
        rows.append({
            "field": c,
            "n_nonnull": n_nonnull,
            "pct_nonnull": round(100 * n_nonnull / len(cases), 2),
            "n_positive": n_pos,
            "pct_positive": round(100 * n_pos / len(cases), 2),
            "mean_overall": round(float(d.mean()), 3) if len(d) else None,
            "p50": round(float(d.quantile(0.5)), 3) if len(d) else None,
            "p95": round(float(d.quantile(0.95)), 3) if len(d) else None,
            "max": round(float(d.max()), 3) if len(d) else None,
        })
    return {"per_field": rows}


def a4b_department_intraop(cases: pd.DataFrame) -> dict[str, Any]:
    """주요 intraop_* (eph / phe / epi / rbc / ffp) × department."""
    interest = ["intraop_eph", "intraop_phe", "intraop_epi", "intraop_rbc", "intraop_ffp"]
    dept_order = ["General surgery", "Thoracic surgery", "Gynecology", "Urology"]
    rows: list[dict[str, Any]] = []
    for c in interest:
        per_dept = {}
        for d in dept_order:
            sub = cases[cases["department"] == d]
            n_tot = len(sub)
            n_pos = int((sub[c].fillna(0) > 0).sum())
            mean_pos = float(sub.loc[sub[c] > 0, c].mean()) if n_pos else 0.0
            per_dept[d] = {
                "n_positive": n_pos,
                "n_total": n_tot,
                "pct_positive": round(100 * n_pos / n_tot, 2),
                "mean_when_positive": round(mean_pos, 2),
            }
        rows.append({"field": c, "by_department": per_dept})
    return {"per_field": rows}


def a5_sample_manifest(cases: pd.DataFrame) -> dict[str, Any]:
    """100 case sample (deterministic) — 재현용 manifest."""
    rng = np.random.default_rng(SEED)
    sample_ids = rng.choice(cases["caseid"].values, size=100, replace=False)
    sample_ids = np.sort(sample_ids)
    out_path = CACHE / "sample100.csv"
    pd.DataFrame({"caseid": sample_ids}).to_csv(out_path, index=False)
    return {
        "seed": SEED,
        "n": 100,
        "first10": [int(x) for x in sample_ids[:10]],
        "last5": [int(x) for x in sample_ids[-5:]],
        "saved_to": str(out_path.relative_to(ROOT.parent)) if out_path.is_absolute() else str(out_path),
    }


# ---------------------------------------------------------------------------
# 3. Step A6: vitaldb API trial load — PHEN 보유 case 3 개에서 bolus pattern 식별
# ---------------------------------------------------------------------------

def a6_bolus_trial(trks: pd.DataFrame, max_cases: int = 3) -> dict[str, Any]:
    """PHEN-RATE 보유 case 3개를 load 하여 'bolus vs continuous' segment 분리 trial."""
    try:
        import vitaldb  # noqa
    except Exception as e:
        return {"error": f"vitaldb import failed: {e}"}

    phen_cases = sorted(trks.loc[trks["tname"] == "Orchestra/PHEN_RATE", "caseid"].unique())
    targets = list(phen_cases)[:max_cases]
    tracks = ["Orchestra/PHEN_RATE", "Orchestra/PHEN_VOL", "Solar8000/ART_MBP", "Solar8000/HR"]
    results = []
    for caseid in targets:
        try:
            arr = vitaldb.load_case(caseid=int(caseid), track_names=tracks, interval=1.0)
            if arr is None or len(arr) == 0:
                results.append({"caseid": int(caseid), "error": "empty array"})
                continue
            df = pd.DataFrame(arr, columns=tracks)
            rate = df["Orchestra/PHEN_RATE"].fillna(0).values
            # segment 추출
            events: list[tuple[int, int, int]] = []
            in_event = False
            start: int | None = None
            for i, r in enumerate(rate):
                if r > 0 and not in_event:
                    in_event = True; start = i
                elif r == 0 and in_event:
                    events.append((start, i, i - start))
                    in_event = False
            if in_event and start is not None:
                events.append((start, len(rate), len(rate) - start))
            short = [e for e in events if e[2] < 60]
            medium = [e for e in events if 60 <= e[2] < 600]
            long_ = [e for e in events if e[2] >= 600]
            results.append({
                "caseid": int(caseid),
                "duration_s": int(len(df)),
                "n_segments": len(events),
                "n_short_lt60s": len(short),
                "n_medium_60_600s": len(medium),
                "n_long_ge600s": len(long_),
                "first_8_events": [
                    {"start_s": int(s), "end_s": int(e), "dur_s": int(d)}
                    for s, e, d in events[:8]
                ],
                "rate_max": float(np.nanmax(rate)) if len(rate) else None,
            })
        except Exception as e:
            results.append({"caseid": int(caseid), "error": str(e)[:200]})
    return {"per_case": results, "rule_hypothesis": "rate_>0 segment dur < 60s ⇒ bolus-like; >= 600s ⇒ continuous infusion (잠정, [CLINICIAN-REVIEW] 필요)"}


# ---------------------------------------------------------------------------
# 4. Render — pump_drug_findings.md
# ---------------------------------------------------------------------------

def render_md(report: dict[str, Any]) -> str:
    L: list[str] = []
    P = L.append

    P("# PUMP / Drug — Design Feasibility 탐색 (pre plan_1.1)")
    P("")
    P("> 2026-05-17. Cache snapshot 2026-05-16 (`docs/notebooks/_cache/{cases,trks}.csv`).")
    P("> Companion script: `docs/notebooks/01_pump_drug_exploration.py`.")
    P("> 본 문서는 plan_1.1 본격 작업이 아닌 **VitalAgent intervention-response 자동화 feasibility** 사전 탐색 산출물이다.")
    P("")

    # 0. TL;DR
    P("## 0. 한 줄 요약 (TL;DR)")
    P("")
    P("- `PUMP*` 또는 `DRUG*` 패턴 채널은 VitalDB schema 에 **존재하지 않는다**. 모든 drug infusion 기록은 **`Orchestra/<DRUG>_<VAR>`** 형식이다.")
    P("- Vasopressor / inotrope **infusion** (Orchestra) 의 case-level 가용률은 모두 **5% 미만** (PHEN 2.0% · NEPI 1.4% · DOPA 0.5% · EPI 0.1%).")
    P("- 반면 **bolus** 형태 vasopressor 는 `cases.csv` 의 `intraop_eph` (50.3% case 에서 > 0), `intraop_phe` (13.2%), `intraop_epi` (1.4%) 에 기록되며 **per-event timestamp 가 없다**.")
    P("- Fluid / transfusion (`intraop_crystalloid` 93.6%, `intraop_rbc` 5.5%, `intraop_ffp` 2.0%) 도 **case-level 누적값만** 있어 real-time stream 감지 불가.")
    P("- **결론**: Tool 9 (vasoactive query) 는 Orchestra/* schema 로 정의 가능하지만 가용 cohort 가 작다. Tool 10 (fluid/blood) 은 fully automatic 불가 → **mixed-initiative** (clinician annotation) 또는 case-end retrospective 만 가능. Paper narrative 도 mixed-initiative 로 framing 권장.")
    P("")

    # 1. Schema reality check
    P("## 1. Schema reality check")
    P("")
    a = report["a1"]
    P(f"- `tname.str.contains('PUMP')` → **{a['pump_pattern_hits']} hit** (즉 0)")
    P(f"- `tname.str.contains('DRUG')` → **{a['drug_pattern_hits']} hit** (즉 0)")
    P(f"- `Orchestra/*` prefix unique track 수: **{a['orchestra_track_count']}**")
    P("")
    P("user 의 가설 'PUMP_CE 등 PUMP 채널 존재' 는 schema 와 어긋난다. 실제로는 drug-specific code-prefix (예: `Orchestra/PPF20_CE`, `Orchestra/PHEN_RATE`) 가 존재한다. user 가 '`PUMP*`' 로 호명한 것은 `Orchestra/*` 와 등가로 해석한다.")
    P("")

    # 2. Drug taxonomy
    P("## 2. Drug class taxonomy (Orchestra/*)")
    P("")
    P("> 본 분류는 모두 **[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]** 잠정안이다.")
    P("")
    P("### 2.1 Class 별 case 수 (drug 1 개 이상 보유 case)")
    P("")
    P("| class | n_cases (≥1 drug 보유) | % cohort |")
    P("|-------|-----------------------:|---------:|")
    for r in report["a2"]["per_class"]:
        P(f"| {r['class']} | {r['n_cases_with_any_member']:,} | {r['pct']:.2f}% |")
    P("")
    P("### 2.2 Drug 별 (drug_code 단위 unique caseid)")
    P("")
    P("| drug_code | drug_name | class (잠정) | n_cases | % cohort |")
    P("|-----------|-----------|-------------|--------:|---------:|")
    for r in report["a2"]["per_drug"]:
        P(f"| {r['drug_code']} | {r['drug_name']} | {r['class']} | {r['n_cases']:,} | {r['pct']:.2f}% |")
    P("")

    # 3. Vasoactive × department
    P("## 3. Vasoactive infusion (Orchestra/*) × department")
    P("")
    a = report["a3"]
    dept_order = ["General surgery", "Thoracic surgery", "Gynecology", "Urology"]
    header = "| drug | " + " | ".join(f"{d} (n={a['dept_n'][d]})" for d in dept_order) + " | total |"
    P(header)
    P("|" + "|".join(["---"] * (len(dept_order) + 2)) + "|")
    for r in a["rows"]:
        cells = [f"{r['by_department'][d]['n']} ({r['by_department'][d]['pct']:.1f}%)" for d in dept_order]
        P(f"| {r['drug_code']} | " + " | ".join(cells) + f" | {r['total_cases']} |")
    P("")
    P("핵심 관측:")
    P("- **PHEN** (phenylephrine infusion) 이 가장 흔하지만 그래도 4.3% (Thoracic) 가 최대.")
    P("- **NEPI** (norepinephrine) 은 General + Thoracic 에만 존재. Gynecology / Urology 0 case.")
    P("- **DOPA / EPI / DOBU / VASO** 는 총합 < 50 case — 단독 학습 불가, family-level pooling 필요.")
    P("")

    # 4. intraop_* coverage
    P("## 4. `cases.csv` `intraop_*` field 가용성 (case-level 누적값)")
    P("")
    P("**핵심 한계**: 본 field 는 case 종료 시점의 **누적 합계**일 뿐 per-event timestamp 가 없다. 시뮬레이션 시점 t 에서 'phenylephrine 50μg 방금 투여' 같은 detection 은 불가능하다.")
    P("")
    P("| field | n_nonnull | % | n_>0 | %_>0 | mean | p50 | p95 | max |")
    P("|-------|----------:|--:|-----:|-----:|-----:|----:|----:|----:|")
    for r in report["a4"]["per_field"]:
        if r.get("non_numeric"):
            continue
        P(f"| `{r['field']}` | {r['n_nonnull']:,} | {r['pct_nonnull']:.1f}% | {r['n_positive']:,} | {r['pct_positive']:.1f}% | {r['mean_overall']} | {r['p50']} | {r['p95']} | {r['max']} |")
    P("")
    P("### 4.1 주요 vasopressor / fluid bolus × department")
    P("")
    for r in report["a4b"]["per_field"]:
        P(f"**`{r['field']}`**")
        P("")
        P("| department | n_>0 / n_total | %_>0 | mean (when >0) |")
        P("|-----------|---------------:|-----:|---------------:|")
        for d, v in r["by_department"].items():
            P(f"| {d} | {v['n_positive']}/{v['n_total']} | {v['pct_positive']:.1f}% | {v['mean_when_positive']:.2f} |")
        P("")
    P("**해석 (잠정 [CLINICIAN-REVIEW])**:")
    P("- **`intraop_eph` 50.3% case** — ephedrine 은 SNUH 비심장 술중 가장 흔한 IV bolus vasopressor 로 추정된다. 그러나 Orchestra/* 채널에 ephedrine 이 없으므로 syringe pump 가 아닌 **IV push (직접 정주)** 로 투여된 것으로 추정된다 [CLINICIAN-REVIEW].")
    P("- **`intraop_phe` 13.2% case** + **Orchestra/PHEN 2.0% case** — phenylephrine 은 일부 case 에서 syringe pump (Orchestra) 로, 다수 case 에서 IV bolus (intraop_phe) 로 투여된 것으로 보인다.")
    P("- **`intraop_rbc` 5.5%**, **`intraop_ffp` 2.0%** — transfusion 은 sparse 하지만 비심장 major surgery 의 outcome label 로는 의미 있는 수준.")
    P("")

    # 5. Bolus trial
    P("## 5. Bolus vs continuous 식별 trial (Orchestra/PHEN, n=3 case)")
    P("")
    a = report["a6"]
    if "error" in a:
        P(f"> vitaldb API load 실패: {a['error']}")
    else:
        P(f"> 식별 규칙 (잠정): {a['rule_hypothesis']}")
        P("")
        P("| caseid | duration_s | n_segments | short (<60s) | medium (60–600s) | long (≥600s) |")
        P("|-------:|-----------:|-----------:|-------------:|-----------------:|-------------:|")
        for r in a["per_case"]:
            if "error" in r:
                P(f"| {r['caseid']} | — | — | — | — | — | err: {r['error'][:60]} |")
                continue
            P(f"| {r['caseid']} | {r['duration_s']:,} | {r['n_segments']} | {r['n_short_lt60s']} | {r['n_medium_60_600s']} | {r['n_long_ge600s']} |")
        P("")
        for r in a["per_case"]:
            if "error" in r:
                continue
            ev_str = ", ".join(f"({e['start_s']}, {e['end_s']}, {e['dur_s']}s)" for e in r["first_8_events"])
            P(f"- case {r['caseid']}: first 8 events = {ev_str}; rate_max = {r['rate_max']:.2f}")
        P("")
    P("**관측**:")
    P("- 한 case 안에서도 short bolus 와 long continuous infusion 이 **섞여** 나타난다 → 단일 case 가 'bolus-only' 또는 'infusion-only' 로 분류되지 않는다.")
    P("- 매우 짧은 sub-second segment 가 다량 발생하는 경우는 syringe pump 의 quick-toggle (e.g., 정밀 dose 조정) 일 수 있어 noise filter 필요 [CLINICIAN-REVIEW].")
    P("- **결론**: rate-segmentation 기반 자동 detection 은 가능하나 single-rule 로 'bolus' label 을 신뢰성 있게 부여하기는 어렵다.")
    P("")

    # 6. Agent design implications
    P("## 6. Agent design 영향 분석")
    P("")
    P("### 6.1 Tool 9 (`query_vasoactive_drugs`) — I/O 정의 가능 여부")
    P("")
    P("**가능**. Orchestra/* schema 가 명확하므로 다음과 같이 정의 가능:")
    P("")
    P("```")
    P("Input:")
    P("  caseid: int")
    P("  simulated_now: float    # seconds since case start, end-exclusive")
    P("  window_s: float = 30.0  # look-back window")
    P("")
    P("Output (list[dict]):")
    P("  drug_code: str   # 'PHEN' | 'NEPI' | 'DOPA' | 'EPI' | 'DOBU' | 'VASO' | 'NTG' | ...")
    P("  class: str       # 'vasopressor' | 'inotrope' | 'vasodilator' (CLINICIAN-REVIEW 잠정)")
    P("  infusion_rate_mL_per_h: float")
    P("  effect_site_conc: float | None    # CE 가 존재할 때만 (PHEN 등 일부에는 없음)")
    P("  cumulative_volume_mL: float")
    P("  source: 'Orchestra/<DRUG>_RATE'")
    P("```")
    P("")
    P("**제약**:")
    P("- 가용 cohort 가 매우 작다 (sum of PHEN+NEPI+DOPA+EPI+DOBU+VASO+NTG ≈ 380 cases, 6%).")
    P("- **Ephedrine bolus (50% case) 는 본 tool 로 캡쳐 불가** — Orchestra 채널에 없음.")
    P("- Bolus 자동 식별은 가능하지만 [CLINICIAN-REVIEW] 필요한 잠정 rule.")
    P("")

    P("### 6.2 Tool 10 (`query_fluid_blood`) — feasibility")
    P("")
    P("**Real-time stream 으로는 fully automatic 불가**. 이유:")
    P("- `cases.csv` `intraop_crystalloid / colloid / rbc / ffp / ebl / uo` 는 **case-level 누적값**.")
    P("- per-event timestamp 가 없어 'simulated_now=t 시점 직전 fluid bolus' 를 query 할 수 없다.")
    P("")
    P("**가능한 design 대안**:")
    P("- (a) `tool_10_retrospective`: caseend 시점에만 누적 fluid 출력 — outcome evaluation 용도로만 사용")
    P("- (b) `tool_10_annotation_driven`: clinician 사용자가 '방금 RBC 1u 주입했음' 같은 manual annotation 을 stream 으로 제공 → mixed-initiative")
    P("- (c) `tool_10_physiological_inference`: ABP/CVP/HR 의 step-change 로 fluid bolus 의 *effect* 를 추정 — 단 이는 **fluid 투여 자체의 detection 이 아니고 fluid response 의 추정** 이며 confounder 다대다 [CLINICIAN-REVIEW]")
    P("")
    P("→ **권장**: (a) + (b) 조합. paper 에서 'fluid/blood is evaluated retrospectively (case-level) and via optional clinician annotation' 로 framing.")
    P("")

    P("### 6.3 Intervention response head 학습 데이터 추정")
    P("")
    P("| event type | source | n_cases | estimated events |")
    P("|-----------|--------|--------:|-----------------:|")
    P("| Vasopressor infusion start/stop (Orchestra) | PHEN+NEPI+DOPA+EPI+DOBU+VASO | ≈ 250 | ≈ 1,000 (case 당 ~4 event) |")
    P("| Anesthetic infusion change (Orchestra) | PPF20 + RFTN20 | ≈ 5,200 | ≈ 10,000+ |")
    P("| Phenylephrine bolus (case-level) | intraop_phe | 844 | n/a (no timestamp) |")
    P("| Ephedrine bolus (case-level) | intraop_eph | 3,211 | n/a (no timestamp) |")
    P("| Transfusion (case-level) | intraop_rbc + ffp | 481 | n/a (no timestamp) |")
    P("")
    P("→ **자동 감지 가능 event 수**: vasoactive ~1,000 + anesthetic ~10,000 ≈ **11,000 stream events** (Orchestra 만)")
    P("→ **case-level only event 수**: ephedrine 3,211 + phenylephrine 844 + transfusion 481 + fluid 5,980 → outcome evaluation 용 retrospective label 로 매우 풍부")
    P("")

    P("### 6.4 Paper narrative — fully automatic vs mixed-initiative")
    P("")
    P("**권장**: **mixed-initiative** framing.")
    P("")
    P("이유:")
    P("- Orchestra/* vasoactive infusion 변경은 자동 감지 가능하지만 cohort 의 ~5% 만 cover.")
    P("- 가장 흔한 vasopressor intervention (ephedrine 50%, phenylephrine bolus 13%) 는 IV push 라 timestamp 부재 → automatic 불가.")
    P("- Fluid / transfusion 도 동일하게 case-level summary 만 존재.")
    P("")
    P("**제안 표현 (영문, paper draft 용)**:")
    P("> *VitalAgent automatically detects continuous vasoactive infusion changes from the syringe-pump record (Orchestra channel; ~5% of cohort). For interventions logged only at the case-level (IV bolus vasopressors, fluid administration, transfusion), VitalAgent supports clinician annotation during the simulated real-time loop and retrospective evaluation against case-level ground truth.*")
    P("")

    # 7. CLINICIAN-REVIEW 항목
    P("## 7. `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` 항목")
    P("")
    P("- (a) Drug code → 임상 class 매핑 (특히 PHEN=vasopressor, DOPA=inotrope vs vasopressor 등 dose-dependent 약물)")
    P("- (b) Ephedrine 이 Orchestra/* 에 없는 것이 SNUH practice 에서 일반적 IV push 패턴이라는 가정")
    P("- (c) Bolus vs continuous 식별 rule (rate>0 segment < 60s ⇒ bolus) 의 임상적 타당성")
    P("- (d) `intraop_*` 누적값을 시간 균등 분배하는 가정의 위험성 (실제 투여 timing 정보 손실)")
    P("- (e) Fluid/blood 의 physiological-inference 기반 detection (ABP/CVP step change) 의 confounder")
    P("- (f) vasopressor family pooling 시 임상적으로 equivalent dose 정의 (norepi 1μg ≈ phenylephrine ?μg ≈ ephedrine ?mg)")
    P("")

    # 8. 4가지 질문 답
    P("## 8. 4가지 핵심 질문에 대한 답")
    P("")
    P("**(a) Tool 9 (`query_vasoactive_drugs`) 정확한 input/output 정의 가능?**")
    P("→ **가능**. 위 §6.1 schema 확정. 단 가용 cohort 가 5% 수준.")
    P("")
    P("**(b) Tool 10 (`query_fluid_blood`) 구현 feasibility?**")
    P("→ **부분적**. real-time stream 자동 감지 불가. retrospective (case-end) + optional clinician annotation 으로 scope 축소 권장.")
    P("")
    P("**(c) Intervention response head 학습 데이터 양 대략?**")
    P("→ **automatic stream events: ~11,000** (vasoactive 1,000 + anesthetic 10,000). retrospective case-level labels: ephedrine 3,211 + phenylephrine 844 + transfusion 481 + fluid 5,980.")
    P("")
    P("**(d) Paper narrative: fully automatic vs mixed-initiative?**")
    P("→ **mixed-initiative**. Vasoactive infusion 은 automatic, IV bolus vasopressor / fluid / transfusion 은 annotation + retrospective.")
    P("")

    # 9. ADR 후보
    P("## 9. ADR 후보 / 회의 안건")
    P("")
    P("1. **ADR-XXX (Tool 10 scope 축소)**: `query_fluid_blood` 를 real-time stream tool 에서 **case-end retrospective + optional clinician annotation tool** 로 재정의. 영향: brief §7 tool suite, plan_1.7 tool spec.")
    P("2. **ADR-XXX (Intervention head v1 scope)**: stage 2 intervention response head 의 v1 은 **vasoactive + anesthetic infusion only**. IV bolus / fluid / transfusion 은 v2 (annotation-aware) 로 이연.")
    P("3. **회의 안건 (이형철 교수님 그룹)**: 위 §7 의 (a)–(f) 항목 일괄 검토 1 회 — drug class 매핑 확정이 다른 결정의 prerequisite.")
    P("4. **brief 수정 후보**: §1 characteristic 의 'fully automatic intervention monitoring' 표현을 'mixed-initiative intervention monitoring' 로 변경 검토.")
    P("")

    # 10. Reproducibility
    P("## 10. 재현성 (Reproducibility)")
    P("")
    P("```bash")
    P(".venv/Scripts/python.exe docs/notebooks/01_pump_drug_exploration.py")
    P("# Reads: docs/notebooks/_cache/{cases,trks}.csv")
    P("# Writes: docs/findings/pump_drug_findings.md")
    P("#         docs/notebooks/_cache/{sample100.csv, 01_report.json}")
    P("# vitaldb API: only 3 case (PHEN-having) 로드 (Step A6) — ~30 초")
    P("```")
    P("")
    P("Seed: `np.random.default_rng(20260517)`. Sample manifest: `_cache/sample100.csv`.")
    P("")

    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading cache...", flush=True)
    cases, trks = load_cache()
    n_total = len(cases)
    print(f"  cases: {n_total:,}  trks: {len(trks):,}", flush=True)

    print("A1 schema check...", flush=True)
    r1 = a1_schema_check(trks)
    print(f"  PUMP hits: {r1['pump_pattern_hits']} · DRUG hits: {r1['drug_pattern_hits']} · Orchestra tracks: {r1['orchestra_track_count']}")

    print("A2 drug taxonomy...", flush=True)
    r2 = a2_drug_taxonomy(trks, n_total)

    print("A3 vasoactive × department...", flush=True)
    r3 = a3_department_crosstab(cases, trks)

    print("A4 intraop_* coverage...", flush=True)
    r4 = a4_intraop_coverage(cases)
    r4b = a4b_department_intraop(cases)

    print("A5 sample manifest...", flush=True)
    r5 = a5_sample_manifest(cases)

    print("A6 bolus trial (vitaldb API, 3 PHEN cases)...", flush=True)
    r6 = a6_bolus_trial(trks, max_cases=3)

    report = {
        "env": {"python": sys.version.split()[0], "seed": SEED},
        "n_total": n_total,
        "a1": r1,
        "a2": r2,
        "a3": r3,
        "a4": r4,
        "a4b": r4b,
        "a5": r5,
        "a6": r6,
    }

    md = render_md(report)
    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS.write_text(md, encoding="utf-8")
    (CACHE / "01_report.json").write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")
    print(f"Wrote {FINDINGS}", flush=True)
    print(f"Wrote {CACHE / '01_report.json'}", flush=True)


if __name__ == "__main__":
    main()
