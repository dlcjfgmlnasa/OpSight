"""yaml config templates → factory smoke tests.
yaml config 템플릿 → factory 통합 스모크 테스트.

Verifies that every yaml under ``configs/fm/`` loads, has the required
structure, and (where the implementation is implemented) instantiates a
Protocol-compliant FM via ``create_fm``.
모든 ``configs/fm/*.yaml``이 로드 가능하고 필수 구조를 갖추며, 구현된 tier는
``create_fm``으로 Protocol 만족 인스턴스가 생성됨을 검증한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opsight.fm.factory import create_fm
from opsight.fm.interface import BiosignalFMInterface

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs" / "fm"

EXPECTED_TEMPLATES = {
    "mock_stub.yaml",
    "mock_rule_based.yaml",
    "mock_light_ml.yaml",
    "real.yaml",
    "default.yaml",
}


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_all_5_templates_exist() -> None:
    """All 5 expected yaml templates exist under ``configs/fm/``.
    예상한 5개의 yaml template이 ``configs/fm/`` 아래에 존재한다.
    """
    found = {p.name for p in CONFIGS_DIR.glob("*.yaml")}
    missing = EXPECTED_TEMPLATES - found
    assert not missing, f"missing templates: {missing}"


@pytest.mark.parametrize("name", sorted(EXPECTED_TEMPLATES))
def test_template_has_fm_implementation_field(name: str) -> None:
    """Every template parses as yaml and has ``fm.implementation``.
    모든 template이 yaml로 파싱되고 ``fm.implementation``을 가진다.
    """
    config = _load_yaml(CONFIGS_DIR / name)
    assert isinstance(config, dict), f"{name} did not parse to a dict"
    assert "fm" in config and isinstance(config["fm"], dict), (
        f"{name} missing 'fm' object"
    )
    assert "implementation" in config["fm"], (
        f"{name} missing 'fm.implementation'"
    )


def test_default_yaml_points_at_implemented_tier() -> None:
    """``default.yaml`` must point at an implemented tier.
    ``default.yaml``은 구현된 tier를 가리켜야 한다.

    Allowed values evolve with the lifecycle in ``configs/fm/default.yaml``:
    ``mock_stub`` (Week 1–3) → ``mock_rule_based`` (Week 4–8) → ``real``
    (Stage 2+). Currently ``mock_rule_based`` after plan_1.6.5.
    허용 값은 ``configs/fm/default.yaml``의 lifecycle을 따른다: mock_stub →
    mock_rule_based → real. plan_1.6.5 완료 후 현재는 ``mock_rule_based``.
    """
    config = _load_yaml(CONFIGS_DIR / "default.yaml")
    implemented_tiers = {"mock_stub", "mock_rule_based"}
    assert config["fm"]["implementation"] in implemented_tiers, (
        f"default.yaml은 구현된 tier {implemented_tiers}를 가리켜야 한다"
    )


def test_mock_stub_yaml_instantiates_via_factory() -> None:
    """``mock_stub.yaml`` round-trips through ``create_fm`` and the result
    satisfies the Protocol.
    ``mock_stub.yaml``이 ``create_fm``을 통해 round-trip되어 Protocol을 만족.
    """
    config = _load_yaml(CONFIGS_DIR / "mock_stub.yaml")
    fm = create_fm(config)
    assert isinstance(fm, BiosignalFMInterface)


def test_default_yaml_instantiates_via_factory() -> None:
    """``default.yaml`` instantiates through the factory.
    ``default.yaml``이 factory를 통해 인스턴스화된다.
    """
    config = _load_yaml(CONFIGS_DIR / "default.yaml")
    fm = create_fm(config)
    assert isinstance(fm, BiosignalFMInterface)


@pytest.mark.parametrize(
    ("name", "expected_msg"),
    [
        # mock_rule_based.yaml / mock_light_ml.yaml are implemented
        # (plan_1.6.5 / plan_1.7.5 — 2026-05-16 / 2026-05-17).
        # See test_*_yaml_instantiates_via_factory below.
        ("real.yaml", "Stage 2"),
    ],
)
def test_unimplemented_yaml_raises_notimplemented(
    name: str, expected_msg: str
) -> None:
    """Templates for unimplemented tiers raise ``NotImplementedError``
    via ``create_fm`` (with the appropriate plan / stage reference).
    미구현 tier의 template은 ``create_fm`` 호출 시 plan / stage 참조와 함께
    ``NotImplementedError``를 발생시킨다.
    """
    config = _load_yaml(CONFIGS_DIR / name)
    with pytest.raises(NotImplementedError, match=expected_msg):
        create_fm(config)


def test_mock_rule_based_yaml_instantiates_via_factory() -> None:
    """``mock_rule_based.yaml`` round-trips through ``create_fm`` and the
    result satisfies the Protocol (added when plan_1.6.5 landed, 2026-05-16).
    ``mock_rule_based.yaml``이 ``create_fm`` round-trip 후 Protocol 만족 인스턴스
    반환 (plan_1.6.5 완료 시 추가, 2026-05-16).
    """
    config = _load_yaml(CONFIGS_DIR / "mock_rule_based.yaml")
    fm = create_fm(config)
    assert isinstance(fm, BiosignalFMInterface)


def test_mock_light_ml_yaml_instantiates_via_factory() -> None:
    """``mock_light_ml.yaml`` round-trips through ``create_fm`` and the result
    satisfies the Protocol (added when plan_1.7.5 landed, 2026-05-17 Sprint 5).
    ``mock_light_ml.yaml`` 이 ``create_fm`` round-trip 후 Protocol 만족 인스턴스
    반환 (plan_1.7.5 완료 시 추가, 2026-05-17 Sprint 5).
    """
    config = _load_yaml(CONFIGS_DIR / "mock_light_ml.yaml")
    fm = create_fm(config)
    assert isinstance(fm, BiosignalFMInterface)
