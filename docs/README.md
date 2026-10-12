# agentkit docs

The documentation site, built with [VitePress](https://vitepress.dev) and
[Tailwind CSS](https://tailwindcss.com). The visual theme uses soft, animated
gradients inspired by [feralui.dev/gradients](https://feralui.dev/gradients).

## Develop

```bash
npm install
npm run dev        # http://localhost:5173
```

## Build

```bash
npm run build      # → .vitepress/dist
npm run preview    # serve the built site
```

## Structure

```
docs/
├── index.md                 # landing page (hero + features)
├── guide/                   # the prose documentation
├── reference/               # configuration, environment, API, changelog
├── public/                  # logo, favicon
└── .vitepress/
    ├── config.mts           # nav, sidebar, search, markdown, tailwind plugin
    └── theme/
        ├── index.ts         # extends the default theme
        └── style.css        # Tailwind + gradient theme
```

## Theme notes

- Tailwind v4 is imported **without preflight** (`tailwindcss/theme.css` +
  `tailwindcss/utilities.css`) so it never fights VitePress's base styles.
- The gradient palette is seeded from traditional Japanese colours (藍, 藤, 桜,
  茜, 常磐, 琥珀) and painted as layered radial gradients plus two animated aurora
  blobs on the landing page.
- Motion is disabled under `prefers-reduced-motion`.
