"""Signal-state tools (ADR-016, amended 2026-06-10).
신호 상태 tool 패키지 (구 signal_state.py + signal_access_tools.py 병합).

LLM (text-only) 은 raw signal 에 직접 접근할 수 없으므로, 브리프
§[Signal status] / §[Surgery context] / §[Evidence] section 의 정량 claim 을
명시적 tool 호출로 grounded 한다. Per ADR-016 / ADR-011, ``BiosignalFMInterface``
와 무관 (FM Protocol 미사용). 모두 순수 numpy·결정적, time-leakage guard 적용.

6 deterministic tools. Each tool module is named after its registered tool name
(one tool = one module, modality-agnostic; 공용 헬퍼는 ``_common``); the
signal-type taxonomy lives in ``signal_families``.
각 tool 모듈은 등록된 tool 이름과 동일하게 명명 (한 tool = 한 모듈, modality-agnostic):
- ``get_current_state``      (get_current_state.py)      — 현재 vital 스냅샷 (trailing-window 평균).
- ``get_signal_trend``       (get_signal_trend.py)       — vital 별 시간적 추세 (slope / 방향 / R²).
- ``describe_signal``        (describe_signal.py)        — modality window 통계.
- ``assess_variability``     (assess_variability/)       — HRV / BPV / SVV (family 별 모듈로 분리).
- ``compare_to_baseline``    (compare_to_baseline.py)    — preop / intraop-early baseline 대비 변화.
- ``summarize_current_state``(summarize_current_state.py)— rule-based 통합 현재 상태 평가.

The package preserves the flat import surface — ``from opsight.tools.signal_state_tools
import tool_get_current_state`` works unchanged.
"""
from __future__ import annotations

from opsight.tools.signal_state_tools._common import (
    DEFAULT_CURRENT_WINDOW_S,
    DEFAULT_SAMPLING_RATE_HZ,
    DEFAULT_TREND_WINDOW_S,
)
from opsight.tools.signal_state_tools.assess_variability import tool_assess_variability
from opsight.tools.signal_state_tools.compare_to_baseline import tool_compare_to_baseline
from opsight.tools.signal_state_tools.describe_signal import tool_describe_signal
from opsight.tools.signal_state_tools.get_current_state import tool_get_current_state
from opsight.tools.signal_state_tools.get_signal_trend import tool_get_signal_trend
from opsight.tools.signal_state_tools.summarize_current_state import (
    tool_summarize_current_state,
)

__all__ = [
    "tool_get_current_state",
    "tool_get_signal_trend",
    "tool_describe_signal",
    "tool_assess_variability",
    "tool_compare_to_baseline",
    "tool_summarize_current_state",
    "DEFAULT_SAMPLING_RATE_HZ",
    "DEFAULT_CURRENT_WINDOW_S",
    "DEFAULT_TREND_WINDOW_S",
]
