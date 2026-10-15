import { DocsPage } from "@/pages/docs"
import { getPage } from "@/lib/docs"

export function meta({ params }: { params: { slug?: string } }) {
  const page = params.slug ? getPage("reference", params.slug) : undefined
  return [
    { title: page ? `${page.title} · agentkit` : "Reference · agentkit" },
    { name: "description", content: page?.description || "The agentkit reference." },
  ]
}

export default function ReferenceDoc() {
  return <DocsPage section="reference" />
}
