import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

/** A (partial) JSON-Schema node — enough to drive the generic Studio form. */
export type JSONSchema = {
  type?: string
  title?: string
  description?: string
  format?: string
  default?: unknown
  enum?: unknown[]
  properties?: Record<string, JSONSchema>
  required?: string[]
  items?: JSONSchema
  $ref?: string
  anyOf?: JSONSchema[]
  oneOf?: JSONSchema[]
  additionalProperties?: unknown
}

function resolveRef(ref: string, root: JSONSchema): JSONSchema {
  const parts = ref.replace(/^#\//, "").split("/")
  let node: unknown = root
  for (const part of parts) {
    if (node && typeof node === "object") {
      node = (node as Record<string, unknown>)[part]
    } else {
      return {}
    }
  }
  return (node as JSONSchema) ?? {}
}

/** Follow ``$ref`` and unwrap a nullable ``anyOf``/``oneOf`` to the real schema. */
export function normalize(schema: JSONSchema, root: JSONSchema): { schema: JSONSchema; nullable: boolean } {
  if (schema.$ref) return normalize(resolveRef(schema.$ref, root), root)
  const variants = schema.anyOf ?? schema.oneOf
  if (variants && variants.length) {
    const nullable = variants.some((variant) => variant.type === "null")
    const real = variants.filter((variant) => variant.type !== "null")
    if (real.length === 1) {
      return { ...normalize(real[0], root), nullable }
    }
    return { schema, nullable }
  }
  return { schema, nullable: false }
}

export function typeOf(schema: JSONSchema): string {
  if (schema.type) return schema.type
  if (schema.enum) return typeof schema.enum[0] === "number" ? "number" : "string"
  if (schema.properties || schema.additionalProperties !== undefined) return "object"
  if (schema.items) return "array"
  return "string"
}

/** A sensible initial value for a schema (used when creating a new spec). */
export function defaultFor(schema: JSONSchema, root: JSONSchema = schema): unknown {
  const { schema: node } = normalize(schema, root)
  if (node.default !== undefined) return node.default
  switch (typeOf(node)) {
    case "object": {
      const value: Record<string, unknown> = {}
      for (const [key, child] of Object.entries(node.properties ?? {})) {
        const { schema: resolved } = normalize(child, root)
        if (resolved.default !== undefined) value[key] = resolved.default
        else if (typeOf(resolved) === "array") value[key] = []
        else if (typeOf(resolved) === "boolean") value[key] = false
        else if (typeOf(resolved) === "integer" || typeOf(resolved) === "number") value[key] = 0
        else if (typeOf(resolved) === "object") value[key] = defaultFor(resolved, root)
        else value[key] = ""
      }
      return value
    }
    case "array":
      return []
    case "integer":
    case "number":
      return 0
    case "boolean":
      return false
    default:
      return ""
  }
}

const TEXTAREA_HINT = /instruction|prompt|description|criteria|content|body|notes/i

export function SchemaForm({
  schema,
  value,
  onChange,
  root,
}: {
  schema: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
  root?: JSONSchema
}) {
  const resolvedRoot = root ?? schema
  const props = schema.properties ?? {}
  return (
    <div className="space-y-4">
      {Object.entries(props).map(([name, child]) => (
        <SchemaField
          key={name}
          name={name}
          schema={child}
          root={resolvedRoot}
          required={(schema.required ?? []).includes(name)}
          value={(value as Record<string, unknown>)?.[name]}
          onChange={(next) => {
            const base = (value && typeof value === "object" ? value : {}) as Record<string, unknown>
            onChange({ ...base, [name]: next })
          }}
        />
      ))}
    </div>
  )
}

function FieldLabel({ name, schema, required }: { name: string; schema: JSONSchema; required: boolean }) {
  return (
    <div className="space-y-0.5">
      <Label className="text-xs">
        {schema.title ?? name}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      {schema.description ? (
        <p className="text-muted-foreground text-[11px]">{schema.description}</p>
      ) : null}
    </div>
  )
}

function SchemaField({
  name,
  schema,
  root,
  value,
  onChange,
  required,
}: {
  name: string
  schema: JSONSchema
  root: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
  required: boolean
}) {
  const { schema: node, nullable } = normalize(schema, root)
  const kind = typeOf(node)

  if (node.enum) {
    return (
      <div className="space-y-1">
        <FieldLabel name={name} schema={node} required={required} />
        <select
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(event) => {
            const raw = event.target.value
            const matched = node.enum?.find((option) => String(option) === raw)
            onChange(raw === "" && nullable ? null : (matched ?? raw))
          }}
        >
          {nullable ? <option value="">(none)</option> : null}
          {(node.enum ?? []).map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
      </div>
    )
  }

  if (kind === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4 rounded border"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{node.title ?? name}</span>
      </label>
    )
  }

  if (kind === "integer" || kind === "number") {
    return (
      <div className="space-y-1">
        <FieldLabel name={name} schema={node} required={required} />
        <Input
          type="number"
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(event) =>
            onChange(event.target.value === "" ? (nullable ? null : 0) : Number(event.target.value))
          }
        />
      </div>
    )
  }

  if (kind === "array") {
    return (
      <ArrayField
        name={name}
        schema={node}
        root={root}
        value={value}
        onChange={onChange}
        required={required}
      />
    )
  }

  if (kind === "object") {
    const hasProps = Object.keys(node.properties ?? {}).length > 0
    return (
      <div className="space-y-2 rounded-md border p-3">
        <FieldLabel name={name} schema={node} required={required} />
        {hasProps ? (
          <SchemaForm schema={node} root={root} value={value ?? {}} onChange={onChange} />
        ) : (
          <JsonArea value={value} onChange={onChange} />
        )}
      </div>
    )
  }

  const useTextarea = TEXTAREA_HINT.test(name) || node.format === "textarea"
  return (
    <div className="space-y-1">
      <FieldLabel name={name} schema={node} required={required} />
      {useTextarea ? (
        <Textarea
          rows={3}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <Input
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(event) =>
            onChange(event.target.value === "" && nullable ? null : event.target.value)
          }
        />
      )}
    </div>
  )
}

