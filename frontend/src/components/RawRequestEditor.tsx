/**
 * A RESTCONF request you can type into.
 *
 * The tree plans what can be ticked. This is for the rest: a body pasted from
 * another client, or a planned request nudged before it goes out — a query
 * parameter added, a second list entry written in. It is sent to the chosen
 * device with that device's credentials, exactly as it stands.
 */
import { Play, RotateCcw } from 'lucide-react'
import { useMemo } from 'react'

import { Button } from './ui'
import type { RawRequest } from '@/lib/types'

const METHODS = ['GET', 'PATCH', 'PUT', 'POST', 'DELETE'] as const
const hasBody = (method: string) => method !== 'GET' && method !== 'DELETE'

/** Why this body will not parse, or '' when it will (or there is none). */
function jsonProblem(draft: RawRequest): string {
  if (!hasBody(draft.method) || !draft.body.trim()) return ''
  try {
    JSON.parse(draft.body)
    return ''
  } catch (error) {
    return error instanceof Error ? error.message : String(error)
  }
}

interface Props {
  draft: RawRequest
  onChange: (draft: RawRequest) => void
  onSend: () => void
  /** Throw the edits away. Omitted when there is nothing to go back to. */
  onReset?: () => void
  resetLabel?: string
  canSend: boolean
  sending: boolean
  /** Shown beside Send when it is disabled for a reason the editor cannot see. */
  blockedBy?: string
}

export function RawRequestEditor({
  draft, onChange, onSend, onReset, resetLabel = 'Reset', canSend, sending, blockedBy,
}: Props) {
  const problem = useMemo(() => jsonProblem(draft), [draft])
  const urlMissing = !draft.url.trim()

  return (
    <div className="flex shrink-0 flex-col gap-1.5 px-3 pb-2">
      <div className="flex items-center gap-1.5">
        <select
          value={draft.method}
          onChange={(e) => onChange({ ...draft, method: e.target.value })}
          aria-label="HTTP method"
          className="h-7 shrink-0 rounded border border-line bg-surface px-1.5 font-mono text-[11px] text-ink"
        >
          {METHODS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input
          value={draft.url}
          onChange={(e) => onChange({ ...draft, url: e.target.value })}
          spellCheck={false}
          aria-label="Request URL"
          placeholder="/restconf/data/…   (a full https:// URL is fine — only its path is used)"
          className="h-7 min-w-0 flex-1 rounded border border-line bg-surface px-2 font-mono text-[11.5px] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
        />
      </div>

      {hasBody(draft.method) ? (
        <textarea
          value={draft.body}
          onChange={(e) => onChange({ ...draft, body: e.target.value })}
          spellCheck={false}
          rows={12}
          aria-label="Request body"
          placeholder={'{\n  "module:node": { … }\n}'}
          className="min-h-24 w-full resize-y rounded border border-line bg-canvas/50 p-2 font-mono text-[11px] leading-relaxed text-code-value placeholder:text-ink-faint focus:border-brand focus:outline-none"
        />
      ) : (
        <p className="text-[11px] text-ink-faint">{draft.method} carries no body.</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {problem ? (
          <span className="min-w-0 flex-1 truncate text-[11px] text-danger" title={problem}>
            Not valid JSON — {problem}
          </span>
        ) : (
          <span className="min-w-0 flex-1 truncate text-[11px] text-ink-faint">
            {blockedBy || 'Sent as written, with the device profile’s credentials.'}
          </span>
        )}
        {onReset ? (
          <Button size="sm" variant="ghost" onClick={onReset}>
            <RotateCcw className="size-3" /> {resetLabel}
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="primary"
          disabled={!canSend || Boolean(problem) || urlMissing}
          loading={sending}
          onClick={onSend}
        >
          <Play className="size-3" /> Send
        </Button>
      </div>
    </div>
  )
}
