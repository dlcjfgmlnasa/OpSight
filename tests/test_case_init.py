"""Tests for the case-init node — patient context loaded once at graph entry (ADR-018).
case-init node 테스트 — graph 진입 시 환자 컨텍스트 1회 로드 (ADR-018).

- 정상 caseid → state.case_baseline 채워짐
- synthetic/미존재 case_id → None (graceful degrade, 실패 아님)

Run / 실행:
    .venv/Scripts/python.exe -m pytest tests/test_case_init.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest
import torch

import opsight.tools.emr_tools.get_patient_context as gpc
from opsight.graph import build_graph
from opsight.sim_clock import SimClock
from opsight.state import AgentState


def _one_tick_graph(clock: SimClock):
    signal = {
        "ABP": torch.zeros(30 * 500), "ECG_II": torch.zeros(30 * 500),
        "PPG": torch.zeros(30 * 500), "BIS": torch.zeros(30 * 100),
    }
    return build_graph(
        clock=clock, signal=signal, modalities=["ABP", "ECG_II", "PPG", "BIS"],
        max_ticks=1, tick_sim_advance_s=30.0,
    )


def _final(graph, case_id: str) -> AgentState:
    out = graph.invoke(AgentState(case_id=case_id, trace_id="t1"),
                       {"recursion_limit": 50})
    return out if isinstance(out, AgentState) else AgentState.model_validate(out)


def test_case_init_graceful_on_synthetic_case_id() -> None:
    """A non-VitalDB case_id leaves case_baseline None (no crash)."""
    fs = _final(_one_tick_graph(SimClock(start_s=0.0)), "synthetic-case-1")
    assert fs.case_baseline is None


def test_case_init_populates_baseline(monkeypatch) -> None:
    """A valid integer caseid populates case_baseline from VitalDB cases."""
    df = pd.DataFrame([{
        "caseid": 1, "age": 77, "sex": "M", "bmi": 26.3, "asa": 2,
        "department": "General surgery", "opname": "Low anterior resection",
        "dx": "Rectal cancer",
        "intraop_ebl": 500, "death_inhosp": 0,  # forbidden — must not surface
    }])
    monkeypatch.setattr(gpc, "load_cases", lambda: df)

    fs = _final(_one_tick_graph(SimClock(start_s=0.0)), "1")
    assert fs.case_baseline is not None
    assert fs.case_baseline["caseid"] == 1
    assert fs.case_baseline["demographics"]["age"] == 77
    assert fs.case_baseline["risk"]["asa"] == 2
    # leakage contract still holds through the case-init path
    import json
    blob = json.dumps(fs.case_baseline)
    assert "intraop_ebl" not in blob and "death_inhosp" not in blob
