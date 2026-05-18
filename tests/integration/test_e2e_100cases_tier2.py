"""100-case end-to-end test against Mock FM Tier 2 (plan_1.8 final task).
Mock FM Tier 2 100-case end-to-end 테스트 (plan_1.8 마지막 task).

Closes Stage 1 acceptance criterion (master_plan.md §5):
"Mock FM Tier 1 + Tier 2 drive the end-to-end agent loop".
Stage 1 acceptance criterion 충족 (master_plan.md §5):
"Mock FM Tier 1 + Tier 2가 end-to-end agent loop를 구동".

Synthetic cases are used here. When ``plan_1.2`` cohort lands, fixture
``_make_case`` is the only change needed.
본 테스트는 synthetic case 사용. ``plan_1.2`` 코호트 도착 시 ``_make_case``
fixture만 교체.

Assertions / 검증:
- Shallow latency budget met (p95 < 15 sec).
- Deep triggers fire plausibly across 100 cases.
- No leakage error anywhere in the trace.
- 9-section Korean brief rendered end-to-end per deep fire.
- FM consumed only via BiosignalFMInterface (already enforced statically).
"""
from __future__ import annotations

import statistics
import time
from pathlib import Path

import numpy as np
import pytest
import torch

from vitalagent.fm.factory import create_fm
from vitalagent.fm.interface import BiosignalFMInterface
from vitalagent.graph import build_graph
from vitalagent.sim_clock import SimClock
from vitalagent.state import AgentState
from vitalagent.trace import TraceWriter, read_trace


# ── Synthetic case generator / Synthetic case generator ──


def _make_case(case_idx: int, seed: int = 0) -> tuple[dict[str, torch.Tensor], list[str]]:
    """Generate a 30-second 4-modality synthetic case.
    30초 4-modality synthetic case 생성.

    Cases vary in MAP baseline + slope + HR to expose the agent to a spectrum
    of risk levels (low / mid / high). 100 cases cover the parameter sweep.
    Case는 MAP baseline + slope + HR을 변경하여 risk 범위 (low / mid / high)
    스펙트럼에 agent를 노출시킨다. 100 case가 parameter sweep을 cover.
    """
    rng = np.random.default_rng(seed + case_idx)
    sampling_rate_hz = 500.0
    n = 30 * int(sampling_rate_hz)

    # Sweep MAP baseline ~ [55, 95] mmHg / MAP baseline을 ~ [55, 95] 사이로 sweep.
    map_baseline = 55 + (40 * case_idx / 99.0)
    # Slope varies with case index so some cases trigger hypotension risk.
    # Slope을 case index에 따라 변경 — 일부 case는 hypotension trigger 발화.
    slope_mmhg_per_min = -6.0 + (10.0 * case_idx / 99.0)  # [-6, 4]
    slope_per_step = slope_mmhg_per_min / (sampling_rate_hz * 60.0)

    # ABP trace
    abp = (
        map_baseline
        + slope_per_step * np.arange(n, dtype=np.float64)
        + rng.normal(0, 1.0, size=n)
    )
    # ECG (zero baseline noise — not used by rules besides quality)
    ecg = rng.normal(0, 0.05, size=n)
    # PPG (correlated with ABP)
    ppg = 0.5 * abp + rng.normal(0, 0.5, size=n)
    # HR — most cases nominal, a few extreme
    if case_idx % 13 == 0:
        hr_value = 200.0  # tachy
    elif case_idx % 17 == 0:
        hr_value = 30.0   # brady
    else:
        hr_value = 75.0 + rng.normal(0, 3, size=1)[0]
    hr = np.full(500, float(hr_value))

    signal = {
        "ABP":    torch.from_numpy(abp),
        "ECG_II": torch.from_numpy(ecg),
        "PPG":    torch.from_numpy(ppg),
        "HR":     torch.from_numpy(hr),
    }
    modalities = list(signal)
    return signal, modalities


# ── Tier-2 FM factory / Tier-2 FM factory ──


@pytest.fixture
def tier2_fm() -> BiosignalFMInterface:
    """Build Tier-2 rule-based FM via the factory (deterministic, no noise).
    Factory로 Tier-2 rule-based FM 빌드 (결정적, no noise).
    """
    return create_fm(
        {
            "fm": {
                "implementation": "mock_rule_based",
                "config": {"seed": 42, "sampling_rate_hz": 500.0, "noise_pct": 0.0},
            }
        }
    )


# ── Test ──


