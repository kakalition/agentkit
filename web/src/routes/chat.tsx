import { useMutation, useQuery } from "@tanstack/react-query"
import { SendHorizontal } from "lucide-react"
import { useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import type { Message } from "@/lib/api"

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <Card className={isUser ? "bg-primary text-primary-foreground max-w-[80%]" : "max-w-[80%]"}>
        <CardContent className="space-y-2 py-3 text-sm">
          <div className="text-muted-foreground text-xs uppercase">{message.role}</div>
          {message.parts.map((part, index) => {
            if (part.kind === "tool-call") {
              return (
                <Badge key={index} variant="secondary">
                  tool: {part.tool_name}
                </Badge>
              )
            }
            if (part.kind === "tool-return") {
              return (
                <details key={index} className="text-xs">
                  <summary className="cursor-pointer">tool result: {part.tool_name}</summary>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">{part.text}</pre>
                </details>
              )
            }
            if (!part.text) return null
            return (
              <p key={index} className="whitespace-pre-wrap">
                {part.text}
              </p>
            )
          })}
        </CardContent>
      </Card>
    </div>
  )
}

export default function Chat() {
  const [conversationId, setConversationId] = useState("webui:default")
  const [draft, setDraft] = useState("")
  const [ephemeral, setEphemeral] = useState(false)

  const info = useQuery({ queryKey: ["info"], queryFn: api.info })
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.conversations })
  const messages = useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => api.messages(conversationId),
    enabled: conversationId.length > 0 && !ephemeral,
  })

  const send = useMutation({
    mutationFn: () => api.chat(conversationId, draft, ephemeral),
    onSuccess: () => {
      setDraft("")
      if (!ephemeral) void messages.refetch()
    },
  })

  const chatEnabled = info.data?.chat_enabled ?? false
  const compacted = send.data?.usage?.compacted_messages ?? 0

  return (
    <Page
      title="Chat"
      description="Send turns through the agent's own ChatRunner (shared durable history)."
    >
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="max-w-sm"
          value={conversationId}
          onChange={(event) => setConversationId(event.target.value)}
          placeholder="conversation id, e.g. webui:default"
        />
        <select
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value=""
          onChange={(event) => {
            if (event.target.value) setConversationId(event.target.value)
          }}
        >
          <option value="">pick existing…</option>
          {conversations.data?.conversations.map((conversation) => (
            <option key={conversation.id} value={conversation.id}>
              {conversation.id}
            </option>
          ))}
        </select>
        <Button variant="outline" size="sm" onClick={() => void messages.refetch()}>
          Refresh
        </Button>
        <div className="flex items-center gap-2">
          <Switch id="ephemeral" checked={ephemeral} onCheckedChange={setEphemeral} />
          <Label htmlFor="ephemeral" className="text-sm">
            Temporary chat
          </Label>
        </div>
      </div>

      {!chatEnabled && !info.isLoading ? (
        <Alert>
          <AlertTitle>Chat unavailable</AlertTitle>
          <AlertDescription>This agent did not provide an answer callable.</AlertDescription>
        </Alert>
      ) : null}

      {ephemeral ? (
        <Alert>
          <AlertTitle>Temporary chat</AlertTitle>
          <AlertDescription>
            Messages are not saved to conversation history and are not shown here.
          </AlertDescription>
        </Alert>
      ) : null}

      <ErrorAlert error={messages.error ?? send.error} />

      <Card>
        <CardContent className="p-4">
          <ScrollArea className="h-[26rem] pr-4">
            <div className="flex flex-col gap-3">
              {ephemeral ? (
                <p className="text-muted-foreground text-sm">
                  Temporary chat: history is disabled. Send a message to get a one-off reply.
                </p>
              ) : messages.data?.messages.length ? (
                messages.data.messages.map((message, index) => (
                  <MessageBubble key={index} message={message} />
                ))
              ) : (
                <p className="text-muted-foreground text-sm">No messages yet.</p>
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (draft.trim() && chatEnabled) send.mutate()
        }}
      >
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask the agent…"
          disabled={!chatEnabled}
          rows={2}
        />
        <Button type="submit" disabled={!chatEnabled || send.isPending || !draft.trim()}>
          <SendHorizontal />
          {send.isPending ? "Sending…" : "Send"}
        </Button>
      </form>

      {send.data ? (
        <p className="text-muted-foreground text-xs">
          {send.data.history_length} messages in history
          {send.data.usage ? ` · ${send.data.usage.total_tokens ?? 0} tokens` : ""}
          {compacted > 0 ? ` · context compacted (${compacted})` : ""}
        </p>
      ) : null}
    </Page>
  )
}
