"""Primitive (leaf) signal-state tools — each reads the raw signal directly.
원시(leaf) 신호 상태 tool — 각자 signal 을 직접 읽는 독립 tool.

이 하위 패키지의 tool 들은 **서로 호출하지 않는다** (의존 트리의 잎). 공용 헬퍼는
상위 패키지의 ``_common`` / ``signal_families`` 를 공유한다. 이들을 합성하는 상위
tool(``summarize_current_state``)은 패키지 루트에 위치한다 — 폴더 계층이 곧 호출 계층.

- ``get_current_state``   — 현재 vital 스냅샷 (trailing-window 평균).
- ``get_signal_trend``    — vital 별 시간적 추세 (slope / 방향 / R²).
- ``describe_signal``     — modality window 통계.
- ``assess_variability``  — HRV / BPV / SVV (family 별 모듈로 분리).
- ``compare_to_baseline`` — preop / intraop-early baseline 대비 변화.
"""
from __future__ import annotations

from opsight.tools.signal_state_tools.extractors.assess_variability import (
    tool_assess_variability,
)
from opsight.tools.signal_state_tools.extractors.compare_to_baseline import (
    tool_compare_to_baseline,
)
from opsight.tools.signal_state_tools.extractors.describe_signal import (
    tool_describe_signal,
)
from opsight.tools.signal_state_tools.extractors.get_current_state import (
    tool_get_current_state,
)
from opsight.tools.signal_state_tools.extractors.get_signal_trend import (
    tool_get_signal_trend,
)

__all__ = [
    "tool_get_current_state",
    "tool_get_signal_trend",
    "tool_describe_signal",
    "tool_assess_variability",
    "tool_compare_to_baseline",
]
