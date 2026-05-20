"""Live tick-by-tick viewer for OpSight on a real VitalDB case.
실 VitalDB case 의 tick 흐름을 콘솔에서 라이브로 본다.

Bypasses ``graph.invoke`` and drives the nodes directly so each tick can be
printed before the next one starts. Output one line per shallow tick + an
indented sub-line when a deep brief fires.

Usage::

    # Placeholder LLM, fast (1-2 s/tick wall):
    python scripts/live_view.py --case-id 3 --max-ticks 30 --tick-sec 30 --pace 0.8

    # Real LLM streaming (Ollama llama3.1:8b, Korean):
    python scripts/live_view.py --case-id 13 --max-ticks 5 --pace 0 --llm

    # English narration via OpenBioLLM (or any English medical model):
    python scripts/live_view.py --case-id 13 --max-ticks 5 --pace 0 --llm \\
        --model koesn/llama3-openbiollm-8b --lang en

Args:
  --case-id    VitalDB case ID (default 3)
  --max-ticks  number of shallow ticks (default 30 = 15 min sim)
  --tick-sec   sim seconds per tick (default 30)
  --pace       wall-clock seconds to sleep between ticks (default 0.8;
               set 0 for fastest scroll, ~2 for slow-read)
  --llm        stream a real narration via Ollama / OpenAI-compatible endpoint
  --endpoint   OpenAI-compatible endpoint (default http://localhost:11434/v1)
  --model      model name on that endpoint (default llama3.1:8b)
  --lang       narration language: 'ko' (default) or 'en' (with English models)
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opsight.fm.factory import create_fm
from opsight.llm.vllm_client import VLLMClient
from opsight.nodes.shallow_loop import run_shallow_loop
from opsight.nodes.deep_brief import run_deep_brief
from opsight.preprocessing import preprocess_signal_dict
from opsight.signal_stream import stream_from_full_signal
from opsight.sim_clock import SimClock
from opsight.state import AgentState
from opsight.tools.envelope import ToolRequest, ToolResponse
from opsight.tools.registry import call_tool
from opsight.triggers import should_escalate


PRIORITY_TRACKS = [
    # ── Vitals (Solar8000, 1Hz numeric) ──
    "Solar8000/HR",
    "Solar8000/PLETH_HR",
    "Solar8000/ART_MBP", "Solar8000/ART_SBP", "Solar8000/ART_DBP",
    "Solar8000/NIBP_MBP", "Solar8000/NIBP_SBP", "Solar8000/NIBP_DBP",
    "Solar8000/PLETH_SPO2",
    "Solar8000/ETCO2",
    "Solar8000/BT",
    "Solar8000/CVP",
    "Solar8000/RR_CO2",
    "Solar8000/RR",
    # ── BIS (1Hz numeric + 128Hz waveform) ──
    "BIS/BIS",
    "BIS/SQI", "BIS/EMG", "BIS/SR", "BIS/SEF",
    "BIS/EEG1_WAV",
    # ── SNUADC raw waveforms (500Hz native; loaded at 1Hz here) ──
    "SNUADC/ECG_II", "SNUADC/ECG_V5",
    "SNUADC/PLETH",
    "SNUADC/ART",
    "SNUADC/CVP",
    # ── Primus anesthesia machine (~1Hz + 62.5Hz waveform) ──
    "Primus/CO2", "Primus/AWP",                    # waveforms
    "Primus/MAC",
    "Primus/EXP_SEVO", "Primus/INSP_SEVO",         # sevoflurane concentration
    "Primus/ETCO2", "Primus/RR_CO2",
    "Primus/PEEP_MBAR", "Primus/PIP_MBAR",
    # ── Orchestra drug infusion (1Hz) ──
    "Orchestra/RFTN20_CE", "Orchestra/RFTN20_RATE",   # remifentanil
    "Orchestra/PPF20_CE", "Orchestra/PPF20_RATE",     # propofol
    "Orchestra/PHEN_RATE",                            # phenylephrine
    "Orchestra/NEPI_RATE",                            # norepinephrine
    "Orchestra/DOPA_RATE",                            # dopamine
    "Orchestra/EPI_RATE",                             # epinephrine
    "Orchestra/ROC_RATE",                             # rocuronium
]


TRACK_TO_ALIAS = {
    # ── Vitals (numeric parameters — preprocessing applies physiological clip) ──
    "Solar8000/HR": "HR",
    "Solar8000/PLETH_HR": "HR_ppg",
    # NB: Solar8000/ART_MBP is a 1Hz numeric mean — alias "MAP". SNUADC/ART is
    # the 500Hz waveform — alias "ABP" below.
    "Solar8000/ART_MBP": "MAP",
    "Solar8000/ART_SBP": "SBP",
    "Solar8000/ART_DBP": "DBP",
    "Solar8000/NIBP_MBP": "NIBP_MBP",
    "Solar8000/NIBP_SBP": "NIBP_SBP",
    "Solar8000/NIBP_DBP": "NIBP_DBP",
    "Solar8000/PLETH_SPO2": "SpO2",
    "Solar8000/ETCO2": "EtCO2",
    "Solar8000/BT": "BT",
    "Solar8000/CVP": "CVP_MEAN",                 # numeric — distinct from CVP waveform
    "Solar8000/RR_CO2": "RR_CO2",
    "Solar8000/RR": "RR",
    # ── BIS ──
    "BIS/BIS": "BIS",
    "BIS/SQI": "BIS_SQI",
    "BIS/EMG": "BIS_EMG",
    "BIS/SR": "BIS_SR",
    "BIS/SEF": "BIS_SEF",
    "BIS/EEG1_WAV": "EEG",
    # ── SNUADC waveforms ──
    "SNUADC/ECG_II": "ECG",
    "SNUADC/ECG_V5": "ECG_V5",
    "SNUADC/PLETH": "PPG",
    "SNUADC/ART": "ABP",
    "SNUADC/CVP": "CVP",                         # raw waveform
    # ── Primus ──
    "Primus/CO2": "CO2",
    "Primus/AWP": "AWP",
    "Primus/MAC": "MAC",
    "Primus/EXP_SEVO": "SEVO_exp",
    "Primus/INSP_SEVO": "SEVO_insp",
    "Primus/ETCO2": "EtCO2_pr",
    "Primus/RR_CO2": "RR_CO2_pr",
    "Primus/PEEP_MBAR": "PEEP",
    "Primus/PIP_MBAR": "PIP",
    # ── Orchestra drugs (rate in mL/h or CE in ng/mL etc.) ──
    "Orchestra/RFTN20_CE": "RFTN_CE",
    "Orchestra/RFTN20_RATE": "RFTN_rate",
    "Orchestra/PPF20_CE": "PPF_CE",
    "Orchestra/PPF20_RATE": "PPF_rate",
    "Orchestra/PHEN_RATE": "PHEN",
    "Orchestra/NEPI_RATE": "NEPI",
    "Orchestra/DOPA_RATE": "DOPA",
    "Orchestra/EPI_RATE": "EPI",
    "Orchestra/ROC_RATE": "ROC",
}


# Display groups — modality lines are rendered in 3 grouped rows so a 200-char
# terminal can fit everything legibly.
# 표시 그룹 — 한 tick 의 modality 가 3 줄로 나뉘어 200자 터미널에 들어맞도록.
_DISPLAY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("VITALS  ", ("HR", "MAP", "SBP", "DBP", "NIBP_MBP",
                  "NIBP_SBP", "NIBP_DBP", "SpO2", "EtCO2", "BT",
                  "CVP_MEAN", "BIS", "MAC")),
    ("WAVES   ", ("ECG", "ECG_V5", "PPG", "ABP", "CVP", "EEG",
                  "CO2", "AWP")),
    ("DRUGS   ", ("RFTN_CE", "RFTN_rate", "PPF_CE", "PPF_rate",
                  "PHEN", "NEPI", "DOPA", "EPI", "ROC",
                  "SEVO_exp", "SEVO_insp")),
)


# ── ANSI helpers (Windows 10+ supports VT) ──
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
GRN = "\033[32m"
YLW = "\033[33m"
RED = "\033[31m"
CYN = "\033[36m"
MAG = "\033[35m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def _enable_vt() -> None:
    """Best-effort ANSI VT enable on Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(h, ctypes.byref(mode))
        kernel32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


