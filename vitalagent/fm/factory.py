"""FM factory — config-driven instantiation (ADR-011 swap mechanism).
FM factory — config 기반 인스턴스 생성 (ADR-011 swap 메커니즘).

The factory is the single import path that agent / tool layer code uses to
obtain an FM backend. Swapping implementations is a config change, not a code
change — call sites depend ONLY on the :class:`BiosignalFMInterface` Protocol.
본 factory는 agent / tool layer가 FM backend를 얻을 때 사용하는 유일한
import 경로다. 구현체 교체는 코드 변경이 아닌 config 변경이다 — 호출 site는
:class:`BiosignalFMInterface` Protocol에만 의존한다.

Implementations are imported lazily so that an unimplemented tier raises a
clear :class:`NotImplementedError` at call time (and not at module import).
구현체는 lazy import되어, 미구현 tier 호출 시 명확한
:class:`NotImplementedError`를 발생시킨다 (module import 시점이 아닌 호출
시점).

Config schema / config 스키마::

    {
        "fm": {
            "implementation": "mock_stub" | "mock_rule_based"
                              | "mock_light_ml" | "real",
            "config": {           # optional, kwargs for the implementation
                "seed": 42,
                "latency_sim_sec": 0.0,
                # ... tier-specific
            },
        }
    }

Spec: ``docs/fm_interface_guide.md §3``, ADR-011 §"Swap mechanism".
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Final

if TYPE_CHECKING:
    import torch

    from vitalagent.fm.interface import BiosignalFMInterface
    from vitalagent.fm.result_types import (
        AnomalyResult,
        ArrestResult,
        ConsistencyResult,
        ForecastResult,
        HypotensionResult,
        QualityResult,
        TrendResult,
    )

_log = logging.getLogger(__name__)


# Allowed implementation names / 허용된 구현체 이름
_KNOWN_IMPLEMENTATIONS: Final[tuple[str, ...]] = (
    "mock_stub",
    "mock_rule_based",
    "mock_light_ml",
    "real",
)


def create_fm(config: dict[str, Any]) -> BiosignalFMInterface:
    """Instantiate an FM backend selected by ``config["fm"]["implementation"]``.
    ``config["fm"]["implementation"]``으로 선택된 FM backend를 인스턴스화한다.

    Args:
        config: Dict with at minimum::

            {"fm": {"implementation": "<one of mock_stub | mock_rule_based |
                                       mock_light_ml | real>",
                    "config": {...kwargs for the implementation...}}}

            최소 구조: 위 dict. ``config["fm"]["config"]``는 선택, 누락 시
            빈 dict로 처리.

    Returns:
        An instance satisfying :class:`BiosignalFMInterface`.
        :class:`BiosignalFMInterface`를 만족하는 인스턴스.

    Raises:
        ValueError: ``implementation`` not in the known list.
            ``implementation``이 알려진 목록에 없을 때.
        NotImplementedError: tier name is valid but the corresponding module
            is not yet implemented (e.g. requesting ``mock_rule_based`` before
            ``plan_1.6.5`` lands).
            tier 이름은 유효하나 해당 module이 아직 구현되지 않은 경우 (예:
            ``plan_1.6.5`` 도착 전 ``mock_rule_based`` 요청).
    """
    fm_section = config.get("fm")
    if not isinstance(fm_section, dict):
        raise ValueError(
            "config must contain an 'fm' object with an 'implementation' key. "
            f"got: {type(fm_section).__name__}"
        )
    impl = fm_section.get("implementation")
    fm_kwargs: dict[str, Any] = fm_section.get("config") or {}

    if impl not in _KNOWN_IMPLEMENTATIONS:
        raise ValueError(
            f"Unknown FM implementation: {impl!r}. "
            f"Expected one of: {list(_KNOWN_IMPLEMENTATIONS)}."
        )

    # Lazy import per tier / tier별 lazy import.
    # Each tier ships in its own module; importing only the requested one
    # avoids ImportError for tiers that have not landed yet.
    # 각 tier는 자체 module로 배포된다. 요청된 tier만 import하여 아직 도착하지
    # 않은 tier의 ImportError를 회피한다.
    if impl == "mock_stub":
        from vitalagent.fm.mock_stub import StubBiosignalFM

        return StubBiosignalFM(**fm_kwargs)

    if impl == "mock_rule_based":
        try:
            from vitalagent.fm.mock_rule_based import RuleBasedBiosignalFM
        except ImportError as exc:
            raise NotImplementedError(
                "FM tier 'mock_rule_based' is not yet implemented "
                "(see plan_1.6.5_mock_fm_rule_based.md)."
            ) from exc
        return RuleBasedBiosignalFM(**fm_kwargs)

    if impl == "mock_light_ml":
        try:
            from vitalagent.fm.mock_light_ml import LightMLBiosignalFM
        except ImportError as exc:
            raise NotImplementedError(
                "FM tier 'mock_light_ml' is not yet implemented "
                "(see plan_1.7.5_mock_fm_light_ml.md; optional)."
            ) from exc
        return LightMLBiosignalFM(**fm_kwargs)

    if impl == "real":
        try:
            from vitalagent.fm.real import RealBiosignalFM
        except ImportError as exc:
            raise NotImplementedError(
                "FM tier 'real' is not yet implemented "
                "(real FM lands at the start of Stage 2 / Month 3)."
            ) from exc
        return RealBiosignalFM(**fm_kwargs)

    # Unreachable: the membership check above covers every branch.
    # 도달 불가: 위 membership 체크가 모든 분기를 cover한다.
    raise AssertionError(f"unreachable: impl={impl!r}")  # pragma: no cover


# ─── Graceful degradation / Graceful degradation ─────────────────────────────


# Alert callback signature / Alert callback 시그니처:
#   alert(reason, method_name, exc, extra)
#     - reason     : "primary_failed" or "latency_exceeded"
#     - method_name: the Protocol method that triggered
#     - exc        : the exception caught (None when reason == "latency_exceeded")
#     - extra      : dict of supplementary fields (e.g. elapsed_sec, budget_sec)
AlertCallback = Callable[[str, str, BaseException | None, dict[str, Any]], None]


def _default_alert(
    reason: str,
    method_name: str,
    exc: BaseException | None,
    extra: dict[str, Any],
) -> None:
    """Default alert — logs at WARNING level via ``logging``.
    기본 alert — ``logging`` WARNING level 로 기록한다.
    """
    if reason == "primary_failed":
        _log.warning(
            "FM primary failed in method=%s; falling back. exc=%r extra=%s",
            method_name,
            exc,
            extra,
        )
    elif reason == "latency_exceeded":
        _log.warning(
            "FM primary latency exceeded budget in method=%s. extra=%s",
            method_name,
            extra,
        )
    else:
        _log.warning("FM alert reason=%s method=%s extra=%s", reason, method_name, extra)


class _FallbackFM:
    """Wraps two FM instances; tries primary, falls back on exception.
    두 FM 인스턴스를 wrap한다. primary를 시도하고 exception 시 fallback.

    Used by :func:`make_fallback`. Not a public class — agents and tools should
    depend on :class:`BiosignalFMInterface` only (this class satisfies it).
    :func:`make_fallback`이 사용한다. public class가 아니다 — agent / tool은
    :class:`BiosignalFMInterface`에만 의존한다 (본 class는 이를 만족).

    Fallback policy / Fallback 정책:

    - **Exception in primary** → fallback is invoked, alert is emitted, fallback
      result is returned. Exception is swallowed (logged via alert).
      **Primary에서 예외 발생** → fallback 호출, alert 발생, fallback 결과 반환.
      예외는 alert 안에서 흡수.
    - **Latency budget exceeded** (primary returned but slow) → result is still
      returned from primary; alert is emitted for observability. No forced
      timeout on the current call (sync sleep cannot be interrupted reliably).
      Stage-2 circuit-breaker can be added later if needed.
      **Latency 초과** (primary가 반환했으나 느림) → primary 결과를 그대로
      반환; observability를 위해 alert만 발생. 현재 호출에 대한 강제 timeout은
      없음 (sync sleep은 신뢰성 있는 interrupt 불가). 필요 시 Stage 2에서
      circuit-breaker 추가 가능.

    ADR-011 §"Real-FM migration protocol" step 5 reference.
    ADR-011 §"Real-FM migration protocol" step 5 참조.
    """

    def __init__(
        self,
        primary: BiosignalFMInterface,
        fallback: BiosignalFMInterface,
        latency_budget_sec: float | None = None,
        alert: AlertCallback | None = None,
    ) -> None:
        """Wrap ``primary`` with ``fallback`` for graceful degradation.
        ``primary``를 ``fallback``으로 wrap하여 graceful degradation 제공.

        Args:
            primary: the preferred FM (e.g. real adapter).
                선호되는 FM (예: real adapter).
            fallback: the safety-net FM (e.g. mock_rule_based).
                안전망 FM (예: mock_rule_based).
            latency_budget_sec: if set, emits an alert when a primary call
                takes longer than this. ``None`` = no budget check.
                설정 시 primary 호출이 본 값을 초과하면 alert. ``None``은 미체크.
            alert: optional callback; defaults to a WARNING log entry.
                선택적 callback. 기본은 WARNING log 항목.
        """
        self._primary = primary
        self._fallback = fallback
        self._latency_budget_sec = latency_budget_sec
        self._alert: AlertCallback = alert or _default_alert

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch ``method_name`` to primary with fallback / observability.
        ``method_name``을 primary로 디스패치 + fallback + observability.
        """
        try:
            t0 = time.perf_counter()
            result = getattr(self._primary, method_name)(*args, **kwargs)
            elapsed = time.perf_counter() - t0
            if (
                self._latency_budget_sec is not None
                and elapsed > self._latency_budget_sec
            ):
                self._alert(
                    "latency_exceeded",
                    method_name,
                    None,
                    {
                        "elapsed_sec": elapsed,
                        "budget_sec": self._latency_budget_sec,
                    },
                )
            return result
        except Exception as exc:  # noqa: BLE001 — primary failure is the policy
            self._alert("primary_failed", method_name, exc, {})
            return getattr(self._fallback, method_name)(*args, **kwargs)

    # ── 8 Protocol method delegates / 8개 Protocol method 위임 ──

    def encode(
        self,
        signal: dict[str, torch.Tensor],
        available_modalities: list[str],
    ) -> torch.Tensor:
        return self._call("encode", signal, available_modalities)

    def predict_hypotension(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> HypotensionResult:
        return self._call("predict_hypotension", signal, horizon_min, available_modalities)

    def predict_cardiac_arrest(
        self,
        signal: dict[str, torch.Tensor],
        horizon_min: int,
        available_modalities: list[str],
    ) -> ArrestResult:
        return self._call("predict_cardiac_arrest", signal, horizon_min, available_modalities)

    def assess_signal_quality(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> QualityResult:
        return self._call("assess_signal_quality", signal, modality)

    def cross_modal_consistency(
        self,
        signal: dict[str, torch.Tensor],
        modality_pair: tuple[str, str],
    ) -> ConsistencyResult:
        return self._call("cross_modal_consistency", signal, modality_pair)

    def temporal_trend(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        window_min: int,
    ) -> TrendResult:
        return self._call("temporal_trend", signal, modality, window_min)

    def forecast_signal(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
        horizon_min: int,
    ) -> ForecastResult:
        return self._call("forecast_signal", signal, modality, horizon_min)

    def anomaly_score(
        self,
        signal: dict[str, torch.Tensor],
        modality: str,
    ) -> AnomalyResult:
        return self._call("anomaly_score", signal, modality)


def make_fallback(
    primary: BiosignalFMInterface,
    fallback: BiosignalFMInterface,
    latency_budget_sec: float | None = None,
    alert: AlertCallback | None = None,
) -> BiosignalFMInterface:
    """Compose ``primary`` and ``fallback`` into a single FM with safety net.
    ``primary``와 ``fallback``을 안전망이 있는 단일 FM으로 합친다.

    Returned instance satisfies :class:`BiosignalFMInterface` — agents and
    tools see a normal FM. The wrapper transparently routes each method call
    to ``primary``, catches exceptions to delegate to ``fallback``, and emits
    an alert via the optional callback when a budget is exceeded.
    반환 인스턴스는 :class:`BiosignalFMInterface`를 만족한다 — agent와 tool은
    일반 FM으로 본다. wrapper가 각 method 호출을 ``primary``로 라우팅하고,
    예외 시 ``fallback``으로 위임하며, budget 초과 시 alert를 발생시킨다.

    Args:
        primary: preferred FM (e.g. real adapter).
            선호되는 FM (예: real adapter).
        fallback: safety-net FM (e.g. mock_rule_based).
            안전망 FM (예: mock_rule_based).
        latency_budget_sec: alert if a primary call exceeds this (seconds).
            ``None`` disables the latency check.
            primary 호출이 이 값을 초과하면 alert (초). ``None``은 latency 체크 비활성.
        alert: optional callback ``(reason, method_name, exc, extra)``.
            Defaults to a WARNING log entry.
            선택적 callback. 기본은 WARNING log.

    Returns:
        A Protocol-compliant FM that delegates to ``primary`` first and
        falls back to ``fallback`` on exception.
        Protocol을 만족하며 ``primary`` 우선 + 예외 시 ``fallback``으로 위임하는 FM.

    Example / 사용 예::

        from vitalagent.fm.factory import create_fm, make_fallback

        # Stage 2: real FM with mock_rule_based as the safety net.
        # Stage 2: real FM + mock_rule_based 안전망.
        real_fm     = create_fm({"fm": {"implementation": "real"}})
        rule_based  = create_fm({"fm": {"implementation": "mock_rule_based"}})
        fm = make_fallback(real_fm, rule_based, latency_budget_sec=0.5)
        # fm is BiosignalFMInterface-compliant — use it like any other FM.
        # fm은 BiosignalFMInterface를 만족 — 일반 FM처럼 사용.

    Spec: ADR-011 §"Real-FM migration protocol" step 5.
    """
    return _FallbackFM(primary, fallback, latency_budget_sec, alert)


__all__ = ["create_fm", "make_fallback", "AlertCallback"]
