import { useEffect, useRef, useState, type ReactNode } from "react"

import { cn } from "@/lib/utils"

/**
 * Wraps a shadcn `Table` in the standard bordered container and shows soft
 * edge shadows when the inner `[data-slot=table-container]` can scroll
 * horizontally. Lets phone users discover off-screen columns.
 */
export function TableShell({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [edges, setEdges] = useState({ left: false, right: false })

  useEffect(() => {
    const container = ref.current?.querySelector<HTMLElement>('[data-slot="table-container"]')
    if (!container) return

    const update = () => {
      const max = container.scrollWidth - container.clientWidth
      const left = container.scrollLeft > 1
      const right = max > 1 && container.scrollLeft < max - 1
      setEdges((current) =>
        current.left === left && current.right === right ? current : { left, right },
      )
    }

    update()
    container.addEventListener("scroll", update, { passive: true })
    const observer = new ResizeObserver(update)
    observer.observe(container)
    return () => {
      container.removeEventListener("scroll", update)
      observer.disconnect()
    }
  }, [children])

  return (
    <div ref={ref} className={cn("relative overflow-hidden rounded-lg border", className)}>
      {children}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 w-8 bg-linear-to-r from-foreground/[0.06] to-transparent transition-opacity duration-200",
          edges.left ? "opacity-100" : "opacity-0",
        )}
      />
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-y-0 right-0 w-8 bg-linear-to-l from-foreground/[0.06] to-transparent transition-opacity duration-200",
          edges.right ? "opacity-100" : "opacity-0",
        )}
      />
    </div>
  )
}
