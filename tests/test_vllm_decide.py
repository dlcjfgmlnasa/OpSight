"""Tests for VLLMClient.decide() — investigation ReAct tool-selection (ADR-023).
VLLMClient.decide() 테스트 — 조사 ReAct 도구 선택.

Mocks the OpenAI client via ``_openai_factory`` (no vLLM server / GPU needed).

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_vllm_decide.py -v
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.llm.vllm_client import VLLMClient, _parse_investigate_action
from opsight.nodes.investigate import (
    DEFAULT_INVESTIGATE_TOOLS,
    InvestigationContext,
    InvestigatorLLM,
    llm_investigate,
)
from opsight.router import Route, RouteDecision
from opsight.sim_clock import SimClock


# ── Fake OpenAI client (scripted responses) ──


class _Msg:
    def __init__(self, content): self.content = content


class _Choice:
    def __init__(self, content): self.message = _Msg(content)


class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, scripted): self._s = list(scripted); self._i = 0

    def create(self, **kw):
        c = self._s[min(self._i, len(self._s) - 1)]
        self._i += 1
        return _Resp(c)


class _Chat:
    def __init__(self, scripted): self.completions = _Completions(scripted)


class _FakeOpenAI:
    def __init__(self, scripted): self.chat = _Chat(scripted)


def _factory(scripted):
    return lambda base_url: _FakeOpenAI(scripted)


def _ctx(observations=None) -> InvestigationContext:
    return InvestigationContext(
        route_decision=RouteDecision(
            route=Route.AMBIGUOUS, reasons=["borderline: map_mmHg=63.0"],
            clear_breaches=[], borderline=["map_mmHg=63.0"], missing=[]),
        vitals={"map_mmHg": 63.0},
        observations=observations or [],
        available_tools=DEFAULT_INVESTIGATE_TOOLS,
        step=0, max_steps=6,
    )


# ── decide() output parsing ──


def test_decide_returns_tool_call() -> None:
    client = VLLMClient(_openai_factory=_factory(
        ['{"action": "tool_call", "tool": "get_signal_trend", "args": {}}']))
    a = client.decide(_ctx())
    assert a.kind == "tool_call" and a.tool_name == "get_signal_trend"


def test_decide_returns_final() -> None:
    client = VLLMClient(_openai_factory=_factory(
        ['{"action": "final", "assessment": {"hypotension_risk": 0.7, "rationale": "drift"}}']))
    a = client.decide(_ctx())
    assert a.kind == "final" and a.assessment["hypotension_risk"] == 0.7


def test_decide_tolerates_markdown_fence() -> None:
    client = VLLMClient(_openai_factory=_factory(
        ['```json\n{"action": "final", "assessment": {"hypotension_risk": 0.1}}\n```']))
    a = client.decide(_ctx())
    assert a.kind == "final" and a.assessment["hypotension_risk"] == 0.1


def test_decide_unparseable_defaults_to_final() -> None:
    client = VLLMClient(_openai_factory=_factory(["let me call a tool first"]))
    a = client.decide(_ctx())
    assert a.kind == "final" and a.assessment.get("parse_error") is True


def test_vllm_client_satisfies_investigator_protocol() -> None:
    assert isinstance(VLLMClient(), InvestigatorLLM)


# ── parser unit ──


def test_parser_tool_call_passthrough() -> None:
    a = _parse_investigate_action(
        '{"action":"tool_call","tool":"describe_signal","args":{"modality":"ABP"}}',
        DEFAULT_INVESTIGATE_TOOLS)
    assert a.kind == "tool_call" and a.args == {"modality": "ABP"}


def test_parser_bad_tool_type_falls_to_final() -> None:
    a = _parse_investigate_action('{"action":"tool_call","tool":123}', DEFAULT_INVESTIGATE_TOOLS)
    assert a.kind == "final"


# ── end-to-end: real decide() drives the investigation loop ──


def test_decide_drives_investigation_loop() -> None:
    client = VLLMClient(_openai_factory=_factory([
        '{"action": "tool_call", "tool": "get_signal_trend", "args": {}}',
        '{"action": "final", "assessment": {"hypotension_risk": 0.8}}',
    ]))
    clock = SimClock(start_s=0.0)
    clock.tick(60.0)
    signal = {"MAP": torch.from_numpy(np.full(300, 68.0, dtype=np.float32))}
    result = llm_investigate(
        route_decision=_ctx().route_decision, vitals={"map_mmHg": 63.0},
        clock=clock, signal=signal, llm_client=client,
        case_id="c1", sim_time_s=30.0,
    )
    assert result.tools_used == ["get_signal_trend"]
    assert result.hit_step_limit is False
    assert result.assessment["hypotension_risk"] == 0.8
    assert len(result.observations) == 1 and result.observations[0].ok
