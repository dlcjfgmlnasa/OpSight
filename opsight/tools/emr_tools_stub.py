"""EMR tools 8–12 — **STUB** placeholder data (plan_1.8 task 5).
EMR tool 8–12 — **STUB** placeholder 데이터 (plan_1.8 task 5).

⚠️ This module returns hard-coded fake EMR data so the LangGraph skeleton
   can call the full 16-tool surface end-to-end. **It is replaced by the real
   implementation in plan_1.3_emr_tools.md.**
⚠️ 본 module은 hard-coded fake EMR data를 반환하여 LangGraph skeleton이
   16-tool surface 전체를 end-to-end로 호출 가능하게 한다. **plan_1.3에서
   실제 구현으로 대체된다.**

Clinical Fact Guard (project_brief §13.1): the fake data here has no clinical
meaning. Any downstream consumer rendering it to a clinician MUST mark it
``[CLINICIAN-REVIEW: 의료진 검토 필요]`` or refuse to render.
임상 사실 가드 (project_brief §13.1): 본 module의 fake data는 임상 의미가
없다. 임상의에게 렌더링하는 모든 consumer는 반드시
``[CLINICIAN-REVIEW: 의료진 검토 필요]`` marker를 부착하거나
렌더링을 거부해야 한다.

The leakage guard (§13.2) is still enforced — time-window queries beyond
``clock.now_s`` will error out, matching the contract the real EMR tools
will follow.
Leakage guard (§13.2)는 여전히 강제된다 — ``clock.now_s`` 이후의 time-window
조회는 error 반환 (real EMR tool 계약과 동일).
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from opsight.tools._leakage_guard import leakage_guard as _shared_leakage_guard
from opsight.tools.envelope import ToolError, ToolRequest, ToolResponse

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


# ── Drug alias maps — Orchestra/Primus signal keys per drug ──
# Sprint 7.12: Tool 8/9 가 signal 에서 약물 사용 정보 추출 (live_view 가 load
# 한 Orchestra/Primus alias 와 raw track 이름 둘 다 인식).
# Each entry: (drug_name, ce_keys, rate_keys, unit_ce, unit_rate, channel).

_ANESTHESIA_DRUGS = [
    ("remifentanil",
     ("RFTN_CE",   "Orchestra/RFTN20_CE"),
     ("RFTN_rate", "Orchestra/RFTN20_RATE"),
     "ng/mL", "mL/h", "Orchestra/RFTN20"),
    ("propofol",
     ("PPF_CE",    "Orchestra/PPF20_CE"),
     ("PPF_rate",  "Orchestra/PPF20_RATE"),
     "mcg/mL", "mL/h", "Orchestra/PPF20"),
    ("sevoflurane",
     ("SEVO_exp",  "Primus/EXP_SEVO"),     # primary: expired concentration
     ("SEVO_insp", "Primus/INSP_SEVO"),    # secondary: inspired
     "%", "%", "Primus/SEVO"),
]

_VASOACTIVE_DRUGS = [
    ("phenylephrine",   ("PHEN", "Orchestra/PHEN_RATE"), "mL/h", "Orchestra/PHEN_RATE"),
    ("norepinephrine",  ("NEPI", "Orchestra/NEPI_RATE"), "mL/h", "Orchestra/NEPI_RATE"),
    ("dopamine",        ("DOPA", "Orchestra/DOPA_RATE"), "mL/h", "Orchestra/DOPA_RATE"),
    ("epinephrine",     ("EPI",  "Orchestra/EPI_RATE"),  "mL/h", "Orchestra/EPI_RATE"),
]


def _find_signal(signal: dict[str, torch.Tensor], aliases: tuple[str, ...]) -> tuple[str, np.ndarray] | None:
    """Return ``(key, numpy_array)`` of the first alias present in ``signal``."""
    for k in aliases:
        if k in signal:
            arr = signal[k].detach().cpu().numpy()
            return k, arr
    return None


def _window_slice(arr: np.ndarray, start_s: float, end_s: float, sr_hz: float = 1.0) -> np.ndarray:
    """Slice ``arr`` to the ``[start_s, end_s]`` window (clamped to bounds)."""
    start_idx = max(0, int(start_s * sr_hz))
    end_idx = min(arr.size, int(end_s * sr_hz) + 1)
    if end_idx <= start_idx:
        return np.array([], dtype=arr.dtype)
    return arr[start_idx:end_idx]


def _last_nonzero_finite_with_idx(arr: np.ndarray) -> tuple[int, float] | None:
    """Return ``(index, value)`` of the most recent finite non-zero sample."""
    if arr.size == 0:
        return None
    finite = np.isfinite(arr) & (arr != 0.0)
    if not finite.any():
        return None
    idx = int(np.where(finite)[0][-1])
    return idx, float(arr[idx])


# ── cases.csv lazy cache (Tool 11 / 12 real-lookup support) ──
# cases.csv 의 lazy cache (Tool 11 / 12 real-lookup 지원).

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CASES_CSV_PATH = _REPO_ROOT / "docs" / "notebooks" / "_cache" / "cases.csv"

# Cached lookup: caseid (int) → dict of cases.csv row.
# 캐시된 lookup: caseid (int) → cases.csv row dict.
_CASES_CACHE: dict[int, dict[str, Any]] | None = None

_CASE_ID_RE = re.compile(r"vitaldb-(\d+)$")


def _extract_vitaldb_case_id(case_id: str) -> int | None:
    """Parse ``"vitaldb-N"`` → int. Returns ``None`` for other id schemes.
    ``"vitaldb-N"`` → int 파싱. 다른 id 형식은 ``None`` 반환.
    """
    m = _CASE_ID_RE.match(case_id)
    return int(m.group(1)) if m is not None else None


def _load_cases_cache() -> dict[int, dict[str, Any]] | None:
    """Lazy-load ``cases.csv`` into ``{caseid: row_dict}``. Cached for process.
    ``cases.csv`` 를 ``{caseid: row_dict}`` 로 lazy load. process 캐시.

    Returns ``None`` when the cache file is absent (CI / fresh checkout) so
    callers can fall back to mock data gracefully.
    cache 파일 부재 시 ``None`` 반환 (CI / fresh checkout) — 호출자가 mock 으로
    graceful fallback 가능.
    """
    global _CASES_CACHE
    if _CASES_CACHE is not None:
        return _CASES_CACHE
    if not _CASES_CSV_PATH.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(_CASES_CSV_PATH)
    except Exception:
        return None
    if "caseid" not in df.columns:
        return None
    df = df.set_index("caseid")
    _CASES_CACHE = {int(k): _row_to_dict(v) for k, v in df.iterrows()}
    return _CASES_CACHE


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a pandas Series row to a plain dict (NaN → None)."""
    import math
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            out[k] = None
        else:
            out[k] = v
    return out


