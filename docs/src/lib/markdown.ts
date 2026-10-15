type MdastNode = {
  type: string
  value?: string
  meta?: string | null
  children?: MdastNode[]
  data?: {
    hName?: string
    hProperties?: Record<string, unknown>
    [key: string]: unknown
  }
  [key: string]: unknown
}

const CONTAINER_OPEN = /^:::[ \t]*([a-zA-Z][\w-]*)(?:[ \t]+([\s\S]*?))?[ \t]*$/
const CONTAINER_CLOSE = /^:::[ \t]*$/

/**
 * VitePress lets container markers sit flush against their content
 * (`::: tip Title` on the line directly above prose). Blank-line them out so the
 * markdown parser treats each marker as its own paragraph before we group them.
 */
export function normalizeDocsMarkdown(source: string): string {
  const lines = source.split("\n")
  const out: string[] = []
  let inFence = false

  const blank = () => {
    if (out.length > 0 && out[out.length - 1].trim() !== "") out.push("")
  }

  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence
    if (!inFence) {
      if (CONTAINER_OPEN.test(line)) {
        blank()
        out.push(line, "")
        continue
      }
      if (CONTAINER_CLOSE.test(line)) {
        blank()
        out.push(line, "")
        continue
      }
    }
    out.push(line)
  }

  return out.join("\n")
}

function paragraphText(node: MdastNode): string {
  if (!node.children) return ""
  return node.children
    .map((child) => {
      if (child.type === "text") return child.value ?? ""
      if (child.type === "inlineCode") return `\`${child.value ?? ""}\``
      return ""
    })
    .join("")
}

/**
 * Rewrite `::: tip Title ... :::` blocks into nodes with a custom `hName`, so
 * react-markdown can map them to shadcn components at render time.
 */
export function remarkDocsContainers() {
  return (tree: MdastNode) => {
    const children = tree.children ?? []
    const result: MdastNode[] = []
    let index = 0

    while (index < children.length) {
      const node = children[index]
      const text = node.type === "paragraph" ? paragraphText(node).trim() : ""
      const match = text ? CONTAINER_OPEN.exec(text) : null

      if (!match) {
        result.push(node)
        index += 1
        continue
      }

      const name = match[1].toLowerCase()
      const title = (match[2] ?? "").replace(/`/g, "").trim()
      const inner: MdastNode[] = []
      index += 1

      while (index < children.length) {
        const current = children[index]
        const currentText =
          current.type === "paragraph" ? paragraphText(current).trim() : ""
        if (CONTAINER_CLOSE.test(currentText)) {
          index += 1
          break
        }
        inner.push(current)
        index += 1
      }

      result.push({
        type: "docsContainer",
        data: {
          hName: name,
          hProperties: title ? { "data-title": title } : {},
        },
        children: inner,
      })
    }

    tree.children = result
  }
}

function walkCodeTitles(node: MdastNode) {
  if (node.type === "code" && typeof node.meta === "string") {
    const title = /\[([^\]]+)\]/.exec(node.meta)
    if (title) {
      node.data = node.data ?? {}
      node.data.hProperties = {
        ...(node.data.hProperties ?? {}),
        "data-title": title[1].trim(),
      }
    }
  }
  for (const child of node.children ?? []) walkCodeTitles(child)
}

/** Lift ```` ```bash [uv] ```` fence titles onto the rendered `<code data-title>`. */
export function remarkCodeTitles() {
  return (tree: MdastNode) => {
    walkCodeTitles(tree)
  }
}
