# Extensions

An **extension** is a package (or app) that contributes specs, Studio panels,
actions, drivers, catalogs, and codegen targets through one declarative object —
so new capability is registered on the same contract + driver substrate agentkit
already uses, rather than by mutating globals by hand.

```python
from agentkit import ExtensionManifest, PanelSpec

manifest = ExtensionManifest(
    name="my-extension",
    version="1.0.0",
    specs=[("greeting", GreetingSpec)],
    panels=[PanelSpec(id="greetings", spec_kind="greeting")],
    actions={"greet": lambda body, ctx: {"hello": body.get("who", "world")}},
    drivers=[("cache", "pantry", lambda app: PantryCache())],
    catalogs=[("pantry", lambda app: PantryCatalog())],
    codegen={"toml": render_toml},
)

app = App("assistant").extensions(manifest)
app.boot()
```

## What a manifest contributes

| Field | Registered into |
| --- | --- |
| `specs` | `agentkit.specs.SPECS` (kind → pydantic model + materializer + runner) |
| `panels` | `agentkit.extensions.panels.PANELS` (Studio panel SPI) |
| `actions` | `agentkit.extensions.actions.ACTIONS` (`POST /api/studio/actions/{id}`) |
| `drivers` | `agentkit.support.register_driver` (`(kind, name)` factories) |
| `catalogs` | `agentkit.catalog.CATALOGS` (named catalog sources) |
| `codegen` | `agentkit.specs.codegen` (named codegen targets) |

## Discovery order

Manifests are discovered and applied once at `App.boot()`, in increasing
precedence (last wins): **entry points** (`agentkit.extensions` group) →
`AGENTKIT_EXTENSIONS` env var (`module:callable[,module:callable]`) →
programmatic `app.extensions(...)`.

Applying is **idempotent** and **failure-isolated**: a broken manifest or action
is logged and skipped, and boot always completes.

```bash
AGENTKIT_EXTENSIONS="my_pkg.ext:manifest" agentkit extensions list
```

Registering a manifest twice under the same name logs a warning and the last
definition wins, so overrides are deterministic.

## Serving extensions

`GET /api/studio/extensions` lists the registered manifests; `GET
/api/studio/panels` lists the panels they (and core) declare. Because the SPA
falls back to a schema-driven form for unknown panels, **adding a spec kind
server-side shows a new builder panel with no SPA rebuild**.
