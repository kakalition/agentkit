import { useMutation, useQuery } from "@tanstack/react-query"
import { SendHorizontal, Square } from "lucide-react"
import { useRef, useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
                <Collapsible key={index} className="text-xs">
                  <CollapsibleTrigger className="cursor-pointer hover:underline">
                    tool result: {part.tool_name}
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap">{part.text}</pre>
                  </CollapsibleContent>
                </Collapsible>
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
  const [streaming, setStreaming] = useState(true)
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState("")
  const [liveNote, setLiveNote] = useState<string | null>(null)
  const [streamError, setStreamError] = useState<Error | null>(null)
  const [liveUsage, setLiveUsage] = useState<{ history_length: number; total_tokens: number } | null>(
    null,
  )
  const abortRef = useRef<AbortController | null>(null)

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

  const sendStreaming = async () => {
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(true)
    setStreamError(null)
    setLive("")
    setLiveNote(null)
    setLiveUsage(null)
    const text = draft
    setDraft("")
    try {
      await api.chatStream(
        conversationId,
        text,
        {
          onText: (chunk) => setLive((current) => current + chunk),
          onCompaction: (note) => setLiveNote(note),
          onFinal: (final) => {
            setLive((current) => current || final.output)
            setLiveUsage({
              history_length: final.history_length,
              total_tokens: final.usage?.total_tokens ?? 0,
            })
          },
        },
        { ephemeral, signal: controller.signal },
      )
      if (!ephemeral) void messages.refetch()
    } catch (error) {
      if (!controller.signal.aborted) setStreamError(error as Error)
    } finally {
      setBusy(false)
      abortRef.current = null
    }
  }

  const cancelStream = () => {
    abortRef.current?.abort()
    setBusy(false)
  }

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
        <Select value="" onValueChange={(value) => value && setConversationId(value)}>
          <SelectTrigger className="w-[12rem]">
            <SelectValue placeholder="pick existing…" />
          </SelectTrigger>
          <SelectContent>
            {conversations.data?.conversations.map((conversation) => (
              <SelectItem key={conversation.id} value={conversation.id}>
                {conversation.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={() => void messages.refetch()}>
          Refresh
        </Button>
        <div className="flex items-center gap-2">
          <Switch id="ephemeral" checked={ephemeral} onCheckedChange={setEphemeral} />
          <Label htmlFor="ephemeral" className="text-sm">
            Temporary chat
          </Label>
        </div>
        <div className="flex items-center gap-2">
          <Switch id="streaming" checked={streaming} onCheckedChange={setStreaming} />
          <Label htmlFor="streaming" className="text-sm">
            Stream tokens
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

      <ErrorAlert error={messages.error ?? send.error ?? streamError} />

      <Card>
        <CardContent className="p-4">
          <ScrollArea className="h-[calc(100svh-22rem)] min-h-[16rem] pr-4">
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
              {liveNote ? (
                <p className="text-muted-foreground text-xs italic">{liveNote}</p>
              ) : null}
              {live ? (
                <div className="flex justify-start">
                  <Card className="max-w-[80%]">
                    <CardContent className="space-y-1 py-3 text-sm">
                      <div className="text-muted-foreground text-xs uppercase">assistant</div>
                      <p className="whitespace-pre-wrap">{live}</p>
                      {busy ? <span className="text-muted-foreground text-xs">▍</span> : null}
                    </CardContent>
                  </Card>
                </div>
              ) : null}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (!draft.trim() || !chatEnabled || busy) return
          if (streaming) void sendStreaming()
          else send.mutate()
        }}
      >
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask the agent…"
          disabled={!chatEnabled}
          rows={2}
        />
        {busy ? (
          <Button type="button" variant="outline" onClick={cancelStream}>
            <Square /> Cancel
          </Button>
        ) : (
          <Button type="submit" disabled={!chatEnabled || send.isPending || !draft.trim()}>
            <SendHorizontal />
            {send.isPending ? "Sending…" : "Send"}
          </Button>
        )}
      </form>

      {send.data ? (
        <p className="text-muted-foreground text-xs">
          {send.data.history_length} messages in history
          {send.data.usage ? ` · ${send.data.usage.total_tokens ?? 0} tokens` : ""}
          {compacted > 0 ? ` · context compacted (${compacted})` : ""}
        </p>
      ) : null}
      {liveUsage ? (
        <p className="text-muted-foreground text-xs">
          {liveUsage.history_length} messages in history · {liveUsage.total_tokens} tokens
        </p>
      ) : null}
    </Page>
  )
}
