"""``make_fallback`` graceful-degradation tests (ADR-011 step 5).
``make_fallback`` graceful-degradation 테스트 (ADR-011 step 5).

Verifies:
검증 항목:
- happy path: primary returns → result is from primary, fallback untouched /
  primary 정상 → primary 결과 반환, fallback 미사용
- exception path: primary raises → fallback called, alert fired /
  primary 예외 → fallback 호출, alert 발생
- latency-budget path: primary slow → result still from primary, alert fired /
  primary 느림 → primary 결과 그대로 + alert
- wrapped instance satisfies BiosignalFMInterface /
  wrapped 인스턴스가 Protocol 만족
- per-method tracking: failure on one method does not affect others /
  한 method 실패가 다른 method에 영향 없음
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

import pytest

from vitalagent.fm.factory import AlertCallback, make_fallback
from vitalagent.fm.interface import BiosignalFMInterface
from vitalagent.fm.mock_stub import StubBiosignalFM
from vitalagent.fm.result_types import HypotensionResult


# ── Helpers / 헬퍼 ──


class _FailingPrimary(StubBiosignalFM):
    """Stub that raises on every method — for fallback testing.
    모든 method가 예외 → fallback 검증용.
    """

    def predict_hypotension(self, signal, horizon_min, available_modalities):  # type: ignore[override]
        raise RuntimeError("simulated primary failure")

    def encode(self, signal, available_modalities):  # type: ignore[override]
        raise RuntimeError("simulated primary failure in encode")


class _SlowPrimary(StubBiosignalFM):
    """Stub that always sleeps 50ms in predict_hypotension — for latency-budget testing.
    predict_hypotension에서 50ms sleep → latency-budget 검증용.
    """

    def predict_hypotension(self, signal, horizon_min, available_modalities):  # type: ignore[override]
        time.sleep(0.05)
        return super().predict_hypotension(signal, horizon_min, available_modalities)


class _AlertSpy:
    """Capture alert callbacks for inspection.
    Alert 호출을 캡쳐.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, str, BaseException | None, dict[str, Any]]] = []

    def __call__(
        self,
        reason: str,
        method: str,
        exc: BaseException | None,
        extra: dict[str, Any],
    ) -> None:
        self.events.append((reason, method, exc, extra))


# ── Tests ──


def test_fallback_satisfies_protocol() -> None:
    """Wrapped instance must satisfy ``BiosignalFMInterface``.
    Wrap된 인스턴스는 ``BiosignalFMInterface``를 만족해야 한다.
    """
    primary = StubBiosignalFM(seed=1)
    fallback = StubBiosignalFM(seed=2)
    fm = make_fallback(primary, fallback)
    assert isinstance(fm, BiosignalFMInterface)


def test_happy_path_primary_only() -> None:
    """Primary returns → primary's result is used; fallback untouched.
    Primary 정상 → primary 결과 사용, fallback 미사용.
    """
    primary = StubBiosignalFM(seed=1)
    # Use a different seed for fallback so we can distinguish results.
    # fallback에는 다른 seed → 결과 구분 가능.
    fallback = StubBiosignalFM(seed=999)
    fm = make_fallback(primary, fallback)

    direct = primary.predict_hypotension({}, 5, [])  # consume primary's first sample
    primary2 = StubBiosignalFM(seed=1)  # fresh primary to mirror the wrapper's state
    wrapped_primary = make_fallback(primary2, fallback)
    via_wrap = wrapped_primary.predict_hypotension({}, 5, [])
    # The wrapped call should match a fresh primary's first sample.
    # wrap 호출은 fresh primary의 첫 sample과 일치해야 한다.
    assert isinstance(via_wrap, HypotensionResult)
    assert via_wrap.risk == direct.risk
    # Sanity: fallback (seed=999) would have produced a different value.
    # 검증: fallback (seed=999)이라면 다른 값이 나옴.
    fallback_independent = StubBiosignalFM(seed=999).predict_hypotension({}, 5, [])
    assert via_wrap.risk != fallback_independent.risk


