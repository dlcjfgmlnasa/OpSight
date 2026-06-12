"""Tests for predict_hypotension — Mock FM rule_based tier (ADR-011/023).
predict_hypotension 테스트 — Mock FM rule_based tier.

- 안정 고MAP → 저위험 / 안정 저MAP → 고위험 / 하강 MAP → 더 높은 위험(외삽)
- MAP 미가용 → invalid_args / mock_tier 표기 / horizon / leakage
- registry 등록(category=fm) + investigation whitelist 포함

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_predict_hypotension.py -v
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from opsight.envelope import ToolRequest
from opsight.registry import TOOLS, call_tool
from opsight.sim_clock import SimClock
from opsight.nodes.investigate import DEFAULT_INVESTIGATE_TOOLS
from opsight.tools.model_tools.predict_hypotension import tool_predict_hypotension


@pytest.fixture
def clock() -> SimClock:
    c = SimClock(start_s=0.0)
    c.tick(300.0)  # now_s = 300 so a 300 s trend window is in-bounds
    return c


def _req(args: dict, sim_time_s: float = 250.0) -> ToolRequest:
    return ToolRequest(case_id="c1", sim_time_s=sim_time_s,
                       tool_name="predict_hypotension", args=args)


def _map(arr: np.ndarray) -> dict[str, torch.Tensor]:
    return {"MAP": torch.from_numpy(arr.astype(np.float32))}


# ── Risk responds to level + trend ──


def test_stable_high_map_low_risk(clock) -> None:
    r = tool_predict_hypotension(_req({}), clock, _map(np.full(300, 80.0)))
    assert r.ok
    assert r.result["hypotension_risk"] < 0.2
    assert r.result["map_slope_per_min"] == pytest.approx(0.0, abs=0.05)


def test_stable_low_map_high_risk(clock) -> None:
    r = tool_predict_hypotension(_req({}), clock, _map(np.full(300, 55.0)))
    assert r.ok
    assert r.result["hypotension_risk"] > 0.7


def test_falling_map_higher_than_stable(clock) -> None:
    # linspace 75→60 over 300 s → slope ≈ -3/min → projected ≈ 45 → high risk.
    falling = tool_predict_hypotension(
        _req({}), clock, _map(np.linspace(75.0, 60.0, 300)))
    stable60 = tool_predict_hypotension(
        _req({}), clock, _map(np.full(300, 60.0)))
    assert falling.ok and stable60.ok
    assert falling.result["map_slope_per_min"] < -1.0
    assert falling.result["projected_map_mmHg"] < 55.0
    assert falling.result["hypotension_risk"] > stable60.result["hypotension_risk"]


# ── Horizon ──


def test_longer_horizon_extrapolates_further(clock) -> None:
    sig = _map(np.linspace(75.0, 60.0, 300))  # falling
    short = tool_predict_hypotension(_req({"horizon_min": 1.0}), clock, sig)
    long = tool_predict_hypotension(_req({"horizon_min": 10.0}), clock, sig)
    # falling → longer horizon projects lower MAP → higher risk
    assert long.result["projected_map_mmHg"] < short.result["projected_map_mmHg"]
    assert long.result["hypotension_risk"] >= short.result["hypotension_risk"]


# ── Errors / metadata ──


def test_map_unavailable_degrades_gracefully(clock) -> None:
    # swept unconditionally → missing MAP is a no-prediction outcome, not an error.
    sig = {"HR": torch.full((60,), 75.0)}  # no MAP/ABP
    r = tool_predict_hypotension(_req({}), clock, sig)
    assert r.ok
    assert r.result["hypotension_risk"] is None
    assert r.result["meta"]["note"] == "MAP unavailable"


def test_mock_tier_surfaced(clock) -> None:
    r = tool_predict_hypotension(_req({}), clock, _map(np.full(300, 70.0)))
    assert r.result["meta"]["mock_tier"] == "rule_based"
    assert r.quality_meta["mock_tier"] == "rule_based"
    assert r.quality_meta["category"] == "fm"
    assert r.quality_meta["clinical_review_required"] is True


def test_leakage_violation(clock) -> None:
    r = tool_predict_hypotension(_req({}, sim_time_s=9999.0), clock,
                                 _map(np.full(300, 70.0)))
    assert not r.ok and r.error.type == "leakage_violation"


# ── Registry / wiring ──


def test_registered_as_fm_and_dispatchable(clock) -> None:
    spec = TOOLS["predict_hypotension"]
    assert spec.category == "fm" and spec.needs_signal is True
    r = call_tool("predict_hypotension", _req({}), clock=clock,
                  signal=_map(np.full(300, 70.0)))
    assert r.ok and "hypotension_risk" in r.result


def test_in_investigation_whitelist() -> None:
    assert "predict_hypotension" in DEFAULT_INVESTIGATE_TOOLS
