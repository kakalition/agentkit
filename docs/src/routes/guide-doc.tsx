import { DocsPage } from "@/pages/docs"
import { getPage } from "@/lib/docs"

export function meta({ params }: { params: { slug?: string } }) {
  const page = params.slug ? getPage("guide", params.slug) : undefined
  return [
    { title: page ? `${page.title} · agentkit` : "Guide · agentkit" },
    { name: "description", content: page?.description || "The agentkit guide." },
  ]
}

export default function GuideDoc() {
  return <DocsPage section="guide" />
}
