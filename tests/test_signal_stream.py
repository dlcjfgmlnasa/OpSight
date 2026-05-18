"""Tests for opsight.signal_stream (Sprint 6, Issue #2 mitigation).
opsight.signal_stream 테스트 (Sprint 6, Issue #2 mitigation).

Coverage:
- SignalStream construction + validation
- view_until at various sim_time points (start, mid, beyond duration)
- sampling rate per-modality resolution (explicit > config > fallback)
- n_samples_until rounding
- total_duration_s
- build_graph integration: streaming view changes per tick
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.signal_stream import SignalStream, stream_from_full_signal


# ── SignalStream basics ──


def test_signal_stream_construction():
    sig = {
        "ABP": torch.zeros(500, dtype=torch.float32),  # 500 sample @ 100Hz = 5 sec
        "HR": torch.zeros(60, dtype=torch.float32),    # 60 sample @ 1Hz = 60 sec
    }
    rates = {"ABP": 100.0, "HR": 1.0}
    stream = SignalStream(signal=sig, sampling_rates_hz=rates)
    assert stream.sampling_rate_hz_for("ABP") == 100.0
    assert stream.sampling_rate_hz_for("HR") == 1.0


def test_signal_stream_rejects_non_tensor():
    with pytest.raises(TypeError, match="must be torch.Tensor"):
        SignalStream(signal={"ABP": [1.0, 2.0, 3.0]})


def test_signal_stream_rejects_non_1d():
    with pytest.raises(ValueError, match="must be 1-D"):
        SignalStream(signal={"ABP": torch.zeros(10, 5)})


def test_signal_stream_falls_back_to_config_rate():
    """When sampling_rates_hz omits a modality, config default is used.
    sampling_rates_hz 에서 누락된 modality 는 config default 사용.
    """
    sig = {"HR": torch.zeros(60, dtype=torch.float32)}
    stream = SignalStream(signal=sig)  # no rates passed
    # HR config has typical_sampling_rate_hz=1.0
    assert stream.sampling_rate_hz_for("HR") == 1.0


def test_signal_stream_unknown_modality_fallback_1hz():
    sig = {"unknown": torch.zeros(10, dtype=torch.float32)}
    stream = SignalStream(signal=sig)
    assert stream.sampling_rate_hz_for("unknown") == 1.0


# ── view_until — core slicing logic (Issue #2 fix) ──


def test_view_until_at_zero_yields_empty():
    sig = {"ABP": torch.arange(100, dtype=torch.float32)}
    stream = SignalStream(signal=sig, sampling_rates_hz={"ABP": 10.0})
    view = stream.view_until(0.0)
    assert view["ABP"].numel() == 0


def test_view_until_mid_window():
    # 100 sample @ 10Hz = 10 sec total
    sig = {"ABP": torch.arange(100, dtype=torch.float32)}
    stream = SignalStream(signal=sig, sampling_rates_hz={"ABP": 10.0})
    # sim_time=3s → 30 samples
    view = stream.view_until(3.0)
    assert view["ABP"].numel() == 30
    # First sample matches original
    assert view["ABP"][0].item() == 0.0
    assert view["ABP"][-1].item() == 29.0


def test_view_until_beyond_duration_returns_full_signal():
    sig = {"ABP": torch.arange(50, dtype=torch.float32)}
    stream = SignalStream(signal=sig, sampling_rates_hz={"ABP": 10.0})
    view = stream.view_until(100.0)  # way past 5 sec
    assert view["ABP"].numel() == 50  # all samples


def test_view_until_per_modality_different_rates():
    """ABP 500Hz vs HR 1Hz — same sim_time yields different sample counts.
    같은 sim_time 에서 modality 별 sample 수가 다르다.
    """
    sig = {
        "ABP": torch.arange(5000, dtype=torch.float32),  # 10 sec @ 500Hz
        "HR": torch.arange(10, dtype=torch.float32),     # 10 sec @ 1Hz
    }
    stream = SignalStream(signal=sig, sampling_rates_hz={"ABP": 500.0, "HR": 1.0})
    view = stream.view_until(5.0)
    assert view["ABP"].numel() == 2500  # 5 sec × 500 Hz
    assert view["HR"].numel() == 5      # 5 sec × 1 Hz


def test_view_until_start_offset():
    # start_offset=10 sec means signal[0] corresponds to sim_time=10
    sig = {"ABP": torch.arange(100, dtype=torch.float32)}
    stream = SignalStream(
        signal=sig, sampling_rates_hz={"ABP": 10.0}, start_offset_s=10.0,
    )
    # sim_time=15 → elapsed=5s → 50 samples
    view = stream.view_until(15.0)
    assert view["ABP"].numel() == 50
    # sim_time=8 (before offset) → 0 samples
    view2 = stream.view_until(8.0)
    assert view2["ABP"].numel() == 0


def test_total_duration_s_longest_modality():
    sig = {
        "ABP": torch.zeros(500, dtype=torch.float32),   # 5 sec @ 100Hz
        "HR": torch.zeros(60, dtype=torch.float32),     # 60 sec @ 1Hz ← longer
    }
    stream = SignalStream(signal=sig, sampling_rates_hz={"ABP": 100.0, "HR": 1.0})
    assert stream.total_duration_s() == 60.0


def test_stream_from_full_signal_factory_default_rate():
    sig = {"X": torch.zeros(100, dtype=torch.float32)}
    stream = stream_from_full_signal(
        sig, default_sampling_rate_hz=50.0,
    )
    assert stream.sampling_rate_hz_for("X") == 50.0


# ── Integration with build_graph (Issue #2 fix) ──


def test_graph_uses_streaming_when_signal_stream_passed(tmp_path):
    """Graph 가 streaming 으로 동작 — tool 이 받는 signal 길이가 tick 마다 증가.
    Graph operates in streaming mode — tool-visible signal grows per tick.
    """
    from opsight.fm.factory import create_fm
    from opsight.graph import build_graph
    from opsight.sim_clock import SimClock
    from opsight.state import AgentState
    from opsight.trace import TraceWriter, read_trace

    # 600 sample @ 1Hz = 10 min trajectory
    n = 600
    sig = {
        "ABP": torch.from_numpy(
            np.linspace(80.0, 60.0, n).astype(np.float32),
        ),
        "HR": torch.from_numpy(
            np.full(n, 75.0, dtype=np.float32),
        ),
    }
    stream = stream_from_full_signal(sig, default_sampling_rate_hz=1.0)
    fm = create_fm({"fm": {"implementation": "mock_rule_based",
                            "config": {"seed": 42, "sampling_rate_hz": 1.0,
                                       "noise_pct": 0.0}}})
    clock = SimClock(start_s=0.0)
    trace_path = tmp_path / "stream.jsonl"
    with TraceWriter(trace_path, trace_id="t1", case_id="c1") as tw:
        graph = build_graph(
            fm=fm, clock=clock,
            signal_stream=stream,
            modalities=["ABP", "HR"],
            max_ticks=3, tick_sim_advance_s=60.0,
            trace=tw,
        )
        initial = AgentState(case_id="c1", trace_id="t1")
        final = graph.invoke(initial, {"recursion_limit": 50})

    final_state = (
        final if isinstance(final, AgentState)
        else AgentState.model_validate(final)
    )
    # 3 ticks executed
    assert final_state.scratch.get("tick_count", 0) == 3
    # No leakage (would surface in tool_result events)
    events = read_trace(trace_path)
    bad = [e for e in events if e["event"] == "tool_result" and not e["payload"]["ok"]]
    assert not bad, f"unexpected tool failures: {bad}"


def test_graph_legacy_signal_dict_still_works():
    """Backward compat — 기존 signal=... 패턴이 여전히 작동.
    Legacy signal=... 패턴 backward compat.
    """
    from opsight.fm.factory import create_fm
    from opsight.graph import build_graph
    from opsight.sim_clock import SimClock
    from opsight.state import AgentState

    sig = {
        "ABP": torch.full((600,), 80.0, dtype=torch.float32),
        "HR": torch.full((600,), 75.0, dtype=torch.float32),
    }
    fm = create_fm({"fm": {"implementation": "mock_rule_based",
                            "config": {"seed": 42, "sampling_rate_hz": 1.0}}})
    clock = SimClock(start_s=0.0)
    graph = build_graph(
        fm=fm, clock=clock, signal=sig,
        modalities=["ABP", "HR"],
        max_ticks=2, tick_sim_advance_s=60.0,
    )
    initial = AgentState(case_id="c1", trace_id="t1")
    final = graph.invoke(initial, {"recursion_limit": 30})
    final_state = (
        final if isinstance(final, AgentState)
        else AgentState.model_validate(final)
    )
    assert final_state.scratch.get("tick_count", 0) == 2


def test_graph_rejects_both_signal_and_stream():
    from opsight.fm.factory import create_fm
    from opsight.graph import build_graph
    from opsight.sim_clock import SimClock

    sig = {"ABP": torch.zeros(100, dtype=torch.float32)}
    stream = stream_from_full_signal(sig)
    fm = create_fm({"fm": {"implementation": "mock_stub"}})
    clock = SimClock()
    with pytest.raises(ValueError, match="either signal OR signal_stream"):
        build_graph(
            fm=fm, clock=clock, signal=sig, signal_stream=stream,
            modalities=["ABP"], max_ticks=1,
        )


def test_graph_rejects_neither_signal_nor_stream():
    from opsight.fm.factory import create_fm
    from opsight.graph import build_graph
    from opsight.sim_clock import SimClock

    fm = create_fm({"fm": {"implementation": "mock_stub"}})
    clock = SimClock()
    with pytest.raises(ValueError, match="must pass signal or signal_stream"):
        build_graph(
            fm=fm, clock=clock, modalities=["ABP"], max_ticks=1,
        )
