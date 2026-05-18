"""Protocol compliance tests for FM implementations (ADR-011).
FM 구현체의 Protocol compliance 테스트 (ADR-011).

Each new FM tier (Tier 1 stub, Tier 2 rule-based, Tier 3 light ML, real)
MUST be registered in :data:`FM_IMPLEMENTATIONS` so the tests in this module
verify that the implementation satisfies :class:`BiosignalFMInterface`.
새 FM tier (Tier 1 stub / Tier 2 rule-based / Tier 3 light ML / real)는 반드시
:data:`FM_IMPLEMENTATIONS`에 등록되어야 한다. 본 module의 테스트가 해당 구현이
:class:`BiosignalFMInterface`를 만족하는지 검증한다.

Three layers of compliance are checked:
세 단계의 compliance를 검증한다:

1. ``runtime_checkable`` — Protocol method existence (Python의 기본 체크).
2. Method enumeration — every method in the ADR-011 method list is present
   and callable on the instance / ADR-011 method 목록의 모든 method가 존재 +
   callable.
3. Signature alignment — parameter names match the Protocol exactly
   (stricter than ``runtime_checkable``, which doesn't verify signatures) /
   parameter 이름이 Protocol과 정확히 일치 (``runtime_checkable``보다 엄격).

Spec: ``docs/fm_interface_guide.md §2.5``, ADR-011 §"Interface Protocol".
"""
from __future__ import annotations

import inspect
from typing import Callable

import pytest

from vitalagent.fm.interface import BiosignalFMInterface
from vitalagent.fm.mock_light_ml import LightMLBiosignalFM
from vitalagent.fm.mock_rule_based import RuleBasedBiosignalFM
from vitalagent.fm.mock_stub import StubBiosignalFM


# ── Registry of FM implementations / FM 구현체 등록 ──
#
# Each entry: (display_name, zero-arg factory returning an instance).
# 각 항목: (표시 이름, 인자 없이 인스턴스를 반환하는 factory).
#
# When a new tier lands, add a row here. The same three tests below run
# automatically against every entry.
# 새 tier가 도착하면 행을 추가한다. 아래 세 개의 테스트가 모든 항목에 대해
# 자동 실행된다.
FM_IMPLEMENTATIONS: list[tuple[str, Callable[[], object]]] = [
    ("StubBiosignalFM",      lambda: StubBiosignalFM(seed=42)),
    ("RuleBasedBiosignalFM", lambda: RuleBasedBiosignalFM(seed=42)),
    ("LightMLBiosignalFM",   lambda: LightMLBiosignalFM(primary_baseline="logreg_abp", seed=42)),
    # TODO: ("RealBiosignalFM",    lambda: RealBiosignalFM(...))       # when real FM lands
]

# Expected 8 methods per ADR-011 / ADR-011 기준 8 method
EXPECTED_METHODS: tuple[str, ...] = (
    "encode",
    "predict_hypotension",
    "predict_cardiac_arrest",
    "assess_signal_quality",
    "cross_modal_consistency",
    "temporal_trend",
    "forecast_signal",
    "anomaly_score",
)


# ── Parametrize ids / parametrize id ──
_PARAMS = pytest.mark.parametrize(
    ("name", "factory"),
    FM_IMPLEMENTATIONS,
    ids=[name for name, _ in FM_IMPLEMENTATIONS],
)


@_PARAMS
def test_runtime_checkable_protocol(name: str, factory: Callable[[], object]) -> None:
    """The implementation must pass ``isinstance(fm, BiosignalFMInterface)``.
    구현체는 ``isinstance(fm, BiosignalFMInterface)``를 통과해야 한다.

    This is the cheapest check — ``runtime_checkable`` only verifies that
    every Protocol method exists by name. It does NOT check signatures.
    가장 가벼운 체크 — ``runtime_checkable``은 Protocol method가 이름으로
    존재하는지만 검증한다. signature는 검증하지 않는다.
    """
    fm = factory()
    assert isinstance(fm, BiosignalFMInterface), (
        f"{name} does not satisfy BiosignalFMInterface Protocol"
    )


@_PARAMS
def test_all_methods_present_and_callable(
    name: str, factory: Callable[[], object]
) -> None:
    """Every required method must exist on the instance and be callable.
    필수 method가 모두 인스턴스에 존재하고 callable이어야 한다.
    """
    fm = factory()
    missing = [m for m in EXPECTED_METHODS if not hasattr(fm, m)]
    assert not missing, f"{name} missing methods: {missing}"
    not_callable = [m for m in EXPECTED_METHODS if not callable(getattr(fm, m))]
    assert not not_callable, f"{name} non-callable methods: {not_callable}"


@_PARAMS
def test_method_signatures_match_protocol(
    name: str, factory: Callable[[], object]
) -> None:
    """Stricter check: parameter names match the Protocol exactly.
    더 엄격한 체크: parameter 이름이 Protocol과 정확히 일치한다.

    ``runtime_checkable`` only verifies method existence, not signatures.
    This test enforces signature alignment using :func:`inspect.signature`,
    catching the case where a tier renames or drops a parameter silently.
    ``runtime_checkable``은 method 존재만 검증한다 (signature 미검증). 본
    테스트는 :func:`inspect.signature`로 signature 일치를 강제한다.
    parameter 이름을 변경 또는 누락한 케이스를 잡는다.
    """
    fm = factory()
    mismatches: list[str] = []
    for method_name in EXPECTED_METHODS:
        protocol_method = getattr(BiosignalFMInterface, method_name)
        impl_method = getattr(fm, method_name)
        # Protocol method carries an explicit ``self``; the bound impl method
        # has already consumed it.
        # Protocol method는 ``self``를 명시 갖고, bound 구현 method는 이미 소비.
        proto_names = [
            p_name
            for p_name in inspect.signature(protocol_method).parameters
            if p_name != "self"
        ]
        impl_names = list(inspect.signature(impl_method).parameters)
        if proto_names != impl_names:
            mismatches.append(
                f"  {method_name}: Protocol{proto_names} vs {name}{impl_names}"
            )
    assert not mismatches, (
        f"{name} parameter-name mismatches:\n" + "\n".join(mismatches)
    )


# ── Negative sanity test (not parametrized) ──
# Confirms the compliance check would actually catch a broken implementation.
# 깨진 구현이 실제로 잡히는지 확인하는 negative sanity test.


class _BrokenFM:
    """Deliberately incomplete — only 1 of 8 methods. Used as a negative case.
    의도적으로 불완전 — 8개 중 1개 method만 구현. negative case 용.
    """

    def encode(self, signal, available_modalities):  # type: ignore[no-untyped-def]
        return None


def test_negative_sanity_broken_implementation_rejected() -> None:
    """``runtime_checkable`` must reject an incomplete implementation.
    ``runtime_checkable``은 불완전 구현을 거부해야 한다.
    """
    broken = _BrokenFM()
    assert not isinstance(broken, BiosignalFMInterface), (
        "runtime_checkable accepted an incomplete implementation — "
        "compliance harness is not actually enforcing anything"
    )
