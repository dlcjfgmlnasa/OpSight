"""Real-cohort 10-case e2e test (Sprint 6 Task C).
실 cohort 10 case e2e test (Sprint 6 Task C).

manifest 의 첫 10 case 로 dual-mode graph 자동 검증. preprocessing +
streaming + leakage guard 통합 동작 (FM 분리 — Biosignal Foundation Model 제거).

Skipped when:
- manifest.parquet 부재 (plan_1.2 build_cohort 안 실행)
- network 불가 (vitaldb load 실패) — pytest.skip with reason

Assertions:
- 각 case 에서 graph invoke 성공 (no exception)
- leakage error 0 (streaming + leakage guard 모두 작동)
- shallow latency p95 < 15 sec budget
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from opsight.graph import build_graph
from opsight.preprocessing import preprocess_signal_dict
from opsight.signal_stream import stream_from_full_signal
from opsight.sim_clock import SimClock
from opsight.state import AgentState
from opsight.trace import TraceWriter, read_trace


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "data" / "cohort" / "manifest.parquet"

PRIORITY_TRACKS = [
    "Solar8000/HR",
    "Solar8000/ART_MBP",
    "Solar8000/NIBP_MBP",
    "Solar8000/PLETH_SPO2",
    "Solar8000/ETCO2",
    "BIS/BIS",
]
TRACK_TO_ALIAS = {
    "Solar8000/HR": "HR",
    "Solar8000/ART_MBP": "ABP",
    "Solar8000/NIBP_MBP": "Solar8000/NIBP_MBP",
    "Solar8000/PLETH_SPO2": "SpO2",
    "Solar8000/ETCO2": "EtCO2",
    "BIS/BIS": "BIS",
}


def _load_real_case(case_id: int, interval_sec: float = 1.0) -> tuple[
    dict[str, torch.Tensor], list[str], float,
]:
    import vitaldb

    vf = vitaldb.VitalFile(case_id, track_names=PRIORITY_TRACKS)
    df = vf.to_pandas(PRIORITY_TRACKS, interval=interval_sec)

    signal: dict[str, torch.Tensor] = {}
    modalities: list[str] = []
    for col in df.columns:
        arr = df[col].to_numpy(dtype=np.float64)
        if np.isnan(arr).all():
            continue
        alias = TRACK_TO_ALIAS.get(col, col)
        signal[alias] = torch.from_numpy(arr.astype(np.float32))
        modalities.append(alias)
    return signal, modalities, 1.0 / interval_sec


@pytest.fixture(scope="module")
def manifest_sample_ids() -> list[int]:
    if not MANIFEST_PATH.exists():
        pytest.skip(
            f"manifest not built — run `python scripts/build_cohort.py` first "
            f"(expected {MANIFEST_PATH})"
        )
    manifest = pd.read_parquet(MANIFEST_PATH)
    abp_cases = manifest[manifest["abp_invasive"]]["case_id"].tolist()
    chosen = abp_cases[:10] if len(abp_cases) >= 10 else manifest["case_id"].tolist()[:10]
    return [int(c) for c in chosen]


def test_real_cohort_10cases_e2e(manifest_sample_ids, tmp_path: Path) -> None:
    if not manifest_sample_ids:
        pytest.skip("no case_ids in manifest")

    try:
        signal0, _mods0, _sr0 = _load_real_case(manifest_sample_ids[0])
    except Exception as exc:
        pytest.skip(f"vitaldb load failed (network?): {exc}")
    if not signal0:
        pytest.skip(f"case {manifest_sample_ids[0]} has no priority tracks")

    shallow_tick_latencies_ms: list[float] = []
    leakage_events = 0
    n_cases_with_brief = 0
    confidence_counts: dict[str, int] = {}
    trigger_reason_counts: dict[str, int] = {}
    max_ticks = 5
    tick_sim_advance_s = 60.0
    trace_path = tmp_path / "real_cohort.jsonl"

    for case_id in manifest_sample_ids:
        try:
            signal, modalities, sr_hz = _load_real_case(case_id)
        except Exception as exc:
            pytest.skip(f"case {case_id} load failed: {exc}")
        if not signal:
            continue

        signal, prep_report = preprocess_signal_dict(signal, sampling_rate_hz=sr_hz)
        rates = {
            mod: float(rep["output_sampling_rate_hz"])
            for mod, rep in prep_report.per_modality.items()
        }
        stream = stream_from_full_signal(
            signal, sampling_rates_hz=rates, default_sampling_rate_hz=sr_hz,
        )

        clock = SimClock(start_s=0.0)
        initial = AgentState(case_id=f"vitaldb-{case_id}", trace_id=f"real-{case_id}")

        with TraceWriter(trace_path, trace_id=initial.trace_id, case_id=initial.case_id) as tw:
            graph = build_graph(
                clock=clock, signal_stream=stream, modalities=modalities,
                max_ticks=max_ticks, tick_sim_advance_s=tick_sim_advance_s, trace=tw,
            )
            t0 = time.perf_counter()
            final = graph.invoke(initial, {"recursion_limit": 100})
            wall = time.perf_counter() - t0

        shallow_tick_latencies_ms.append(wall * 1000.0 / max_ticks)
        final_state = (
            final if isinstance(final, AgentState)
            else AgentState.model_validate(final)
        )
        if final_state.brief_history:
            n_cases_with_brief += 1
            for record in final_state.brief_history:
                reason_key = record.trigger_reason.split(" ", 1)[0]
                trigger_reason_counts[reason_key] = trigger_reason_counts.get(reason_key, 0) + 1
                conf_section = record.sections.get("Assessment confidence", "")
                for band in ("HIGH", "MEDIUM", "LOW", "UNRELIABLE"):
                    if band in conf_section:
                        confidence_counts[band] = confidence_counts.get(band, 0) + 1
                        break

    events = read_trace(trace_path)
    for ev in events:
        if ev["event"] == "tool_result" and not ev["payload"]["ok"]:
            leakage_events += 1

    p95_ms = float(np.percentile(shallow_tick_latencies_ms, 95))
    assert p95_ms < 15_000, f"p95 per-tick latency {p95_ms:.1f}ms exceeds 15s budget"
    assert leakage_events == 0, f"unexpected leakage events: {leakage_events}"
    # NOTE: deep-brief firing + confidence-band assertions removed — they were
    # driven by FM risk forecasts (Biosignal Foundation Model now decoupled).
    # The new false-alarm agent will reintroduce trigger-driven assertions.
    # 주: deep-brief 발화 + confidence band 단언은 FM risk forecast 가 구동하던
    # 것이라 제거 (Biosignal Foundation Model 분리). 새 false-alarm agent 에서
    # trigger 기반 단언을 재도입한다.

    print(f"\n=== Real cohort 10-case e2e summary ===")
    print(f"  cases run         : {len(manifest_sample_ids)}")
    print(f"  cases with brief  : {n_cases_with_brief}")
    print(f"  p95 latency ms    : {p95_ms:.1f}")
    print(f"  leakage events    : {leakage_events}")
    print(f"  confidence dist   : {confidence_counts}")
    print(f"  trigger reasons   : {trigger_reason_counts}")
