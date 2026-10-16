import { useMutation, useQuery } from "@tanstack/react-query"
import { Download, Search } from "lucide-react"
import { useState } from "react"

import { ErrorAlert } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"

/** The rich catalog panel: browse sources and install specs/skills. */
export function CatalogBrowser() {
  const [query, setQuery] = useState("")
  const items = useQuery({
    queryKey: ["studio", "catalog", query],
    queryFn: () => api.studioCatalog(query),
  })
  const install = useMutation({
    mutationFn: (id: string) => api.installCatalogItem(id, "definitions"),
  })
  const error = items.error ?? install.error
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          Catalog{items.data?.driver ? ` · ${items.data.driver}` : ""}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorAlert error={error} />
        <div className="flex items-center gap-2">
          <Search className="text-muted-foreground size-4" />
          <Input
            value={query}
            placeholder="Search the catalog…"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        {items.data?.items.length ? (
          items.data.items.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-md border p-2 text-sm"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span>{item.name}</span>
                  <Badge variant="secondary" className="text-[10px]">
                    {item.kind}
                  </Badge>
                </div>
                {item.description ? (
                  <p className="text-muted-foreground truncate text-xs">{item.description}</p>
                ) : null}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => install.mutate(item.id)}
                disabled={install.isPending}
              >
                <Download className="size-4" /> Install
              </Button>
            </div>
          ))
        ) : (
          <p className="text-muted-foreground text-sm">
            {items.isLoading ? "Loading…" : "No catalog items found."}
          </p>
        )}
        {install.data ? (
          <p className="text-muted-foreground text-xs">{JSON.stringify(install.data)}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}
