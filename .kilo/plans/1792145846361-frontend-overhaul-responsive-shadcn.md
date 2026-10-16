# Frontend overhaul — responsive, shadcn-complete, better UX

## Goal

Overhaul both frontends so they are responsive, solid, and pleasant to use:

- **Internal operator app** (`web/`) — complete shadcn/ui usage, responsive layout, real
  navigation/feedback/error UX.
- **Public site** (`docs/`) — fix the low-visibility / unfinished landing page and tighten
  the rest of the site's contrast and responsiveness.

Locked decisions (from planning):

- **Fix + polish, keep the aesthetic.** No new brand identity; stay monochrome/neutral.
- Internal app: shadcn completeness, command palette + grouped nav, responsive layout,
  mobile-friendly tables, global error boundary + toast feedback, header breadcrumbs.
- Public site: hero visibility + hierarchy, add a product visual, responsive sections +
  code/table overflow, de-drift stats, docs-page contrast.
- Data tables on phones: **horizontal scroll + scroll affordance** (no card fallback).
- Landing stats: **soft-cap + centralize** in one module.
- **Frontend only** — no API/backend changes.

## Constraints & conventions

- **Internal SPA** (`web/`): Vite + React 19, `react-router-dom` v7, `@tanstack/react-query`,
  `next-themes`, `sonner`, `cmdk`, `lucide-react`, shadcn style `radix-nova` (`web/components.json`).
- **Public site** (`docs/`): React Router v8 **framework mode, SSR + static prerender**
  (`docs/react-router.config.ts`). Any new component must be **SSR-safe**: no `window`/`Date`/
  randomness at render, no hydration mismatch (render must be deterministic on server + client).
- **shadcn components**: add through the shadcn CLI using each app's `components.json`
  (`bunx shadcn@latest add <name>` from `web/` or `docs/`). Do **not** hand-edit generated
  `components/ui/*` if the CLI works; if the CLI is blocked by sandbox permissions, hand-write
  the file to match the existing `radix-nova` pattern (see `web/src/components/ui/switch.tsx`,
  `web/src/components/ui/select.tsx`) and note it.
- **The SPA bundle is committed**: `web/vite.config.ts` builds into
  `src/agentkit/webui/static/` (tracked in git). After `web/` changes you **must** run the
  web build so the served operator UI updates. `docs/build/` is gitignored (no commit needed).
- No `shadcn` skill is installed in this environment; use the repo's shadcn wiring directly.

## Workstream A — Internal app: shadcn completeness

Replace every raw HTML control with its shadcn equivalent.

1. **Add missing primitives** (via CLI from `web/`): `checkbox`. Add others only if a task below
   needs them (`empty`/`pagination` are optional, not required).
2. `web/src/routes/chat.tsx` — raw `<select>` (pick existing conversation, ~L140) → `Select`;
   raw `<details>/<summary>` tool-result (~L35) → `Collapsible`/`CollapsibleTrigger`/`Content`.
3. `web/src/routes/studio.tsx` — 3 raw `<select>` (kind/speaker/moderator, ~L401/416/433) →
   `Select`; raw team-list `<button>` (~L350) → shared selectable list row (see A6).
4. `web/src/lib/spec-panel.tsx` — raw `<select>` (code target, ~L132) → `Select`; raw list
   `<button>` (~L89) → shared list row.
5. `web/src/lib/schema-form.tsx` — raw enum `<select>` (~L160) → `Select`; raw
   `<input type=checkbox>` (~L183) → `Checkbox` + `Label`.
6. `web/src/lib/panel-host.tsx` (~L38) and `web/src/lib/studio-panels.tsx` (~L169) — raw list
   `<button>` → shared row; `studio-panels.tsx` `<details>` (~L232) → `Collapsible`.
7. `web/src/routes/data.tsx` — raw checkbox (~L74) → `Checkbox` + `Label`.
8. `web/src/routes/artifacts.tsx` — keep `<a download>` but wrap as `Button asChild`.
9. **New shared helper** `web/src/components/list-item.tsx`: a selectable list row built from
   `cn` + button semantics (or reuse `SidebarMenuButton`) used by 3, 4, 6 for consistent
   active/hover/focus styling.

## Workstream B — Internal app: layout, navigation, feedback

10. **Content frame** — `web/src/App.tsx`: `mx-auto w-full max-w-6xl p-6` → responsive
    `mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-6`. Ensure header title/breadcrumb
    truncates and controls don't overflow at 360px.
11. **Group the sidebar** — `web/src/components/app-sidebar.tsx` + `App.tsx` `baseItems`:
    group the 16 flat items into labelled `SidebarGroup`s (e.g. *Chat & History*,
    *Automation*, *Insights*, *Agent*, *System*). Keep `collapsible="icon"`; the shadcn
    `Sidebar` already renders a mobile `Sheet` (verify `SidebarTrigger` visible on mobile).
12. **Command palette (⌘K)** — new `web/src/components/command-menu.tsx` using `Dialog` +
    `Command` (mirror the proven pattern in `docs/src/components/search-dialog.tsx`). Commands:
    navigate to every route, toggle theme, refresh info/health. Register ⌘K / Ctrl+K in
    `App.tsx`. `cmdk` is already a dependency.
13. **Breadcrumbs** — use existing `web/src/components/ui/breadcrumb.tsx` in the `App.tsx`
    header: `agentkit / <Group> / <Page>`. Replace the current single title span.
