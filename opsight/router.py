"""Rule-based triage router (ADR-023) — obvious vs ambiguous classifier.
Rule 기반 triage router (ADR-023) — 뻔한 케이스 vs 애매한 케이스 분류.

매 shallow tick 의 rule-based 현재상태(vitals + trend)를 셋 중 하나로 분류한다:

- ``OBVIOUS_ALARM``  : 임계 명확 + 품질 양호 + 모달리티 일치 → 즉시 알람(결정적)
- ``OBVIOUS_NORMAL`` : 여유롭게 정상 + 품질 양호 → 무동작
- ``AMBIGUOUS``      : 경계값 OR 품질 저하 OR 모달리티 불일치 OR 결측 OR 임계로의
                       drift → LLM+FM 조사(``llm_investigate``)로 escalation

⚠️ 본 module 은 **분류만** 한다. 알람 발화 / 조사 dispatch 는 node 의 책임이며,
   LLM 이 조사하더라도 **최종 알람은 rule gate 를 통과**한다(ADR-023 자율성 경계).
⚠️ Trigger(알람) 결정은 rule-based — 본 router 가 그 rule 의 진입점이다.

Threshold 정책(ADR-023 §4):
- **임상 임계값**(MAP/HR/SpO2/BIS)은 문헌 + 임상의 검토 대상 → ``[CLINICIAN-REVIEW]``.
  현재는 ``summarize.py`` 와 동일 lit-standard. 추후 ``router_config.yaml`` 외부화 + 단일화.
- **애매 band(margin)** 는 임상 사실 아님 — cohort 로 캘리브레이션. magic number 금지,
  임계값 기준 상대로 정의.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opsight.envelope import ToolResponse


class Route(str, Enum):
    """Triage outcome for one tick / 한 tick 의 triage 결과."""

    OBVIOUS_ALARM = "obvious_alarm"
    OBVIOUS_NORMAL = "obvious_normal"
    AMBIGUOUS = "ambiguous"
    NO_DATA = "no_data"        # no assessable vital present — don't investigate/alarm


# ── Config / 설정 ──
# Clinical thresholds [CLINICIAN-REVIEW: 의료진 검토 필요] — mirror summarize.py;
# unify + externalize to router_config.yaml per ADR-023. (low, high); None = 무한.
# 임상 임계값 — summarize.py 와 동일 lit-standard. 추후 YAML 외부화 + 단일화.
#
# NOTE: the router decides HEMODYNAMIC alarms (MAP/HR) + oxygenation (SpO2). BIS
# is anesthesia DEPTH (a state, not an emergency — BIS 30 in maintenance is normal
# /intended), so it is intentionally NOT a router alarm trigger. BIS is still
# reported by ``summarize_current_state`` for the deep brief. (real-data finding:
# BIS-driven over-alarming, demo_real_stream case 1, 2026-06-12.)
# 주: router 는 혈역학(MAP/HR)+산소화(SpO2) 알람만. BIS(마취 심도)는 알람 trigger 아님.
_DEFAULT_THRESHOLDS: dict[str, tuple[float | None, float | None]] = {
    "map_mmHg": (65.0, 110.0),
    # HR upper raised 100→110: mild intraoperative tachycardia (100–110, surgical
    # stimulation / light anesthesia) is common and usually benign; concern at >110.
    # (real-data finding: HR borderline clustered 90–102, demo cohort 2026-06-12.)
    # [CLINICIAN-REVIEW: 의료진 검토 필요]
    "hr_bpm": (50.0, 110.0),
    "spo2_pct": (92.0, None),
}
# Ambiguity margin per vital — relative band around the threshold (NOT magic
# numbers; calibrate on cohort, ADR-023 §4).
# vital 별 애매 band — 임계값 기준 상대 폭 (cohort 캘리브레이션 대상).
_DEFAULT_MARGINS: dict[str, float] = {
    "map_mmHg": 5.0,
    "hr_bpm": 10.0,
    "spo2_pct": 3.0,
}
# Signal-quality / cross-modal-agreement gates (hooks; no producer until FM
# assess_signal_quality / cross_modal land — pass None to skip).
# 신호품질 / 모달리티 일치 gate (hook; FM tool 도착 전 producer 없음 → None 이면 skip).
_DEFAULT_QUALITY_GATE: float = 0.7
_DEFAULT_AGREEMENT_GATE: float = 0.4


@dataclass(frozen=True)
class RouterConfig:
    """Router thresholds/margins/gates — defaults mirror lit-standard.
    추후 ``router_config.yaml`` 에서 로드해 주입(ADR-023). 임상 임계값은 CLINICIAN-REVIEW.
    """

    thresholds: dict[str, tuple[float | None, float | None]] = field(
        default_factory=lambda: dict(_DEFAULT_THRESHOLDS)
    )
    margins: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_MARGINS))
    quality_gate: float = _DEFAULT_QUALITY_GATE
    agreement_gate: float = _DEFAULT_AGREEMENT_GATE


DEFAULT_CONFIG = RouterConfig()


@dataclass(frozen=True)
class RouteDecision:
    """Triage decision for one tick / 한 tick 의 triage 결정.

    ``route`` 가 행동을 결정하고, 나머지 필드는 trace / 디버깅 / ablation 근거.
    """

    route: Route
    reasons: list[str]          # human-readable why / 사람이 읽는 사유
    clear_breaches: list[str]   # 임계 명확 위반 vital
    borderline: list[str]       # 애매 band 내 vital
    missing: list[str]          # 결측 vital


# ── Per-vital classification / vital 단위 분류 ──

# Which trend direction moves a vital *toward* a threshold (in-range drift).
# in-range 상태에서 임계로 다가가는 추세 방향.
def _classify_vital(
    value: float | None,
    low: float | None,
    high: float | None,
    margin: float,
    direction: str | None,
) -> str:
    """Classify one vital → 'clear' | 'borderline' | 'missing' | 'normal'.

    - clear      : 임계를 margin 넘어 위반 (명확)
    - borderline : 임계 ± margin 안 (경계) OR 임계로 drift 중
    - missing    : 값 없음
    - normal     : 여유롭게 정상
    """
    if value is None:
        return "missing"
    if low is not None:
        if value < low - margin:
            return "clear"
        if value < low:
            return "borderline"
    if high is not None:
        if value > high + margin:
            return "clear"
        if value > high:
            return "borderline"
    # In-range but drifting toward a threshold within the approach band.
    # 정상 범위지만 임계 쪽으로 drift 중(approach band 안) → 경계.
    if direction == "falling" and low is not None and value < low + margin:
        return "borderline"
    if direction == "rising" and high is not None and value > high - margin:
        return "borderline"
    return "normal"


# ── Public API / 공개 API ──


def route_tick(
    vitals: dict[str, float | None],
    trend_directions: dict[str, str | None] | None = None,
    *,
    quality: float | None = None,
    agreement: float | None = None,
    config: RouterConfig = DEFAULT_CONFIG,
) -> RouteDecision:
    """Classify the current tick into a :class:`Route` (pure, rule-based).
    현재 tick 을 :class:`Route` 로 분류한다 (순수 함수, rule-based).

    Args:
        vitals: ``get_current_state`` 의 ``result["vitals"]`` (예: ``{"map_mmHg": 62, ...}``).
            결측 vital 은 key 부재 또는 ``None``.
        trend_directions: ``summarize_current_state`` 의 ``result["trend_directions"]``
            (예: ``{"map_mmHg": "falling"}``). in-range drift 판정에 사용.
        quality: 평균 신호품질 [0,1] — 있으면 < ``quality_gate`` 일 때 ambiguity.
            (FM ``assess_signal_quality`` 도착 전엔 ``None`` → skip.)
        agreement: cross-modal 일치도 [0,1] — 있으면 < ``agreement_gate`` 일 때 ambiguity.
            (FM ``cross_modal_consistency`` 도착 전엔 ``None`` → skip.)
        config: threshold/margin/gate (기본은 lit-standard; YAML 주입 가능).

    Returns:
        :class:`RouteDecision`.

    Rule (ADR-023):
        clear breach 있고 품질·일치 양호      → OBVIOUS_ALARM
        clear breach 있으나 품질 저하/불일치    → AMBIGUOUS (artifact 의심 → 조사)
        borderline / 결측 / 품질 저하 / 불일치  → AMBIGUOUS
        그 외                                  → OBVIOUS_NORMAL
    """
    trends = trend_directions or {}
    clear: list[str] = []
    borderline: list[str] = []
    missing: list[str] = []

    for name, (low, high) in config.thresholds.items():
        value = vitals.get(name)
        margin = config.margins.get(name, 0.0)
        kind = _classify_vital(value, low, high, margin, trends.get(name))
        if kind == "clear":
            clear.append(f"{name}={value}")
        elif kind == "borderline":
            borderline.append(f"{name}={value}")
        elif kind == "missing":
            missing.append(name)

    quality_bad = quality is not None and quality < config.quality_gate
    agreement_bad = agreement is not None and agreement < config.agreement_gate
    n_present = len(config.thresholds) - len(missing)

    reasons: list[str] = []
    if clear:
        reasons.append("clear_breach: " + ", ".join(clear))
    if borderline:
        reasons.append("borderline: " + ", ".join(borderline))
    if missing:
        reasons.append("missing: " + ", ".join(missing))  # informative only — not a driver
    if quality_bad:
        reasons.append(f"quality_below_gate ({quality:.2f}<{config.quality_gate})")
    if agreement_bad:
        reasons.append(f"agreement_below_gate ({agreement:.2f}<{config.agreement_gate})")

    # Decision. A MISSING vital is simply not assessed — it does NOT drive
    # ambiguity (you don't investigate/alarm on a vital that isn't measured). Only
    # PRESENT vitals (+ quality/agreement) decide the route. With nothing present,
    # we cannot say "normal" → NO_DATA (benign: no alarm, no investigation).
    # 결측 vital 은 그냥 평가 안 함 — ambiguity 유발 안 함. 있는 vital 만으로 결정.
    # 전부 결측이면 "정상" 이라 할 수 없으니 NO_DATA(무해: 알람·조사 없음).
    if n_present == 0:
        route = Route.NO_DATA
        reasons.append("no_assessable_vital")
    elif clear and not (quality_bad or agreement_bad):
        route = Route.OBVIOUS_ALARM
    elif clear or borderline or quality_bad or agreement_bad:
        route = Route.AMBIGUOUS
    else:
        route = Route.OBVIOUS_NORMAL
        reasons.append("present_vitals_normal")

    return RouteDecision(
        route=route,
        reasons=reasons,
        clear_breaches=clear,
        borderline=borderline,
        missing=missing,
    )


def extract_router_inputs(
    tool_results: list[ToolResponse],
) -> tuple[dict[str, Any], dict[str, Any], float | None]:
    """Pull ``(vitals, trend_directions, quality)`` from a tick's tool results.
    한 tick 의 tool 결과에서 ``(vitals, trend_directions, quality)`` 추출.

    Bridges the shallow sweep (``get_current_state`` + ``summarize_current_state``
    + ``assess_signal_quality``) to :func:`route_tick`. ``quality`` is the worst SQI
    over **primary** hemodynamic/oxygenation channels (ABP/HR/SpO2) — a single
    artifact-quality primary channel (e.g. the ABP behind MAP) makes the tick
    cautious, but a sparse/dead irrelevant channel (BT/EtCO2) does NOT. ``None`` if absent.
    ``quality`` 는 primary 채널(ABP/HR/SpO2)의 worst SQI. 부재/실패 시 ``{}``/``None``.
    """
    vitals: dict[str, Any] = {}
    trends: dict[str, Any] = {}
    quality: float | None = None
    for r in tool_results:
        if not r.ok or r.result is None:
            continue
        if r.tool_name == "get_current_state":
            vitals = r.result.get("vitals", {})
        elif r.tool_name == "summarize_current_state":
            trends = r.result.get("trend_directions", {})
        elif r.tool_name == "assess_signal_quality":
            quality = r.result.get("primary_worst")
    return vitals, trends, quality


__all__ = [
    "Route",
    "RouterConfig",
    "RouteDecision",
    "DEFAULT_CONFIG",
    "route_tick",
    "extract_router_inputs",
]
