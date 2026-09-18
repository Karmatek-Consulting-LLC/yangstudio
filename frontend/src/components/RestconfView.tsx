/**
 * The same selection, expressed as RESTCONF.
 *
 * Shown beside the NETCONF XML so the mapping is visible rather than asserted:
 * the top container carries its module name, list keys move into the path, and
 * sibling leaves collapse into one ?fields= query. Where NETCONF sends one
 * filter with several branches, RESTCONF addresses one resource per call — so
 * a selection can plan to more than one request, and that is worth seeing.
 *
 * A write can instead be composed into one request, every selection nested in
 * a single body. That is the only form a device accepts for anything it
 * validates as a whole — an access-list entry sent leaf by leaf is refused at
 * the first leaf. The same change can be aimed at several levels of the tree,
 * so the card says which and lets you move it.
 */
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, Pencil, Play } from 'lucide-react'
import { useState } from 'react'

import { CodeView } from './CodeView'
import { RawRequestEditor } from './RawRequestEditor'
import { Badge, Button, EmptyState, Spinner } from './ui'
import { api, ApiError } from '@/lib/api'
import type { ComposeMode, RawRequest, RestRequest, RestResult, Selection } from '@/lib/types'

const METHOD_STYLE: Record<string, string> = {
  GET: 'border-brand/40 bg-brand/10 text-brand',
  PUT: 'border-warn/40 bg-warn/10 text-warn',
  PATCH: 'border-warn/40 bg-warn/10 text-warn',
  POST: 'border-ok/40 bg-ok/10 text-ok',
  DELETE: 'border-danger/40 bg-danger/10 text-danger',
}

export function RestconfView({
  yangsetSlug, selections, operation, compose, target, onTargetChange,
  results, onRun, onSendRaw, running, canRun,
}: {
  yangsetSlug: string
  selections: Selection[]
  operation: string
  compose: ComposeMode
  /** Where a composed body starts; '' leaves it to the planner. */
  target: string
  onTargetChange: (xpath: string) => void
  results: RestResult[] | null
  onRun: (index?: number) => void
  /** Send an edited request in place of the planned one at `index`. */
  onSendRaw: (index: number, raw: RawRequest) => void
  running: boolean
  canRun: boolean
}) {
  const plan = useQuery({
    queryKey: ['restconf-build', yangsetSlug, operation, selections, compose, target],
    queryFn: () =>
      api.buildRestconf({ yangset: yangsetSlug, operation, selections, compose, target }),
    enabled: Boolean(yangsetSlug) && selections.length > 0,
    retry: false,
    // Moving the target re-plans; keep the old card up rather than flashing a
    // spinner over the body you are in the middle of reading.
    placeholderData: (previous) => previous,
  })

  if (selections.length === 0) {
    return <EmptyState title="No nodes selected" hint="Tick nodes in the tree to plan a RESTCONF call." />
  }
  if (plan.isLoading) return <Spinner label="Planning…" />
  if (plan.isError) {
    return (
      <div className="flex flex-1 items-start gap-2 p-3 text-[12px] text-danger">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
        <p>{plan.error instanceof ApiError ? plan.error.message : String(plan.error)}</p>
      </div>
    )
  }

  const requests = plan.data?.requests ?? []
  // With a single call there is no list to scroll, so let that one card fill
  // the panel — the reply is the thing you are here to read.
  const single = requests.length === 1

  return (
    <div
      className={clsx(
        'flex min-h-0 flex-1 flex-col',
        single ? 'overflow-hidden' : 'overflow-y-auto',
      )}
    >
      {requests.length > 1 ? (
        <p className="border-b border-line-soft px-3 py-1.5 text-[11px] text-ink-faint">
          {requests.length} calls — RESTCONF addresses one resource per request, where a
          NETCONF filter carries several branches at once.
        </p>
      ) : null}

      {requests.map((request, index) => (
        <RequestCard
          key={request.url + index}
          request={request}
          result={results?.[index]}
          onRun={() => onRun(index)}
          onSendRaw={(raw) => onSendRaw(index, raw)}
          onTargetChange={onTargetChange}
          running={running}
          canRun={canRun}
          grow={single}
        />
      ))}
    </div>
  )
}

