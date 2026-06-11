"""LLM client Protocol + vLLM wiring.
LLM client Protocol + vLLM wiring.

Mock/placeholder LLM removed — narration / brief are produced by the real
vLLM-backed client only (or skipped when no client is wired).
Mock/placeholder LLM 제거 — narration / brief 는 실제 vLLM client 로만 생성
(client 미연결 시 생략).
"""
from opsight.llm.client import LLMClient, create_llm_client

__all__ = [
    "LLMClient",
    "create_llm_client",
]
