"""Signal-state tools (ADR-016, amended 2026-06-10).
신호 상태 tool 패키지 (구 signal_state.py + signal_access_tools.py 병합).

LLM (text-only) 은 raw signal 에 직접 접근할 수 없으므로, 브리프
§[Signal status] / §[Surgery context] / §[Evidence] section 의 정량 claim 을
명시적 tool 호출로 grounded 한다. Per ADR-016 / ADR-011, ``BiosignalFMInterface``
와 무관 (FM Protocol 미사용). 모두 순수 numpy·결정적, time-leakage guard 적용.

6 deterministic tools, laid out so the **folder hierarchy mirrors the call
hierarchy** (한 tool = 한 모듈, modality-agnostic):

    signal_state_tools/
    ├── _common.py             ← 공용 헬퍼 (envelope wrapper / leakage guard / window)
    ├── signal_families.py     ← 신호 종류 taxonomy (alias maps)
    ├── extractors/            ← leaf tool — 각자 signal 을 직접 읽고 서로 호출 안 함
    │   ├── get_current_state      — 현재 vital 스냅샷 (trailing-window 평균)
    │   ├── get_signal_trend       — vital 별 시간적 추세 (slope / 방향 / R²)
    │   ├── describe_signal        — modality window 통계
    │   ├── assess_variability/    — HRV / BPV / SVV (family 별 모듈로 분리)
    │   └── compare_to_baseline    — preop / intraop-early baseline 대비 변화
    └── summarize.py           ← ★ 합성(apex) tool ``summarize_current_state``.
                                  extractors 를 엮어 rule-based 통합 상태 평가.

의존 트리의 꼭대기는 ``summarize_current_state`` 하나뿐이며 (extractors 를 호출),
나머지 5개는 모두 leaf 다. 폴더만 봐도 "누가 누구를 부르는지"가 드러난다.

The package preserves the flat import surface — ``from opsight.tools.signal_state_tools
import tool_get_current_state`` works unchanged (extractors 는 re-export 됨).
"""
from __future__ import annotations

from opsight.tools.signal_state_tools._common import (
    DEFAULT_CURRENT_WINDOW_S,
    DEFAULT_SAMPLING_RATE_HZ,
    DEFAULT_TREND_WINDOW_S,
)
# Leaf tools (extractors) — read the signal directly, no inter-tool calls.
from opsight.tools.signal_state_tools.extractors import (
    tool_assess_variability,
    tool_compare_to_baseline,
    tool_describe_signal,
    tool_get_current_state,
    tool_get_signal_trend,
)
# Composite (apex) tool — synthesizes extractors.
from opsight.tools.signal_state_tools.summarize import (
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
