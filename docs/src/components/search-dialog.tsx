import { FileText } from "lucide-react"
import { useMemo, useState } from "react"
import { useNavigate } from "react-router"

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { searchDocs, type SearchEntry } from "@/lib/docs"

export function SearchDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState("")

  const groups = useMemo(() => {
    const entries = searchDocs(query)
    const grouped = new Map<string, SearchEntry[]>()
    for (const entry of entries) {
      const key = entry.section === "reference" ? "Reference" : entry.group || "Guide"
      const list = grouped.get(key) ?? []
      list.push(entry)
      grouped.set(key, list)
    }
    return [...grouped.entries()]
  }, [query])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[12%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl">
        <DialogTitle className="sr-only">Search documentation</DialogTitle>
        <Command shouldFilter={false} className="rounded-none! p-1">
          <CommandInput
            placeholder="Search documentation…"
            value={query}
            onValueChange={setQuery}
          />
          <CommandList className="max-h-[60vh]">
            <CommandEmpty>
              {query.trim().length < 2
                ? "Type to search the documentation."
                : "No results found."}
            </CommandEmpty>
            {groups.map(([group, entries]) => (
              <CommandGroup key={group} heading={group}>
                {entries.map((entry) => (
                  <CommandItem
                    key={entry.path}
                    value={`${entry.title} ${entry.path}`}
                    onSelect={() => {
                      navigate(entry.path)
                      onOpenChange(false)
                      setQuery("")
                    }}
                  >
                    <FileText className="text-muted-foreground" />
                    <span className="truncate">{entry.title}</span>
                    <span className="ml-auto truncate font-mono text-xs text-muted-foreground">
                      {entry.path}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
