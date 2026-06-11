"""Shared internals for the emr_tools package (EMR / preoperative context).
emr_tools 패키지 공용 내부 (EMR / 수술 전 환자 컨텍스트).

The EMR tool group (구 tools 8–12) was deferred to Stage 2 in the false-alarm-agent
rebuild. ``get_patient_context`` is brought forward as the first revived member
because it reads **only preoperative, leakage-free** case metadata.
EMR tool 그룹(구 8–12)은 Stage 2 로 deferred 됐으나, ``get_patient_context`` 는
**수술 전(preop)·누수 0** 메타데이터만 읽으므로 먼저 부활시킨다.

⚠️ Leakage contract / 누수 계약:
   VitalDB ``cases`` 메타데이터는 한 행 안에 preop 정보와 **postop/outcome/누적
   intraop** 값을 함께 담는다. emr tool 은 ``PREOP_SAFE_FIELDS`` 화이트리스트 컬럼만
   읽고 ``LEAKAGE_FORBIDDEN_FIELDS`` 는 구조적으로 절대 surface 하지 않는다 — 이것이
   시간 가드가 아닌 **컬럼 가드**로서의 누수 방어다 (project_brief §13.2).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from opsight.envelope import (
    ToolRequest,
    ToolResponse,
    error_response as _shared_error_response,
    ok as _shared_ok,
)

# Data source — cache-first, mirroring scripts/build_cohort.py::load_cases.
# _common.py 는 opsight/tools/emr_tools/ 아래 → repo root 는 parents[3].
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CACHE_PATH = _REPO_ROOT / "docs" / "notebooks" / "_cache" / "cases.csv"
_CASES_URL = "https://api.vitaldb.net/cases"

# Preop-safe whitelist — the ONLY case columns any emr tool may surface.
# 수술 전 확정 + 누수 0 컬럼만. (VitalDB 공식 컬럼명)
PREOP_SAFE_FIELDS: tuple[str, ...] = (
    "age", "sex", "bmi", "asa", "department", "opname", "dx",
)

# Never-read columns — postop/outcome/timing + ALL cumulative ``intraop_*``
# totals (case-final, not a time series). Reading any at sim-time t leaks the
# future. Enumerated so a test can assert none ever appears in a result.
# 절대 읽지 않는 컬럼 — postop/outcome/timing + 모든 ``intraop_*`` 누적총량.
LEAKAGE_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "casestart", "caseend", "anestart", "aneend", "opstart", "opend",
    "adm", "dis", "icu_days", "death_inhosp",
    "intraop_ebl", "intraop_uo", "intraop_rbc", "intraop_ffp",
    "intraop_crystalloid", "intraop_colloid", "intraop_ppf", "intraop_mdz",
    "intraop_ftn", "intraop_rocu", "intraop_vecu", "intraop_eph",
    "intraop_phe", "intraop_epi", "intraop_ca",
})

# Fields surfaced as integers (VitalDB stores them as numeric).
INT_FIELDS: frozenset[str] = frozenset({"age", "asa"})

_CASES_CACHE: Any = None  # lazily-loaded pandas DataFrame (process-wide)


def load_cases() -> Any | None:
    """Load VitalDB case metadata (cache-first); ``None`` if unavailable.
    VitalDB case 메타데이터 로드 (cache 우선); 불가 시 ``None``.

    Cache (``docs/notebooks/_cache/cases.csv``) 가 있으면 그것을, 없으면 1회
    fetch 후 cache. pandas 부재 / 네트워크 실패 등 어떤 이유로든 못 읽으면 ``None``
    을 반환하고, tool 은 ``missing_dependency`` 로 graceful degrade 한다.
    """
    global _CASES_CACHE
    if _CASES_CACHE is not None:
        return _CASES_CACHE
    try:
        import pandas as pd
    except Exception:
        return None
    try:
        if _CACHE_PATH.exists():
            _CASES_CACHE = pd.read_csv(_CACHE_PATH)
            return _CASES_CACHE
        df = pd.read_csv(_CASES_URL)
        try:  # best-effort cache write; failure is non-fatal
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(_CACHE_PATH, index=False)
        except Exception:
            pass
        _CASES_CACHE = df
        return _CASES_CACHE
    except Exception:
        return None


def _ok(
    request: ToolRequest,
    result: dict[str, Any],
    latency_ms: float,
    *,
    quality_meta: dict[str, Any] | None = None,
) -> ToolResponse:
    """Success envelope with ``category="emr"`` baked in."""
    return _shared_ok(request, result, latency_ms, category="emr",
                      quality_meta=quality_meta)


def _error_response(
    request: ToolRequest,
    err_type: str,
    message: str,
    latency_ms: float,
    *,
    extra: dict[str, Any] | None = None,
) -> ToolResponse:
    """Failure envelope with ``category="emr"`` baked in."""
    return _shared_error_response(request, err_type, message, latency_ms,
                                  category="emr", extra=extra)


__all__ = [
    "PREOP_SAFE_FIELDS",
    "LEAKAGE_FORBIDDEN_FIELDS",
    "INT_FIELDS",
    "load_cases",
]