# ── Helper / 헬퍼 ──


def _leakage_guard(
    request: ToolRequest, clock: SimClock, query_window_end_s: float
) -> ToolResponse | None:
    """Refuse queries whose window extends past the current sim-time.
    현재 sim-time 이후를 포함하는 window 조회를 거부한다.

    Thin wrapper over the shared ``opsight.tools._leakage_guard`` primitive
    (plan_1.3 task 1) that preserves the EMR ``{"emr_stub": True}`` quality_meta
    marker on the error response.
    공유 leakage guard primitive 의 thin wrapper — EMR ``{"emr_stub": True}``
    marker 보존.
    """
    return _shared_leakage_guard(
        request, clock, query_window_end_s, quality_meta={"emr_stub": True}
    )


def _ok(
    request: ToolRequest,
    result: dict,
    latency_ms: float,
    *,
    clinician_review: bool = True,
) -> ToolResponse:
    """Wrap a success EMR result with the standard ``emr_stub`` marker.
    표준 ``emr_stub`` marker가 부착된 성공 EMR 결과 wrap.
    """
    return ToolResponse(
        case_id=request.case_id,
        sim_time_s=request.sim_time_s,
        tool_name=request.tool_name,
        args=dict(request.args),
        result=result,
        quality_meta={
            "emr_stub": True,
            "clinical_review_required": clinician_review,
        },
        latency_ms=latency_ms,
    )


def _resolve_window(args: dict) -> tuple[float, float]:
    """Extract ``(start_s, end_s)`` from request args; raise on bad shape.
    request args에서 ``(start_s, end_s)`` 추출; 잘못된 shape는 raise.
    """
    tw = args.get("time_window")
    if not (isinstance(tw, (list, tuple)) and len(tw) == 2):
        raise ValueError(f"time_window must be a 2-element list (got {tw!r})")
    return float(tw[0]), float(tw[1])


# ── Tool 8 — query_anesthesia_drugs (real — Orchestra/Primus signal lookup) ──


