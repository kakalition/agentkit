import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"

export default function Search() {
  const [term, setTerm] = useState("")
  const [submitted, setSubmitted] = useState("")

  const hits = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => api.search(submitted),
    enabled: submitted.length > 0,
  })

  return (
    <Page title="Search" description="Indexed search across every past conversation.">
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          setSubmitted(term.trim())
        }}
      >
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Search messages…"
        />
        <Button type="submit" disabled={!term.trim()}>
          Search
        </Button>
      </form>
      <ErrorAlert error={hits.error} />
      <div className="space-y-2">
        {hits.data?.hits.map((hit, index) => (
          <div key={`${hit.conversation_id}-${index}`} className="rounded-lg border p-3">
            <div className="text-muted-foreground text-xs">{hit.conversation_id}</div>
            <div className="text-sm whitespace-pre-wrap">{hit.text}</div>
          </div>
        ))}
        {submitted && hits.data?.hits.length === 0 ? (
          <p className="text-muted-foreground text-sm">No matches.</p>
        ) : null}
      </div>
    </Page>
  )
}
