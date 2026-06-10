"""LLM client Protocol + factory (Sprint 6 follow-up: vLLM wiring sketch).
LLM client Protocol + factory (Sprint 6 follow-up: vLLM wiring sketch).

Agent / node code depends ONLY on the :class:`LLMClient` Protocol; the
concrete implementation (vLLM-backed Llama 8B/70B) is selected by config.
The mock/placeholder template LLM was removed.
agent / node code 는 :class:`LLMClient` Protocol 에만 의존; concrete 구현
(vLLM Llama) 은 config 로 선택. mock/placeholder template LLM 은 제거됨.

Config schema / Config 스키마::

    {
      "llm": {
        "implementation": "vllm",
        "shallow": {
          "endpoint": "http://gpu1:8000/v1",
          "model": "meta-llama/Llama-3.1-8B-Instruct",
          "system_prompt_path": "prompts/v1_light_shallow.md",
          "max_tokens": 80,
          "temperature": 0.1,
        },
        "deep": {
          "endpoint": "http://gpu2:8000/v1",
          "model": "meta-llama/Llama-3.3-70B-Instruct",
          "system_prompt_path": "prompts/v2_heavy_deep_brief.md",
          "max_tokens": 900,
          "temperature": 0.2,
        }
      }
    }

⚠️ Real deployment requires 2× L40S 48GB. Wiring 만 구현 + mock unit test 가능.
   실 배포 hardware 없이도 *interface* 와 *prompt 구성* 은 모두 검증됨.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from opsight.tools.envelope import ToolResponse


@runtime_checkable
class LLMClient(Protocol):
    """Common LLM surface satisfied by the vLLM-backed client.
    vLLM 기반 client 가 만족하는 공통 LLM surface.
    """

    name: str

    def narrate(self, tool_results: list[ToolResponse]) -> str:
        """Generate one-sentence Korean narration for shallow loop.
        Shallow loop 용 1 문장 한글 narration 생성.

        Returns ≤ 50 token sentence with tone band prefix (안정/주의/경고/위험).
        """
        ...

    def brief(
        self,
        tool_results: list[ToolResponse],
        *,
        surgery_type: str,
        surgery_phase: str,
        elapsed_min: float,
    ) -> dict[str, str]:
        """Generate 9-section Korean brief for deep mode.
        Deep mode 용 9 section 한글 brief 생성.

        Returns dict from section name → Korean prose. All 9 sections must be
        present (parser fills "" if absent).
        section name → 한글 본문 dict. 9 section 모두 존재 (parser 가 빈 값 채움).
        """
        ...


# ── Config dataclasses / Config dataclass ──


def create_llm_client(config: dict[str, Any]) -> LLMClient:
    """Instantiate an LLM client per ``config["llm"]["implementation"]``.
    ``config["llm"]["implementation"]`` 으로 LLM client 인스턴스화.

    Args:
        config: dict with at minimum::

            {"llm": {"implementation": "vllm",
                     "shallow": {...}, "deep": {...}}}

    Returns:
        Concrete client implementing :class:`LLMClient`.

    Raises:
        ValueError: ``implementation`` is not a known kind.
        NotImplementedError: kind valid but module missing (e.g. vllm imports fail).
    """
    llm_section = config.get("llm")
    if not isinstance(llm_section, dict):
        raise ValueError(
            "config must contain 'llm' object with 'implementation' key. "
            f"got: {type(llm_section).__name__}"
        )
    impl = llm_section.get("implementation", "vllm")
    known = ("vllm",)
    if impl not in known:
        raise ValueError(
            f"Unknown LLM implementation: {impl!r}. Expected one of {list(known)} "
            f"(mock/placeholder LLM was removed)."
        )

    try:
        from opsight.llm.vllm_client import VLLMClient
    except ImportError as exc:
        raise NotImplementedError(
            "vLLM client requires `openai` Python package "
            "(pip install openai). Import failed."
        ) from exc
    return VLLMClient(
        shallow_config=llm_section.get("shallow") or {},
        deep_config=llm_section.get("deep") or {},
    )


__all__ = ["LLMClient", "create_llm_client"]
