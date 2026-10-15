import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react"
import { Link, Navigate, useParams } from "react-router"

import { DocsSidebar } from "@/components/docs-sidebar"
import { DocsToc } from "@/components/docs-toc"
import { Markdown } from "@/components/markdown"
import { Button } from "@/components/ui/button"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { getNeighbours, getPage, type Section } from "@/lib/docs"
import { cn } from "@/lib/utils"

const DEFAULTS: Record<Section, string> = {
  guide: "introduction",
  reference: "configuration",
}

function DocLink({
  direction,
  to,
  label,
}: {
  direction: "prev" | "next"
  to: string
  label: string
}) {
  const isNext = direction === "next"
  return (
    <Link
      to={to}
      className={cn(
        "flex flex-1 flex-col rounded-lg border px-4 py-3 transition-colors hover:bg-muted",
        isNext && "sm:items-end sm:text-right",
      )}
    >
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        {isNext ? (
          <>
            Next <ChevronRight className="size-3" />
          </>
        ) : (
          <>
            <ChevronLeft className="size-3" /> Previous
          </>
        )}
      </span>
      <span className="mt-1 text-sm font-medium">{label}</span>
    </Link>
  )
}

export function DocsPage({ section }: { section: Section }) {
  const { slug = "" } = useParams()
  const page = getPage(section, slug)

  if (!page) {
    return <Navigate to={`/${section}/${DEFAULTS[section]}`} replace />
  }

  const { prev, next } = getNeighbours(page)

  return (
    <div className="mx-auto flex w-full max-w-[88rem] gap-10 px-4 sm:px-6">
      <aside className="sticky top-14 hidden h-[calc(100svh-3.5rem)] w-56 shrink-0 overflow-y-auto py-10 lg:block">
        <DocsSidebar section={section} />
      </aside>

      <div className="min-w-0 flex-1 py-8 lg:py-10">
        <div className="mx-auto max-w-5xl">
          <Collapsible className="mb-8 lg:hidden">
            <CollapsibleTrigger asChild>
              <Button variant="outline" className="w-full justify-between">
                {section === "guide" ? "Browse the guide" : "Browse the reference"}
                <ChevronDown className="size-4" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3 max-h-[60svh] overflow-y-auto rounded-lg border p-3">
              <DocsSidebar section={section} />
            </CollapsibleContent>
          </Collapsible>

          <article>
            <header className="mb-8">
              <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
                {section === "guide" ? "Guide" : "Reference"}
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
                {page.title}
              </h1>
              {page.description ? (
                <p className="mt-3 text-lg text-muted-foreground">{page.description}</p>
              ) : null}
            </header>
            <Markdown source={page.markdown} />
          </article>

          <nav className="mt-14 flex flex-col gap-3 border-t pt-8 sm:flex-row sm:justify-between">
            {prev ? (
              <DocLink direction="prev" to={`/${section}/${prev.slug}`} label={prev.label} />
            ) : (
              <span className="hidden sm:block sm:flex-1" />
            )}
            {next ? (
              <DocLink direction="next" to={`/${section}/${next.slug}`} label={next.label} />
            ) : null}
          </nav>
        </div>
      </div>

      <aside className="sticky top-14 hidden h-[calc(100svh-3.5rem)] w-56 shrink-0 overflow-y-auto py-10 xl:block">
        <DocsToc headings={page.headings} />
      </aside>
    </div>
  )
}
