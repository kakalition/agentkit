const BASE = "/api"

export interface Info {
  name: string
  version: string
  owner_id: string
  workspace_root: string
  home: string
  db_path: string
  database_url: string | null
  model_name: string
  webui: { enabled: boolean; host: string; port: number; url: string }
  chat_enabled: boolean
  channels: {
    telegram: boolean
    a2a: { host: string; port: number }
    mcp: { host: string; port: number }
  }
}

export interface Health {
  ok: boolean
  checks: Record<string, boolean>
}

export interface Conversation {
  id: string
  channel: string
  created_at: string
  updated_at: string
  message_count: number | null
}

export interface SearchHit {
  conversation_id: string
  text: string
}

export interface MessagePart {
  kind: string
  text?: string
  tool_name?: string
  args?: unknown
}

export interface Message {
  role: string
  kind: string
  parts: MessagePart[]
}

export interface ChatReply {
  conversation_id: string
  output: string
  artifacts: { kind: string; path: string }[]
  usage: Record<string, number> | null
  history_length: number
}

export interface Job {
  name: string
  kind: string
  schedule: string
  task: string
  args: Record<string, unknown>
  enabled: boolean
  last_run: string | null
  run_count: number
}

export interface Workflow {
  id: string
  name: string | null
  status: string | null
  queue: string | null
  created_at: number | null
  updated_at: number | null
  completed_at: number | null
  error: string | null
  input?: unknown
  output?: unknown
}

export interface UsageRow {
  id: number
  conversation_id: string | null
  kind: string
  model: string
  requests: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cache_read_tokens: number
  context_tokens: number
  context_window: number | null
  created_at: string
}

export interface Usage {
  totals: {
    requests: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    cache_read_tokens: number
    context_tokens: number
  }
  recent: UsageRow[]
}

export interface Team {
  name: string
  kind: string
  roster: string[]
}

export interface TeamMember {
  name: string
  description: string
  capabilities: string[]
}

export interface TeamDefinition {
  name: string
  kind: string
  members: TeamMember[]
  speaker: string
  moderator: string | null
  manual_order: string[]
  max_turns: number
  max_rounds: number
  instructions: string | null
}

export interface StudioTeam extends TeamDefinition {
  registered: boolean
  updated_at: string
}

export interface TeamLedgerTask {
  id: number
  description: string
  owner: string | null
  status: string
  result: string
}

export interface TeamRun {
  team: string
  kind: string
  output: string
  rounds: number
  transcript: { speaker: string; text: string }[]
  ledger: { facts: string[]; plan: string[]; tasks: TeamLedgerTask[] } | null
}

export interface AuditEntry {
  id: number
  seq: number
  action: string
  target: string
  detail: Record<string, unknown>
  actor: string
  created_at: string
}

export interface A2ATask {
  id: string
  context_id: string | null
  state: string
  created_at: string
  updated_at: string
  payload?: unknown
}

export interface Artifact {
  path: string
  name: string
  size: number
  modified_at: string
}

export interface Soul {
  path: string
  text: string
  exists: boolean
}

export type ConfigView = Record<string, unknown>

export interface Whoami {
  owner_id: string
  subject: string
  roles: string[]
  method: string
  authenticated: boolean
}

export interface Lesson {
  id: number
  content: string
  status: string
  kind: string
  importance: number
  source_conversation_id: string | null
  created_at: string | null
}

export interface PendingApproval {
  tool_call_id: string
  tool_name: string
  args: Record<string, unknown>
}

const TOKEN_KEY = "agentkit_token"

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable (private mode); requests simply go unauthenticated
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (init?.body) headers["Content-Type"] = "application/json"
  const token = getToken()
  if (token) headers["Authorization"] = `Bearer ${token}`
  const response = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
})

