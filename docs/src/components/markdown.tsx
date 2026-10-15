import { Check, Copy, Lightbulb, OctagonAlert, TriangleAlert } from "lucide-react"
import { useRef, useState, type ReactNode } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import rehypeHighlight from "rehype-highlight"
import rehypeSlug from "rehype-slug"
import remarkGfm from "remark-gfm"
import { Link } from "react-router"

import { Button } from "@/components/ui/button"
import {
  normalizeDocsMarkdown,
  remarkCodeTitles,
  remarkDocsContainers,
} from "@/lib/markdown"
import { cn } from "@/lib/utils"

const rehypeHighlightOptions = {
  detect: false,
  plainText: ["text", "txt", "plaintext", "toml", "dockerfile"],
}

const CALLOUTS: Record<
  string,
  { label: string; icon: typeof Lightbulb; accent: string; surface: string }
> = {
  tip: {
    label: "Tip",
    icon: Lightbulb,
    accent: "border-l-foreground/50",
    surface: "bg-muted/40",
  },
  warning: {
    label: "Warning",
    icon: TriangleAlert,
    accent: "border-l-amber-500",
    surface: "bg-amber-500/[0.06]",
  },
  danger: {
    label: "Danger",
    icon: OctagonAlert,
    accent: "border-l-red-500",
    surface: "bg-red-500/[0.06]",
  },
}

function Callout({
  variant,
  title,
  children,
}: {
  variant: string
  title?: string
  children?: ReactNode
}) {
  const config = CALLOUTS[variant] ?? CALLOUTS.tip
  const Icon = config.icon
  return (
    <div
      data-callout={variant}
      className={cn(
        "my-6 rounded-lg border border-l-2 px-4 py-3.5 text-sm leading-relaxed",
        config.accent,
        config.surface,
      )}
    >
      <div className="mb-1.5 flex items-center gap-2 font-medium text-foreground">
        <Icon className="size-4 shrink-0" />
        <span>{title ?? config.label}</span>
      </div>
      <div className="text-muted-foreground [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_p]:my-2 [&_ul]:my-2 [&_ol]:my-2">
        {children}
      </div>
    </div>
  )
}

function CopyButton({
  text,
  className,
}: {
  text: () => string
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label="Copy code"
      className={className}
      onClick={() => {
        const value = text()
        if (!value) return
        void navigator.clipboard?.writeText(value)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }}
    >
      {copied ? <Check className="text-emerald-500" /> : <Copy />}
    </Button>
  )
}

function CodeBlock({
  children,
  node,
}: {
  children?: ReactNode
  node?: { properties?: Record<string, unknown> }
}) {
  const ref = useRef<HTMLPreElement>(null)
  const child = (Array.isArray(children) ? children[0] : children) as
    | { props?: { className?: string; "data-title"?: string } }
    | undefined
  const className = child?.props?.className ?? ""
  const language = /language-([\w-]+)/.exec(className)?.[1]
  const title =
    child?.props?.["data-title"] ??
    (node?.properties?.["data-title"] as string | undefined)
  const label = title ?? language

  return (
    <div
      data-slot="code-block"
      className="group/code relative my-6 overflow-hidden rounded-lg border bg-muted/40"
    >
      {label ? (
        <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
          <span className="font-mono text-xs text-muted-foreground">{label}</span>
          <CopyButton
            text={() => ref.current?.innerText ?? ""}
            className="opacity-0 transition-opacity group-hover/code:opacity-100 focus-visible:opacity-100"
          />
        </div>
      ) : (
        <CopyButton
          text={() => ref.current?.innerText ?? ""}
          className="absolute top-2 right-2 border border-border bg-background/80 opacity-0 backdrop-blur transition-opacity group-hover/code:opacity-100 focus-visible:opacity-100"
        />
      )}
      <pre ref={ref} className="overflow-x-auto p-4">
        {children}
      </pre>
    </div>
  )
}

function CodeGroup({ children }: { children?: ReactNode }) {
  return (
    <div
      data-slot="code-group"
      className="my-6 overflow-hidden rounded-lg border bg-muted/20 [&>[data-slot=code-block]]:my-0 [&>[data-slot=code-block]]:rounded-none [&>[data-slot=code-block]]:border-0 [&>[data-slot=code-block]]:border-t [&>[data-slot=code-block]]:bg-transparent [&>[data-slot=code-block]:first-child]:border-t-0"
    >
      {children}
    </div>
  )
}

type HeadingProps = {
  node?: { properties?: Record<string, unknown> }
  children?: ReactNode
}

type CalloutTagProps = {
  "data-title"?: string
  children?: ReactNode
}

function Heading({
  as: Tag,
  node,
  children,
}: HeadingProps & { as: "h2" | "h3" | "h4" }) {
  const id = node?.properties?.id as string | undefined
  return (
    <Tag id={id} className="group/heading">
      {children}
      {id ? (
        <a
          href={`#${id}`}
          aria-label="Link to this section"
          className="ml-2 font-normal text-muted-foreground no-underline opacity-0 transition-opacity group-hover/heading:opacity-100"
        >
          #
        </a>
      ) : null}
    </Tag>
  )
}

function Anchor({
  href = "",
  children,
}: {
  href?: string
  children?: ReactNode
}) {
  if (href.startsWith("/")) {
    return <Link to={href}>{children}</Link>
  }
  if (href.startsWith("#")) {
    return <a href={href}>{children}</a>
  }
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  )
}

function calloutTag(variant: string) {
  return function CalloutTag({ "data-title": title, children }: CalloutTagProps) {
    return (
      <Callout variant={variant} title={title}>
        {children}
      </Callout>
    )
  }
}

const components = {
  pre: CodeBlock,
  a: Anchor,
  h2: (props: HeadingProps) => <Heading as="h2" {...props} />,
  h3: (props: HeadingProps) => <Heading as="h3" {...props} />,
  h4: (props: HeadingProps) => <Heading as="h4" {...props} />,
  table: ({ children }: { children?: ReactNode }) => (
    <div className="my-6 overflow-x-auto">
      <table>{children}</table>
    </div>
  ),
  tip: calloutTag("tip"),
  warning: calloutTag("warning"),
  danger: calloutTag("danger"),
  "code-group": ({ children }: { children?: ReactNode }) => <CodeGroup>{children}</CodeGroup>,
} as unknown as Components

export function Markdown({ source }: { source: string }) {
  return (
    <div className="prose-ak">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkDocsContainers, remarkCodeTitles]}
        rehypePlugins={[rehypeSlug, [rehypeHighlight, rehypeHighlightOptions]]}
        components={components}
      >
        {normalizeDocsMarkdown(source)}
      </ReactMarkdown>
    </div>
  )
}
