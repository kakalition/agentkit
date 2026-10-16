import {
  BarChart3,
  Bot,
  Blocks,
  Database,
  Inbox,
  LayoutDashboard,
  MessageCircle,
  Search,
  SendHorizontal,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react"

import { cn } from "@/lib/utils"

const RAIL = [
  { icon: LayoutDashboard, label: "Overview" },
  { icon: MessageCircle, label: "Chat" },
  { icon: Inbox, label: "Conversations" },
  { icon: Search, label: "Search" },
  { icon: Blocks, label: "Studio" },
  { icon: Users, label: "Teams" },
  { icon: BarChart3, label: "Usage" },
  { icon: ShieldCheck, label: "Audit" },
  { icon: Database, label: "Data" },
  { icon: Settings, label: "Config" },
]

const STATS = [
  { label: "Conversations", value: "12" },
  { label: "Schedules on", value: "3" },
  { label: "Tokens", value: "8.4k" },
]

/**
 * A static, image-free mock of the operator console. Pure markup so it renders
 * identically on the server and client (no window/Date/random).
 */
export function ConsoleMock() {
  return (
    <div className="overflow-hidden rounded-xl border bg-card text-left shadow-sm">
      <div className="flex items-center gap-1.5 border-b bg-muted/40 px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-red-400/70" />
        <span className="size-2.5 rounded-full bg-amber-400/70" />
        <span className="size-2.5 rounded-full bg-emerald-400/70" />
        <span className="ml-2 truncate font-mono text-xs text-muted-foreground">
          agentkit — operator console
        </span>
        <span className="ml-auto hidden items-center gap-1 rounded-md border bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:flex">
          <Search className="size-3" /> ⌘K
        </span>
      </div>

      <div className="grid grid-cols-[3.25rem_1fr] sm:grid-cols-[8.5rem_1fr]">
        <aside className="border-r bg-muted/30 p-2">
          <div className="mb-3 flex items-center gap-2 px-1">
            <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Bot className="size-3.5" />
            </div>
            <span className="hidden truncate text-xs font-medium sm:block">nudge</span>
          </div>
          <div className="space-y-0.5">
            {RAIL.map((item, index) => (
              <div
                key={item.label}
                className={cn(
                  "flex items-center gap-2 rounded-md px-1.5 py-1.5 text-xs",
                  index === 1
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground",
                )}
              >
                <item.icon className="size-3.5 shrink-0" />
                <span className="hidden truncate sm:block">{item.label}</span>
              </div>
            ))}
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-2 border-b px-3 py-2">
            <span className="text-xs font-medium">Chat</span>
            <span className="ml-auto inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] text-muted-foreground">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              streaming
            </span>
          </div>

          <div className="flex flex-col gap-2.5 p-3">
            <div className="ml-auto max-w-[80%] rounded-lg bg-primary px-2.5 py-1.5 text-[11px] text-primary-foreground">
              remind me to stretch at 5pm
            </div>
            <div className="max-w-[85%] space-y-1 rounded-lg border bg-background px-2.5 py-1.5">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                assistant
              </div>
              <div className="text-[11px] text-foreground">
                Scheduled. I&apos;ll nudge you at 5:00 PM.
              </div>
              <div className="inline-flex items-center gap-1 rounded-md border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                <ShieldCheck className="size-3" /> schedule.create
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 border-t px-3 py-2">
            <div className="flex-1 rounded-md border bg-background px-2 py-1.5 text-[11px] text-muted-foreground">
              Ask the agent…
            </div>
            <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <SendHorizontal className="size-3.5" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 border-t bg-muted/20 p-3">
            {STATS.map((stat) => (
              <div key={stat.label} className="rounded-lg border bg-background px-2 py-1.5">
                <div className="text-sm font-semibold tracking-tight">{stat.value}</div>
                <div className="truncate text-[10px] text-muted-foreground">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
