import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

export default function Conversations() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string | null>(null)

  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.conversations })
  const messages = useQuery({
    queryKey: ["messages", selected],
    queryFn: () => api.messages(selected as string),
    enabled: selected !== null,
  })
  const clear = useMutation({
    mutationFn: (id: string) => api.clearMessages(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["messages", selected] })
      void queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  return (
    <Page title="Conversations" description="Durable conversation history.">
      <ErrorAlert error={conversations.error} />
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Id</TableHead>
              <TableHead>Channel</TableHead>
              <TableHead>Messages</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {conversations.data?.conversations.map((conversation) => (
              <TableRow
                key={conversation.id}
                className="cursor-pointer"
                onClick={() => setSelected(conversation.id)}
              >
                <TableCell className="font-medium">{conversation.id}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{conversation.channel}</Badge>
                </TableCell>
                <TableCell>{conversation.message_count ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {conversation.updated_at}
                </TableCell>
              </TableRow>
            ))}
            {conversations.data?.conversations.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground text-center">
                  No conversations yet.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="flex w-full flex-col sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{selected}</SheetTitle>
            <SheetDescription>{messages.data?.messages.length ?? 0} stored messages</SheetDescription>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="w-fit">
                  Clear messages
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear this conversation?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently deletes the stored messages for {selected}.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => selected && clear.mutate(selected)}
                  >
                    Clear
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </SheetHeader>
          <ScrollArea className="mt-4 flex-1 pr-2">
            <div className="flex flex-col gap-3">
              {messages.data?.messages.map((message, index) => (
                <div key={index} className="rounded-md border p-3 text-sm">
                  <div className="text-muted-foreground mb-1 text-xs uppercase">{message.role}</div>
                  {message.parts.map((part, partIndex) => (
                    <p key={partIndex} className="whitespace-pre-wrap">
                      {part.kind === "tool-call" ? `⚙ ${part.tool_name}` : part.text}
                    </p>
                  ))}
                </div>
              ))}
            </div>
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </Page>
  )
}