14. **Fluid scroll heights** — `chat.tsx` `h-[26rem]` → `h-[calc(100svh-22rem)] min-h-[16rem]`
    (or a flex column that fills); `a2a.tsx`/`workflows.tsx` `h-[70vh]` → `h-[70svh]`;
    `persona.tsx` `min-h-[28rem]` → `min-h-[50svh]`.
15. **Tab overflow** — `studio.tsx` 7-tab `TabsList` → single-line horizontally scrollable
    (`overflow-x-auto`, `w-full`, no wrap) so it never clips on mobile.
16. **Table affordance** — shadcn `Table` already scrolls (`table.tsx` wraps in
    `overflow-x-auto`). Add a small reusable `web/src/components/table-shell.tsx` that wraps the
    existing `rounded-lg border` container with left/right scroll-shadow gradients driven by
    scroll position, applied to all table routes (`conversations`, `scheduler`, `usage`,
    `teams`, `config`). Add `title` attrs on long id/URL cells (`conversations`, `usage`).
17. **Toasts** — `sonner` is mounted (`main.tsx`) but only used in `persona.tsx`. Add
    `toast.success`/`toast.error` to mutations in `scheduler`, `conversations`, `data`,
    `studio`, `spec-panel`, `panel-host`, and any lessons/approval actions, so failures are no
    longer silent. Keep inline `ErrorAlert` for query errors.
18. **Global error boundary** — new `web/src/components/error-boundary.tsx` (React class
    boundary) rendering a shadcn `Alert` + relaunch `Button`; wrap `<App/>` in `main.tsx`
    inside the providers.
19. **Loading/empty states** — ensure each route renders `Loading` (from `components/page.tsx`)
    while `isLoading` and an explicit empty state when data is empty (several routes currently
    render nothing while loading).

## Workstream C — Public site

20. **Hero visibility + hierarchy** — `docs/src/pages/landing.tsx` hero section +
    `docs/src/index.css`: replace the near-invisible
    `bg-[radial-gradient(60%_60%_at_50%_0%,var(--muted),transparent)]` with a visible but
    restrained treatment (add `.hero-glow` using `--foreground`/`--primary` at low alpha, plus
    a faint grid/dot `.hero-grid` background) with explicit light/dark variants. Bump hero type
    (`text-4xl sm:text-6xl lg:text-7xl`), tighten leading/tracking, and raise lede contrast
    (`text-foreground/70` where pure `muted-foreground` is too faint). Keep monochrome.
21. **Product visual** — new `docs/src/components/console-mock.tsx`: an SSR-safe, image-free
    static mock of the operator console (sidebar rail + chat pane + stat chips) built from
    plain `div`s, Tailwind, and `lucide-react` icons. Place alongside the hero (two-column on
    `lg`, stacked below the fold on mobile). No client-only APIs, no random output.
22. **Responsive sections + overflow** — ensure the feature grid, the Laravel concept-map
    table (`overflow-x-auto` + sensible `min-w`), code blocks (already `overflow-x-auto` via
    `markdown.tsx` `CodeBlock`), stats row, and final CTA behave at 360/768/1280px; normalize
    section vertical rhythm and `text-balance`.
23. **De-drift stats** — new `docs/src/lib/site.ts` exporting a single `STATS` constant with
    soft-capped values (`150+`, `40+`, etc.); import it in `landing.tsx` and remove the inline
    `STATS` array.
24. **Docs-page contrast** — `docs/src/index.css`: nudge `--muted-foreground` in light mode
    toward AA for small text, verify hairline `--border` visibility in both themes, raise
    low-contrast highlight tokens, and add visible `:focus-visible` rings. Applies to prose,
    callouts, code headers, and the sidebar.
25. **Chrome polish (light touch)** — `site-header.tsx` / `site-footer.tsx` / `docs-sidebar.tsx`:
    consistent focus states, mobile sheet nav checks, and spacing; no structural redesign.

## Validation

- Typecheck (allowed): `tsc -b` in `web/` and in `docs/` (`docs/package.json` also runs
  `react-router typegen`).
- Lint/build (may require confirming a sandbox prompt): `bun run lint` (oxlint) and
  `bun run build` in each app.
- **Rebuild + commit the SPA bundle**: run `web`'s build (`bun run build`) so
  `src/agentkit/webui/static/` matches the source; this output is tracked in git.
- Manual visual pass (`bun run dev` in each app): 360px, 768px, 1280px widths; light + dark;
  keyboard-only nav; ⌘K palette; tab strip; table scroll affordance; empty/loading/error
  states; docs landing hero + product visual.
- Accessibility spot-check: icon-button `aria-label`s, focus-visible, form `Label` wiring,
  contrast in both themes.
- Confirm the docs site still prerenders: build must emit HTML for `/` and every `DOC_PATHS`
  route (`docs/src/lib/nav.ts`) without hydration warnings.

## Risks / open items

- **SSR/hydration**: any new `docs/` component must render deterministically on the server;
  put client-only behaviour behind effects and avoid `window`/random at render (items 21–22).
- **shadcn CLI availability**: if the sandbox blocks `bunx shadcn`, hand-write the missing
  primitives to match the existing `radix-nova` style and flag it in the PR.
- **Do not hand-edit generated `ui/*`** unless the CLI is unavailable; prefer regeneration so
  future upgrades stay clean.
- **No backend/API changes**; if a landing claim cannot be sourced frontend-side, reword it
  rather than adding an endpoint.
- Grouping taxonomy for the sidebar (item 11) is a judgment call — implement a sensible
  4–5 group split and keep labels short; adjust if a reviewer prefers different grouping.