def test_e2e_100cases_tier2(tmp_path: Path, tier2_fm) -> None:
    """Run the dual-mode graph against 100 synthetic cases under Tier 2.
    100 synthetic case에 대해 Tier 2 dual-mode graph 실행.
    """
    # ── Knobs / 설정값 ──
    n_cases = 100
    max_ticks = 6
    tick_sim_advance_s = 30.0

    # Aggregations / 집계.
    shallow_tick_latencies_ms: list[float] = []
    deep_fire_count = 0
    deep_brief_with_9_sections = 0
    leakage_events = 0
    cases_with_deep = 0
    trigger_reasons: dict[str, int] = {}

    trace_path = tmp_path / "e2e.jsonl"

    for case_idx in range(n_cases):
        signal, modalities = _make_case(case_idx)
        clock = SimClock(start_s=0.0)
        initial = AgentState(
            case_id=f"synth-{case_idx:03d}",
            trace_id=f"e2e-{case_idx:03d}",
        )
        with TraceWriter(trace_path, trace_id=initial.trace_id, case_id=initial.case_id) as tw:
            graph = build_graph(
                fm=tier2_fm,
                clock=clock,
                signal=signal,
                modalities=modalities,
                max_ticks=max_ticks,
                tick_sim_advance_s=tick_sim_advance_s,
                trace=tw,
            )
            t0 = time.perf_counter()
            final = graph.invoke(initial, {"recursion_limit": 100})
            wall_total = time.perf_counter() - t0
        shallow_tick_latencies_ms.append(wall_total * 1000.0 / max_ticks)

        final_state = (
            final if isinstance(final, AgentState) else AgentState.model_validate(final)
        )
        if final_state.brief_history:
            cases_with_deep += 1
        deep_fire_count += len(final_state.brief_history)
        for record in final_state.brief_history:
            if len(record.sections) == 9:
                deep_brief_with_9_sections += 1
            reason_key = record.trigger_reason.split(" ", 1)[0]
            trigger_reasons[reason_key] = trigger_reasons.get(reason_key, 0) + 1

    # Per-case trace events / case별 trace 이벤트.
    events = read_trace(trace_path)
    for ev in events:
        if ev["event"] == "tool_result" and not ev["payload"]["ok"]:
            # Any leakage would surface here / leakage는 여기서 노출됨.
            leakage_events += 1

    # ── Assertions / 검증 ──
    # 1) Shallow latency budget: p95 < 15 sec per tick.
    p95_ms = float(np.percentile(shallow_tick_latencies_ms, 95))
    assert p95_ms < 15_000, (
        f"p95 per-tick latency {p95_ms:.1f}ms exceeds 15s budget"
    )

    # 2) Deep triggers fired on a plausible share of cases.
    #    Risk sweep spans hypotension, so at least 10% should fire.
    # 2) Deep trigger가 합리적 비율 case에서 발화. Risk sweep에 hypotension이
    #    포함되므로 최소 10% 발화 기대.
    assert cases_with_deep >= 10, (
        f"only {cases_with_deep}/100 cases produced a deep brief — "
        f"trigger sensitivity too low"
    )

    # 3) Every deep brief carries 9 sections.
    # 3) 모든 deep brief가 9 section 보유.
    assert deep_brief_with_9_sections == deep_fire_count, (
        f"{deep_brief_with_9_sections}/{deep_fire_count} briefs had 9 sections"
    )

    # 4) No leakage errors in any tool_result event.
    # 4) 어떤 tool_result에도 leakage 없음.
    assert leakage_events == 0, f"unexpected leakage / tool failures: {leakage_events}"

    # 5) Trigger reasons diversity — at least one non-clinician trigger fired
    #    across the 100-case sweep (no clinician on-demand was injected).
    # 5) Trigger 사유 다양성 — 100 case sweep에 걸쳐 clinician on-demand 없이
    #    최소 하나의 trigger 발화 (본 test는 on-demand 미주입).
    assert "clinician_on_demand" not in trigger_reasons, (
        f"unexpected clinician_on_demand fired: {trigger_reasons}"
    )
    assert len(trigger_reasons) >= 1, (
        f"no trigger fired across 100 cases (suspicious): {trigger_reasons}"
    )

    # Diagnostic prints (visible with pytest -s) / 진단 print.
    print(
        f"\n[e2e summary] 100 cases | "
        f"cases_with_deep={cases_with_deep} | "
        f"deep_fires={deep_fire_count} | "
        f"p95_per_tick_ms={p95_ms:.1f} | "
        f"triggers={trigger_reasons}"
    )
