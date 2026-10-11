from __future__ import annotations

import pytest

from agentkit import workspace
from agentkit.errors import Conflict


@pytest.fixture
def legacy(monkeypatch, tmp_path):
    monkeypatch.setattr(
        workspace, "LEGACY_ROOTS", (str(tmp_path / "agentkit"), str(tmp_path / "own" / "{name}"))
    )
    return tmp_path


def test_workspace_dir_default_and_custom_root(tmp_path):
    assert workspace.workspace_dir("calliope", root=tmp_path) == tmp_path / "calliope"


def test_detect_legacy_prefers_name_specific_data(legacy):
    shared = legacy / "agentkit"
    shared.mkdir()
    (shared / "calliope.db").write_text("db")
    assert workspace.detect_legacy("calliope") == shared
    assert workspace.detect_legacy("artemis") is None


def test_detect_legacy_ignores_artifact_only_dir(legacy):
    own = legacy / "own" / "kilo"
    (own / "logs").mkdir(parents=True)
    (own / "artifacts").mkdir()
    assert workspace.detect_legacy("kilo") is None


def test_detect_legacy_matches_name_specific_db(legacy):
    own = legacy / "own" / "artemis"
    own.mkdir(parents=True)
    (own / "artemis.db").write_text("db")
    assert workspace.detect_legacy("artemis") == own


def test_migrate_moves_payload(legacy):
    shared = legacy / "agentkit"
    (shared / "artifacts").mkdir(parents=True)
    (shared / "calliope.db").write_text("db")
    (shared / "SOUL.md").write_text("soul")

    summary = workspace.migrate("calliope", root=legacy / "ws")

    assert summary["migrated"] is True
    assert summary["mode"] == "move"
    target = legacy / "ws" / "calliope"
    assert (target / "calliope.db").read_text() == "db"
    assert (target / "SOUL.md").read_text() == "soul"
    assert (target / "artifacts").is_dir()
    assert not (shared / "calliope.db").exists()


def test_migrate_is_a_safe_noop_without_legacy(legacy):
    summary = workspace.migrate("ghost", root=legacy / "ws")
    assert summary["migrated"] is False
    assert summary["reason"] == "no legacy data found"


def test_migrate_copy_mode_keeps_source(legacy):
    shared = legacy / "agentkit"
    shared.mkdir()
    (shared / "calliope.db").write_text("db")

    summary = workspace.migrate("calliope", root=legacy / "ws", move=False)

    assert summary["mode"] == "copy"
    assert (shared / "calliope.db").exists()


def test_migrate_refuses_non_empty_target(legacy):
    shared = legacy / "agentkit"
    shared.mkdir()
    (shared / "calliope.db").write_text("db")
    target = legacy / "ws" / "calliope"
    target.mkdir(parents=True)
    (target / "agent.db").write_text("existing")

    with pytest.raises(Conflict):
        workspace.migrate("calliope", root=legacy / "ws")
