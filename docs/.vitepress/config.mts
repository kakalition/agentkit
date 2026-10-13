import { defineConfig } from "vitepress";
import tailwindcss from "@tailwindcss/vite";

const base = "/";

export default defineConfig({
  title: "agentkit",
  description:
    "A batteries-included framework for building, running, and shipping durable AI agents in Python.",
  base,
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,
  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: `${base}favicon.svg` }],
    ["meta", { name: "theme-color", content: "#0b0b12" }],
    ["meta", { property: "og:type", content: "website" }],
    ["meta", { property: "og:title", content: "agentkit documentation" }],
    [
      "meta",
      { property: "og:description", content: "Build, run, and ship durable AI agents." },
    ],
  ],

  markdown: {
    lineNumbers: true,
    theme: { light: "github-light", dark: "github-dark" },
    anchor: { level: [2, 3, 4] },
  },

  vite: {
    plugins: [tailwindcss()],
  },

  themeConfig: {
    logo: { light: "/logo.svg", dark: "/logo.svg" },
    siteTitle: "agentkit",

    nav: [
      { text: "Guide", link: "/guide/getting-started", activeMatch: "/guide/" },
      { text: "Reference", link: "/reference/configuration", activeMatch: "/reference/" },
      { text: "Concepts", link: "/guide/philosophy" },
      {
        text: "v0.1.0",
        items: [
          { text: "Changelog", link: "/reference/changelog" },
          { text: "GitHub", link: "https://github.com/kakalition/agentkit" },
        ],
      },
    ],

    sidebar: {
      "/guide/": [
        {
          text: "Prologue",
          items: [
            { text: "Introduction", link: "/guide/introduction" },
            { text: "Installation", link: "/guide/installation" },
            { text: "Getting Started", link: "/guide/getting-started" },
            { text: "Philosophy", link: "/guide/philosophy" },
          ],
        },
        {
          text: "The Basics",
          items: [
            { text: "The Application", link: "/guide/application" },
            { text: "Service Providers", link: "/guide/providers" },
            { text: "The Agent Builder", link: "/guide/agents" },
            { text: "Tools", link: "/guide/tools" },
            { text: "Configuration", link: "/guide/configuration" },
            { text: "Facades", link: "/guide/facades" },
            { text: "Helpers", link: "/guide/helpers" },
          ],
        },
        {
          text: "Digging Deeper",
          items: [
            { text: "Events & Lifecycle", link: "/guide/events" },
            { text: "Middleware", link: "/guide/middleware" },
            { text: "Models & Repositories", link: "/guide/repositories" },
            { text: "Database", link: "/guide/database" },
            { text: "Conversations", link: "/guide/conversations" },
            { text: "Memory", link: "/guide/memory" },
            { text: "Skills", link: "/guide/skills" },
            { text: "Knowledge (RAG)", link: "/guide/knowledge" },
            { text: "Context Compaction", link: "/guide/compaction" },
          ],
        },
        {
          text: "Running Agents",
          items: [
            { text: "Streaming", link: "/guide/streaming" },
            { text: "Human-in-the-Loop", link: "/guide/hitl" },
            { text: "Orchestrator & Sub-Agents", link: "/guide/orchestrator" },
            { text: "Planning & Graphs", link: "/guide/planning" },
            { text: "Multi-Agent Teams", link: "/guide/teams" },
            { text: "Model Routing & Cost", link: "/guide/routing" },
            { text: "Multimodal & Voice", link: "/guide/multimodal" },
          ],
        },
        {
          text: "Production",
          items: [
            { text: "Safety & Moderation", link: "/guide/safety" },
            { text: "Observability", link: "/guide/observability" },
            { text: "Scheduling & Durability", link: "/guide/scheduling" },
            { text: "Notifications", link: "/guide/notifications" },
            { text: "Jobs & Utilities", link: "/guide/jobs" },
            { text: "Budgets & Limits", link: "/guide/budgets" },
            { text: "Prompt Registry", link: "/guide/prompts" },
            { text: "MCP & A2A", link: "/guide/protocols" },
            { text: "Deployment", link: "/guide/deployment" },
          ],
        },
        {
          text: "Tooling",
          items: [
            { text: "Artisan-style CLI", link: "/guide/cli" },
            { text: "Evaluations", link: "/guide/evaluations" },
            { text: "Testing", link: "/guide/testing" },
          ],
        },
      ],
      "/reference/": [
        {
          text: "Reference",
          items: [
            { text: "Configuration", link: "/reference/configuration" },
            { text: "Environment", link: "/reference/environment" },
            { text: "Public API", link: "/reference/api" },
            { text: "Changelog", link: "/reference/changelog" },
          ],
        },
      ],
    },

    search: {
      provider: "local",
      options: {
        detailedView: true,
      },
    },

    socialLinks: [{ icon: "github", link: "https://github.com/kakalition/agentkit" }],

    editLink: {
      pattern: "https://github.com/kakalition/agentkit/edit/main/docs/:path",
      text: "Edit this page",
    },

    outline: { level: [2, 3], label: "On this page" },

    docFooter: { prev: "Previous", next: "Next" },

    footer: {
      message: "Released under the MIT License.",
      copyright: "agentkit — build, run, and ship durable AI agents.",
    },

    lastUpdated: {
      text: "Last updated",
      formatOptions: { dateStyle: "medium", timeStyle: "short" },
    },
  },
});
