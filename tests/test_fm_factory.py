"""Factory tests — config-driven instantiation (ADR-011).
Factory 테스트 — config 기반 인스턴스 생성 (ADR-011).

Verifies:
검증 항목:
- mock_stub instantiation works / mock_stub 인스턴스 생성 OK
- factory output satisfies the Protocol / factory 출력이 Protocol 만족
- unknown implementation raises ValueError / 알 수 없는 값은 ValueError
- unimplemented tiers raise NotImplementedError with a clear message /
  미구현 tier는 명확한 메시지의 NotImplementedError
- malformed config raises ValueError / 잘못된 config는 ValueError
"""
from __future__ import annotations

import pytest

from opsight.fm.factory import create_fm
from opsight.fm.interface import BiosignalFMInterface
from opsight.fm.mock_stub import StubBiosignalFM


def test_create_mock_stub_returns_protocol_instance() -> None:
    """mock_stub instantiation returns a Protocol-compliant instance.
    mock_stub 생성 시 Protocol을 만족하는 인스턴스를 반환한다.
    """
    fm = create_fm({"fm": {"implementation": "mock_stub", "config": {"seed": 42}}})
    assert isinstance(fm, StubBiosignalFM)
    assert isinstance(fm, BiosignalFMInterface)


def test_create_mock_stub_without_config_section() -> None:
    """``config["fm"]["config"]`` omitted → defaults used.
    ``config["fm"]["config"]`` 누락 시 default 사용.
    """
    fm = create_fm({"fm": {"implementation": "mock_stub"}})
    assert isinstance(fm, StubBiosignalFM)


def test_create_mock_stub_forwards_kwargs() -> None:
    """``config["fm"]["config"]`` kwargs are forwarded to the constructor.
    ``config["fm"]["config"]`` kwargs가 생성자에 전달된다.
    """
    fm = create_fm(
        {
            "fm": {
                "implementation": "mock_stub",
                "config": {"seed": 7, "latent_dim": 64, "latency_sim_sec": 0.01},
            }
        }
    )
    assert isinstance(fm, StubBiosignalFM)
    # latent_dim forwarded → encode tensor shape (64,)
    # latent_dim 전달됨 → encode tensor shape (64,)
    out = fm.encode({}, [])
    assert tuple(out.shape) == (64,)


def test_unknown_implementation_raises_valueerror() -> None:
    """Unknown implementation name raises ``ValueError`` with the offending string.
    알 수 없는 구현체 이름은 위반 문자열을 포함한 ``ValueError``를 발생시킨다.
    """
    with pytest.raises(ValueError, match="Unknown FM implementation"):
        create_fm({"fm": {"implementation": "nonexistent_tier"}})


def test_missing_fm_section_raises_valueerror() -> None:
    """Config without an ``fm`` object raises ``ValueError``.
    ``fm`` 객체가 없는 config는 ``ValueError``를 발생시킨다.
    """
    with pytest.raises(ValueError, match="'fm' object"):
        create_fm({})


@pytest.mark.parametrize(
    ("impl_name", "expected_phrase"),
    [
        # mock_rule_based / mock_light_ml are implemented (plan_1.6.5 / plan_1.7.5);
        # see test_create_*_returns_protocol_instance below.
        # mock_rule_based / mock_light_ml 는 구현됨 (plan_1.6.5 / plan_1.7.5).
        ("real", "Stage 2"),
    ],
)
def test_unimplemented_tier_raises_notimplemented(
    impl_name: str, expected_phrase: str
) -> None:
    """Tier names valid but module missing → ``NotImplementedError`` with hint.
    tier 이름은 유효하나 module 부재 → 안내 메시지가 포함된 ``NotImplementedError``.
    """
    with pytest.raises(NotImplementedError, match=expected_phrase):
        create_fm({"fm": {"implementation": impl_name}})


def test_create_mock_rule_based_returns_protocol_instance() -> None:
    """``mock_rule_based`` factory path returns a Protocol-compliant instance.
    ``mock_rule_based`` factory가 Protocol 만족 인스턴스 반환.

    Added when plan_1.6.5 landed (2026-05-16).
    plan_1.6.5 완료 시점에 추가됨 (2026-05-16).
    """
    fm = create_fm(
        {"fm": {"implementation": "mock_rule_based", "config": {"seed": 42}}}
    )
    assert isinstance(fm, BiosignalFMInterface)


def test_create_mock_light_ml_returns_protocol_instance() -> None:
    """``mock_light_ml`` factory path returns a Protocol-compliant instance.
    ``mock_light_ml`` factory 가 Protocol 만족 인스턴스 반환.

    Added when plan_1.7.5 landed (2026-05-17, Sprint 5).
    plan_1.7.5 완료 시점에 추가됨 (2026-05-17, Sprint 5).
    """
    fm = create_fm(
        {
            "fm": {
                "implementation": "mock_light_ml",
                "config": {"primary_baseline": "logreg_abp", "seed": 42},
            }
        }
    )
    assert isinstance(fm, BiosignalFMInterface)
