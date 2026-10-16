import { useQueryClient } from "@tanstack/react-query"
import { Moon, RefreshCw, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { useNavigate } from "react-router-dom"

import type { NavGroup } from "@/components/app-sidebar"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"

/** ⌘K palette: jump to any route, toggle the theme, or refresh status. */
export function CommandMenu({
  open,
  onOpenChange,
  groups,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  groups: NavGroup[]
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { resolvedTheme, setTheme } = useTheme()

  const run = (action: () => void) => {
    action()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="top-[12%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">Command menu</DialogTitle>
        <Command className="rounded-none! p-1">
          <CommandInput placeholder="Search pages and actions…" />
          <CommandList className="max-h-[60vh]">
            <CommandEmpty>No results found.</CommandEmpty>
            {groups.map((group) => (
              <CommandGroup key={group.label} heading={group.label}>
                {group.items.map((item) => (
                  <CommandItem
                    key={item.url}
                    value={`${item.title} ${item.url}`}
                    onSelect={() => run(() => navigate(item.url))}
                  >
                    <item.icon />
                    <span className="truncate">{item.title}</span>
                    <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                      {item.url}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
            <CommandSeparator />
            <CommandGroup heading="Actions">
              <CommandItem
                value="toggle theme light dark appearance"
                onSelect={() =>
                  run(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"))
                }
              >
                {resolvedTheme === "dark" ? <Sun /> : <Moon />}
                <span>Toggle theme</span>
              </CommandItem>
              <CommandItem
                value="refresh status info health"
                onSelect={() =>
                  run(() => {
                    void queryClient.invalidateQueries({ queryKey: ["info"] })
                    void queryClient.invalidateQueries({ queryKey: ["health"] })
                  })
                }
              >
                <RefreshCw />
                <span>Refresh status</span>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
