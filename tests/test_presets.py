from __future__ import annotations

import pytest

from agentkit.foundation.scaffold import PRESETS, preset_files, scaffold_project


def test_presets_are_known():
    assert set(PRESETS) == {"support", "research", "ops"}
    with pytest.raises(ValueError):
        preset_files("nope")


@pytest.mark.parametrize("preset", PRESETS)
def test_scaffold_preset_overlays(preset, tmp_path):
    target = scaffold_project(f"proj-{preset}", tmp_path, preset=preset)
    assistant = (target / "app" / "Agents" / "assistant.py").read_text(encoding="utf-8")
    assert f"proj-{preset}" in assistant
    assert "{{" not in assistant  # every placeholder was substituted
    assert (target / "evals" / f"{preset}.json").is_file()
    # the full-stack overlay still applies
    assert (target / "config" / "learning.py").is_file()
