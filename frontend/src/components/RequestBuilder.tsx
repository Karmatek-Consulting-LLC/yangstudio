/**
 * The request basket: chosen nodes, their values, and the live XML.
 *
 * The XML is rebuilt on the server as the selection changes, so what you see
 * is exactly what will be sent — not an approximation rendered client-side.
 */
import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, PencilLine, Play, Send, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { CodeView } from './CodeView'
import { RawRequestEditor } from './RawRequestEditor'
import { RestconfView } from './RestconfView'
import { Badge, Button, EmptyState } from './ui'
import { api, ApiError } from '@/lib/api'
import { nodeStyle } from '@/lib/nodeStyle'
import type {
  ComposeMode, Device, RawRequest, RestResult, RpcResult, Selection,
} from '@/lib/types'

const READ_OPS = ['get', 'get-config'] as const
const EDIT_OPS = ['edit-config'] as const
// Datastore operations act on a whole datastore, not on selected nodes. Many
// devices refuse a direct write to running (IOS-XR and Junos always, IOS-XE
// with candidate-datastore enabled), so without commit an edit is composed,
// sent, and then silently dropped when the session ends.
const DATASTORE_OPS = ['commit', 'discard-changes', 'validate'] as const
const NETCONF_OPERATIONS = [...READ_OPS, ...EDIT_OPS, ...DATASTORE_OPS, 'rpc'] as const

const needsSelection = (op: string) => !(DATASTORE_OPS as readonly string[]).includes(op)
// RESTCONF speaks HTTP methods, so offer those rather than silently translating.
const RESTCONF_OPERATIONS = ['GET', 'PATCH', 'PUT', 'POST', 'DELETE'] as const
// The methods that carry a body, and so can be composed into one request.
const RESTCONF_WRITES: readonly string[] = ['PATCH', 'PUT', 'POST']

const failedResult = (error: unknown): RestResult => ({
  ok: false, status: 0, elapsed_ms: 0,
  error: { message: error instanceof ApiError ? error.message : String(error) },
  request: { method: '', path: '', query: '', url: '', body: '', content_type: '', covers: [] },
})

const NODE_OPS = ['merge', 'replace', 'create', 'delete', 'remove'] as const

interface Props {
  selections: Selection[]
  onChange: (selections: Selection[]) => void
  namespaces: Record<string, string>
  devices: Device[]
  /** Show this path back in the tree and the Node panel. */
  onReveal?: (xpath: string) => void
  /** Fired when a run finishes, so the reply can be given room to be read. */
  onRan?: () => void
  /** Needed to resolve paths into RESTCONF URLs. */
  yangsetSlug: string
}

