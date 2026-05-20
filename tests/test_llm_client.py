"""Tests for opsight.llm (Sprint 6 — vLLM wiring sketch).
opsight.llm 테스트 (Sprint 6 — vLLM wiring sketch).

Coverage:
- LLMClient Protocol (PlaceholderClient + VLLMClient 둘 다 만족)
- create_llm_client factory (placeholder / vllm / hybrid / unknown)
- VLLMClient prompt loading (system prompt file)
- VLLMClient narrate / brief via mocked OpenAI client
- 9-section parser robustness (missing sections, extra noise, marker preserve)
- Tool result serialization length cap
- Config YAML round-trip
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from opsight.llm import LLMClient, create_llm_client
from opsight.llm.placeholder_client import PlaceholderClient
from opsight.llm.vllm_client import VLLMClient, _parse_9_section_brief
from opsight.tools.envelope import ToolResponse


REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Fixtures ──


def _mock_chat_response(content: str) -> Any:
    """Build a mock OpenAI chat completion response object.
    """
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_openai_factory(canned_response: str) -> Any:
    """Return a factory that yields a mocked OpenAI client.
    Mocked OpenAI client 을 yield 하는 factory 반환.
    """
    def _factory(*, base_url: str) -> Any:
        client = MagicMock()
        client.chat.completions.create = MagicMock(
            return_value=_mock_chat_response(canned_response)
        )
        client._base_url = base_url
        return client
    return _factory


@pytest.fixture
def sample_tool_results() -> list[ToolResponse]:
    return [
        ToolResponse(
            case_id="c1", sim_time_s=30.0, tool_name="predict_hypotension",
            args={"horizon_min": 5},
            result={"risk": 0.42, "uncertainty": 0.18, "horizon_min": 5,
                    "meta": {"mock_tier": "rule_based"}},
            quality_meta={"fm_meta": {"mock_tier": "rule_based"}},
            latency_ms=1.2,
        ),
        ToolResponse(
            case_id="c1", sim_time_s=30.0, tool_name="predict_cardiac_arrest",
            args={"horizon_min": 5},
            result={"risk": 0.05, "uncertainty": 0.3, "horizon_min": 5},
            latency_ms=0.8,
        ),
        ToolResponse(
            case_id="c1", sim_time_s=30.0, tool_name="assess_signal_quality",
            args={"modality": "ABP"},
            result={"score": 0.95, "reason": None},
            latency_ms=0.3,
        ),
    ]


# ── PlaceholderClient — Protocol 만족 + 기본 동작 ──


def test_placeholder_client_satisfies_protocol():
    c = PlaceholderClient()
    assert isinstance(c, LLMClient)
    assert c.name == "placeholder"


def test_placeholder_narrate_returns_korean_sentence(sample_tool_results):
    c = PlaceholderClient()
    text = c.narrate(sample_tool_results)
    assert "저혈압 risk" in text
    assert "심정지 risk" in text


def test_placeholder_brief_has_9_sections(sample_tool_results):
    c = PlaceholderClient()
    sections = c.brief(sample_tool_results, surgery_type="general",
                       surgery_phase="maintenance", elapsed_min=45.0)
    assert len(sections) == 9
    assert "[CLINICIAN-REVIEW" in sections["Recommendations"]


# ── VLLMClient with mocked OpenAI client ──


def test_vllm_client_satisfies_protocol():
    c = VLLMClient(_openai_factory=_mock_openai_factory("[안정] dummy."))
    assert isinstance(c, LLMClient)
    assert c.name == "vllm"


def test_vllm_narrate_routes_to_shallow_endpoint(sample_tool_results):
    canned = "[주의] 저혈압 risk 0.42, 심정지 risk 0.05. 추세 모니터링 필요."
    factory = _mock_openai_factory(canned)
    c = VLLMClient(_openai_factory=factory)
    text = c.narrate(sample_tool_results)
    assert text == canned
    # Shallow client lazy-built — should target shallow endpoint
    shallow_client = c._get_shallow_client()
    assert "8000" in shallow_client._base_url


def test_vllm_brief_routes_to_deep_endpoint_and_parses_9_sections(sample_tool_results):
    canned_brief = (
        "[Surgery context]\n"
        "복부 수술 maintenance, 경과 45분.\n\n"
        "[Signal status]\n"
        "ABP 품질 0.95.\n\n"
        "[Assessment confidence]\n"
        "HIGH.\n\n"
        "[Risk evaluation]\n"
        "저혈압 risk 0.42 (5분 horizon).\n\n"
        "[Evidence]\n"
        "추세 모니터링.\n\n"
        "[Intraoperative context]\n"
        "마취제 안정.\n\n"
        "[Similar trajectory]\n"
        "TBD.\n\n"
        "[Recommendations]\n"
        "임상의 판단 필요. [CLINICIAN-REVIEW: 의료진 검토 필요]\n\n"
        "[Limitations]\n"
        "본 brief 는 placeholder. [CLINICIAN-REVIEW]\n"
    )
    factory = _mock_openai_factory(canned_brief)
    c = VLLMClient(_openai_factory=factory)
    sections = c.brief(
        sample_tool_results, surgery_type="general",
        surgery_phase="maintenance", elapsed_min=45.0,
    )
    assert len(sections) == 9
    assert "복부 수술" in sections["Surgery context"]
    assert "0.95" in sections["Signal status"]
    assert "[CLINICIAN-REVIEW" in sections["Recommendations"]


def test_vllm_prompt_file_missing_raises():
    c = VLLMClient(
        shallow_config={"system_prompt_path": "prompts/_no_such_prompt.md"},
        _openai_factory=_mock_openai_factory("dummy"),
    )
    with pytest.raises(FileNotFoundError, match="system prompt not found"):
        c.narrate([])


def test_vllm_prompt_caching():
    """Prompt 는 첫 호출 시 load + cache.
    """
    factory = _mock_openai_factory("[안정] x.")
    c = VLLMClient(_openai_factory=factory)
    # Two narrate calls → prompt file read once
    c.narrate([])
    first_prompt = c._shallow_prompt
    c.narrate([])
    # Cached object identity preserved
    assert c._shallow_prompt is first_prompt


def test_vllm_uses_provided_endpoint():
    c = VLLMClient(
        shallow_config={"endpoint": "http://custom-shallow:9001/v1"},
        deep_config={"endpoint": "http://custom-deep:9002/v1"},
        _openai_factory=_mock_openai_factory("dummy"),
    )
    shallow = c._get_shallow_client()
    deep = c._get_deep_client()
    assert shallow._base_url == "http://custom-shallow:9001/v1"
    assert deep._base_url == "http://custom-deep:9002/v1"


# ── 9-section parser ──


def test_parser_handles_complete_brief():
    text = (
        "[Surgery context]\nA.\n\n"
        "[Signal status]\nB.\n\n"
        "[Assessment confidence]\nC.\n\n"
        "[Risk evaluation]\nD.\n\n"
        "[Evidence]\nE.\n\n"
        "[Intraoperative context]\nF.\n\n"
        "[Similar trajectory]\nG.\n\n"
        "[Recommendations]\nH.\n\n"
        "[Limitations]\nI.\n"
    )
    out = _parse_9_section_brief(text)
    assert len(out) == 9
    assert out["Surgery context"] == "A."
    assert out["Limitations"] == "I."


def test_parser_missing_sections_empty_string():
    """LLM 이 일부 section 누락 시 빈 문자열로 채움 (강제 9 key).
    """
    text = "[Surgery context]\nOnly this one.\n"
    out = _parse_9_section_brief(text)
    assert len(out) == 9
    assert out["Surgery context"] == "Only this one."
    assert out["Recommendations"] == ""
    assert out["Limitations"] == ""


def test_parser_preserves_clinician_review_marker():
    text = (
        "[Recommendations]\n"
        "고려사항. [CLINICIAN-REVIEW: 의료진 검토 필요]\n"
    )
    out = _parse_9_section_brief(text)
    assert "[CLINICIAN-REVIEW" in out["Recommendations"]


def test_parser_ignores_unknown_section_headers():
    text = (
        "[Surgery context]\nA.\n\n"
        "[Unknown Section]\nIgnored.\n\n"
        "[Risk evaluation]\nB.\n"
    )
    out = _parse_9_section_brief(text)
    assert out["Surgery context"] == "A."
    assert out["Risk evaluation"] == "B."
    # 9 canonical keys only
    assert "Unknown Section" not in out


def test_parser_markdown_bold_headers():
    """8B/70B often wrap headers in markdown bold (**[X]**) despite the prompt.
    Parser must still extract all sections (Sprint 7.14 fix).
    8B/70B 가 header 를 **[X]** 로 감싸도 parse 되어야 함 (Sprint 7.14).
    """
    text = (
        "**[Surgery context]**\nGeneral, induction.\n\n"
        "**[Signal status]**\nMAP unavailable.\n\n"
        "**[Assessment confidence]**\nLOW.\n\n"
        "**[Risk evaluation]**\nHypotension 0.00.\n\n"
        "**[Evidence]**\nFlat trend.\n\n"
        "**[Intraoperative context]**\nSevoflurane.\n\n"
        "**[Similar trajectory]**\nTBD.\n\n"
        "**[Recommendations]**\nMonitor. [CLINICIAN-REVIEW: clinician review required]\n\n"
        "**[Limitations]**\nMock FM. [CLINICIAN-REVIEW: clinician review required]\n"
    )
    out = _parse_9_section_brief(text)
    nonempty = sum(1 for v in out.values() if v.strip())
    assert nonempty == 9, f"expected 9 sections, got {nonempty}: {out}"
    assert out["Surgery context"] == "General, induction."
    assert out["Assessment confidence"] == "LOW."
    assert "[CLINICIAN-REVIEW" in out["Recommendations"]
    assert "[CLINICIAN-REVIEW" in out["Limitations"]


def test_parser_markdown_header_and_colon_variants():
    """Tolerate '## [X]' and '[X]:' header decorations.
    '## [X]' 와 '[X]:' 형식도 관용.
    """
    text = (
        "## [Surgery context]\nA.\n\n"
        "[Signal status]:\nB.\n\n"
        "### [Risk evaluation] :\nC.\n"
    )
    out = _parse_9_section_brief(text)
    assert out["Surgery context"] == "A."
    assert out["Signal status"] == "B."
    assert out["Risk evaluation"] == "C."


def test_parser_clinician_review_on_own_line_preserved():
    """[CLINICIAN-REVIEW ...] on its own line stays in the section body.
    자체 줄의 [CLINICIAN-REVIEW ...] marker 가 본문에 보존됨.
    """
    text = (
        "[Recommendations]\n"
        "Consider clinician judgment.\n"
        "[CLINICIAN-REVIEW: clinician review required]\n\n"
        "[Limitations]\n"
        "Mock FM tier.\n"
    )
    out = _parse_9_section_brief(text)
    assert "[CLINICIAN-REVIEW" in out["Recommendations"]
    assert out["Limitations"] == "Mock FM tier."


# ── Serializer ──


def test_serializer_truncates_long_results(sample_tool_results):
    # Inject a huge result
    big = dict(sample_tool_results[0].args)
    huge = ToolResponse(
        case_id="c1", sim_time_s=0.0, tool_name="huge_tool",
        args={}, result={"data": "x" * 10000},
        latency_ms=0.0,
    )
    serialized = VLLMClient._serialize_tool_results(
        [huge], max_per_tool_chars=200,
    )
    assert "...truncated" in serialized
    assert len(serialized) < 1000  # bounded


def test_serializer_preserves_quality_meta(sample_tool_results):
    serialized = VLLMClient._serialize_tool_results(sample_tool_results)
    # ABP quality_meta should appear if present
    # 첫 번째 tool 의 quality_meta 가 직렬화되었는지
    assert "mock_tier" in serialized or "fm_meta" in serialized


# ── Factory ──


def test_factory_placeholder():
    c = create_llm_client({"llm": {"implementation": "placeholder"}})
    assert isinstance(c, PlaceholderClient)


def test_factory_default_is_placeholder():
    c = create_llm_client({"llm": {}})
    assert isinstance(c, PlaceholderClient)


def test_factory_vllm_constructs_client():
    c = create_llm_client({
        "llm": {
            "implementation": "vllm",
            "shallow": {"endpoint": "http://test:8000/v1"},
            "deep": {"endpoint": "http://test:8001/v1"},
        }
    })
    assert isinstance(c, VLLMClient)


def test_factory_hybrid_placeholder_shallow_vllm_deep():
    c = create_llm_client({
        "llm": {
            "implementation": "hybrid",
            "shallow": {"kind": "placeholder"},
            "deep": {"kind": "vllm", "endpoint": "http://gpu1:8000/v1"},
        }
    })
    # Hybrid composes — name attr set on wrapper
    assert hasattr(c, "narrate")
    assert hasattr(c, "brief")


def test_factory_unknown_impl_raises():
    with pytest.raises(ValueError, match="Unknown LLM implementation"):
        create_llm_client({"llm": {"implementation": "magic"}})


def test_factory_missing_llm_section_raises():
    with pytest.raises(ValueError, match="must contain 'llm' object"):
        create_llm_client({})


# ── Config YAML round-trip ──


@pytest.mark.parametrize(
    "yaml_name", ["placeholder.yaml", "vllm.yaml", "hybrid_deep_only.yaml"],
)
def test_config_yaml_files_loadable(yaml_name):
    path = REPO_ROOT / "configs" / "llm" / yaml_name
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "llm" in config
    assert "implementation" in config["llm"]


def test_placeholder_yaml_instantiates():
    path = REPO_ROOT / "configs" / "llm" / "placeholder.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    c = create_llm_client(config)
    assert isinstance(c, PlaceholderClient)


# ── Graph integration — llm_client param flows through ──


def test_graph_invokes_llm_client_narrate_for_shallow(tmp_path):
    """Graph 가 shallow tick 마다 llm_client.narrate 호출하는지.
    """
    from opsight.fm.factory import create_fm
    from opsight.graph import build_graph
    from opsight.sim_clock import SimClock
    from opsight.state import AgentState
    import torch

    sig = {
        "ABP": torch.full((600,), 80.0, dtype=torch.float32),
        "HR": torch.full((600,), 75.0, dtype=torch.float32),
    }
    fm = create_fm({"fm": {"implementation": "mock_rule_based",
                            "config": {"sampling_rate_hz": 1.0}}})
    clock = SimClock()

    # Wrap a placeholder client and count calls.
    class _Counting:
        name = "counting"
        def __init__(self):
            self.narrate_count = 0
            self.brief_count = 0
            self._inner = PlaceholderClient()
        def narrate(self, results):
            self.narrate_count += 1
            return self._inner.narrate(results)
        def brief(self, results, **kw):
            self.brief_count += 1
            return self._inner.brief(results, **kw)

    counter = _Counting()
    graph = build_graph(
        fm=fm, clock=clock, signal=sig, modalities=["ABP", "HR"],
        max_ticks=3, tick_sim_advance_s=60.0, llm_client=counter,
    )
    initial = AgentState(case_id="c1", trace_id="t1")
    graph.invoke(initial, {"recursion_limit": 30})
    assert counter.narrate_count == 3  # one per tick
    # brief_count depends on triggers — may be 0 or more
    assert counter.brief_count >= 0
