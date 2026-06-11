"""vLLM-backed LLM client (Sprint 6 wiring sketch — real deployment pending hardware).
vLLM 기반 LLM client (Sprint 6 wiring sketch — 실 배포는 hardware 대기).

Talks to vLLM's OpenAI-compatible HTTP server. Both Light (Llama-3.1-8B) and
Heavy (Llama-3.3-70B) are served via separate vLLM processes (different
endpoints; same OpenAI Chat Completions schema). This client routes:
- ``narrate()`` → shallow endpoint (Light, ≤ 80 tokens)
- ``brief()``   → deep endpoint (Heavy, 500–800 tokens, 9-section parsing)

vLLM 의 OpenAI 호환 HTTP server 와 통신. Light (Llama-3.1-8B) + Heavy (Llama-3.3-70B)
는 별도 vLLM 프로세스 (endpoint 분리; OpenAI Chat Completions schema 동일).

⚠️ Real deployment hardware: 2× L40S 48GB (one per model, 4-bit quantized).
   본 module 은 wiring + interface 검증; vLLM server 미실행 시에도 unit test
   가능 (`openai.OpenAI` 를 mock 으로 교체).

System prompt loading:
- ``shallow.system_prompt_path`` → ``prompts/v1_light_shallow.md`` (default)
- ``deep.system_prompt_path``    → ``prompts/v2_heavy_deep_brief.md`` (default)

Prompt 파일 부재 시: ``narrate`` / ``brief`` 호출이 ``FileNotFoundError`` 발생.
prompt 파일은 plan_1.6 / v2 산출물 (이미 작성됨).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opsight.envelope import ToolResponse


REPO_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_SHALLOW = {
    "endpoint": "http://localhost:8000/v1",
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "system_prompt_path": "prompts/v1_light_shallow.md",
    "max_tokens": 80,
    "temperature": 0.1,
    "timeout_s": 8.0,  # Shallow latency budget 15s, leave headroom
}

_DEFAULT_DEEP = {
    "endpoint": "http://localhost:8001/v1",
    "model": "meta-llama/Llama-3.3-70B-Instruct",
    "system_prompt_path": "prompts/v2_heavy_deep_brief.md",
    "max_tokens": 900,
    "temperature": 0.2,
    "timeout_s": 50.0,  # Deep budget 60s
}


# 9-section header pattern for deep brief parser.
# Heavy LLM 의 9-section header 패턴 (정확히 영문 header 유지).
_BRIEF_SECTIONS: tuple[str, ...] = (
    "Surgery context",
    "Signal status",
    "Assessment confidence",
    "Risk evaluation",
    "Evidence",
    "Intraoperative context",
    "Similar trajectory",
    "Recommendations",
    "Limitations",
)


class VLLMClient:
    """OpenAI-compatible client routed to vLLM Light + Heavy endpoints.
    OpenAI 호환 client. vLLM Light + Heavy endpoint 로 routing.
    """

    name: str = "vllm"

    def __init__(
        self,
        *,
        shallow_config: dict[str, Any] | None = None,
        deep_config: dict[str, Any] | None = None,
        _openai_factory: Any = None,  # for test injection
    ) -> None:
        self._shallow = {**_DEFAULT_SHALLOW, **(shallow_config or {})}
        self._deep = {**_DEFAULT_DEEP, **(deep_config or {})}
        self._openai_factory = _openai_factory
        # Lazy clients — only construct on first use (avoids openai import at __init__).
        # Lazy client 생성 — 첫 호출 시까지 미생성 (init 시 openai import 회피).
        self._shallow_client: Any = None
        self._deep_client: Any = None
        # Cached prompts
        self._shallow_prompt: str | None = None
        self._deep_prompt: str | None = None

    # ── Lazy client construction / Lazy client 생성 ──

    def _make_openai_client(self, base_url: str) -> Any:
        """Construct an openai.OpenAI client. Override-able for tests.
        openai.OpenAI client 생성. 테스트에서 override 가능.
        """
        if self._openai_factory is not None:
            return self._openai_factory(base_url=base_url)
        from openai import OpenAI  # type: ignore
        return OpenAI(base_url=base_url, api_key="vllm-no-auth")

    def _get_shallow_client(self) -> Any:
        if self._shallow_client is None:
            self._shallow_client = self._make_openai_client(self._shallow["endpoint"])
        return self._shallow_client

    def _get_deep_client(self) -> Any:
        if self._deep_client is None:
            self._deep_client = self._make_openai_client(self._deep["endpoint"])
        return self._deep_client

    # ── Prompt loading / Prompt 로딩 ──

    def _load_prompt(self, rel_path: str) -> str:
        path = REPO_ROOT / rel_path
        if not path.exists():
            raise FileNotFoundError(
                f"system prompt not found: {path}. "
                f"plan_1.6 / v2 산출물 확인 필요."
            )
        return path.read_text(encoding="utf-8")

    def _shallow_prompt_text(self) -> str:
        if self._shallow_prompt is None:
            self._shallow_prompt = self._load_prompt(self._shallow["system_prompt_path"])
        return self._shallow_prompt

    def _deep_prompt_text(self) -> str:
        if self._deep_prompt is None:
            self._deep_prompt = self._load_prompt(self._deep["system_prompt_path"])
        return self._deep_prompt

    # ── Tool results → user message / Tool 결과 → user message ──

    @staticmethod
    def _serialize_tool_results(
        tool_results: list[ToolResponse],
        *,
        max_per_tool_chars: int = 800,
    ) -> str:
        """Serialize tool results to a compact JSON user message body.
        Tool 결과를 압축 JSON user message body 로 직렬화.

        Per-tool length cap to avoid blowing the context window.
        Tool 당 길이 제한으로 context window overflow 방지.
        """
        compact: list[dict[str, Any]] = []
        for r in tool_results:
            entry: dict[str, Any] = {
                "tool": r.tool_name,
                "ok": r.ok,
                "args": r.args,
            }
            if r.ok and r.result is not None:
                serialized = json.dumps(r.result, ensure_ascii=False, default=str)
                if len(serialized) > max_per_tool_chars:
                    serialized = serialized[: max_per_tool_chars - 12] + "...truncated"
                entry["result"] = serialized
            if r.error is not None:
                entry["error"] = {"type": r.error.type, "message": r.error.message}
            if r.quality_meta:
                entry["quality_meta"] = r.quality_meta
            entry["latency_ms"] = r.latency_ms
            compact.append(entry)
        return json.dumps({"tool_results": compact}, ensure_ascii=False, indent=None)

    # ── narrate (shallow) / narrate (shallow) ──

    def narrate(self, tool_results: list[ToolResponse]) -> str:
        client = self._get_shallow_client()
        system_msg = self._shallow_prompt_text()
        user_msg = self._serialize_tool_results(tool_results)
        resp = client.chat.completions.create(
            model=self._shallow["model"],
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=int(self._shallow["max_tokens"]),
            temperature=float(self._shallow["temperature"]),
            timeout=float(self._shallow["timeout_s"]),
        )
        text = resp.choices[0].message.content or ""
        # Strip whitespace; single sentence assumption.
        return text.strip().splitlines()[0] if text else ""

    # ── brief (deep) / brief (deep) ──

    def brief(
        self,
        tool_results: list[ToolResponse],
        *,
        surgery_type: str,
        surgery_phase: str,
        elapsed_min: float,
    ) -> dict[str, str]:
        client = self._get_deep_client()
        system_msg = self._deep_prompt_text()
        # Surgery context inlined at the head of user message; tool results follow.
        # Surgery context 를 user message head 에; tool 결과 followed.
        user_msg = (
            f"수술 맥락:\n"
            f"  surgery_type = {surgery_type}\n"
            f"  surgery_phase = {surgery_phase}\n"
            f"  elapsed_min = {elapsed_min:.1f}\n\n"
            f"21 tool 결과 (JSON):\n"
            f"{self._serialize_tool_results(tool_results)}\n\n"
            f"위 정보를 바탕으로 9-section 한글 brief 를 작성하세요. "
            f"각 section 의 영문 header 를 그대로 출력하세요."
        )
        resp = client.chat.completions.create(
            model=self._deep["model"],
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=int(self._deep["max_tokens"]),
            temperature=float(self._deep["temperature"]),
            timeout=float(self._deep["timeout_s"]),
        )
        text = resp.choices[0].message.content or ""
        return _parse_9_section_brief(text)


# ── 9-section parser / 9-section parser ──


def _parse_9_section_brief(text: str) -> dict[str, str]:
    """Parse Heavy LLM output into a 9-section dict.
    Heavy LLM 출력을 9-section dict 로 parse.

    Strategy:
        1. Locate each *known* section header, tolerating common markdown
           decorations the model adds despite the prompt: ``**[X]**``, ``## [X]``,
           ``### [X]``, ``[X]:``, trailing ``*``/``:``, and header-on-same-line
           bodies. Matching is by the canonical section name (case-insensitive).
        2. Slice body text between consecutive located headers.
        3. Missing sections → empty string.

    NB (Sprint 7.14): the earlier parser required a bare ``[X]`` followed by a
    newline, so 8B/70B output wrapping headers in markdown bold (``**[X]**``)
    produced 0/9 parsed sections even though all sections were present. This
    version is markdown-tolerant.
    이전 parser 는 ``[X]\\n`` 만 인식 → 모델이 ``**[X]**`` 로 감싸면 9/9 생성해도
    0/9 parse 됐음. 본 버전은 markdown 관용.
    """
    parsed: dict[str, str] = {name: "" for name in _BRIEF_SECTIONS}
    canonical = {name.lower(): name for name in _BRIEF_SECTIONS}

    # Generic header matcher (markdown-tolerant): optional leading markdown
    # (#, *, whitespace), then ``[Anything]``, then optional trailing ``:``/``*``.
    # Must sit at line start (^ or after \n) so inline ``[CLINICIAN-REVIEW: ...]``
    # mid-sentence is not treated as a header.
    # 일반 header matcher (markdown 관용). 줄 시작에 있어야 하므로 문장 중간
    # 의 ``[CLINICIAN-REVIEW: ...]`` 는 header 로 오인하지 않음.
    header_pat = re.compile(
        r"(?:^|\n)[ \t]*(?:[#*]+[ \t]*)?\[([^\]]+)\](?:[ \t]*[:*]+)?[ \t]*\n?",
        re.MULTILINE,
    )
    # Exclude our own [CLINICIAN-REVIEW ...] marker from header boundaries so it
    # stays inside section bodies (even when emitted on its own line).
    # 자체 [CLINICIAN-REVIEW ...] marker 는 boundary 에서 제외 → 본문에 남김.
    matches = [
        m for m in header_pat.finditer(text)
        if not m.group(1).strip().upper().startswith("CLINICIAN-REVIEW")
    ]

    for i, m in enumerate(matches):
        key = canonical.get(m.group(1).strip().lower())
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if key is None:
            continue  # unknown header — used as a boundary but not stored
        body = text[body_start:body_end].strip().strip("*").strip()
        parsed[key] = body

    # Preserve canonical order
    return {name: parsed[name] for name in _BRIEF_SECTIONS}


__all__ = ["VLLMClient"]
