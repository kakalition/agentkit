import { useQuery } from "@tanstack/react-query"
import {
  Activity,
  BarChart3,
  Blocks,
  CalendarClock,
  Database,
  FolderOpen,
  GraduationCap,
  Inbox,
  LayoutDashboard,
  MessageCircle,
  Network,
  Search as SearchIcon,
  Settings,
  ShieldCheck,
  Users,
  UserCog,
  Workflow,
} from "lucide-react"
import { useEffect, useState } from "react"
import { Link, Route, Routes, useLocation } from "react-router-dom"

import { AppSidebar, type NavGroup, type NavItem } from "@/components/app-sidebar"
import { CommandMenu } from "@/components/command-menu"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { api } from "@/lib/api"
import A2A from "@/routes/a2a"
import Artifacts from "@/routes/artifacts"
import Audit from "@/routes/audit"
import Chat from "@/routes/chat"
import Config from "@/routes/config"
import Conversations from "@/routes/conversations"
import Data from "@/routes/data"
import Events from "@/routes/events"
import Lessons from "@/routes/lessons"
import Overview from "@/routes/overview"
import Persona from "@/routes/persona"
import Scheduler from "@/routes/scheduler"
import Search from "@/routes/search"
import Studio from "@/routes/studio"
import Teams from "@/routes/teams"
import Usage from "@/routes/usage"
import Workflows from "@/routes/workflows"

const overviewItem: NavItem = { title: "Overview", url: "/", icon: LayoutDashboard }
const chatItem: NavItem = { title: "Chat", url: "/chat", icon: MessageCircle }

const baseGroups: NavGroup[] = [
  { label: "Overview", items: [overviewItem] },
  {
    label: "Chat & History",
    items: [
      { title: "Conversations", url: "/conversations", icon: Inbox },
      { title: "Search", url: "/search", icon: SearchIcon },
    ],
  },
  {
    label: "Automation",
    items: [
      { title: "Scheduler", url: "/scheduler", icon: CalendarClock },
      { title: "Workflows", url: "/workflows", icon: Workflow },
      { title: "Events", url: "/events", icon: Activity },
    ],
  },
  {
    label: "Build",
    items: [
      { title: "Studio", url: "/studio", icon: Blocks },
      { title: "Teams", url: "/teams", icon: Users },
      { title: "Data", url: "/data", icon: Database },
      { title: "Persona", url: "/persona", icon: UserCog },
      { title: "Config", url: "/config", icon: Settings },
      { title: "Artifacts", url: "/artifacts", icon: FolderOpen },
    ],
  },
  {
    label: "Insights",
    items: [
      { title: "Usage", url: "/usage", icon: BarChart3 },
      { title: "Audit", url: "/audit", icon: ShieldCheck },
      { title: "Lessons", url: "/lessons", icon: GraduationCap },
      { title: "A2A", url: "/a2a", icon: Network },
    ],
  },
]

function findCurrent(groups: NavGroup[], pathname: string, fallback: NavItem) {
  for (const group of groups) {
    const item = group.items.find((entry) => entry.url === pathname)
    if (item) return { item, group }
  }
  for (const group of groups) {
    const item = group.items.find((entry) => entry.url !== "/" && pathname.startsWith(entry.url))
    if (item) return { item, group }
  }
  return { item: fallback, group: groups[0] }
}

export default function App() {
  const info = useQuery({ queryKey: ["info"], queryFn: api.info })
  const location = useLocation()
  const [commandOpen, setCommandOpen] = useState(false)

  const groups: NavGroup[] =
    info.data?.chat_enabled === false
      ? baseGroups
      : baseGroups.map((group) =>
          group.label === "Chat & History"
            ? { ...group, items: [chatItem, ...group.items] }
            : group,
        )

  const { item, group } = findCurrent(groups, location.pathname, overviewItem)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setCommandOpen((open) => !open)
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [])

  return (
    <SidebarProvider>
      <AppSidebar groups={groups} subtitle={info.data?.name} />
      <SidebarInset>
        <header className="flex h-14 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 h-4" />
          <Breadcrumb className="min-w-0 flex-1">
            <BreadcrumbList className="flex-nowrap">
              <BreadcrumbItem className="hidden sm:inline-flex">
                <BreadcrumbLink asChild>
                  <Link to="/">agentkit</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator className="hidden sm:block" />
              <BreadcrumbItem className="hidden md:inline-flex">
                <span>{group.label}</span>
              </BreadcrumbItem>
              <BreadcrumbSeparator className="hidden md:block" />
              <BreadcrumbItem className="min-w-0">
                <BreadcrumbPage className="truncate">{item.title}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <div className="ml-auto flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="text-muted-foreground hidden sm:inline-flex"
              onClick={() => setCommandOpen(true)}
            >
              <SearchIcon />
              <span>Search</span>
              <kbd className="bg-muted ml-1 rounded border px-1 py-0.5 font-mono text-[10px]">
                ⌘K
              </kbd>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="sm:hidden"
              aria-label="Search"
              onClick={() => setCommandOpen(true)}
            >
              <SearchIcon />
            </Button>
            <ThemeToggle />
          </div>
        </header>
        <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-6">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/conversations" element={<Conversations />} />
            <Route path="/search" element={<Search />} />
            <Route path="/lessons" element={<Lessons />} />
            <Route path="/scheduler" element={<Scheduler />} />
            <Route path="/workflows" element={<Workflows />} />
            <Route path="/studio" element={<Studio />} />
            <Route path="/teams" element={<Teams />} />
            <Route path="/usage" element={<Usage />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/a2a" element={<A2A />} />
            <Route path="/events" element={<Events />} />
            <Route path="/data" element={<Data />} />
            <Route path="/persona" element={<Persona />} />
            <Route path="/config" element={<Config />} />
            <Route path="/artifacts" element={<Artifacts />} />
          </Routes>
        </div>
      </SidebarInset>
      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} groups={groups} />
    </SidebarProvider>
  )
}
