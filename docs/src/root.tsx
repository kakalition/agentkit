import { ThemeProvider } from "next-themes"
import { useEffect, useState, type ReactNode } from "react"
import { Links, Meta, Outlet, Scripts, ScrollRestoration, useLocation } from "react-router"

import { SearchDialog } from "@/components/search-dialog"
import { SiteFooter } from "@/components/site-footer"
import { SiteHeader } from "@/components/site-header"
import { TooltipProvider } from "@/components/ui/tooltip"
import "./index.css"

export function meta() {
  return [
    { title: "agentkit — durable AI agents in Python" },
    {
      name: "description",
      content:
        "Build, run, and ship durable AI agents in Python. A batteries-included framework with a Laravel-style developer experience.",
    },
  ]
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content="#0a0a0a" media="(prefers-color-scheme: dark)" />
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  )
}

export default function App() {
  const [searchOpen, setSearchOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setSearchOpen((open) => !open)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  useEffect(() => {
    if (!location.hash) return
    const target = document.getElementById(location.hash.slice(1))
    if (target) target.scrollIntoView()
  }, [location.pathname, location.hash])

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <TooltipProvider>
        <div className="flex min-h-svh flex-col">
          <SiteHeader onSearch={() => setSearchOpen(true)} />
          <main className="flex-1">
            <Outlet />
          </main>
          <SiteFooter />
        </div>
        <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
      </TooltipProvider>
    </ThemeProvider>
  )
}
