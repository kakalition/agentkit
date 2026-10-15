import GithubSlugger from "github-slugger"

import {
  getFlatNav,
  navLabel,
  NAV,
  type NavGroup,
  type NavItem,
  type Section,
} from "@/lib/nav"

export type { NavGroup, NavItem, Section }

export type Heading = {
  depth: number
  text: string
  id: string
}

export type DocPage = {
  section: Section
  slug: string
  path: string
  title: string
  description: string
  markdown: string
  headings: Heading[]
}


const guideModules = import.meta.glob("/guide/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const referenceModules = import.meta.glob("/reference/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

const MODULES: Record<Section, Record<string, string>> = {
  guide: guideModules,
  reference: referenceModules,
}


function keyToSlug(key: string): string {
  return key.split("/").pop()!.replace(/\.md$/, "")
}

function stripInline(text: string): string {
  return text
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .trim()
}

function extractTitle(source: string): string {
  for (const line of source.split("\n")) {
    const match = /^#\s+(.+?)\s*$/.exec(line)
    if (match) return stripInline(match[1])
  }
  return ""
}

function stripFirstHeading(source: string): string {
  return source.replace(/^#\s+.+?\s*$(\r?\n)?/, "")
}

function extractHeadings(source: string): Heading[] {
  const slugger = new GithubSlugger()
  const headings: Heading[] = []
  let inFence = false
  for (const line of source.split("\n")) {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const match = /^(#{2,4})\s+(.+?)\s*$/.exec(line)
    if (!match) continue
    const text = stripInline(match[2])
    headings.push({ depth: match[1].length, text, id: slugger.slug(text) })
  }
  return headings
}

function extractDescription(source: string): string {
  const lines = stripFirstHeading(source).split("\n")
  let inFence = false
  for (const raw of lines) {
    const line = raw.trim()
    if (/^```/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence || line === "") continue
    if (/^(#|[-*+]\s|\d+\.\s|>|\||:::)/.test(line)) continue
    return stripInline(line)
  }
  return ""
}

function buildPage(section: Section, key: string, source: string): DocPage {
  const slug = keyToSlug(key)
  const label = navLabel(section, slug)
  return {
    section,
    slug,
    path: `/${section}/${slug}`,
    title: label ?? extractTitle(source) ?? slug,
    description: extractDescription(source),
    markdown: stripFirstHeading(source),
    headings: extractHeadings(stripFirstHeading(source)),
  }
}

const PAGES: DocPage[] = (() => {
  const pages: DocPage[] = []
  for (const section of Object.keys(MODULES) as Section[]) {
    for (const [key, source] of Object.entries(MODULES[section])) {
      pages.push(buildPage(section, key, source))
    }
  }
  return pages
})()

const PAGE_INDEX = new Map(PAGES.map((page) => [page.path, page]))

export function getPage(section: Section, slug: string): DocPage | undefined {
  return PAGE_INDEX.get(`/${section}/${slug}`)
}

export function getPageByPath(path: string): DocPage | undefined {
  return PAGE_INDEX.get(path)
}

export function getSectionPages(section: Section): DocPage[] {
  return PAGES.filter((page) => page.section === section)
}


export function getNeighbours(page: DocPage): {
  prev?: NavItem & { section: Section }
  next?: NavItem & { section: Section }
} {
  const flat = getFlatNav(page.section)
  const index = flat.findIndex((item) => item.slug === page.slug)
  return {
    prev: index > 0 ? { ...flat[index - 1], section: page.section } : undefined,
    next:
      index >= 0 && index < flat.length - 1
        ? { ...flat[index + 1], section: page.section }
        : undefined,
  }
}

export type SearchEntry = {
  path: string
  title: string
  section: Section
  group: string
  headings: string[]
  text: string
}

const SEARCH_INDEX: SearchEntry[] = (() => {
  const groupOf = (section: Section, slug: string): string => {
    for (const group of NAV[section]) {
      if (group.items.some((item) => item.slug === slug)) return group.title
    }
    return ""
  }
  return PAGES.map((page) => ({
    path: page.path,
    title: page.title,
    section: page.section,
    group: groupOf(page.section, page.slug),
    headings: page.headings.map((heading) => heading.text),
    text: page.markdown
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/[#>*_`|]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 4000),
  }))
})()

export function searchDocs(query: string, limit = 12): SearchEntry[] {
  const terms = query
    .toLowerCase()
    .split(/\s+/)
    .filter((term) => term.length > 1)
  if (terms.length === 0) return []
  const scored: { entry: SearchEntry; score: number }[] = []
  for (const entry of SEARCH_INDEX) {
    const haystack = `${entry.title} ${entry.headings.join(" ")} ${entry.text}`.toLowerCase()
    const title = `${entry.title} ${entry.group}`.toLowerCase()
    let score = 0
    let matched = true
    for (const term of terms) {
      const count = haystack.split(term).length - 1
      if (count === 0) {
        matched = false
        break
      }
      score += Math.min(count, 8)
      if (title.includes(term)) score += 12
    }
    if (matched) scored.push({ entry, score })
  }
  return scored
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((item) => item.entry)
}