function RequestCard({
  request, result, onRun, onSendRaw, onTargetChange, running, canRun, grow,
}: {
  request: RestRequest
  result?: RestResult
  onRun: () => void
  onSendRaw: (raw: RawRequest) => void
  onTargetChange: (xpath: string) => void
  running: boolean
  canRun: boolean
  grow?: boolean
}) {
  // Null while the planned request is what will be sent. Once edited, the
  // draft is kept even if the plan changes underneath it: typed work is not
  // something to throw away because a box was ticked.
  const [draft, setDraft] = useState<RawRequest | null>(null)
  const targets = request.targets ?? []
  const drifted = draft !== null
    && (draft.method !== request.method || draft.url !== request.url || draft.body !== request.body)

  return (
    <div
      className={clsx(
        'flex flex-col border-b border-line-soft last:border-0',
        grow && 'min-h-0 flex-1',
      )}
    >
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 px-3 py-2">
        <Badge className={clsx('border font-mono', METHOD_STYLE[request.method] ?? '')}>
          {request.method}
        </Badge>
        <code className="min-w-0 flex-1 break-all font-mono text-[11.5px] text-ink">
          {request.path}
          {request.query ? <span className="text-ink-faint">?{request.query}</span> : null}
        </code>
        {result ? (
          <Badge
            className={clsx(
              'border',
              result.ok
                ? 'border-ok/40 bg-ok/10 text-ok'
                : 'border-danger/40 bg-danger/10 text-danger',
            )}
          >
            {result.status || 'err'}
          </Badge>
        ) : null}
        {draft === null ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDraft({ method: request.method, url: request.url, body: request.body })}
              title="Edit the method, URL and body by hand before sending"
            >
              <Pencil className="size-3" /> Edit
            </Button>
            <Button size="sm" variant="outline" disabled={!canRun} loading={running} onClick={onRun}>
              <Play className="size-3" /> Send
            </Button>
          </>
        ) : (
          <Badge className="border-warn/40 bg-warn/10 text-warn">
            {drifted ? 'edited by hand' : 'editing'}
          </Badge>
        )}
      </div>

      {targets.length > 1 && draft === null ? (
        <label className="flex shrink-0 flex-wrap items-center gap-1.5 px-3 pb-1.5 text-[11px] text-ink-faint">
          Body starts at
          <select
            value={request.target}
            onChange={(e) => onTargetChange(e.target.value)}
            title="The same change can be a small body deep in the URL, or a larger body higher up"
            className="h-6 max-w-72 rounded border border-line bg-surface px-1.5 font-mono text-[11px] text-ink"
          >
            {targets.map((t, depth) => (
              <option key={t.xpath} value={t.xpath}>
                {'\u00a0\u00a0'.repeat(depth)}{t.name}
              </option>
            ))}
          </select>
          <span>
            {request.method === 'POST'
              ? '— POST creates it, so the URL is its parent'
              : '— the URL ends on it'}
          </span>
        </label>
      ) : null}

      {request.notes?.length ? (
        <div className="shrink-0 px-3 pb-1.5">
          {request.notes.map((note) => (
            <p
              key={note}
              className="rounded border border-warn/40 bg-warn/10 px-2 py-1.5 text-[11px] leading-relaxed text-warn"
            >
              {note}
            </p>
          ))}
        </div>
      ) : null}

      {request.covers.length ? (
        <p className="shrink-0 px-3 pb-1.5 font-mono text-[10px] text-ink-faint">
          covers {request.covers.join('  ·  ')}
        </p>
      ) : null}

      {draft !== null ? (
        <RawRequestEditor
          draft={draft}
          onChange={setDraft}
          onSend={() => onSendRaw(draft)}
          onReset={() => setDraft(null)}
          resetLabel="Back to the planned request"
          canSend={canRun}
          sending={running}
          blockedBy={canRun ? '' : 'Select a device to send this to.'}
        />
      ) : request.body ? (
        <div className="shrink-0 px-3 pb-2">
          <p className="mb-1 text-[10px] text-ink-faint">
            Content-Type: <span className="font-mono">{request.content_type}</span>
          </p>
          <pre className="overflow-x-auto rounded border border-line bg-canvas/50 p-2 font-mono text-[11px] text-code-value">
            {request.body}
          </pre>
        </div>
      ) : null}

      {result ? (
        <div
          className={clsx(
            'flex min-h-0 flex-col border-t border-line-soft/60',
            // A bounded height is what lets the code pane scroll rather than
            // clip: flex-1 needs something definite to resolve against.
            grow ? 'flex-1' : 'max-h-96',
          )}
        >
          <div className="flex shrink-0 items-center gap-2 px-3 py-1">
            <span className="text-[10px] text-ink-faint">
              {result.status} {result.reason} · {result.elapsed_ms} ms
            </span>
          </div>
          <CodeView
            source={result.reply || result.error?.message || '(empty response)'}
            kind={result.ok ? 'json' : 'text'}
          />
        </div>
      ) : null}
    </div>
  )
}
