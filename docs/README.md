# agentkit docs

The landing page and documentation site for agentkit, built with **React Router v8
framework mode** (SSR) on Vite + React + TypeScript + Tailwind CSS v4 + **shadcn/ui**.
Every element under `src/components/ui/` is shadcn-generated, and the whole site is
rendered from those primitives.

The site is server-rendered and **statically prerendered** at build time: the landing
page and all 50+ documentation pages ship as complete HTML, so search engines index
real content and the site works without JavaScript. The design is intentionally
minimal — a monochrome neutral palette, hairline borders, generous whitespace, and a
light/dark theme toggle.

## Develop

```bash
bun install
bun run dev        # http://localhost:5173 (SSR dev server)
```

## Build

```bash
bun run build      # typegen + tsc + react-router build, prerenders every route
bun run start      # react-router-serve ./build/server/index.js (SSR server)
```

`react-router build` emits:

- `build/client/` — the client bundle **and prerendered `index.html` per route**
  (this is the static site; serve it from any static host).
- `build/server/` — the SSR server entry used by `bun run start`.

## Structure

```
docs/
├── react-router.config.ts   # appDirectory, ssr, prerender path list
├── guide/                   # the prose documentation (markdown, unchanged)
├── reference/               # configuration, environment, API, changelog
├── public/                  # logo, favicon
└── src/
    ├── root.tsx             # document shell, providers, header/footer, ⌘K search
    ├── routes.ts            # route config
    ├── routes/              # thin route modules (landing, docs, 404, redirects)
    ├── components/          # site chrome + markdown renderer
    │   ├── ui/              # shadcn primitives (do not hand-edit; regenerate)
    │   ├── markdown.tsx     # react-markdown pipeline + Callout / CodeBlock
    │   ├── docs-sidebar.tsx # section navigation built from src/lib/nav.ts
    │   ├── docs-toc.tsx     # "On this page" rail
    │   └── site-*.tsx       # header, footer
    ├── lib/nav.ts           # nav config + prerender path list (imported by config)
    ├── lib/docs.ts          # markdown loader, headings, search index
    ├── pages/               # landing + documentation page components
    └── index.css            # design tokens, prose styles, code themes
```

## Adding documentation

1. Drop a `.md` file in `guide/` or `reference/` (start it with a single `# Title`).
2. Add its slug and label to `NAV` in `src/lib/nav.ts`.

Nav, headings, the "On this page" rail, the search index, prev/next links, and the
prerender path list are all derived automatically — there is no separate sidebar
config to keep in sync.

## Authoring notes

- `::: tip|warning|danger Title` containers are supported and render as shadcn-styled
  callouts. `::: code-group` groups consecutive code fences.
- Fenced code blocks are syntax-highlighted with `rehype-highlight`; a fence title
  such as ```` ```bash [uv] ```` is shown in the block header.
- Internal links written as `/guide/...` or `/reference/...` become client-side
  router links automatically.
