"""LLM client + placeholder template + vLLM wiring (Sprint 6).
LLM client + placeholder template + vLLM wiring (Sprint 6).
"""
from opsight.llm.client import LLMClient, create_llm_client
from opsight.llm.placeholder import render_deep_brief, render_shallow_narration
from opsight.llm.placeholder_client import PlaceholderClient

__all__ = [
    "LLMClient",
    "create_llm_client",
    "PlaceholderClient",
    "render_shallow_narration",
    "render_deep_brief",
]
