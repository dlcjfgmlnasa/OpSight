"""PlaceholderClient — wraps placeholder template functions in LLMClient surface.
PlaceholderClient — placeholder template 함수를 LLMClient surface 로 wrap.

Sprint 6 follow-up: `opsight.llm.client.LLMClient` Protocol 호환 wrapper.
기존 `placeholder.py` 의 함수 그대로 사용; 본 wrapper 는 instance 형식만 제공.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from opsight.llm.placeholder import render_deep_brief, render_shallow_narration

if TYPE_CHECKING:
    from opsight.tools.envelope import ToolResponse


class PlaceholderClient:
    """LLMClient impl backed by template rendering (no LLM call).
    Template 렌더링 기반 LLMClient 구현 (LLM 호출 없음).
    """

    name: str = "placeholder"

    def narrate(self, tool_results: list[ToolResponse]) -> str:
        return render_shallow_narration(tool_results)

    def brief(
        self,
        tool_results: list[ToolResponse],
        *,
        surgery_type: str,
        surgery_phase: str,
        elapsed_min: float,
    ) -> dict[str, str]:
        return render_deep_brief(
            tool_results,
            surgery_type=surgery_type,
            surgery_phase=surgery_phase,
            elapsed_min=elapsed_min,
        )


__all__ = ["PlaceholderClient"]
