import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_engine_and_protocol_have_distinct_license_boundaries() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["license"] == "AGPL-3.0-only"
    assert project["version"] == "0.2.0"
    assert (ROOT / "LICENSES" / "AGPL-3.0.txt").is_file()
    assert (ROOT / "LICENSES" / "Apache-2.0.txt").is_file()
    assert project["license-files"] == ["LICENSE", "LICENSES/AGPL-3.0.txt"]
    protocol_notice = (ROOT / "docs" / "protocol" / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in protocol_notice


def test_property_test_dependency_is_declared() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert any(
        item.startswith("hypothesis>=") for item in project["optional-dependencies"]["dev"]
    )
