"""Tool: assess_variability — routes a modality to its family's variability math.
modality 를 해당 family 의 변동성 수학으로 라우팅한다.

Unlike the other signal-state tools (which are modality-agnostic), variability
is genuinely per-family: HR→HRV, MAP/ABP/CVP/PAP→BPV, PPG→SVV. Each family's
math lives in its own module (``hrv``/``bpv``/``svv``); this package's
``__init__`` is the thin routing + envelope layer that combines them.
다른 signal-state tool 과 달리 변동성은 family 별 수학이 실재한다 (HR→HRV,
MAP/ABP/CVP/PAP→BPV, PPG→SVV). family 별 수학은 각 모듈(``hrv``/``bpv``/``svv``)에
있고, 본 ``__init__`` 은 이를 합치는 thin 라우팅 + envelope 계층이다.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from opsight.envelope import ToolRequest, ToolResponse
from opsight.tools.signal_state_tools._common import (
    _error_response,
    _leakage_guard,
    _ok,
    _to_numpy,
)
from opsight.tools.signal_state_tools.signal_families import (
    _ABP_ALIASES,
    _CVP_ALIASES,
    _HR_ALIASES,
    _PAP_ALIASES,
    _PPG_ALIASES,
)
from opsight.tools.signal_state_tools.extractors.assess_variability.bpv import bpv_metrics
from opsight.tools.signal_state_tools.extractors.assess_variability.hrv import hrv_metrics
from opsight.tools.signal_state_tools.extractors.assess_variability.svv import svv_metrics

if TYPE_CHECKING:
    import torch

    from opsight.sim_clock import SimClock


def tool_assess_variability(
    request: ToolRequest,
    clock: SimClock,
    signal: dict[str, torch.Tensor],
) -> ToolResponse:
    """Variability metrics per modality (HRV / BPV / SVV).
    Modality 별 변동성 metric (HRV / BPV / SVV).
    """
    t0 = time.perf_counter()
    err = _leakage_guard(request, clock, float(request.sim_time_s))
    if err is not None:
        return err

    modality = request.args.get("modality")
    if not isinstance(modality, str):
        return _error_response(
            request, "invalid_args", "modality must be a string",
            (time.perf_counter() - t0) * 1000.0,
        )

    # HR family → HRV
    if modality in _HR_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = hrv_metrics(arr)
        meta: dict[str, Any] = {
            "modality": modality,
            "modality_class": "HR",
            # Self-implemented HRV (time-domain SDNN/RMSSD + Welch-PSD LF/HF).
            # No external HRV library. LF/HF is None for short / flat series.
            "implementation": "numpy_welch_psd",
        }
    # ABP/MAP family → BPV
    elif modality in _ABP_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = bpv_metrics(arr)
        meta = {"modality": modality, "modality_class": "MAP",
                "implementation": "numpy"}
    # PPG family → amplitude/SVV
    elif modality in _PPG_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = svv_metrics(arr)
        meta = {"modality": modality, "modality_class": "PPG",
                "implementation": "numpy"}
    # CVP / PAP → BPV-style variability (SD + ARV).
    # [CLINICIAN-REVIEW: 의료진 검토 필요] — CVP는 호흡 swing 분리,
    # PAP는 pulmonary HTN context와 함께 해석 필요.
    elif modality in _CVP_ALIASES or modality in _PAP_ALIASES:
        if modality not in signal:
            return _error_response(
                request, "invalid_args",
                f"modality {modality!r} not in signal",
                (time.perf_counter() - t0) * 1000.0,
            )
        arr = _to_numpy(signal[modality])
        metrics = bpv_metrics(arr)
        modality_class = "CVP" if modality in _CVP_ALIASES else "PAP"
        meta = {"modality": modality, "modality_class": modality_class,
                "implementation": "numpy"}
    else:
        return _error_response(
            request, "invalid_args",
            f"modality {modality!r} not supported (use HR / MAP / ABP / PPG / CVP / PAP family)",
            (time.perf_counter() - t0) * 1000.0,
        )

    result = {"metrics": metrics, "meta": meta}
    return _ok(request, result, (time.perf_counter() - t0) * 1000.0)


__all__ = ["tool_assess_variability"]
