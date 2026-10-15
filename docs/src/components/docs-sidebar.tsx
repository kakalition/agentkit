import { NavLink } from "react-router"

import { NAV, type Section } from "@/lib/nav"
import { cn } from "@/lib/utils"

export function DocsSidebar({ section }: { section: Section }) {
  return (
    <nav className="flex flex-col gap-6 pb-10">
      {NAV[section].map((group) => (
        <div key={group.title} className="flex flex-col gap-1">
          <p className="px-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {group.title}
          </p>
          {group.items.map((item) => (
            <NavLink
              key={item.slug}
              to={`/${section}/${item.slug}`}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  isActive && "bg-muted font-medium text-foreground",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}
