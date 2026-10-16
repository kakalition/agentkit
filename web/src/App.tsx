import { useQuery } from "@tanstack/react-query"
import {
  BarChart3,
  Blocks,
  CalendarClock,
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
import { Route, Routes, useLocation } from "react-router-dom"

import { AppSidebar, type NavItem } from "@/components/app-sidebar"
import { ThemeToggle } from "@/components/theme-toggle"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { api } from "@/lib/api"
import A2A from "@/routes/a2a"
import Artifacts from "@/routes/artifacts"
import Audit from "@/routes/audit"
import Chat from "@/routes/chat"
import Config from "@/routes/config"
import Conversations from "@/routes/conversations"
import Lessons from "@/routes/lessons"
import Overview from "@/routes/overview"
import Persona from "@/routes/persona"
import Scheduler from "@/routes/scheduler"
import Search from "@/routes/search"
import Studio from "@/routes/studio"
import Teams from "@/routes/teams"
import Usage from "@/routes/usage"
import Workflows from "@/routes/workflows"

const baseItems: NavItem[] = [
  { title: "Overview", url: "/", icon: LayoutDashboard },
  { title: "Conversations", url: "/conversations", icon: Inbox },
  { title: "Search", url: "/search", icon: SearchIcon },
  { title: "Lessons", url: "/lessons", icon: GraduationCap },
  { title: "Scheduler", url: "/scheduler", icon: CalendarClock },
  { title: "Workflows", url: "/workflows", icon: Workflow },
  { title: "Studio", url: "/studio", icon: Blocks },
  { title: "Teams", url: "/teams", icon: Users },
  { title: "Usage", url: "/usage", icon: BarChart3 },
  { title: "Audit", url: "/audit", icon: ShieldCheck },
  { title: "A2A", url: "/a2a", icon: Network },
  { title: "Persona", url: "/persona", icon: UserCog },
  { title: "Config", url: "/config", icon: Settings },
  { title: "Artifacts", url: "/artifacts", icon: FolderOpen },
]

export default function App() {
  const info = useQuery({ queryKey: ["info"], queryFn: api.info })
  const location = useLocation()

  const chatItem: NavItem = { title: "Chat", url: "/chat", icon: MessageCircle }
  const items: NavItem[] =
    info.data?.chat_enabled === false
      ? baseItems
      : [baseItems[0], chatItem, ...baseItems.slice(1)]

  const title =
    items.find((item) => item.url === location.pathname)?.title ??
    items.find((item) => item.url !== "/" && location.pathname.startsWith(item.url))?.title ??
    "Overview"

  return (
    <SidebarProvider>
      <AppSidebar items={items} subtitle={info.data?.name} />
      <SidebarInset>
        <header className="flex h-14 items-center gap-2 border-b px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="mr-1 h-4" />
          <span className="text-sm font-medium">{title}</span>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>
        <div className="mx-auto w-full max-w-6xl p-6">
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
            <Route path="/persona" element={<Persona />} />
            <Route path="/config" element={<Config />} />
            <Route path="/artifacts" element={<Artifacts />} />
          </Routes>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
