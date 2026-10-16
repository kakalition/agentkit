import { Menu, Search } from "lucide-react"
import { useState } from "react"
import { Link, NavLink } from "react-router"

import { GitHubMark, Logo } from "@/components/logo"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { cn } from "@/lib/utils"

const GITHUB = "https://github.com/kakalition/agentkit"

const links = [
  { label: "Guide", to: "/guide/getting-started" },
  { label: "Reference", to: "/reference/configuration" },
  { label: "Philosophy", to: "/guide/philosophy" },
]

export function SiteHeader({ onSearch }: { onSearch: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-[88rem] items-center gap-2 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-medium tracking-tight">
          <Logo />
          <span>agentkit</span>
        </Link>

        <nav className="ml-4 hidden items-center gap-1 md:flex">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground",
                  isActive && "text-foreground",
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            onClick={onSearch}
            className="hidden h-8 items-center gap-2 rounded-md border bg-muted/40 pr-1.5 pl-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted sm:flex"
          >
            <Search className="size-3.5" />
            <span>Search</span>
            <kbd className="rounded border bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              ⌘K
            </kbd>
          </button>

          <Button
            variant="ghost"
            size="icon"
            className="sm:hidden"
            aria-label="Search"
            onClick={onSearch}
          >
            <Search />
          </Button>

          <Button asChild variant="ghost" size="icon">
            <a href={GITHUB} target="_blank" rel="noreferrer" aria-label="GitHub">
              <GitHubMark />
            </a>
          </Button>

          <ThemeToggle />

          <Separator orientation="vertical" className="mx-0.5 hidden h-5 sm:block" />

          <Button asChild size="lg" className="hidden sm:inline-flex">
            <Link to="/guide/getting-started">Get started</Link>
          </Button>

          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="Menu">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-72">
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  <Logo />
                  agentkit
                </SheetTitle>
              </SheetHeader>
              <nav className="flex flex-col gap-1 px-2">
                {links.map((link) => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMenuOpen(false)}
                    className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                ))}
                <Link
                  to="/guide/getting-started"
                  onClick={() => setMenuOpen(false)}
                  className="mt-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
                >
                  Get started
                </Link>
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  )
}
