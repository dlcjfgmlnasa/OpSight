"""Smoke test: real LLM end-to-end on a real VitalDB case (Ollama backend).
실제 VitalDB case + Ollama 로 LLM end-to-end smoke.

Goal / 목표:
    Verify the OpSight LLM wiring on a *real* VitalDB case without needing
    the 2× L40S GPU setup. Three stages, all hitting an OpenAI-compatible
    endpoint (Ollama by default):

      [1] Raw openai SDK ping     — Ollama up + openai installed
      [2] Shallow tools (5) + narrate()  on real case data
      [3] Deep tools (16) + brief()      on the same case (slow)

Setup (one-time) / 최초 셋업:
    1. Install Ollama for Windows:  https://ollama.com/download/windows
    2. Pull a Llama-3.1 model:      ollama pull llama3.1:8b   (~4.7 GB)
    3. Verify the server is up:     curl http://localhost:11434/api/tags
    4. Python deps already in requirements.txt (openai, vitaldb).

Run / 실행:
    python scripts/smoke_llm.py                    # case 1, 1 shallow tick
    python scripts/smoke_llm.py --case-id 5        # different case
    python scripts/smoke_llm.py --skip-brief       # narrate only (faster)
    python scripts/smoke_llm.py --model llama3.2:3b
    python scripts/smoke_llm.py --sim-time-s 600   # tools see first 10 min of case

Outputs / 결과물:
    Prints stage-by-stage progress + final narration / 9-section brief.
    No trace JSONL is written (use run_real_case.py for the full graph run).
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import torch

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from opsight.fm.factory import create_fm
from opsight.llm.vllm_client import VLLMClient
from opsight.preprocessing import preprocess_signal_dict
from opsight.sim_clock import SimClock
from opsight.tools.envelope import ToolRequest, ToolResponse
from opsight.tools.registry import SHALLOW_TOOL_NAMES, TOOLS, call_tool

# Reuse the well-tested loader from run_real_case (track set + alias map).
# run_real_case 의 검증된 loader 재사용 (track 세트 + alias map 동일).
from scripts.run_real_case import (
    DEFAULT_TRACKS,
    df_to_signal_dict,
    load_vitaldb_case,
)


# ── Tool args (mirror shallow_loop._shallow_tool_args / deep_brief._deep_args) ──


def _shallow_args(name: str, sim_time_s: float, modalities: list[str]) -> dict:
    if name == "predict_hypotension":
        return {"horizon_min": 5, "available_modalities": modalities}
    if name == "predict_cardiac_arrest":
        return {"horizon_min": 5, "available_modalities": modalities}
    if name == "assess_signal_quality":
        return {"modality": modalities[0] if modalities else "ABP"}
    if name == "cross_modal_consistency":
        if len(modalities) >= 2:
            return {"modality_pair": [modalities[0], modalities[1]]}
        return {"modality_pair": [modalities[0] if modalities else "ABP", "ABP"]}
    if name == "anomaly_score":
        return {"modality": modalities[0] if modalities else "ABP"}
    # ADR-018 additions
    if name == "summarize_current_state":
        return {}
    if name == "query_surgery_progress":
        return {"current_time": sim_time_s}
    if name == "query_vasoactive_drugs":
        return {"time_window": [max(0.0, sim_time_s - 300.0), sim_time_s]}
    raise ValueError(f"unknown shallow tool: {name}")


def _deep_args(name: str, sim_time_s: float, modalities: list[str]) -> dict:
    """Mirror of opsight.nodes.deep_brief._deep_args (sim_time_s passed in).
    deep_brief._deep_args 와 동일 (sim_time_s 만 직접 받음).
    """
    if name in ("predict_hypotension", "predict_cardiac_arrest"):
        return {"horizon_min": 5, "available_modalities": modalities}
    if name == "assess_signal_quality":
        return {"modality": modalities[0] if modalities else "ABP"}
    if name == "cross_modal_consistency":
        if len(modalities) >= 2:
            return {"modality_pair": [modalities[0], modalities[1]]}
        return {"modality_pair": [modalities[0] if modalities else "ABP", "ABP"]}
    if name == "temporal_trend_analysis":
        return {"modality": modalities[0] if modalities else "ABP", "window_min": 5}
    if name == "forecast_signal":
        return {"modality": modalities[0] if modalities else "ABP", "horizon_min": 5}
    if name == "anomaly_score":
        return {"modality": modalities[0] if modalities else "ABP"}
    if name in ("query_anesthesia_drugs", "query_vasoactive_drugs", "query_fluid_blood"):
        return {"time_window": [max(0.0, sim_time_s - 300.0), sim_time_s]}
    if name == "query_surgery_progress":
        return {"current_time": sim_time_s}
    if name == "query_patient_baseline":
        return {}
    if name == "find_similar_cases":
        return {"k": 5, "surgery_type": "general",
                "current_state": {"sim_time_s": sim_time_s}}
    if name == "intervention_response_prediction":
        return {"intervention": {"name": "no_op", "amount": 0.0, "unit": "none"},
                "horizon_min": 5,
                "current_state": {"sim_time_s": sim_time_s}}
    if name == "surgery_context_awareness":
        return {"surgery_type": "general", "phase": "maintenance"}
    if name == "quality_aware_synthesis":
        return {"predictions": [
                    {"value": 0.0, "quality": 0.5, "source": "placeholder_a"},
                    {"value": 0.0, "quality": 0.5, "source": "placeholder_b"}],
                "method": "weighted_mean"}
    if name == "get_current_vitals":
        return {}
    if name == "describe_signal":
        return {"modality": modalities[0] if modalities else "ABP", "window_min": 5}
    if name == "assess_variability":
        for m in ("HR", "ABP", "MAP", "PPG"):
            if m in modalities:
                return {"modality": m}
        return {"modality": modalities[0] if modalities else "HR"}
    if name == "compare_to_baseline":
        return {"modality": modalities[0] if modalities else "ABP",
                "sampling_rate_hz": 500.0}
    if name == "summarize_current_state":
        return {}
    raise ValueError(f"unknown deep tool: {name}")


# ── Case loading / 케이스 로드 ──


def load_real_case(
    case_id: int, interval: float, *, preprocess: bool
) -> tuple[dict[str, torch.Tensor], list[str], float]:
    """Load + preprocess a VitalDB case → (signal dict, modalities, sampling_rate_hz).
    VitalDB case load + preprocess → (signal dict, modality list, sampling_rate_hz).
    """
    print(f"\n--- Loading VitalDB case {case_id} (interval={interval}s) ---")
    df, sr_hz = load_vitaldb_case(case_id, DEFAULT_TRACKS, interval)
    signal, modalities = df_to_signal_dict(df)
    if not signal:
        raise RuntimeError(f"case {case_id}: all tracks fully NaN")

    if preprocess:
        signal, prep_report = preprocess_signal_dict(signal, sampling_rate_hz=sr_hz)
        clipped_total = sum(
            rep["n_below_range"] + rep["n_above_range"]
            for rep in prep_report.per_modality.values()
        )
        print(f"  [preprocess] clipped={clipped_total} samples across modalities.")
    print(f"  → modalities={modalities}, sr={sr_hz} Hz")
    return signal, modalities, sr_hz


def truncate_to_sim_time(
    signal: dict[str, torch.Tensor], sim_time_s: float, sampling_rate_hz: float
) -> dict[str, torch.Tensor]:
    """Slice the signal dict to [0, sim_time_s] to honor leakage guard.
    Leakage guard 준수: signal 을 [0, sim_time_s] 로 자름.
    """
    n_samples = int(sim_time_s * sampling_rate_hz)
    return {k: v[:n_samples] for k, v in signal.items()}


# ── Stages / 단계 ──


def stage_1_raw_call(endpoint: str, model: str) -> None:
    print(f"\n[1] raw openai SDK call → {endpoint} (model={model})")
    from openai import OpenAI

    client = OpenAI(base_url=endpoint, api_key="ollama-no-auth")
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You answer in one short Korean sentence."},
            {"role": "user", "content": "수술 중 환자 혈압이 떨어지면 가장 먼저 무엇을 확인합니까?"},
        ],
        max_tokens=80, temperature=0.1,
    )
    print(f"  ⏱  {time.perf_counter() - t0:.2f}s")
    print(f"  → {(resp.choices[0].message.content or '').strip()}")


def stage_2_narrate_real(
    endpoint: str, model: str,
    signal: dict[str, torch.Tensor], modalities: list[str],
    sampling_rate_hz: float, sim_time_s: float, case_id: int,
    lang: str = "ko",
) -> None:
    print(f"\n[2] Shallow tools ({len(SHALLOW_TOOL_NAMES)}) on real case → "
          f"narrate() via {model}  (ADR-018 — 8 tool + case_baseline)")

    fm = create_fm({"fm": {"implementation": "mock_rule_based",
                           "config": {"seed": 42,
                                      "sampling_rate_hz": sampling_rate_hz,
                                      "noise_pct": 0.0}}})
    clock = SimClock(start_s=sim_time_s)
    case_tag = f"vitaldb-{case_id}"

    # ADR-018 — case-init: fetch patient baseline once before shallow sweep.
    # ADR-018 — case-init: shallow sweep 전에 환자 baseline 1회 fetch.
    baseline_req = ToolRequest(
        case_id=case_tag, sim_time_s=sim_time_s,
        tool_name="query_patient_baseline", args={},
    )
    t0 = time.perf_counter()
    baseline_resp = call_tool("query_patient_baseline", baseline_req,
                              fm=fm, clock=clock, signal=signal)
    dt = (time.perf_counter() - t0) * 1000
    ok = baseline_resp.ok and baseline_resp.result is not None
    print(f"  · case_init query_patient_baseline    {'ok' if ok else 'ERR':8s} "
          f"{dt:5.0f}ms  baseline={baseline_resp.result if ok else None}")

    tool_results: list[ToolResponse] = []
    for name in SHALLOW_TOOL_NAMES:
        args = _shallow_args(name, sim_time_s, modalities)
        req = ToolRequest(case_id=case_tag, sim_time_s=sim_time_s,
                          tool_name=name, args=args)
        t0 = time.perf_counter()
        resp = call_tool(name, req, fm=fm, clock=clock, signal=signal)
        dt = (time.perf_counter() - t0) * 1000
        ok_str = "ok" if resp.ok else f"ERR({resp.error.type if resp.error else '?'})"
        head = ", ".join(f"{k}={v}" for k, v in list((resp.result or {}).items())[:3])
        print(f"  · {name:32s} {ok_str:8s} {dt:5.0f}ms  {head[:80]}")
        tool_results.append(resp)

    # ADR-018 — inject case_baseline as synthetic tool result for narration.
    # ADR-018 — case_baseline 을 합성 tool result 로 narration 에 주입.
    narration_inputs: list[ToolResponse] = list(tool_results)
    if ok:
        narration_inputs.insert(0, ToolResponse(
            case_id=case_tag, sim_time_s=sim_time_s,
            tool_name="case_baseline", args={},
            result=dict(baseline_resp.result),
            quality_meta={"source": "case_init_cache"},
            latency_ms=0.0,
        ))

    shallow_prompt = (
        "prompts/v1_light_shallow.en.md" if lang == "en"
        else "prompts/v1_light_shallow.md"
    )
    client = VLLMClient(shallow_config={
        "endpoint": endpoint, "model": model,
        "system_prompt_path": shallow_prompt,
        "max_tokens": 120, "temperature": 0.1, "timeout_s": 240.0,
    })
    t0 = time.perf_counter()
    narration = client.narrate(narration_inputs)
    print(f"\n  ⏱  narrate: {time.perf_counter() - t0:.2f}s  (shallow budget 15s)")
    print(f"  → {narration!r}")


def stage_3_brief_real(
    endpoint: str, model: str,
    signal: dict[str, torch.Tensor], modalities: list[str],
    sampling_rate_hz: float, sim_time_s: float, case_id: int,
    lang: str = "ko",
) -> None:
    print(f"\n[3] Deep tools (16) on real case → brief() via {model}")
    print(f"  ⚠ small local models may not produce perfect [Section] headers;")
    print(f"     parser fills missing sections with ''.")

    fm = create_fm({"fm": {"implementation": "mock_rule_based",
                           "config": {"seed": 42,
                                      "sampling_rate_hz": sampling_rate_hz,
                                      "noise_pct": 0.0}}})
    clock = SimClock(start_s=sim_time_s)
    case_tag = f"vitaldb-{case_id}"

    tool_results: list[ToolResponse] = []
    skipped: list[str] = []
    for name in TOOLS:
        try:
            args = _deep_args(name, sim_time_s, modalities)
        except ValueError:
            skipped.append(name)
            continue
        req = ToolRequest(case_id=case_tag, sim_time_s=sim_time_s,
                          tool_name=name, args=args)
        t0 = time.perf_counter()
        resp = call_tool(name, req, fm=fm, clock=clock, signal=signal)
        dt = (time.perf_counter() - t0) * 1000
        ok_str = "ok" if resp.ok else f"ERR({resp.error.type if resp.error else '?'})"
        print(f"  · {name:32s} {ok_str:8s} {dt:5.0f}ms")
        tool_results.append(resp)
    if skipped:
        print(f"  (skipped — no args mapping: {skipped})")

    # Pull surgery context if EMR tool returned it; default otherwise.
    # EMR tool 결과에서 surgery context 추출; 부재 시 default.
    surgery_phase = "maintenance"
    elapsed_min = sim_time_s / 60.0
    for r in tool_results:
        if r.tool_name == "query_surgery_progress" and r.ok and r.result is not None:
            surgery_phase = str(r.result.get("phase", surgery_phase))
            elapsed_min = float(r.result.get("elapsed_min", elapsed_min))
            break

    deep_prompt = (
        "prompts/v2_heavy_deep_brief.en.md" if lang == "en"
        else "prompts/v2_heavy_deep_brief.md"
    )
    client = VLLMClient(deep_config={
        "endpoint": endpoint, "model": model,
        "system_prompt_path": deep_prompt,
        "max_tokens": 900, "temperature": 0.2, "timeout_s": 300.0,
    })
    t0 = time.perf_counter()
    sections = client.brief(
        tool_results,
        surgery_type="general",
        surgery_phase=surgery_phase,
        elapsed_min=elapsed_min,
    )
    print(f"\n  ⏱  brief: {time.perf_counter() - t0:.2f}s  (deep budget 60s)")
    nonempty = sum(1 for v in sections.values() if v.strip())
    print(f"  parsed sections: {nonempty}/9 non-empty")
    for name, body in sections.items():
        short = (body[:160] + "…") if len(body) > 160 else body
        print(f"    [{name}] {short!r}")


# ── Main ──


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--endpoint", default="http://localhost:11434/v1",
                    help="OpenAI-compatible endpoint (default: Ollama local).")
    ap.add_argument("--model", default="llama3.1:8b",
                    help="Model as known by the endpoint (default: llama3.1:8b).")
    ap.add_argument("--case-id", type=int, default=1, help="VitalDB caseid.")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="vitaldb.to_pandas interval seconds (default 1.0).")
    ap.add_argument("--sim-time-s", type=float, default=900.0,
                    help="Simulated clock at which tools are called (default 900s = 15 min).")
    ap.add_argument("--no-preprocess", dest="preprocess", action="store_false",
                    help="Disable signal preprocessing.")
    ap.add_argument("--skip-brief", action="store_true",
                    help="Skip stage 3 (deep brief — slow).")
    ap.add_argument("--skip-stage1", action="store_true",
                    help="Skip raw SDK ping (stage 1).")
    ap.add_argument("--lang", choices=("ko", "en"), default="ko",
                    help="Brief / narrate language (ko=한글 v1/v2; en=v1/v2 .en.md).")
    ap.set_defaults(preprocess=True)
    args = ap.parse_args()

    print(f"=== OpSight LLM smoke test (real VitalDB case) ===")
    print(f"endpoint  = {args.endpoint}")
    print(f"model     = {args.model}")
    print(f"case_id   = {args.case_id}")
    print(f"sim_time  = {args.sim_time_s}s")

    if not args.skip_stage1:
        try:
            stage_1_raw_call(args.endpoint, args.model)
        except Exception as exc:
            print(f"\n[1] FAILED: {type(exc).__name__}: {exc}")
            base = args.endpoint.rsplit('/v1', 1)[0]
            print(f"     → check Ollama:  curl {base}/api/tags")
            sys.exit(1)

    try:
        signal, modalities, sr_hz = load_real_case(
            args.case_id, args.interval, preprocess=args.preprocess
        )
    except Exception as exc:
        print(f"\n[load] FAILED: {type(exc).__name__}: {exc}")
        sys.exit(2)

    # Truncate signal to [0, sim_time_s] so the leakage guard sees only past data.
    # Leakage guard 가 과거 데이터만 보도록 [0, sim_time_s] 로 자름.
    signal_truncated = truncate_to_sim_time(signal, args.sim_time_s, sr_hz)

    try:
        stage_2_narrate_real(args.endpoint, args.model,
                             signal_truncated, modalities, sr_hz,
                             args.sim_time_s, args.case_id, lang=args.lang)
    except Exception as exc:
        print(f"\n[2] FAILED: {type(exc).__name__}: {exc}")
        sys.exit(3)

    if args.skip_brief:
        print("\n[3] skipped (--skip-brief).")
    else:
        try:
            stage_3_brief_real(args.endpoint, args.model,
                               signal_truncated, modalities, sr_hz,
                               args.sim_time_s, args.case_id, lang=args.lang)
        except Exception as exc:
            print(f"\n[3] FAILED: {type(exc).__name__}: {exc}")
            sys.exit(4)

    print("\n=== smoke test OK ===")


if __name__ == "__main__":
    main()