function ArrayField({
  name,
  schema,
  root,
  value,
  onChange,
  required,
}: {
  name: string
  schema: JSONSchema
  root: JSONSchema
  value: unknown
  onChange: (value: unknown) => void
  required: boolean
}) {
  const items = normalize(schema.items ?? {}, root).schema
  const itemKind = typeOf(items)
  const list = Array.isArray(value) ? (value as unknown[]) : []

  if (itemKind === "object") {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <FieldLabel name={name} schema={schema} required={required} />
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onChange([...list, defaultFor(items, root)])}
          >
            Add
          </Button>
        </div>
        {list.map((entry, index) => (
          <div key={index} className="space-y-2 rounded-md border p-3">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground text-xs">#{index + 1}</span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onChange(list.filter((_, i) => i !== index))}
              >
                Remove
              </Button>
            </div>
            <SchemaForm
              schema={items}
              root={root}
              value={entry ?? {}}
              onChange={(next) => onChange(list.map((item, i) => (i === index ? next : item)))}
            />
          </div>
        ))}
        {list.length ? null : <p className="text-muted-foreground text-xs">No entries.</p>}
      </div>
    )
  }

  // Array of primitives: one value per line.
  return (
    <div className="space-y-1">
      <FieldLabel name={name} schema={schema} required={required} />
      <Textarea
        rows={2}
        placeholder="one per line"
        value={list.map((entry) => String(entry)).join("\n")}
        onChange={(event) =>
          onChange(
            event.target.value
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean)
              .map((line) => (itemKind === "integer" || itemKind === "number" ? Number(line) : line)),
          )
        }
      />
    </div>
  )
}

function JsonArea({ value, onChange }: { value: unknown; onChange: (value: unknown) => void }) {
  const text = JSON.stringify(value ?? {}, null, 2)
  return (
    <Textarea
      rows={4}
      className="font-mono text-xs"
      defaultValue={text}
      onChange={(event) => {
        try {
          onChange(JSON.parse(event.target.value))
        } catch {
          /* keep typing */
        }
      }}
    />
  )
}
