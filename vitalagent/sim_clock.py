"""Simulated real-time clock (plan_1.8 task 4).
시뮬레이션된 실시간 clock (plan_1.8 task 4).

Tracks the agent's perception of time across a case. Sim-time advances in
explicit ticks (1 s or 30 s by default). Wall-clock measurement hooks let
nodes record how long each tick actually took.
Case 동안 agent의 시간 인식을 추적한다. Sim-time은 명시적 tick (기본 1초
또는 30초)으로 진행한다. Wall-clock 측정 hook은 각 tick의 실 소요 시간을
기록한다.

⚠️ Strict invariant (project_brief §13.2 — data leakage rule):
   Tools and nodes downstream of this clock MUST NOT access data with
   timestamp ``> SimClock.now_s``. Any violation is a hard error.
⚠️ 강한 invariant (project_brief §13.2 — 데이터 누수 규칙):
   본 clock의 downstream tool / node는 timestamp ``> SimClock.now_s``인 데이터에
   절대 접근하지 않는다. 위반은 hard error.

Spec: ``docs/project_brief.md §10`` (Real-time framing — simulated).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TickMeasurement:
    """Wall-clock measurement for a single tick.
    단일 tick의 wall-clock 측정.
    """

    sim_time_before_s: float
    sim_time_after_s: float
    wall_start: float
    wall_end: float

    @property
    def sim_advance_s(self) -> float:
        """Sim-time advanced this tick (s) / 본 tick에서 진행된 sim-time (초)."""
        return self.sim_time_after_s - self.sim_time_before_s

    @property
    def wall_elapsed_s(self) -> float:
        """Wall-clock elapsed this tick (s) / 본 tick의 wall-clock 경과 (초)."""
        return self.wall_end - self.wall_start


class SimClock:
    """Simulated real-time clock — explicit tick-based.
    명시적 tick 기반 시뮬레이션 실시간 clock.

    The clock starts at ``start_s`` (default 0) and advances only when
    ``tick(...)`` is called. It is NOT a background timer; nodes drive it.
    Clock은 ``start_s`` (기본 0)에서 시작하며 ``tick(...)`` 호출 시에만
    진행한다. Background timer가 아니다 — node가 구동한다.

    Wall-clock measurements are accumulated for latency profiling
    (project_brief §6.1 shallow loop budget < 15 s).
    Wall-clock 측정은 latency profiling용 (project_brief §6.1 shallow loop
    예산 < 15초).
    """

    def __init__(self, start_s: float = 0.0) -> None:
        """Initialize with simulated time ``start_s`` / 시뮬레이션 시간 ``start_s``로 초기화."""
        self._now_s: float = float(start_s)
        self._tick_history: list[TickMeasurement] = []

    @property
    def now_s(self) -> float:
        """Current simulated time in seconds / 현재 시뮬레이션 시간 (초)."""
        return self._now_s

    @property
    def tick_history(self) -> list[TickMeasurement]:
        """Read-only view of past tick measurements.
        과거 tick 측정 read-only view.
        """
        return list(self._tick_history)

    def tick(self, sim_advance_s: float = 30.0) -> TickMeasurement:
        """Advance sim-time by ``sim_advance_s`` and record wall-clock span.
        Sim-time을 ``sim_advance_s``만큼 진행하고 wall-clock span을 기록한다.

        Args:
            sim_advance_s: simulated seconds to advance. Default 30 s
                matches the shallow-loop cadence (brief §6.1).
                진행할 시뮬레이션 초. 기본 30초는 shallow-loop cadence와 일치.

        Returns:
            :class:`TickMeasurement` capturing sim-time and wall-clock span.
            sim-time과 wall-clock span을 캡쳐한 :class:`TickMeasurement`.
        """
        if sim_advance_s <= 0:
            raise ValueError(
                f"sim_advance_s must be positive (got {sim_advance_s})"
            )
        wall_start = time.perf_counter()
        before = self._now_s
        # Wall-clock measurement is for the tick boundary itself — caller
        # is expected to perform work AFTER tick() and read wall_end via
        # ``measure_tick_end`` for accurate node-work latency.
        # Wall-clock 측정은 tick boundary 자체. 호출자는 tick() 후 작업을 수행하고
        # 정확한 node 작업 latency를 위해 ``measure_tick_end``로 wall_end 읽는다.
        self._now_s = before + float(sim_advance_s)
        wall_end = time.perf_counter()
        m = TickMeasurement(
            sim_time_before_s=before,
            sim_time_after_s=self._now_s,
            wall_start=wall_start,
            wall_end=wall_end,
        )
        self._tick_history.append(m)
        return m

    def measure_tick_end(self, measurement: TickMeasurement) -> TickMeasurement:
        """Update ``wall_end`` to *now* — call after node work completes.
        ``wall_end``를 *now*로 갱신 — node 작업 완료 후 호출.

        Returns a new immutable ``TickMeasurement`` (dataclass is mutable but
        we mutate-and-return for caller clarity). The original record in
        ``tick_history`` is updated in place.
        새 ``TickMeasurement`` 반환 (dataclass는 mutable이지만 명료성을 위해
        반환). ``tick_history``의 원본은 in-place 갱신된다.
        """
        measurement.wall_end = time.perf_counter()
        return measurement

    def assert_le(self, query_window_end_s: float) -> None:
        """Leakage guard / 누수 가드.

        Raises ``ValueError`` if a tool tries to read past the current sim-time.
        Tool이 현재 sim-time 이후를 읽으려 하면 ``ValueError``를 발생시킨다.

        Spec: project_brief §13.2 (No data leakage).
        """
        if query_window_end_s > self._now_s:
            raise ValueError(
                f"data leakage: query_window_end_s={query_window_end_s} "
                f"exceeds current sim_time={self._now_s}"
            )


__all__ = ["SimClock", "TickMeasurement"]
