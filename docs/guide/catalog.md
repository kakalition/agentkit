# Catalog & Gallery

A **catalog** is a pluggable source of installable items (specs, skills, MCP
servers). Sources are drivers selected by `catalog_driver`; installing an item
writes it into a *target* after validating it and never escaping paths.

```python
from agentkit.catalog import DefinitionsTarget, LocalCatalog
from agentkit.specs import RepositorySpecStore

catalog = LocalCatalog("catalog")
items = await catalog.search("team")
async with repositories(runtime) as repos:
    await catalog.install("team1", DefinitionsTarget(RepositorySpecStore(repos)))
```

## Sources

| Driver | Backing |
| --- | --- |
| `local` | a directory of `*.json` / `*.yaml` items (default) |
| `skills` | the skills directory (each skill is an item) |
| `http` | a JSON index over HTTP (`{"items": [...]}`) |
| `git` | a JSON index in a git repo (raw GitHub URL) |

Extensions register further sources through `manifest.catalogs` /
`register_catalog_source`.

## Install targets

* `DefinitionsTarget(store)` — validate + upsert into the spec store.
* `SkillsTarget(root)` — write a `SKILL.md` (path-safety enforced).
* `None` — return the payload without persisting.

Installation is **idempotent** and validates the spec/skill before writing.

```bash
agentkit catalog list -q team
agentkit catalog install team1 --into definitions
```
