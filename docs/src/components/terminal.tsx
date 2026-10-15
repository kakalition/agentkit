const LINES = [
  "$ agentkit serve",
  "→ booting bootstrap:app …",
  "→ channels: webui, telegram",
  "→ scheduler: 3 jobs (cron + one-off)",
  "→ ready on http://127.0.0.1:8787",
]

export function Terminal({ title = "nudge — agentkit" }: { title?: string }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-muted/30">
      <div className="flex items-center gap-1.5 border-b px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-red-400/70" />
        <span className="size-2.5 rounded-full bg-amber-400/70" />
        <span className="size-2.5 rounded-full bg-emerald-400/70" />
        <span className="ml-2 font-mono text-xs text-muted-foreground">{title}</span>
      </div>
      <div className="p-4 font-mono text-[13px] leading-relaxed">
        {LINES.map((line) => (
          <div
            key={line}
            className={line.startsWith("$") ? "text-foreground" : "text-muted-foreground"}
          >
            {line}
          </div>
        ))}
        <div className="text-foreground">
          ${" "}
          <span className="inline-block h-3.5 w-2 translate-y-0.5 animate-pulse bg-foreground" />
        </div>
      </div>
    </div>
  )
}
