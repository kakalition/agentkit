import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { ErrorAlert, Page } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"

export default function Persona() {
  const queryClient = useQueryClient()
  const soul = useQuery({ queryKey: ["soul"], queryFn: api.soul })
  const [text, setText] = useState("")

  useEffect(() => {
    if (soul.data) setText(soul.data.text)
  }, [soul.data])

  const save = useMutation({
    mutationFn: () => api.saveSoul(text),
    onSuccess: () => {
      toast.success("SOUL.md saved")
      void queryClient.invalidateQueries({ queryKey: ["soul"] })
    },
    onError: (error) => toast.error((error as Error).message),
  })

  return (
    <Page
      title="Persona"
      description="The agent's SOUL.md — who it is and how it behaves."
      actions={
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      }
    >
      <ErrorAlert error={soul.error} />
      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm">{soul.data?.path ?? "SOUL.md"}</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="min-h-[28rem] font-mono text-sm"
          />
        </CardContent>
      </Card>
    </Page>
  )
}
