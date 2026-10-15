from __future__ import annotations

from agentkit.db.models import OwnerProfile
from agentkit.db.repositories import OwnerProfileRepo, Repositories
from agentkit.memory import memory_digest


async def test_profile_upsert_and_merge(repos: Repositories):
    profile = await repos.profile.set(name="Ada", timezone="Europe/London")
    assert isinstance(profile, OwnerProfile)
    assert profile.name == "Ada"
    assert profile.timezone == "Europe/London"

    await repos.profile.merge(notes="likes tea")
    refreshed = await repos.profile.get()
    assert refreshed is not None
    assert refreshed.name == "Ada"  # untouched by merge
    assert refreshed.notes == "likes tea"
    assert isinstance(repos.profile, OwnerProfileRepo)


async def test_profile_preferences_dict_is_serialized(repos: Repositories):
    await repos.profile.set(preferences={"units": "metric", "tone": "brief"})
    profile = await repos.profile.get()
    assert profile is not None
    assert '"units": "metric"' in profile.preferences


async def test_digest_includes_profile_and_groups_by_kind(repos: Repositories):
    assert await memory_digest(repos) is None
    await repos.profile.set(name="Ada")
    await repos.memories.add("Prefers metric units", kind="preference")
    await repos.memories.add("Cat named Mochi", kind="person")
    digest = await memory_digest(repos)
    assert digest is not None
    assert "Owner profile" in digest
    assert "Ada" in digest
    assert "Preferences:" in digest
    assert "People:" in digest
    assert "Prefers metric units" in digest