def test_exception_path_uses_fallback_and_alerts() -> None:
    """Primary raises → fallback result returned, alert fired.
    Primary 예외 → fallback 결과 반환, alert 발생.
    """
    primary = _FailingPrimary(seed=1)
    fallback = StubBiosignalFM(seed=42)
    spy = _AlertSpy()
    fm = make_fallback(primary, fallback, alert=spy)

    result = fm.predict_hypotension({}, 5, [])

    # Result must come from fallback (matches fresh fallback's first sample).
    # 결과는 fallback에서 (fresh fallback의 첫 sample과 일치).
    expected = StubBiosignalFM(seed=42).predict_hypotension({}, 5, [])
    assert result.risk == expected.risk

    # Alert fired with reason='primary_failed' and the exception.
    # 'primary_failed' reason + exception을 포함한 alert.
    assert len(spy.events) == 1
    reason, method, exc, extra = spy.events[0]
    assert reason == "primary_failed"
    assert method == "predict_hypotension"
    assert isinstance(exc, RuntimeError)
    assert "simulated primary failure" in str(exc)


def test_latency_budget_alerts_but_returns_primary() -> None:
    """Slow primary → primary result is still returned, alert fired.
    느린 primary → primary 결과 그대로 + alert 발생.
    """
    primary = _SlowPrimary(seed=1)
    fallback = StubBiosignalFM(seed=999)
    spy = _AlertSpy()
    fm = make_fallback(primary, fallback, latency_budget_sec=0.01, alert=spy)

    expected_from_primary = _SlowPrimary(seed=1).predict_hypotension({}, 5, [])
    result = fm.predict_hypotension({}, 5, [])
    # Latency exceeded but primary's result is still used.
    # latency 초과해도 primary 결과 사용.
    assert result.risk == expected_from_primary.risk

    assert len(spy.events) == 1
    reason, method, exc, extra = spy.events[0]
    assert reason == "latency_exceeded"
    assert method == "predict_hypotension"
    assert exc is None
    assert extra["elapsed_sec"] >= 0.05
    assert extra["budget_sec"] == 0.01


def test_failure_on_one_method_does_not_affect_others() -> None:
    """``_FailingPrimary`` raises only on predict_hypotension / encode; other
    methods on primary still succeed (no fallback for them).
    ``_FailingPrimary``는 predict_hypotension / encode에서만 raise — 다른
    method는 primary에서 정상 (fallback 미호출).
    """
    primary = _FailingPrimary(seed=1)
    fallback = StubBiosignalFM(seed=999)
    spy = _AlertSpy()
    fm = make_fallback(primary, fallback, alert=spy)

    # anomaly_score is inherited untouched from StubBiosignalFM — should NOT fall back.
    # anomaly_score는 StubBiosignalFM에서 상속 그대로 — fallback 안 함.
    primary_independent = _FailingPrimary(seed=1).anomaly_score({}, "ABP")
    via_wrap = fm.anomaly_score({}, "ABP")
    assert via_wrap.score == primary_independent.score
    # No alert for anomaly_score.
    # anomaly_score에 대한 alert 없음.
    assert all(e[1] != "anomaly_score" for e in spy.events)

    # But predict_hypotension still raises → fallback used.
    # predict_hypotension은 여전히 raise → fallback 사용.
    fm.predict_hypotension({}, 5, [])
    assert any(e[0] == "primary_failed" and e[1] == "predict_hypotension" for e in spy.events)


def test_default_alert_emits_warning_log(caplog: pytest.LogCaptureFixture) -> None:
    """Default alert path logs at WARNING level (no explicit callback).
    명시적 callback 없이도 기본 alert가 WARNING level로 log.
    """
    import logging

    primary = _FailingPrimary(seed=1)
    fallback = StubBiosignalFM(seed=42)
    fm = make_fallback(primary, fallback)
    with caplog.at_level(logging.WARNING, logger="vitalagent.fm.factory"):
        fm.predict_hypotension({}, 5, [])
    assert any("primary failed" in rec.message.lower() for rec in caplog.records)
