import { Link } from "react-router"

import { Logo } from "@/components/logo"

const columns: { title: string; links: { label: string; to: string; external?: boolean }[] }[] = [
  {
    title: "Documentation",
    links: [
      { label: "Introduction", to: "/guide/introduction" },
      { label: "Getting started", to: "/guide/getting-started" },
      { label: "Philosophy", to: "/guide/philosophy" },
      { label: "Configuration", to: "/reference/configuration" },
    ],
  },
  {
    title: "Guides",
    links: [
      { label: "The Agent Builder", to: "/guide/agents" },
      { label: "Memory", to: "/guide/memory" },
      { label: "Knowledge (RAG)", to: "/guide/knowledge" },
      { label: "Deployment", to: "/guide/deployment" },
    ],
  },
  {
    title: "Community",
    links: [
      { label: "GitHub", to: "https://github.com/kakalition/agentkit", external: true },
      { label: "Changelog", to: "/reference/changelog" },
      { label: "Public API", to: "/reference/api" },
      { label: "MIT License", to: "https://github.com/kakalition/agentkit/blob/main/LICENSE", external: true },
    ],
  },
]

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto w-full max-w-[88rem] px-4 py-12 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[1.5fr_repeat(3,1fr)]">
          <div className="space-y-3">
            <Link to="/" className="flex items-center gap-2 font-medium tracking-tight">
              <Logo />
              <span>agentkit</span>
            </Link>
            <p className="max-w-xs text-sm text-muted-foreground">
              Build, run, and ship durable AI agents in Python — one process, one
              mental model.
            </p>
          </div>

          {columns.map((column) => (
            <div key={column.title} className="space-y-3">
              <h3 className="text-sm font-medium">{column.title}</h3>
              <ul className="space-y-2">
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.external ? (
                      <a
                        href={link.to}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <Link
                        to={link.to}
                        className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t pt-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>Released under the MIT License.</p>
          <p>agentkit — build, run, and ship durable AI agents.</p>
        </div>
      </div>
    </footer>
  )
}
