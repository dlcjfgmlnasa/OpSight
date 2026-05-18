"""Trace JSONL writer (plan_1.8 task 9).
Trace JSONL writer (plan_1.8 task 9).

Captures per-node events to a local JSONL file. The Stage 4 clinician
evaluation workflow consumes ``(brief, trace)`` pairs from this format.
Node별 이벤트를 local JSONL 파일에 캡쳐한다. Stage 4 임상의 평가는 본
포맷에서 ``(brief, trace)`` 쌍을 소비한다.

Format / 포맷: one JSON object per line. Each event has:
한 줄당 JSON 객체 하나. 각 이벤트는 다음을 가진다:

- ``trace_id``  : run-wide identifier / 실행 전반 식별자
- ``case_id``   : VitalDB case ID
- ``sim_time_s``: simulated time at the event / 이벤트 시점 sim-time
- ``wall_time`` : Unix epoch ms / Unix epoch ms
- ``event``     : "tick" | "tool_call" | "tool_result" | "narration"
                  | "trigger" | "brief" | "error"
- ``payload``   : event-specific dict / 이벤트별 dict

Spec: ``docs/project_brief.md §10`` (real-time framing) + plan_1.8 task 9.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, TextIO


class TraceWriter:
    """Append-only JSONL writer scoped to a single trace_id.
    단일 trace_id에 scope된 append-only JSONL writer.

    Usage / 사용 예::

        with TraceWriter("logs/trace.jsonl", trace_id="run-1", case_id="c1") as tw:
            tw.event("tick", {"sim_time_s": 30.0})
            tw.event("narration", {"text": "..."})
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        trace_id: str,
        case_id: str,
    ) -> None:
        """Open the file in append mode / append 모드로 파일 open.

        Args:
            path: target JSONL path; parent directory is created if missing.
                JSONL 경로; 부모 디렉토리는 없으면 생성.
            trace_id: run-wide identifier injected into every record.
                모든 record에 주입되는 run-wide 식별자.
            case_id: VitalDB case ID for the run.
                실행 대상 VitalDB case ID.
        """
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._trace_id = trace_id
        self._case_id = case_id
        self._fp: TextIO | None = None

    def __enter__(self) -> TraceWriter:
        self._fp = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    def event(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        sim_time_s: float = 0.0,
    ) -> None:
        """Append one event to the trace file.
        Trace 파일에 이벤트 하나 append.

        Args:
            event: event tag (e.g. ``"tick"``, ``"narration"``).
            payload: event-specific dict (must be JSON-serializable).
            sim_time_s: simulated time at the event.
        """
        if self._fp is None:
            raise RuntimeError("TraceWriter must be used as a context manager")
        record = {
            "trace_id": self._trace_id,
            "case_id": self._case_id,
            "sim_time_s": sim_time_s,
            "wall_time_ms": int(time.time() * 1000),
            "event": event,
            "payload": payload,
        }
        # ensure_ascii=False so Korean text is readable in raw JSONL
        # ensure_ascii=False — raw JSONL에서 한글 가독성 확보
        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()


def read_trace(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read back a JSONL trace as a list of dicts.
    JSONL trace를 dict 리스트로 다시 읽는다.

    Convenience for tests and the eventual viewer tool.
    Test와 향후 viewer tool 편의용.
    """
    out: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


__all__ = ["TraceWriter", "read_trace"]