export function RequestBuilder({
  selections, onChange, namespaces, devices, onReveal, onRan, yangsetSlug,
}: Props) {
  const [operation, setOperation] = useState<string>('get-config')
  const [datastore, setDatastore] = useState('running')
  const [device, setDevice] = useState('')
  const [xml, setXml] = useState('')
  const [buildError, setBuildError] = useState('')
  const [result, setResult] = useState<RpcResult | null>(null)
  // The request and the reply compete for the same space; a tab gives whichever
  // you are reading the full height instead of splitting it into two strips.
  const [tab, setTab] = useState<'request' | 'response'>('request')
  // The same selection, two protocols. Kept side by side deliberately: the
  // mapping between them is the thing worth learning.
  const [protocol, setProtocol] = useState<'netconf' | 'restconf'>('netconf')
  const [restResults, setRestResults] = useState<RestResult[] | null>(null)
  const [staged, setStaged] = useState(false)
  // A RESTCONF write defaults to one composed request: a device validates each
  // call on its own, so anything with more than one required part — an ACL
  // entry, a BGP neighbour — is refused when it arrives a leaf at a time.
  const [compose, setCompose] = useState<ComposeMode>('single')
  const [target, setTarget] = useState('')
  // With nothing ticked, a request can still be written by hand.
  const [scratch, setScratch] = useState<RawRequest | null>(null)
  const [scratchResult, setScratchResult] = useState<RestResult | null>(null)

  const isEdit = operation === 'edit-config'
  const isRestWrite = protocol === 'restconf' && RESTCONF_WRITES.includes(operation)

  // Rebuild the XML whenever the request changes. Only while NETCONF is the
  // active protocol: the operation list differs, and sending an HTTP method to
  // the NETCONF builder just produces a spurious error.
  useEffect(() => {
    if (protocol !== 'netconf' || (selections.length === 0 && needsSelection(operation))) {
      setXml('')
      setBuildError('')
      return
    }
    let cancelled = false
    api
      .buildRpc({ operation, datastore, selections, namespaces })
      .then((r) => {
        if (!cancelled) {
          setXml(r.rpc_xml)
          setBuildError('')
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setXml('')
          setBuildError(error instanceof ApiError ? error.message : String(error))
        }
      })
    return () => {
      cancelled = true
    }
  }, [selections, operation, datastore, namespaces, protocol])

  const run = useMutation({
    mutationFn: () =>
      api.runRpc({ device, operation, datastore, selections, namespaces, rpc_xml: xml }),
    onSuccess: (r) => {
      setResult(r)
      setTab('response')      // You ran it to see this.
      // An edit into candidate is staged, not applied. Say so, rather than
      // letting a successful-looking reply imply the device changed.
      setStaged(r.ok && operation === 'edit-config' && datastore === 'candidate')
      onRan?.()
    },
    onError: (error: unknown) => {
      setResult({
        ok: false,
        elapsed_ms: 0,
        error: { message: error instanceof ApiError ? error.message : String(error) },
      })
      setTab('response')
      onRan?.()
    },
  })

  // Commit and discard need no selection, so they bypass the normal builder.
  const runDatastoreOp = (op: string) =>
    api.runRpc({ device, operation: op, datastore: 'candidate', selections: [], namespaces })

  const runCommit = useMutation({
    mutationFn: () => runDatastoreOp('commit'),
    onSuccess: (r) => { setResult(r); setTab('response'); onRan?.() },
  })

  const runDiscard = useMutation({
    mutationFn: () => runDatastoreOp('discard-changes'),
    onSuccess: (r) => { setResult(r); setTab('response'); onRan?.() },
  })

  // One card's reply belongs under that card. Running a single request used
  // to replace the whole list, which filed its reply under the first one.
  const placeResults = (incoming: RestResult[], only?: number) =>
    setRestResults((previous) => {
      if (only === undefined) return incoming
      const next = [...(previous ?? [])]
      next[only] = incoming[0]
      return next
    })

  const runRest = useMutation({
    mutationFn: async ({ only, raw }: { only?: number; raw?: RawRequest }) => {
      if (raw) return { results: [await api.sendRestconf({ device, ...raw })] }
      return api.runRestconf({
        yangset: yangsetSlug, device, operation, selections, only, compose, target,
      })
    },
    onSuccess: (r, { only }) => {
      placeResults(r.results, only)
      onRan?.()
    },
    onError: (error: unknown, { only }) => placeResults([failedResult(error)], only),
  })

  const runScratch = useMutation({
    mutationFn: (raw: RawRequest) => api.sendRestconf({ device, ...raw }),
    onSuccess: (r) => { setScratchResult(r); onRan?.() },
    onError: (error: unknown) => setScratchResult(failedResult(error)),
  })

  const update = (index: number, patch: Partial<Selection>) => {
    onChange(selections.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }

  if (selections.length === 0 && scratch) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-1.5 border-b border-line-soft p-2">
          <span className="text-[12px] text-ink">RESTCONF request, written by hand</span>
          <span className="flex-1" />
          <select
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            className="h-7 max-w-40 rounded border border-line bg-surface px-1.5 text-xs text-ink"
          >
            <option value="">Select device…</option>
            {devices.map((d) => (
              <option key={d.slug} value={d.slug}>{d.name}</option>
            ))}
          </select>
          <Button size="sm" variant="ghost" onClick={() => setScratch(null)} title="Close">
            <X className="size-3" />
          </Button>
        </div>
        <div className="pt-2">
          <RawRequestEditor
            draft={scratch}
            onChange={setScratch}
            onSend={() => runScratch.mutate(scratch)}
            canSend={Boolean(device)}
            sending={runScratch.isPending}
            blockedBy={device ? '' : 'Select a device to send this to.'}
          />
        </div>
        {scratchResult ? (
          <div className="flex min-h-0 flex-1 flex-col border-t border-line-soft">
            <p className="shrink-0 px-3 py-1 text-[10px] text-ink-faint">
              {scratchResult.status || 'error'} {scratchResult.reason} · {scratchResult.elapsed_ms} ms
            </p>
            <CodeView
              source={scratchResult.reply || scratchResult.error?.message || '(empty response)'}
              kind={scratchResult.ok ? 'json' : 'text'}
            />
          </div>
        ) : null}
      </div>
    )
  }

  if (selections.length === 0) {
    return (
      <EmptyState
        title="No nodes in the request"
        hint="Tick a node in the tree — or highlight one and press the Space bar — to start building a request. The XML is written as you go."
        action={
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setScratch({ method: 'GET', url: '/restconf/data/', body: '' })}
          >
            <PencilLine className="size-3.5" />
            Or write a RESTCONF request by hand
          </Button>
        }
      />
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line-soft p-2">
        <select
          value={operation}
          onChange={(e) => setOperation(e.target.value)}
          className="h-7 rounded border border-line bg-surface px-1.5 text-xs text-ink"
        >
          {(protocol === 'netconf' ? NETCONF_OPERATIONS : RESTCONF_OPERATIONS).map((op) => (
            <option key={op} value={op}>{op}</option>
          ))}
        </select>

        {protocol === 'netconf' && operation !== 'rpc' && operation !== 'get'
          && operation !== 'commit' && operation !== 'discard-changes' ? (
          <select
            value={datastore}
            onChange={(e) => setDatastore(e.target.value)}
            className="h-7 rounded border border-line bg-surface px-1.5 text-xs text-ink"
          >
            {['running', 'candidate', 'startup'].map((ds) => (
              <option key={ds} value={ds}>{ds}</option>
            ))}
          </select>
        ) : null}

        {isRestWrite ? (
          <div
            className="flex overflow-hidden rounded border border-line"
            title="One request carrying every node, or one request per node"
          >
            {([['single', 'One request'], ['per-node', 'Per node']] as const).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => {
                  setCompose(mode)
                  setRestResults(null)      // The cards change; old replies would mislabel them.
                }}
                className={clsx(
                  'h-7 px-2 text-[11px] transition-colors',
                  compose === mode ? 'bg-raised text-ink' : 'bg-surface text-ink-faint hover:bg-raised',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}

        <span className="flex-1" />

        <div className="flex overflow-hidden rounded border border-line">
          {(['netconf', 'restconf'] as const).map((p) => (
            <button
              key={p}
              onClick={() => {
                setProtocol(p)
                // The verbs differ, so carry the intent across rather than
                // leaving a NETCONF operation selected on an HTTP request.
                setOperation((current) =>
                  p === 'restconf'
                    ? current === 'edit-config' ? 'PATCH' : 'GET'
                    : current === 'GET' ? 'get-config' : 'edit-config',
                )
              }}
              className={clsx(
                'h-7 px-2 text-[11px] transition-colors',
                protocol === p ? 'bg-brand text-canvas' : 'bg-surface text-ink-muted hover:bg-raised',
              )}
            >
              {p === 'netconf' ? 'NETCONF' : 'RESTCONF'}
            </button>
          ))}
        </div>

        <select
          value={device}
          onChange={(e) => setDevice(e.target.value)}
          className="h-7 max-w-40 rounded border border-line bg-surface px-1.5 text-xs text-ink"
        >
          <option value="">Select device…</option>
          {devices.map((d) => (
            <option key={d.slug} value={d.slug}>{d.name}</option>
          ))}
        </select>

        <Button
          size="sm"
          variant="primary"
          disabled={
            !device ||
            (protocol === 'netconf'
              ? !xml && needsSelection(operation)
              : selections.length === 0)
          }
          loading={run.isPending || runRest.isPending}
          onClick={() => (protocol === 'netconf' ? run.mutate() : runRest.mutate({}))}
        >
          <Play className="size-3" />
          Run
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onChange([])} title="Clear all">
          <Trash2 className="size-3" />
        </Button>
      </div>

      {staged ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-line-soft bg-warn/10 px-2 py-1.5">
          <AlertTriangle className="size-3.5 shrink-0 text-warn" />
          <span className="text-[11.5px] text-ink">
            Staged in <span className="font-mono">candidate</span> — not applied yet.
          </span>
          <span className="flex-1" />
          <Button
            size="sm"
            variant="primary"
            loading={run.isPending && operation === 'commit'}
            onClick={() => {
              setOperation('commit')
              setStaged(false)
              runCommit.mutate()
            }}
          >
            Commit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setStaged(false)
              runDiscard.mutate()
            }}
          >
            Discard
          </Button>
        </div>
      ) : null}

      {/* Selected nodes */}
      <div className="max-h-56 overflow-y-auto border-b border-line-soft">
        {selections.map((selection, index) => {
          const style = nodeStyle(selection.nodetype)
          const leafLike = selection.nodetype === 'leaf' || selection.nodetype === 'leaf-list'
          // An empty leaf says something by being there; there is no value to
          // type, and asking for one suggests the tick alone does nothing.
          const isEmpty = selection.datatype === 'empty'
          return (
            <div
              key={selection.xpath}
              className="flex items-center gap-1.5 border-b border-line-soft/50 px-2 py-1.5 last:border-0 hover:bg-raised/60"
            >
              <span className="shrink-0 text-[11px]" style={{ color: style.color }}>
                {style.glyph}
              </span>
              {/* Clicking the path takes you back to that node — otherwise the
                  list is a dead end once you have more than a couple in it. */}
              <button
                onClick={() => onReveal?.(selection.xpath)}
                title={`${selection.xpath}\n\nClick to show this node in the tree`}
                className="min-w-0 flex-1 truncate text-left font-mono text-[11px] text-ink-muted hover:text-ink hover:underline underline-offset-2"
              >
                {selection.xpath}
              </button>

              {isEdit ? (
                <select
                  value={selection.operation}
                  onChange={(e) => update(index, { operation: e.target.value })}
                  className="h-6 shrink-0 rounded border border-line bg-surface px-1 text-[10px] text-ink"
                >
                  <option value="">—</option>
                  {NODE_OPS.map((op) => (
                    <option key={op} value={op}>{op}</option>
                  ))}
                </select>
              ) : null}

              {leafLike && isEmpty ? (
                <Badge title="An empty-type leaf has no value: ticking it is what sets it">
                  no value — set by being ticked
                </Badge>
              ) : leafLike ? (
                <input
                  value={selection.value}
                  onChange={(e) => update(index, { value: e.target.value })}
                  placeholder={isEdit || isRestWrite ? 'value' : 'filter'}
                  className="h-6 w-28 shrink-0 rounded border border-line bg-surface px-1.5 text-[11px] text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none"
                />
              ) : null}

              <button
                onClick={() => onChange(selections.filter((_, i) => i !== index))}
                className="shrink-0 rounded p-0.5 text-ink-faint hover:bg-raised hover:text-danger"
                aria-label={`Remove ${selection.xpath}`}
              >
                <X className="size-3" />
              </button>
            </div>
          )
        })}
      </div>

      {/* Request and reply share one full-height pane, switched by tab. */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-1 border-b border-line-soft px-2">
          <TabButton active={tab === 'request'} onClick={() => setTab('request')}>
            Request
            <Badge className="ml-1.5">{selections.length}</Badge>
          </TabButton>
          <TabButton
            active={tab === 'response'}
            onClick={() => setTab('response')}
            disabled={!result && !restResults}
          >
            Response
            {result ? (
              <Badge
                className={clsx(
                  'ml-1.5 border',
                  result.ok
                    ? 'border-ok/40 bg-ok/10 text-ok'
                    : 'border-danger/40 bg-danger/10 text-danger',
                )}
              >
                {result.ok ? 'OK' : 'error'}
              </Badge>
            ) : null}
          </TabButton>
          <span className="flex-1" />
          {result ? (
            <span className="font-mono text-[10px] text-ink-faint">{result.elapsed_ms} ms</span>
          ) : null}
          {buildError ? (
            <Badge className="border-danger/40 text-danger">{buildError}</Badge>
          ) : null}
        </div>

        {tab === 'request' ? (
          protocol === 'netconf' ? (
            <CodeView
              source={xml}
              kind="xml"
              empty={
                <p className="text-center text-xs text-ink-faint">
                  {buildError || 'Building…'}
                </p>
              }
            />
          ) : (
            <RestconfView
              yangsetSlug={yangsetSlug}
              selections={selections}
              operation={operation}
              compose={compose}
              target={target}
              onTargetChange={(xpath) => {
                setTarget(xpath)
                setRestResults(null)
              }}
              results={restResults}
              running={runRest.isPending}
              canRun={Boolean(device)}
              onRun={(index) => runRest.mutate({ only: index })}
              onSendRaw={(index, raw) => runRest.mutate({ only: index, raw })}
            />
          )
        ) : (
          protocol === 'netconf' ? (
            <CodeView
              source={result?.ok ? (result.reply ?? '') : formatError(result)}
              kind={result?.ok ? 'xml' : 'text'}
              empty={<p className="text-center text-xs text-ink-faint">Run the request to see the reply.</p>}
            />
          ) : (
            <RestconfView
              yangsetSlug={yangsetSlug}
              selections={selections}
              operation={operation}
              compose={compose}
              target={target}
              onTargetChange={(xpath) => {
                setTarget(xpath)
                setRestResults(null)
              }}
              results={restResults}
              running={runRest.isPending}
              canRun={Boolean(device)}
              onRun={(index) => runRest.mutate({ only: index })}
              onSendRaw={(index, raw) => runRest.mutate({ only: index, raw })}
            />
          )
        )}
      </div>
    </div>
  )
}

function TabButton({
  active, onClick, disabled, children,
}: {
  active: boolean
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        'relative flex h-8 items-center px-2.5 text-[12px] transition-colors',
        disabled && 'cursor-not-allowed opacity-40',
        active ? 'text-ink' : 'text-ink-faint hover:text-ink-muted',
      )}
    >
      {children}
      {active ? (
        <span className="absolute inset-x-1.5 -bottom-px h-0.5 rounded-full bg-brand" />
      ) : null}
    </button>
  )
}

function formatError(result: RpcResult | null): string {
  const error = result?.error
  if (!error) return 'Unknown error'
  return [
    error.message,
    error.tag ? `tag: ${error.tag}` : '',
    error.path ? `path: ${error.path}` : '',
    error.severity ? `severity: ${error.severity}` : '',
    error.info ? `info: ${error.info}` : '',
  ]
    .filter(Boolean)
    .join('\n')
}

export { Send }