def tool_query_anesthesia_drugs(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Real anesthesia-drug lookup from Orchestra/Primus tracks (Sprint 7.12).
    Orchestra/Primus 트랙에서 실제 마취제 사용 lookup (Sprint 7.12).

    Returns one entry per drug (remifentanil / propofol / sevoflurane) where
    a non-zero finite sample exists in ``time_window``. Reports the latest CE
    (effect-site concentration) and mean rate over the window.
    """
    t0 = time.perf_counter()
    try:
        start_s, end_s = _resolve_window(request.args)
    except ValueError as exc:
        return ToolResponse(
            case_id=request.case_id, sim_time_s=request.sim_time_s,
            tool_name=request.tool_name, args=dict(request.args),
            error=ToolError(type="invalid_args", message=str(exc)),
            quality_meta={"emr_stub": True},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err

    drugs: list[dict[str, Any]] = []
    for name, ce_aliases, rate_aliases, unit_ce, unit_rate, channel in _ANESTHESIA_DRUGS:
        ce_found = _find_signal(signal, ce_aliases)
        rate_found = _find_signal(signal, rate_aliases)
        if ce_found is None and rate_found is None:
            continue

        latest_ce: float | None = None
        latest_ts: float | None = None
        if ce_found is not None:
            _ce_key, ce_arr = ce_found
            win = _window_slice(ce_arr, start_s, end_s)
            found = _last_nonzero_finite_with_idx(win)
            if found is not None:
                offset, val = found
                latest_ce = val
                latest_ts = start_s + float(offset)

        mean_rate: float | None = None
        if rate_found is not None:
            _rate_key, rate_arr = rate_found
            win = _window_slice(rate_arr, start_s, end_s)
            finite = win[np.isfinite(win) & (win != 0.0)]
            if finite.size > 0:
                mean_rate = float(finite.mean())

        if latest_ce is None and mean_rate is None:
            # Channel present but no non-zero infusion in window — skip.
            continue
        drugs.append({
            "name": name,
            "channel": channel,
            "ce": latest_ce, "ce_unit": unit_ce,
            "mean_rate": mean_rate, "rate_unit": unit_rate,
            "timestamp_s": latest_ts,
        })
    return _ok(
        request,
        {
            "drugs": drugs,
            "window_s": [start_s, end_s],
            "source": "signal_lookup",
            # ADR-021 §"Tool 출력 스키마 강화" — track-channel based, fully
            # observable per-tick. Manual bolus push is out of scope (meta.note).
            "meta": {
                "event_capture_mode": "infusion_track",
                "per_event_timestamps_available": True,
                "clinical_review_required": False,
                "note": (
                    "Track-channel anesthetics only (TIVA / inhalational / "
                    "infusion). Manual IV-push bolus (e.g. midazolam) is "
                    "unobservable in VitalDB tracks — out of scope (ADR-021)."
                ),
            },
        },
        (time.perf_counter() - t0) * 1000,
        clinician_review=False,
    )


# ── Tool 9 — query_vasoactive_drugs (real — Orchestra signal lookup) ──


def tool_query_vasoactive_drugs(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Hybrid vasoactive-drug lookup from Orchestra tracks (Sprint 7.12; ADR-021).
    Orchestra 트랙에서 hybrid vasoactive 약물 lookup (Sprint 7.12; ADR-021).

    Returns one ``events`` entry per vasoactive (phenylephrine / norepinephrine
    / dopamine / epinephrine) with non-zero Orchestra infusion in the window
    (``event_capture_mode = "infusion_track"``). When no infusion channel is
    active the result is ``unobservable_bolus_window = True`` +
    ``event_capture_mode = "stub_bolus_unobservable"`` — manual bolus push is
    the dominant route in the non-cardiac cohort and has no track / timestamp,
    so an empty ``events`` list means *unobserved*, never *confirmed-absent*.

    NB: VitalDB Orchestra coverage of vasoactives is low (PHEN ~2%, NEPI
    ~1.4%, DOPA ~0.5%, EPI ~0.1%) — most cases hit the stub_bolus_unobservable
    path.
    """
    t0 = time.perf_counter()
    try:
        start_s, end_s = _resolve_window(request.args)
    except ValueError as exc:
        return ToolResponse(
            case_id=request.case_id, sim_time_s=request.sim_time_s,
            tool_name=request.tool_name, args=dict(request.args),
            error=ToolError(type="invalid_args", message=str(exc)),
            quality_meta={"emr_stub": True},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err

    events: list[dict[str, Any]] = []
    channels_checked: list[str] = []
    for name, rate_aliases, unit, channel in _VASOACTIVE_DRUGS:
        channels_checked.append(channel)
        rate_found = _find_signal(signal, rate_aliases)
        if rate_found is None:
            continue
        _key, rate_arr = rate_found
        win = _window_slice(rate_arr, start_s, end_s)
        finite_nonzero = win[np.isfinite(win) & (win != 0.0)]
        if finite_nonzero.size == 0:
            continue
        latest_idx = int(np.where(np.isfinite(win) & (win != 0.0))[0][-1])
        events.append({
            "name": name,
            "channel": channel,
            "mean_rate": float(finite_nonzero.mean()),
            "latest_rate": float(win[latest_idx]),
            "rate_unit": unit,
            "timestamp_s": start_s + float(latest_idx),
        })

    # ADR-021 §Risk("Tool 9 hybrid") — hybrid output. When an Orchestra infusion
    # channel carries non-zero infusion we report observed ``events`` in
    # ``infusion_track`` mode. Otherwise the window's vasoactive activity (if
    # any) is manual bolus push (phenylephrine / ephedrine — dominant in the
    # non-cardiac cohort) which has no track and no per-event timestamp:
    # ``unobservable_bolus_window`` + ``stub_bolus_unobservable``.
    # ADR-021 §Risk("Tool 9 hybrid") — hybrid 출력. Orchestra infusion 채널에
    # non-zero infusion 이 있으면 ``infusion_track``, 부재 시 수기 bolus
    # (비심장 cohort 다수) 로 보고 unobservable.
    meta: dict[str, Any]
    if events:
        meta = {
            "event_capture_mode": "infusion_track",
            "per_event_timestamps_available": True,
            "clinical_review_required": False,
        }
        unobservable_bolus_window = False
    else:
        meta = {
            "event_capture_mode": "stub_bolus_unobservable",
            "per_event_timestamps_available": False,
            "clinical_review_required": True,
            "note": (
                "No Orchestra infusion channel active in window. Manual bolus "
                "push (phenylephrine 50-100 ug / ephedrine 5-10 mg) is "
                "unobservable in VitalDB tracks — empty events means "
                "unobserved, NOT confirmed-absent (ADR-021)."
            ),
        }
        unobservable_bolus_window = True

    return _ok(
        request,
        {
            "events": events,
            "unobservable_bolus_window": unobservable_bolus_window,
            "window_s": [start_s, end_s],
            "channels_checked": channels_checked,
            "source": "signal_lookup",
            "meta": meta,
        },
        (time.perf_counter() - t0) * 1000,
        clinician_review=bool(meta["clinical_review_required"]),
    )


# ── Tool 10 — query_fluid_blood (honest reason — not streamable) ──


def tool_query_fluid_blood(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Fluid / blood-product query — *not real-time streamable*.
    수액 / 수혈 조회 — 실시간 streaming *불가*.

    Per `docs/findings/pump_drug_findings.md` (2026-05-17 VitalDB audit):
    VitalDB stores fluid / EBL / urine / transfusion as **case-end aggregates**
    (cases.csv ``intraop_ebl`` / ``intraop_uo`` / ``intraop_crystalloid`` /
    ``intraop_colloid`` / ``intraop_rbc`` etc.) with **no per-event timestamp**.
    Returning these at sim_time < case-end would be data leakage — and even
    estimating "cumulative up to sim_time" by interpolation is fabrication
    because the actual chart events aren't accessible.
    pump_drug_findings audit: VitalDB 의 fluid/EBL/urine 은 case-end
    aggregate 만 (per-event timestamp X). sim_time < case-end 에서 반환은
    leakage; 추정도 chart event 가 없어 fabrication.

    The honest behavior is therefore to refuse the streaming query with a
    structured reason. Downstream brief should hedge ("fluid balance unavailable
    intraoperatively in this dataset; clinician chart annotation required").
    따라서 정직한 동작은 streaming query 거부 + reason marker. downstream brief
    가 hedge ("intraop fluid 가용 X; 임상의 chart annotation 필요").
    """
    t0 = time.perf_counter()
    try:
        start_s, end_s = _resolve_window(request.args)
    except ValueError as exc:
        return ToolResponse(
            case_id=request.case_id, sim_time_s=request.sim_time_s,
            tool_name=request.tool_name, args=dict(request.args),
            error=ToolError(type="invalid_args", message=str(exc)),
            quality_meta={"emr_stub": True},
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    err = _leakage_guard(request, clock, end_s)
    if err is not None:
        return err
    result = {
        "fluids": [],
        "blood_products": [],
        "reason": "fluid_blood_not_streamable",
        "explanation": (
            "VitalDB cases.csv 의 intraop_ebl / intraop_uo / intraop_crystalloid 등은 "
            "case-end aggregate 로만 제공되며 per-event timestamp 가 없다. "
            "Intraoperative streaming query 는 leakage 위험 또는 fabrication "
            "이므로 본 tool 은 빈 결과 + reason marker 반환. "
            "임상의 chart annotation 또는 별도 EMR integration 필요."
        ),
        "window_s": [start_s, end_s],
        "source": "honest_unavailable",
        # ADR-021 §"Tool 출력 스키마 강화" — indefinite stub. The entire
        # fluid / blood / EBL domain is case-end cumulative only (intraop_*),
        # so nothing is observable at sim_time t. Empty == unobservable.
        "meta": {
            "event_capture_mode": "stub_case_end_only",
            "per_event_timestamps_available": False,
            "clinical_review_required": True,
            "note": (
                "VitalDB intraop_* per-event timestamp 부재 — ADR-021. "
                "Empty result means unobservable at sim_time t, NOT "
                "confirmed-absent."
            ),
        },
    }
    return _ok(request, result, (time.perf_counter() - t0) * 1000,
               clinician_review=True)


# ── Tool 11 — query_surgery_progress (real — cases.csv lookup) ──


_MOCK_TOTAL_S: float = 7200.0  # 2h fallback when no case-specific timings


def _surgery_progress_from_case(
    case_row: dict[str, Any], current_time: float
) -> dict[str, Any]:
    """Compute phase / elapsed / remaining from cases.csv timing columns.
    cases.csv 의 timing 컬럼으로 phase / elapsed / remaining 계산.

    Timings (seconds since case recording start):
      ``anestart`` < ``opstart`` <= ``opend`` < ``aneend``

    Phase boundaries:
      sim < anestart           → "pre_anesthesia"
      anestart <= sim < opstart → "induction"
      opstart <= sim <= opend  → "maintenance"
      opend < sim <= aneend    → "emergence"
      sim > aneend             → "post_op"
    """
    anestart = float(case_row.get("anestart") or 0.0)
    opstart = float(case_row.get("opstart") or anestart)
    opend = float(case_row.get("opend") or opstart)
    aneend = float(case_row.get("aneend") or opend)

    if current_time < anestart:
        phase = "pre_anesthesia"
    elif current_time < opstart:
        phase = "induction"
    elif current_time <= opend:
        phase = "maintenance"
    elif current_time <= aneend:
        phase = "emergence"
    else:
        phase = "post_op"

    elapsed_min = max(0.0, (current_time - anestart) / 60.0)
    remaining_min = max(0.0, (aneend - current_time) / 60.0)
    return {
        "phase": phase,
        "elapsed_min": elapsed_min,
        "estimated_remaining_min": remaining_min,
        "anestart_s": anestart,
        "opstart_s": opstart,
        "opend_s": opend,
        "aneend_s": aneend,
        "source": "cases_csv",
    }


def _surgery_progress_fallback(current_time: float, *, reason: str) -> dict[str, Any]:
    """Heuristic phase used when case-specific timing is unavailable.
    Case-specific timing 부재 시 휴리스틱 phase.
    """
    elapsed_min = current_time / 60.0
    if elapsed_min < 15:
        phase = "induction"
    elif elapsed_min > (_MOCK_TOTAL_S / 60.0) - 10:
        phase = "emergence"
    else:
        phase = "maintenance"
    return {
        "phase": phase,
        "elapsed_min": elapsed_min,
        "estimated_remaining_min": max(0.0, (_MOCK_TOTAL_S / 60.0) - elapsed_min),
        "source": "mock_fallback",
        "fallback_reason": reason,
    }


def tool_query_surgery_progress(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Real surgery-progress lookup from ``cases.csv`` (Sprint 7.11).
    cases.csv 에서 실제 surgery-progress lookup (Sprint 7.11).

    Falls back to the prior heuristic when:
      - case_id is not a ``vitaldb-N`` form, or
      - cases.csv cache file is absent, or
      - the integer case id is missing from the cache.

    Leakage guard: query window end == current_time; refused if > clock.now_s.
    """
    t0 = time.perf_counter()
    current_time = float(request.args.get("current_time", clock.now_s))
    err = _leakage_guard(request, clock, current_time)
    if err is not None:
        return err

    cid = _extract_vitaldb_case_id(request.case_id)
    cache = _load_cases_cache() if cid is not None else None
    if cid is None:
        result = _surgery_progress_fallback(
            current_time, reason="case_id_not_vitaldb_form",
        )
    elif cache is None:
        result = _surgery_progress_fallback(
            current_time, reason="cases_csv_missing",
        )
    elif cid not in cache:
        result = _surgery_progress_fallback(
            current_time, reason=f"caseid_{cid}_not_in_cache",
        )
    else:
        result = _surgery_progress_from_case(cache[cid], current_time)
    return _ok(request, result, (time.perf_counter() - t0) * 1000)


# ── Tool 12 — query_patient_baseline (real — cases.csv lookup) ──


def _baseline_from_case(case_row: dict[str, Any]) -> dict[str, Any]:
    """Extract preop demographics / comorbidities / labs from cases.csv row.
    cases.csv row 에서 preop demographics / 동반질환 / lab 추출.
    """
    comorbid: list[str] = []
    # Boolean / 0-1 preop flags → comorbidity list.
    if case_row.get("preop_htn"):
        comorbid.append("HTN")
    if case_row.get("preop_dm"):
        comorbid.append("DM")

    def _f(key: str) -> float | None:
        v = case_row.get(key)
        return float(v) if v is not None else None

    return {
        "age": _f("age"),
        "sex": case_row.get("sex"),
        "asa": _f("asa"),
        "height_cm": _f("height"),
        "weight_kg": _f("weight"),
        "bmi": _f("bmi"),
        "comorbidities": comorbid,
        # Preop labs (subset). Hb in g/dL, Cr in mg/dL — VitalDB native units.
        # Preop lab (부분). VitalDB native unit (Hb g/dL, Cr mg/dL).
        "labs": {
            "hb_g_dl": _f("preop_hb"),
            "cr_mg_dl": _f("preop_cr"),
            "k_meq_l": _f("preop_k"),
            "na_meq_l": _f("preop_na"),
            "alb_g_dl": _f("preop_alb"),
        },
        # Surgery context (useful for downstream prompt — surgery_type already
        # in opsight surgery_context yaml, but optype/department are richer).
        # 수술 맥락 (downstream prompt 용).
        "department": case_row.get("department"),
        "optype": case_row.get("optype"),
        "approach": case_row.get("approach"),
        "ane_type": case_row.get("ane_type"),
        "emop": bool(case_row.get("emop") or False),
        "source": "cases_csv",
    }


def _baseline_fallback(*, reason: str) -> dict[str, Any]:
    """Generic mock baseline used when no per-case data is available.
    per-case 데이터 부재 시 generic mock baseline.
    """
    return {
        "age": 65,
        "sex": "M",
        "asa": 2,
        "comorbidities": ["HTN"],
        "baseline_bp": 130.0,
        "labs": {"hb_g_dl": 12.5, "cr_mg_dl": 0.9},
        "source": "mock_fallback",
        "fallback_reason": reason,
    }


def tool_query_patient_baseline(
    request: ToolRequest,
    clock: SimClock,
) -> ToolResponse:
    """Real patient-baseline lookup from ``cases.csv`` (Sprint 7.11).
    cases.csv 에서 실제 patient baseline lookup (Sprint 7.11).

    Falls back to generic mock baseline when the case is not lookup-able
    (non-``vitaldb-N`` case id, cache file absent, id not in cache). The
    ``meta.source`` field flags whether the values are real or mock — downstream
    prompts (Heavy LLM brief) should cite this when assessment confidence
    depends on patient demographics.
    """
    t0 = time.perf_counter()
    # No time-window for baseline; no leakage guard needed beyond sim_time itself.
    # baseline은 time-window 없음; sim_time 자체 외 leakage guard 불필요.
    cid = _extract_vitaldb_case_id(request.case_id)
    cache = _load_cases_cache() if cid is not None else None
    if cid is None:
        result = _baseline_fallback(reason="case_id_not_vitaldb_form")
    elif cache is None:
        result = _baseline_fallback(reason="cases_csv_missing")
    elif cid not in cache:
        result = _baseline_fallback(reason=f"caseid_{cid}_not_in_cache")
    else:
        result = _baseline_from_case(cache[cid])
    return _ok(request, result, (time.perf_counter() - t0) * 1000)


__all__ = [
    "tool_query_anesthesia_drugs",
    "tool_query_vasoactive_drugs",
    "tool_query_fluid_blood",
    "tool_query_surgery_progress",
    "tool_query_patient_baseline",
]
