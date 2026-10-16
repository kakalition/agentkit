from __future__ import annotations

from conformance import checkpoint_store_conformance

from agentkit.checkpoints import (
    FileCheckpointStore,
    MemoryCheckpointStore,
    RepositoryCheckpointStore,
)


async def test_memory_checkpoint_store_conforms():
    await checkpoint_store_conformance(MemoryCheckpointStore())


async def test_file_checkpoint_store_conforms(tmp_path):
    await checkpoint_store_conformance(FileCheckpointStore(tmp_path / "checkpoints"))


async def test_repository_checkpoint_store_conforms(runtime):
    await checkpoint_store_conformance(RepositoryCheckpointStore(runtime))