def _utf8_console() -> None:
    if sys.platform != "win32":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _load_real_case(case_id: int) -> tuple[
    dict[str, torch.Tensor], list[str], float
]:
    import vitaldb
    vf = vitaldb.VitalFile(case_id, track_names=PRIORITY_TRACKS)
    df = vf.to_pandas(PRIORITY_TRACKS, interval=1.0)
    signal: dict[str, torch.Tensor] = {}
    modalities: list[str] = []
    for col in df.columns:
        arr = df[col].to_numpy(dtype=np.float64)
        if np.isnan(arr).all():
            continue
        alias = TRACK_TO_ALIAS.get(col, col)
        signal[alias] = torch.from_numpy(arr.astype(np.float32))
        modalities.append(alias)
    return signal, modalities, 1.0


def _fmt_mmss(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _last_finite(t: torch.Tensor, until_s: float, sr_hz: float) -> float | None:
    """Most recent finite sample at or before ``until_s`` (s)."""
    idx = int(until_s * sr_hz)
    idx = min(idx, t.shape[0] - 1)
    sl = t[: idx + 1]
    if sl.numel() == 0:
        return None
    finite = sl[torch.isfinite(sl)]
    if finite.numel() == 0:
        return None
    return float(finite[-1].item())


def _window_finite_ratio(
    t: torch.Tensor, until_s: float, sr_hz: float, window_s: float = 30.0,
) -> float:
    """Finite-sample ratio in the most recent ``window_s`` seconds.
    직전 ``window_s`` 초 window 의 finite-sample 비율 (0–1).
    """
    idx_end = int(until_s * sr_hz)
    idx_end = min(idx_end, t.shape[0] - 1)
    idx_start = max(0, idx_end - int(window_s * sr_hz))
    sl = t[idx_start: idx_end + 1]
    if sl.numel() == 0:
        return 0.0
    finite = torch.isfinite(sl).sum().item()
    return finite / float(sl.numel())


def _ratio_bar(r: float) -> str:
    """2-cell unicode block bar for a 0–1 ratio.
    0–1 비율을 2-cell unicode block 으로 표시.
    """
    if r <= 0.05:
        return "  "
    if r < 0.30:
        return "▒ "
    if r < 0.60:
        return "█ "
    if r < 0.90:
        return "█▒"
    return "██"


# Modalities whose 1Hz-snapshot value is *not* clinically meaningful — these
# are raw waveforms (mV / ADC / mmHg waveform) and a single 1-second snapshot
# captures whatever the waveform happened to be at that instant (most often
# the isoelectric baseline). For these we show only the liveness bar; the
# actual value is suppressed to avoid the user reading meaning into noise.
# Parameter modalities (HR / MAP / SpO2 / EtCO2 / BIS / NIBP) carry their
# instantaneous reading at 1Hz natively — show their value.
# 1Hz snapshot 이 임상적 의미 없는 raw waveform — value 숨기고 liveness 만.
# Parameter modality 는 1Hz 가 native 라 value 표시.
_WAVEFORM_KEYS = frozenset({
    "ECG", "PPG", "ABP", "CO2", "AWP",
    "CVP",   # SNUADC/CVP — invasive CVP waveform (numeric mean = CVP_MEAN, separate key)
    "EEG",   # BIS/EEG1_WAV / BIS/EEG2_WAV — raw EEG waveform (numeric BIS = BIS, separate key)
})


def _modality_snapshot_with_bars(
    signal: dict[str, torch.Tensor],
    sim_time_s: float,
    sr_hz: float,
    prev_ratios: dict[str, float] | None,
    keys: tuple[str, ...] = (
        "HR", "MAP", "PPG", "ECG", "SpO2", "EtCO2", "BIS", "CVP", "EEG",
    ),
) -> tuple[str, dict[str, float], list[str]]:
    """Render ``HR=76[██] ECG[██] ...`` and detect modality transitions.

    Parameter modalities show ``KEY=VAL[bar]``; raw-waveform modalities
    (``ECG`` / ``PPG`` / ``ABP``) show ``KEY[bar]`` only — value omitted
    because a single 1Hz snapshot of a waveform is uninformative.
    Parameter modality 는 ``KEY=VAL[bar]`` 표시; raw waveform 은 ``KEY[bar]``
    만 (1Hz snapshot 값이 무의미).

    Returns ``(rendered_line, current_ratios, transition_messages)``.
    transition_messages: ["NIBP came online (0.05 -> 0.85)", ...]
    """
    parts: list[str] = []
    current: dict[str, float] = {}
    transitions: list[str] = []
    for k in keys:
        is_wave = k in _WAVEFORM_KEYS
        if k not in signal:
            # Modality absent in this case — omit from display entirely.
            # 본 case 에 없는 modality 는 표시 자체에서 생략.
            current[k] = 0.0
            continue
        v = _last_finite(signal[k], sim_time_s, sr_hz)
        ratio = _window_finite_ratio(signal[k], sim_time_s, sr_hz)
        current[k] = ratio
        # Transition detection runs *before* the display filter so we still
        # log "came online" / "went dark" even if the bar is currently hidden.
        # Transition 감지는 표시 필터 *전* 에 — bar 가 숨겨져도 transition 로깅.
        if prev_ratios is not None:
            prev = prev_ratios.get(k, 0.0)
            if prev < 0.3 <= ratio:
                transitions.append(f"{k} came online ({prev:.2f}→{ratio:.2f})")
            elif ratio < 0.3 <= prev:
                transitions.append(f"{k} went dark ({prev:.2f}→{ratio:.2f})")
        # If the modality is currently silent in this window, omit from display.
        # The key remains in ``current`` for the next-tick transition compare,
        # but the bar is not rendered — keeps the live row free of "MAP=-[  ]"
        # clutter for modalities that were only briefly available.
        # 현재 silent 면 표시에서 생략. transition 비교는 current 에 남김.
        if ratio < 0.05:
            continue
        bar = _ratio_bar(ratio)
        # Color the bar by liveness.
        if ratio >= 0.9:
            bar_c = _color(bar, GRN)
        elif ratio >= 0.5:
            bar_c = _color(bar, YLW)
        else:
            bar_c = _color(bar, DIM)
        if is_wave:
            # Raw waveform — liveness only, value omitted.
            # Raw waveform — liveness 만, value 생략.
            parts.append(f"{k}[{bar_c}]")
        else:
            val_str = "-" if v is None or not math.isfinite(v) else f"{v:.0f}"
            parts.append(f"{k}={val_str:>3}[{bar_c}]")
    return "  ".join(parts), current, transitions


def _modality_snapshot(
    signal: dict[str, torch.Tensor], sim_time_s: float, sr_hz: float,
    keys: tuple[str, ...] = (
        "HR", "MAP", "PPG", "ECG", "SpO2", "EtCO2", "BIS", "CVP", "EEG",
    ),
) -> str:
    """Backward-compatible plain snapshot (no bars, no transitions)."""
    line, _, _ = _modality_snapshot_with_bars(
        signal, sim_time_s, sr_hz, prev_ratios=None, keys=keys,
    )
    return line


def _grouped_modality_snapshot(
    signal: dict[str, torch.Tensor],
    sim_time_s: float,
    sr_hz: float,
    prev_ratios: dict[str, float] | None,
) -> tuple[list[tuple[str, str]], dict[str, float], list[str]]:
    """Render the modality set as grouped multi-line output.

    Groups that have *zero* modalities present in this case (line is empty
    after filtering absent keys) are skipped entirely — keeps the live output
    free of "DRUGS: (all absent)" clutter for cases without Orchestra data.
    case 에 한 modality 도 없는 그룹은 통째로 생략.

    Returns ``(group_lines, ratios, transitions)`` with only non-empty groups.
    """
    accumulated_ratios: dict[str, float] = {}
    accumulated_transitions: list[str] = []
    group_lines: list[tuple[str, str]] = []
    for label, keys in _DISPLAY_GROUPS:
        line, ratios, transitions = _modality_snapshot_with_bars(
            signal, sim_time_s, sr_hz,
            prev_ratios=prev_ratios, keys=keys,
        )
        accumulated_ratios.update(ratios)
        accumulated_transitions.extend(transitions)
        if line:   # at least one modality of this group is present
            group_lines.append((label, line))
    return group_lines, accumulated_ratios, accumulated_transitions


def _make_streamer(endpoint: str, model: str, lang: str = "ko"):
    """Returns ``stream_narrate(tool_results)`` that prints tokens live.
    각 토큰을 stdout 에 즉시 print 하며 narration 을 스트림한다.

    Args:
        lang: 'ko' (default) loads ``v1_light_shallow.md``; 'en' loads
            ``v1_light_shallow.en.md``. Use 'en' with English-medical models
            (OpenBioLLM etc.).
        lang: 'ko' (기본) 한글 prompt; 'en' 영문 prompt (OpenBioLLM 등).
    """
    from openai import OpenAI

    prompt_name = "v1_light_shallow.en.md" if lang == "en" else "v1_light_shallow.md"
    prompt_path = _REPO_ROOT / "prompts" / prompt_name
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt missing: {prompt_path}")
    system_msg = prompt_path.read_text(encoding="utf-8")

    client = OpenAI(base_url=endpoint, api_key="local-no-auth")
    # ``_serialize_tool_results`` is a static method on VLLMClient — reuse to
    # match the exact user-message shape that production narrate() would send.
    serialize = VLLMClient._serialize_tool_results

    def stream_narrate(tool_results: list[ToolResponse]) -> tuple[str, float]:
        user_msg = serialize(tool_results)
        t0 = time.perf_counter()
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=80,
            temperature=0.1,
            stream=True,
        )
        sys.stdout.write(_color("          ▶ ", GRN))
        sys.stdout.flush()
        full = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            sys.stdout.write(_color(delta, GRN))
            sys.stdout.flush()
            full.append(delta)
        elapsed = time.perf_counter() - t0
        sys.stdout.write(_color(f"  ({elapsed:.1f}s)\n", DIM))
        sys.stdout.flush()
        return "".join(full), elapsed

    return stream_narrate


