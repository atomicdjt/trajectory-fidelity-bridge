"""Guard against release-metadata drift (CITATION.cff previously lagged the package version)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _project_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as pyproject:
        return str(tomllib.load(pyproject)["project"]["version"])


def test_citation_version_matches_the_package_version():
    citation = (REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)\s*$", citation, re.MULTILINE)

    assert match is not None
    assert match.group(1) == _project_version()


def test_readme_install_pin_matches_the_package_version():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    pins = re.findall(r"atomicdjt-trajectory-fidelity-bridge==(\S+)", readme)

    if pins:
        assert set(pins) == {_project_version()}


def test_distribution_name_and_legacy_cli_alias():
    with (REPO_ROOT / "pyproject.toml").open("rb") as pyproject:
        project = tomllib.load(pyproject)["project"]

    assert project["name"] == "atomicdjt-trajectory-fidelity-bridge"
    assert project["scripts"]["agent-session"] == "cli.main:main"
    assert project["scripts"]["tfb"] == "cli.main:main"
