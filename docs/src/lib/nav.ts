export type Section = "guide" | "reference"

export type NavItem = {
  slug: string
  label: string
}

export type NavGroup = {
  title: string
  items: NavItem[]
}

export const NAV: Record<Section, NavGroup[]> = {
  guide: [
    {
      title: "Prologue",
      items: [
        { slug: "introduction", label: "Introduction" },
        { slug: "installation", label: "Installation" },
        { slug: "getting-started", label: "Getting Started" },
        { slug: "philosophy", label: "Philosophy" },
      ],
    },
    {
      title: "The Basics",
      items: [
        { slug: "application", label: "The Application" },
        { slug: "providers", label: "Service Providers" },
        { slug: "drivers", label: "Contracts & Drivers" },
        { slug: "fullstack", label: "The Full Stack" },
        { slug: "agents", label: "The Agent Builder" },
        { slug: "posture", label: "Postures" },
        { slug: "tools", label: "Tools" },
        { slug: "native-tools", label: "Native Tools" },
        { slug: "self-learning", label: "Self-Learning" },
        { slug: "configuration", label: "Configuration" },
        { slug: "facades", label: "Facades" },
        { slug: "helpers", label: "Helpers" },
      ],
    },
    {
      title: "Digging Deeper",
      items: [
        { slug: "events", label: "Events & Lifecycle" },
        { slug: "middleware", label: "Middleware" },
        { slug: "repositories", label: "Models & Repositories" },
        { slug: "database", label: "Database" },
        { slug: "conversations", label: "Conversations" },
        { slug: "search", label: "Search" },
        { slug: "memory", label: "Memory" },
        { slug: "skills", label: "Skills" },
        { slug: "knowledge", label: "Knowledge (RAG)" },
        { slug: "compaction", label: "Context Compaction" },
      ],
    },
    {
      title: "Running Agents",
      items: [
        { slug: "streaming", label: "Streaming" },
        { slug: "hitl", label: "Human-in-the-Loop" },
        { slug: "orchestrator", label: "Orchestrator & Sub-Agents" },
        { slug: "agent-communication", label: "Agent Communication" },
        { slug: "tasks", label: "Tasks & Todos" },
        { slug: "planning", label: "Planning & Graphs" },
        { slug: "teams", label: "Multi-Agent Teams" },
        { slug: "group-chat", label: "Group Chat & Teams" },
        { slug: "studio", label: "Studio (Team Builder)" },
        { slug: "routing", label: "Model Routing & Cost" },
        { slug: "multi-provider", label: "Multiple Model Providers" },
        { slug: "multimodal", label: "Multimodal & Voice" },
      ],
    },
    {
      title: "Extending agentkit",
      items: [
        { slug: "extensions", label: "Extensions" },
        { slug: "specs", label: "Specs & Codegen" },
        { slug: "computer-use", label: "Browser & Computer-Use" },
        { slug: "realtime", label: "Realtime Voice" },
        { slug: "catalog", label: "Catalog & Gallery" },
      ],
    },
    {
      title: "Production",
      items: [
        { slug: "safety", label: "Safety & Moderation" },
        { slug: "authentication", label: "Authentication" },
        { slug: "observability", label: "Observability" },
        { slug: "scheduling", label: "Scheduling & Durability" },
        { slug: "code-execution", label: "Code Execution" },
        { slug: "notifications", label: "Notifications" },
        { slug: "jobs", label: "Jobs & Utilities" },
        { slug: "budgets", label: "Budgets & Limits" },
        { slug: "prompts", label: "Prompt Registry" },
        { slug: "protocols", label: "MCP & A2A" },
        { slug: "surfaces", label: "Surfaces & Channels" },
        { slug: "openai-api", label: "OpenAI-Compatible API" },
        { slug: "webhooks", label: "Webhooks" },
        { slug: "data-lifecycle", label: "Data Lifecycle" },
        { slug: "deployment", label: "Deployment" },
        { slug: "async", label: "Async Data Layer" },
      ],
    },
    {
      title: "Tooling",
      items: [
        { slug: "cli", label: "Artisan-style CLI" },
        { slug: "training", label: "Trajectories & Migration" },
        { slug: "evaluations", label: "Evaluations" },
        { slug: "testing", label: "Testing" },
      ],
    },
  ],
  reference: [
    {
      title: "Reference",
      items: [
        { slug: "configuration", label: "Configuration" },
        { slug: "environment", label: "Environment" },
        { slug: "api", label: "Public API" },
        { slug: "changelog", label: "Changelog" },
      ],
    },
  ],
}

export const SECTION_DEFAULT: Record<Section, string> = {
  guide: "introduction",
  reference: "configuration",
}

export function pagePath(section: Section, slug: string): string {
  return `/${section}/${slug}`
}

export function getFlatNav(section: Section): NavItem[] {
  return NAV[section].flatMap((group) => group.items)
}

export function navLabel(section: Section, slug: string): string | undefined {
  for (const group of NAV[section]) {
    const item = group.items.find((entry) => entry.slug === slug)
    if (item) return item.label
  }
  return undefined
}

/** Every statically prerenderable route: the landing page plus every doc page. */
export const DOC_PATHS: string[] = [
  "/",
  ...(Object.keys(NAV) as Section[]).flatMap((section) =>
    getFlatNav(section).map((item) => pagePath(section, item.slug)),
  ),
]
