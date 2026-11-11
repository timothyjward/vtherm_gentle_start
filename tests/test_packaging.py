"""Consistency of the files which HACS, Home Assistant and the release workflow read: a mismatch breaks an install, not a test."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.vtherm_gentle_start.const import DOMAIN

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / DOMAIN


def load(path: Path) -> dict:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def keys_of(tree: dict, prefix: str = "") -> set[str]:
    """The dotted paths of all the leaves of a nested dictionary."""
    found: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            found |= keys_of(value, f"{path}.")
        else:
            found.add(path)
    return found


@pytest.mark.parametrize("translation", ["en", "fr"])
def test_translations_have_the_keys_of_strings_json(translation: str) -> None:
    """Every string is translated, and none is left over."""
    assert keys_of(load(INTEGRATION / "translations" / f"{translation}.json")) == keys_of(load(INTEGRATION / "strings.json"))


def test_the_manifest_matches_the_folder_and_the_constants() -> None:
    """The domain is the name of the folder, which is what Home Assistant and HACS install."""
    manifest = load(INTEGRATION / "manifest.json")
    assert manifest["domain"] == DOMAIN == INTEGRATION.name
    assert "versatile_thermostat" in manifest["dependencies"]
    assert any(requirement.startswith("vtherm_api>=0.8") for requirement in manifest["requirements"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    for key in ("documentation", "issue_tracker", "codeowners", "name"):
        assert manifest[key]


def test_the_release_workflow_builds_the_zip_which_hacs_looks_for() -> None:
    """HACS downloads the file named in hacs.json from the release: the workflow has to attach a file of that name."""
    hacs = load(ROOT / "hacs.json")
    assert hacs["zip_release"] is True
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert f"zip -r ../../{hacs['filename']} ." in workflow
    assert f"files: {hacs['filename']}" in workflow
    # The version is stamped in the manifest of the integration which is zipped
    assert f"custom_components/{DOMAIN}/manifest.json" in workflow
    assert f"cd custom_components/{DOMAIN}" in workflow


def test_the_brand_images_hacs_requires_exist() -> None:
    """HACS requires a brand directory with at least an icon."""
    assert (INTEGRATION / "brand" / "icon.png").is_file()


def test_the_hacs_manifest_names_the_integration() -> None:
    """The minimum Home Assistant and HACS versions are set, as in the blueprint."""
    hacs = load(ROOT / "hacs.json")
    assert hacs["name"]
    assert hacs["homeassistant"]
    assert hacs["hacs"]
