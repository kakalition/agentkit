import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

/**
 * A selectable list row used by the sidebar-style pickers (studio teams, spec
 * definitions, panels, runs). Gives consistent hover/active/focus styling.
 */
export function ListItem({
  active = false,
  onSelect,
  children,
  className,
}: {
  active?: boolean
  onSelect: () => void
  children: ReactNode
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm outline-none transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50",
        active && "bg-accent text-accent-foreground",
        className,
      )}
    >
      {children}
    </button>
  )
}
