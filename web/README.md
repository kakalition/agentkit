# agentkit web UI

Operator console for the hosting agent. Vite + React + TypeScript + Tailwind +
**shadcn/ui** (every element under `src/components/ui/` is shadcn-generated).

## Develop

```bash
bun install
bun run dev      # http://localhost:5173, proxies /api -> 127.0.0.1:8787
```

Run an agent with the UI enabled (e.g. `artemis up` or `agentkit webui`) so the
dev proxy has an API to talk to.

## Build

```bash
bun run build    # tsc -b && vite build
```

The build writes to `../src/agentkit/webui/static/`, so the Python server serves
it directly (and the wheel ships it). The agent resolves `web/dist` first, then
the packaged `agentkit/webui/static/`, and falls back to a built-in page when
neither exists.

## Layout

- `src/components/ui/` — shadcn primitives (do not hand-edit; regenerate).
- `src/components/` — app shell (sidebar, theme toggle, page helpers).
- `src/routes/` — one page per feature, composed only from shadcn primitives.
- `src/lib/api.ts` — typed fetch client for `/api`.
