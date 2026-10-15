import { useEffect, useState } from "react"

import type { Heading } from "@/lib/docs"
import { cn } from "@/lib/utils"

export function DocsToc({ headings }: { headings: Heading[] }) {
  const items = headings.filter((heading) => heading.depth === 2 || heading.depth === 3)
  const ids = items.map((item) => item.id).join("|")
  const [activeId, setActiveId] = useState(items[0]?.id ?? "")

  useEffect(() => {
    const elements = ids
      .split("|")
      .map((id) => (id ? document.getElementById(id) : null))
      .filter((element): element is HTMLElement => element !== null)
    if (elements.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActiveId(visible[0].target.id)
      },
      { rootMargin: "-72px 0px -70% 0px", threshold: [0, 1] },
    )
    elements.forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [ids])

  if (items.length === 0) return null

  return (
    <nav className="flex flex-col gap-2">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        On this page
      </p>
      <ul className="flex flex-col gap-1 border-l">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              className={cn(
                "-ml-px block border-l border-transparent py-1 pl-3 text-sm text-muted-foreground transition-colors hover:text-foreground",
                item.depth === 3 && "pl-6",
                activeId === item.id && "border-l-foreground text-foreground",
              )}
            >
              {item.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