export const api = {
  info: () => request<Info>("/info"),
  whoami: () => request<Whoami>("/whoami"),
  health: () => request<Health>("/health"),
  chat: (conversation_id: string, text: string, ephemeral = false) =>
    request<ChatReply>("/chat", json("POST", { conversation_id, text, ephemeral })),
  cancelChat: (conversation_id: string) =>
    request<{ cancelled: boolean }>("/chat/cancel", json("POST", { conversation_id })),

  lessons: (status = "proposed") =>
    request<{ lessons: Lesson[] }>(`/lessons?status=${encodeURIComponent(status)}`),
  approveLesson: (id: number) =>
    request<{ id: number; status: string }>(`/lessons/${id}/approve`, { method: "POST" }),
  rejectLesson: (id: number) =>
    request<{ id: number; status: string }>(`/lessons/${id}/reject`, { method: "POST" }),

  approvals: () => request<{ approvals: PendingApproval[] }>("/approvals"),
  decideApproval: (toolCallId: string, approved: boolean) =>
    request<{ tool_call_id: string; approved: boolean }>(
      `/approvals/${encodeURIComponent(toolCallId)}`,
      json("POST", { approved }),
    ),

  search: (q: string, limit = 20) =>
    request<{ query: string; hits: SearchHit[] }>(
      `/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  conversations: () => request<{ conversations: Conversation[] }>("/conversations"),
  messages: (id: string) =>
    request<{ conversation_id: string; messages: Message[] }>(
      `/conversations/${encodeURIComponent(id)}/messages`,
    ),
  clearMessages: (id: string) =>
    request<{ cleared: boolean }>(`/conversations/${encodeURIComponent(id)}/messages`, {
      method: "DELETE",
    }),

  schedules: () => request<{ jobs: Job[]; tasks: string[] }>("/schedules"),
  createSchedule: (body: {
    name: string
    kind: "cron" | "once"
    task: string
    schedule?: string
    at?: string
    args?: Record<string, unknown>
    enabled?: boolean
  }) => request<{ name: string }>("/schedules", json("POST", body)),
  patchSchedule: (name: string, body: { enabled?: boolean; schedule?: string; at?: string }) =>
    request<{ name: string }>(`/schedules/${encodeURIComponent(name)}`, json("PATCH", body)),
  deleteSchedule: (name: string) =>
    request<{ removed: boolean }>(`/schedules/${encodeURIComponent(name)}`, { method: "DELETE" }),

  workflows: (status?: string) =>
    request<{ workflows: Workflow[]; error?: string }>(
      `/workflows${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    ),
  failedWorkflows: () => request<{ workflows: Workflow[] }>("/workflows/failed"),
  workflow: (id: string) => request<Workflow>(`/workflows/${encodeURIComponent(id)}`),
  cancelWorkflow: (id: string) =>
    request<{ cancelled: boolean }>(`/workflows/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  resumeWorkflow: (id: string) =>
    request<{ resumed: boolean }>(`/workflows/${encodeURIComponent(id)}/resume`, {
      method: "POST",
    }),

  usage: () => request<Usage>("/usage"),
  teams: () => request<{ teams: Team[] }>("/teams"),

  studioTeams: () =>
    request<{ teams: StudioTeam[]; kinds: string[]; speakers: string[] }>("/studio/teams"),
  saveStudioTeam: (body: TeamDefinition) =>
    request<{ name: string; created: boolean }>("/studio/teams", json("POST", body)),
  deleteStudioTeam: (name: string) =>
    request<{ name: string; removed: boolean }>(`/studio/teams/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  studioTeamCode: (name: string) =>
    request<{ name: string; code: string }>(
      `/studio/teams/${encodeURIComponent(name)}/code`,
    ),
  activateStudioTeam: (name: string) =>
    request<{ name: string; registered: boolean; tool: string }>(
      `/studio/teams/${encodeURIComponent(name)}/activate`,
      { method: "POST" },
    ),
  runStudioTeam: (name: string, prompt: string) =>
    request<TeamRun>(`/studio/teams/${encodeURIComponent(name)}/run`, json("POST", { prompt })),
  audit: () => request<{ entries: AuditEntry[] }>("/audit"),
  verifyAudit: () => request<{ ok: boolean }>("/audit/verify"),

  a2a: () => request<{ tasks: A2ATask[] }>("/a2a"),
  a2aTask: (id: string) => request<A2ATask>(`/a2a/${encodeURIComponent(id)}`),

  soul: () => request<Soul>("/soul"),
  saveSoul: (text: string) => request<{ saved: boolean }>("/soul", json("PUT", { text })),

  config: () => request<{ config: ConfigView }>("/config"),
  artifacts: () => request<{ artifacts: Artifact[]; root?: string }>("/artifacts"),
  artifactUrl: (path: string) => `${BASE}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`,
}
