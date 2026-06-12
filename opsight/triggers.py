"""Deep-mode trigger engine (plan_1.8 task 7).
Deep-mode trigger engine (plan_1.8 task 7).

Pure-function `should_escalate(state) → (bool, reason)`. **NO LLM** —
deterministic rule-based dispatch per project_brief §13.3.
순수 함수 `should_escalate(state) → (bool, reason)`. **LLM 사용 X** —
project_brief §13.3에 따른 deterministic rule-based dispatch.

Implements the 7 triggers from project_brief §6.3 plus a 60-second cooldown.
project_brief §6.3의 7개 trigger + 60초 cooldown 구현.

Trigger list / Trigger 목록 (brief §6.3):
1. Hypotension risk > 0.7
2. Rapid risk increase (Δ > 0.3 in 30 sec)
3. Signal quality degradation (avg drop > 0.3)
4. Cross-modal inconsistency (< 0.4 with good quality)
5. Acute event warning (arrest > 0.5)
6. Clinician on-demand
7. Periodic deep check (every 5 min)
8. Triage alarm (ADR-023) — router/investigation 이 알람을 확정한 tick

⚠️ ADR-023 (tiered escalation): FM 기반 trigger 1–5 는 FM 분리 후 producer 가 없어
   현재 **dormant**. 실제 live escalation driver 는 6(clinician) / 7(periodic) / 8(triage
   alarm) 이며, 그중 **8(triage alarm)이 state 기반 주 driver** 다 — router 가 FM 없이
   vital 로 "깊이 봐야 하는가"를 판정하고, 알람 확정 시 deep brief(설명 리포트)가 따라온다.
   Real FM 도착 시 risk 점수는 별도 trigger 가 아니라 router 의 추가 신호로 합류한다.
⚠️ Trigger threshold는 brief §6.3 그대로. ``[CLINICIAN-REVIEW: 의료진 검토 필요]``
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opsight.state import AgentState


# ── Constants from project_brief §6.3 / brief §6.3 상수 ──
HYPOTENSION_RISK_THRESHOLD: float = 0.7
RISK_DELTA_WINDOW_S: float = 30.0
RISK_DELTA_THRESHOLD: float = 0.3
QUALITY_DROP_THRESHOLD: float = 0.3
CONSISTENCY_THRESHOLD: float = 0.4
CONSISTENCY_GOOD_QUALITY_GATE: float = 0.7
ARREST_RISK_THRESHOLD: float = 0.5
PERIODIC_CHECK_INTERVAL_S: float = 300.0  # 5 minutes
DEEP_COOLDOWN_S: float = 60.0  # cooldown between deep escalations


def _within_cooldown(state: AgentState) -> bool:
    """``True`` if a deep brief fired within the cooldown window.
    Cooldown window 안에 deep brief가 발화했으면 ``True``.

    Cooldown is bypassed by new reasons per project_brief §6.3 — caller
    chooses whether to honor it (currently honored except for clinician
    on-demand, which is checked first).
    Cooldown은 brief §6.3에 따라 새 사유 발생 시 우회 가능 — 호출자가 적용
    여부 결정 (현재는 clinician on-demand 외엔 적용).
    """
    if state.last_deep_trigger_time_s is None:
        return False
    return (state.sim_time_s - state.last_deep_trigger_time_s) < DEEP_COOLDOWN_S


# ── Individual trigger predicates / 개별 trigger 술어 ──


def _check_hypotension(state: AgentState) -> str | None:
    """Trigger 1: latest hypotension risk > threshold.
    Trigger 1: 최근 hypotension risk > threshold.
    """
    for sample in reversed(state.risk_history):
        if sample.risk_type.startswith("hypotension"):
            if sample.risk > HYPOTENSION_RISK_THRESHOLD:
                return (
                    f"hypotension_risk_gt_{HYPOTENSION_RISK_THRESHOLD}"
                    f" (risk={sample.risk:.2f})"
                )
            return None
    return None


def _check_rapid_increase(state: AgentState) -> str | None:
    """Trigger 2: hypotension risk Δ > threshold within 30 s window.
    Trigger 2: 30초 window 내 hypotension risk Δ > threshold.
    """
    hypo = [
        s for s in state.risk_history if s.risk_type.startswith("hypotension")
    ]
    if len(hypo) < 2:
        return None
    latest = hypo[-1]
    # find earliest sample within ``RISK_DELTA_WINDOW_S`` before latest
    # latest로부터 ``RISK_DELTA_WINDOW_S`` 이내 가장 이른 sample 찾기
    for earlier in hypo[:-1]:
        if latest.sim_time_s - earlier.sim_time_s <= RISK_DELTA_WINDOW_S:
            if (latest.risk - earlier.risk) > RISK_DELTA_THRESHOLD:
                return (
                    f"rapid_risk_increase_gt_{RISK_DELTA_THRESHOLD}"
                    f" ({earlier.risk:.2f}->{latest.risk:.2f}"
                    f" in {latest.sim_time_s - earlier.sim_time_s:.0f}s)"
                )
            return None
    return None


def _check_quality_drop(state: AgentState) -> str | None:
    """Trigger 3: average modality quality dropped by > threshold.
    Trigger 3: modality 평균 품질이 threshold 이상 하락.

    Compares the most recent quality sample's mean (per modality) against the
    earliest available within the same modality. Coarse proxy — refined when
    plan_1.6.5 Tier 2 provides plausible quality outputs.
    가장 최근 modality별 평균을 가장 이른 sample과 비교. coarse proxy —
    plan_1.6.5 Tier 2의 plausible 품질 출력 후 정교화.
    """
    if not state.quality_history:
        return None
    # Per modality: earliest and latest scores within history.
    # modality별 earliest / latest 점수.
    earliest: dict[str, float] = {}
    latest: dict[str, float] = {}
    for s in state.quality_history:
        latest[s.modality] = s.score
        earliest.setdefault(s.modality, s.score)
    drops = [
        (mod, earliest[mod] - latest[mod])
        for mod in latest
        if earliest[mod] - latest[mod] > 0
    ]
    if not drops:
        return None
    avg_drop = sum(d for _, d in drops) / len(drops)
    if avg_drop > QUALITY_DROP_THRESHOLD:
        worst = max(drops, key=lambda x: x[1])
        return (
            f"quality_drop_gt_{QUALITY_DROP_THRESHOLD}"
            f" (avg={avg_drop:.2f}, worst={worst[0]}={worst[1]:.2f})"
        )
    return None


def _check_cross_modal_inconsistency(state: AgentState) -> str | None:
    """Trigger 4: cross-modal consistency < threshold while quality is good.
    Trigger 4: 품질이 양호한데 cross-modal consistency < threshold.

    Reads from the most recent tool results. Quality "good" = latest average
    quality across modalities ≥ :data:`CONSISTENCY_GOOD_QUALITY_GATE`.
    최근 tool 결과 사용. 품질 양호 = modality별 평균 품질 ≥
    :data:`CONSISTENCY_GOOD_QUALITY_GATE`.
    """
    # latest average quality / 최근 modality별 평균 품질
    latest: dict[str, float] = {}
    for s in state.quality_history:
        latest[s.modality] = s.score
    if not latest:
        return None
    avg_quality = sum(latest.values()) / len(latest)
    if avg_quality < CONSISTENCY_GOOD_QUALITY_GATE:
        return None

    # find latest consistency result / 최근 consistency 결과
    for r in reversed(state.last_tool_results):
        if r.tool_name == "cross_modal_consistency" and r.ok and r.result is not None:
            score = r.result.get("score")
            if isinstance(score, (int, float)) and score < CONSISTENCY_THRESHOLD:
                return (
                    f"cross_modal_inconsistency_lt_{CONSISTENCY_THRESHOLD}"
                    f" (score={score:.2f}, quality={avg_quality:.2f})"
                )
            return None
    return None


def _check_arrest(state: AgentState) -> str | None:
    """Trigger 5: latest cardiac arrest risk > threshold.
    Trigger 5: 최근 심정지 risk > threshold.
    """
    for sample in reversed(state.risk_history):
        if sample.risk_type.startswith("arrest"):
            if sample.risk > ARREST_RISK_THRESHOLD:
                return (
                    f"arrest_risk_gt_{ARREST_RISK_THRESHOLD}"
                    f" (risk={sample.risk:.2f})"
                )
            return None
    return None


def _check_clinician_on_demand(state: AgentState) -> str | None:
    """Trigger 6: clinician explicitly requested a deep brief.
    Trigger 6: 임상의가 명시적으로 deep brief 요청.

    The shallow_loop or external orchestrator sets
    ``state.scratch["clinician_on_demand"] = True`` to request escalation.
    shallow_loop 또는 외부 orchestrator가 ``state.scratch["clinician_on_demand"]
    = True``를 set하여 escalation 요청.
    """
    if state.scratch.get("clinician_on_demand"):
        return "clinician_on_demand"
    return None


def _check_triage_alarm(state: AgentState) -> str | None:
    """Trigger 8 (ADR-023): a triage alarm was confirmed this tick.
    Trigger 8 (ADR-023): 이번 tick 에 triage 알람이 확정됨.

    ``run_triage`` sets ``scratch["triage_alarm_reason"]`` when the router fires
    an obvious_alarm or an ambiguous case clears the investigation ``alarm_gate``.
    This is the live, state-driven escalation path (FM triggers 1–5 are dormant).
    router obvious_alarm 또는 investigation→alarm_gate 확정 시 ``run_triage`` 가
    ``scratch["triage_alarm_reason"]`` 를 세팅 → 그 reason 으로 deep brief escalate.
    """
    reason = state.scratch.get("triage_alarm_reason")
    return f"triage_alarm: {reason}" if reason else None


def _check_periodic(state: AgentState) -> str | None:
    """Trigger 7: periodic deep check every PERIODIC_CHECK_INTERVAL_S.
    Trigger 7: PERIODIC_CHECK_INTERVAL_S마다 주기적 deep check.
    """
    if state.last_deep_trigger_time_s is None:
        # First periodic boundary at PERIODIC_CHECK_INTERVAL_S.
        # 첫 periodic boundary는 PERIODIC_CHECK_INTERVAL_S.
        if state.sim_time_s >= PERIODIC_CHECK_INTERVAL_S:
            return f"periodic_check_every_{int(PERIODIC_CHECK_INTERVAL_S)}s"
        return None
    elapsed = state.sim_time_s - state.last_deep_trigger_time_s
    if elapsed >= PERIODIC_CHECK_INTERVAL_S:
        return f"periodic_check_every_{int(PERIODIC_CHECK_INTERVAL_S)}s"
    return None


# ── Public API / 공개 API ──


def should_escalate(state: AgentState) -> tuple[bool, str | None]:
    """Decide whether to escalate from shallow to deep mode.
    Shallow에서 deep mode로 escalate할지 결정한다.

    Args:
        state: current ``AgentState``.

    Returns:
        ``(True, reason)`` if escalation is required; ``(False, None)``
        otherwise. ``reason`` is a short identifier suitable for logging
        and the brief's ``trigger_reason`` field.
        Escalation 필요 시 ``(True, reason)``; 아니면 ``(False, None)``.
        ``reason``은 logging 및 브리프 ``trigger_reason`` 필드에 적합한
        짧은 식별자.

    Ordering / 평가 순서:
    1. Clinician on-demand (bypasses cooldown / cooldown 우회)
    2. Acute event — arrest (bypasses cooldown / cooldown 우회)
    3. Cooldown gate (60 s) — suppresses brief storms from sustained alarms.
    4. Triage alarm (ADR-023, live), then hypotension / rapid increase /
       quality drop / cross-modal (dormant), then periodic check.
    """
    # 1. Clinician on-demand — always honored / 항상 적용.
    reason = _check_clinician_on_demand(state)
    if reason is not None:
        return True, reason

    # 2. Acute event — bypasses cooldown / cooldown 우회.
    reason = _check_arrest(state)
    if reason is not None:
        return True, reason

    # 3. Cooldown gate / cooldown gate.
    if _within_cooldown(state):
        return False, None

    # 4. Triage alarm (ADR-023, live state-driven driver) + remaining triggers.
    #    Triage 알람(ADR-023, live) + 잔여 trigger (FM 기반 1–4 는 dormant).
    for check in (
        _check_triage_alarm,
        _check_hypotension,
        _check_rapid_increase,
        _check_quality_drop,
        _check_cross_modal_inconsistency,
        _check_periodic,
    ):
        reason = check(state)
        if reason is not None:
            return True, reason
    return False, None


__all__ = [
    "should_escalate",
    "HYPOTENSION_RISK_THRESHOLD",
    "RISK_DELTA_WINDOW_S",
    "RISK_DELTA_THRESHOLD",
    "QUALITY_DROP_THRESHOLD",
    "CONSISTENCY_THRESHOLD",
    "CONSISTENCY_GOOD_QUALITY_GATE",
    "ARREST_RISK_THRESHOLD",
    "PERIODIC_CHECK_INTERVAL_S",
    "DEEP_COOLDOWN_S",
]
