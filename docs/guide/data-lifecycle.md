# Data Lifecycle

## Introduction

Agentkit stores everything owner-scoped, so a single tenant's data can be
**exported** as a portable JSON bundle and **erased** on request. Export is safe
and on by default; erasure is destructive and opt-in.

## Export

```bash
agentkit data:export --owner acme --out acme.json
```

The bundle contains conversations, messages, memories, the owner profile,
knowledge chunks, learning runs, feedback, and usage records. The same data is
available over the API at `GET /api/data/export` (scoped to the authenticated
actor, gated by `DATA_EXPORT_ENABLED`).

## Forget (erasure)

```bash
agentkit data:forget --owner acme            # dry run: reports what would go
agentkit data:forget --owner acme --yes      # actually erase
```

Erasure removes conversations, messages, memories, the owner profile, knowledge
chunks, learning runs, feedback, and usage. **Audit entries are never deleted**:
a `data.forget` tombstone is appended so the hash chain stays verifiable and the
erasure itself is recorded. The API mirrors this: `POST /api/data/forget` is a
dry run unless called with `?confirm=true`, and is disabled until you set
`DATA_FORGET_ENABLED=true`.

::: warning Destructive and irreversible
Forget cannot be undone. Always run the dry run first, and back up with
`data:export` before erasing.
:::

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `DATA_EXPORT_ENABLED` | `true` | Allow exporting an owner's bundle. |
| `DATA_FORGET_ENABLED` | `false` | Allow destructive erasure (opt-in). |

Continue to [Deployment →](/guide/deployment)