def _shallow_summary(state: AgentState) -> str:
    """Pull key numbers from the most recent shallow sweep."""
    hypo = arrest = qual = anom = None
    state_label = "-"
    for r in state.last_tool_results:
        if not r.ok or r.result is None:
            continue
        if r.tool_name == "predict_hypotension":
            hypo = r.result.get("risk")
        elif r.tool_name == "predict_cardiac_arrest":
            arrest = r.result.get("risk")
        elif r.tool_name == "assess_signal_quality":
            qual = r.result.get("score")
        elif r.tool_name == "anomaly_score":
            anom = r.result.get("score")
        elif r.tool_name == "summarize_current_state":
            anes = r.result.get("anesthesia_state", "-") or "-"
            state_label = anes.replace("possibly_", "")[:6]

    def f(x: Any) -> str:
        return f"{x:.2f}" if isinstance(x, (int, float)) else "-"
    return (f"hypo={f(hypo)} arrest={f(arrest)} "
            f"q={f(qual)} anom={f(anom)} anes={state_label}")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", type=int, default=112)
    parser.add_argument("--max-ticks", type=int, default=300)
    parser.add_argument("--tick-sec", type=float, default=30.0)
    parser.add_argument("--pace", type=float, default=0.8,
                        help="real seconds to sleep between ticks (0 = no delay)")
    parser.add_argument("--llm", action="store_true",
                        help="stream real narration via Ollama / OpenAI endpoint")
    parser.add_argument("--endpoint", type=str,
                        default="http://localhost:11434/v1")
    parser.add_argument("--model", type=str, default="llama3.1:8b")
    parser.add_argument("--lang", choices=("ko", "en"), default="ko",
                        help="Narration language — 'ko' (한글, default) or 'en' "
                        "(English; use with OpenBioLLM or other English-medical "
                        "model).")
    args = parser.parse_args()

    _utf8_console()
    _enable_vt()

    print(_color("=== OpSight live view ===", BOLD))
    print(f"case_id   = {args.case_id}")
    print(f"max_ticks = {args.max_ticks}  ({args.max_ticks * args.tick_sec / 60:.1f} min sim)")
    print(f"tick_sec  = {args.tick_sec}s sim / {args.pace}s wall pace")
    print()

    print(_color(f"[load] VitalDB case {args.case_id}...", DIM))
    t0 = time.perf_counter()
    signal, modalities, sr_hz = _load_real_case(args.case_id)
    print(_color(f"[load] {len(next(iter(signal.values())))} samples × "
                 f"{len(signal)} tracks in {time.perf_counter()-t0:.1f}s "
                 f"({', '.join(modalities)})", DIM))

    signal, prep_report = preprocess_signal_dict(signal, sampling_rate_hz=sr_hz)
    rates = {
        mod: float(rep["output_sampling_rate_hz"])
        for mod, rep in prep_report.per_modality.items()
    }
    stream = stream_from_full_signal(
        signal, sampling_rates_hz=rates, default_sampling_rate_hz=sr_hz
    )
    fm = create_fm({
        "fm": {
            "implementation": "mock_rule_based",
            "config": {"seed": 42, "sampling_rate_hz": sr_hz, "noise_pct": 0.0},
        }
    })
    clock = SimClock(start_s=0.0)
    state = AgentState(case_id=f"vitaldb-{args.case_id}",
                       trace_id=f"live-{args.case_id}")

    # ── case-init (ADR-018) — populate case_baseline once ──
    req = ToolRequest(
        case_id=state.case_id, sim_time_s=state.sim_time_s,
        tool_name="query_patient_baseline", args={},
    )
    sliced = stream.view_until(state.sim_time_s)
    resp = call_tool("query_patient_baseline", req, fm=fm, clock=clock, signal=sliced)
    state = state.model_copy(update={
        "case_baseline": resp.result if resp.ok else None
    })
    if resp.ok and resp.result:
        bl = resp.result
        print(_color(f"[case_init] baseline: age={bl.get('age')} "
                     f"sex={bl.get('sex')} asa={bl.get('asa')} "
                     f"comorbid={bl.get('comorbidities')} "
                     f"baseline_bp={bl.get('baseline_bp')}", DIM))

    # LLM streamer (lazy — only built if --llm).
    stream_narrate = None
    if args.llm:
        print(_color(f"[llm] connecting to {args.endpoint} ({args.model})", DIM))
        try:
            stream_narrate = _make_streamer(args.endpoint, args.model, lang=args.lang)
        except Exception as e:
            print(_color(f"[llm] disabled — {e!r}", YLW))
            stream_narrate = None

    print()
    print(_color(
        "Per-tick grouped output:  VITALS (numeric vitals) / WAVES (raw waveforms) / "
        "DRUGS (Orchestra infusion) / PRED (FM predictions)",
        BOLD,
    ))
    print(_color("  bar = 30s window finite ratio (██=≥0.9  █▒=≥0.6  █ =≥0.3  "
                 "▒ =≥0.05  ' '=<0.05 silent)", DIM))
    print(_color("  Parameter values are 1Hz-meaningful (show VAL); raw waveform "
                 "snapshots are not (show [bar] only).", DIM))
    print(_color("-" * 150, DIM))

    deep_briefs_fired = 0
    trigger_counter: dict[str, int] = {}
    prev_ratios: dict[str, float] | None = None
    tick_i = 0

    for tick_i in range(1, args.max_ticks + 1):
        clock.tick(args.tick_sec)
        state = state.model_copy(update={
            "sim_time_s": clock.now_s,
            "scratch": {**state.scratch, "tick_count": tick_i},
        })

        # Shallow sweep.
        sliced = stream.view_until(state.sim_time_s)
        state = run_shallow_loop(
            state, fm=fm, clock=clock, signal=sliced,
            modalities=modalities, llm_client=None,
        )

        # Trigger evaluation.
        fire, reason = should_escalate(state)
        mode_label = "shallow"
        deep_line = None
        if fire:
            mode_label = _color(f"TRIGGER {reason.split(' ',1)[0]}", YLW)
            sliced = stream.view_until(state.sim_time_s)
            t_deep0 = time.perf_counter()
            state = run_deep_brief(
                state, fm=fm, clock=clock, signal=sliced,
                modalities=modalities, trigger_reason=reason, llm_client=None,
            )
            deep_ms = (time.perf_counter() - t_deep0) * 1000.0
            deep_briefs_fired += 1
            short = reason.split(' ', 1)[0]
            trigger_counter[short] = trigger_counter.get(short, 0) + 1
            deep_line = (_color(
                f"          └─ deep brief #{deep_briefs_fired}  "
                f"21 tools  {deep_ms:.0f}ms  trigger={reason}", MAG
            ))

        group_lines, prev_ratios, transitions = _grouped_modality_snapshot(
            signal, state.sim_time_s, sr_hz, prev_ratios=prev_ratios,
        )
        preds = _shallow_summary(state)
        # First group printed on the header line with sim-time and tick number,
        # subsequent groups indented to align with the first group's start.
        # 첫 그룹은 sim-time / tick 헤더와 같은 줄, 이후 그룹은 들여쓰기 정렬.
        time_header = f"{_color('['+_fmt_mmss(state.sim_time_s)+']', CYN):>16}  {tick_i:>4}  "
        cont_prefix = " " * 24  # visual width of header (no ANSI escapes counted)
        if group_lines:
            first_label, first_line = group_lines[0]
            print(f"{time_header}{_color(first_label, BOLD)} {first_line}")
            for label, line in group_lines[1:]:
                print(f"{cont_prefix}{_color(label, BOLD)} {line}")
        else:
            # All modalities absent in this case — still print time anchor.
            # 모든 modality 부재 — 시간 anchor 만 출력.
            print(f"{time_header}{_color('(no modalities present)', DIM)}")
        # Predictions on their own indented line for legibility.
        # 예측은 별도 들여쓴 줄.
        print(f"{cont_prefix}{_color('PRED    ', BOLD)} {preds}  {mode_label}")
        if transitions:
            for msg in transitions:
                print(_color(f"          ⚡ modality transition: {msg}", YLW))
        if deep_line:
            print(deep_line)

        # Stream a real LLM narration if --llm enabled.
        # --llm enabled 일 때 실 LLM 으로 narration 스트림.
        if stream_narrate is not None:
            try:
                stream_narrate(list(state.last_tool_results))
            except Exception as e:
                print(_color(f"          ! narrate error: {e!r}", RED))

        if args.pace > 0:
            time.sleep(args.pace)

    print()
    print(_color("=" * 60, DIM))
    print(_color(f"FINAL  sim={_fmt_mmss(state.sim_time_s)}  "
                 f"ticks={tick_i}  deep_briefs={deep_briefs_fired}", BOLD))
    if trigger_counter:
        for k, v in sorted(trigger_counter.items(), key=lambda x: -x[1]):
            print(f"  · {k}: {v}")
    else:
        print(_color("  (no trigger fired)", DIM))
    return 0


if __name__ == "__main__":
    sys.exit(main())
