/** The main workspace: pick a set, browse it, build a request from it. */
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  AlertTriangle, ChevronsDownUp, ChevronsUpDown, FileWarning, Layers,
  Maximize2, Minimize2, RefreshCw, Search, X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { NodeDetail } from '@/components/NodeDetail'
import { Split } from '@/components/Split'
import { RequestBuilder } from '@/components/RequestBuilder'
import { TreeView } from '@/components/TreeView'
import { Badge, Button, EmptyState, Input, Kbd, Panel, Spinner } from '@/components/ui'
import { api } from '@/lib/api'
import { NODE_TYPES, nodeStyle } from '@/lib/nodeStyle'
import {
  ancestorsOf, buildRows, emptyFilters, hasActiveFilters, namespaceMap,
  type TreeFilters,
} from '@/lib/tree'
import type { Access, NodeType, Selection, YangNode } from '@/lib/types'

interface Props {
  yangsetSlug: string
  onYangsetChange: (slug: string) => void
  selections: Selection[]
  onSelectionsChange: (selections: Selection[]) => void
  /** Set by the command palette to jump to a node. */
  jumpTo: number | null
  onJumpHandled: () => void
  registerNodes: (nodes: YangNode[]) => void
}

export function Explore({
  yangsetSlug, onYangsetChange, selections, onSelectionsChange,
  jumpTo, onJumpHandled, registerNodes,
}: Props) {
  const [filters, setFilters] = useState<TreeFilters>(emptyFilters)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [activeId, setActiveId] = useState<number | null>(null)
  const [cursor, setCursor] = useState(0)
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  // A reply needs far more room than the request that produced it, so the
  // panel can take over the whole column rather than fighting the node detail
  // for a 210px strip.
  const [requestMaximized, setRequestMaximized] = useState(false)

  const yangsets = useQuery({ queryKey: ['yangsets'], queryFn: api.listYangSets })
  const devices = useQuery({ queryKey: ['devices'], queryFn: api.listDevices })

  const tree = useQuery({
    queryKey: ['tree', yangsetSlug],
    queryFn: () => api.getTree(yangsetSlug),
    enabled: Boolean(yangsetSlug),
    staleTime: 5 * 60 * 1000,
  })

  const modules = useMemo(() => tree.data?.modules ?? [], [tree.data])

  // Expand the first level once a set loads, so the tree is never a blank wall.
  useEffect(() => {
    if (!modules.length) return
    const roots = modules.flatMap((m) => m.children.map((c) => c.id))
    setExpanded(new Set(roots.slice(0, 40)))
    setActiveId(null)
    setCursor(0)
  }, [modules])

  // Publish the flat node list so the command palette can search it.
  useEffect(() => {
    registerNodes(modules.flatMap((m) => m.children))
  }, [modules, registerNodes])

  const { rows, matchCount } = useMemo(
    () => buildRows(modules, expanded, filters),
    [modules, expanded, filters],
  )

  const nodeById = useMemo(() => {
    const map = new Map<number, YangNode>()
    const walk = (n: YangNode) => {
      map.set(n.id, n)
      n.children.forEach(walk)
    }
    modules.forEach((m) => m.children.forEach(walk))
    return map
  }, [modules])

  const idByPath = useMemo(() => {
    const map = new Map<string, number>()
    const walk = (n: YangNode) => {
      map.set(n.xpath_pfx, n.id)
      n.children.forEach(walk)
    }
    modules.forEach((m) => m.children.forEach(walk))
    return map
  }, [modules])

  const reveal = useCallback(
    (xpath: string) => {
      const id = idByPath.get(xpath)
      if (id === undefined) return
      setExpanded((prev) => new Set([...prev, ...ancestorsOf(modules, id)]))
      setActiveId(id)
    },
    [idByPath, modules],
  )

  const activeNode = activeId !== null ? (nodeById.get(activeId) ?? null) : null
  const namespaces = useMemo(() => namespaceMap(modules), [modules])
  const selectedPaths = useMemo(() => new Set(selections.map((s) => s.xpath)), [selections])

  // Handle a jump request from the palette: expand ancestors and scroll to it.
  useEffect(() => {
    if (jumpTo === null) return
    const path = ancestorsOf(modules, jumpTo)
    setExpanded((prev) => new Set([...prev, ...path]))
    setActiveId(jumpTo)
    onJumpHandled()
  }, [jumpTo, modules, onJumpHandled])

  // Once the row exists (after expanding), park the cursor on it.
  useEffect(() => {
    if (activeId === null) return
    const index = rows.findIndex((r) => r.node.id === activeId)
    if (index >= 0) setCursor(index)
  }, [activeId, rows])

  const toggleExpand = useCallback((id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelect = useCallback(
    (node: YangNode) => {
      const exists = selections.some((s) => s.xpath === node.xpath_pfx)
      if (exists) {
        onSelectionsChange(selections.filter((s) => s.xpath !== node.xpath_pfx))
        return
      }
      onSelectionsChange([
        ...selections,
        {
          xpath: node.xpath_pfx,
          value: '',
          operation: '',
          nodetype: node.nodetype,
          datatype: node.datatype ?? '',
          is_key: false,
        },
      ])
    },
    [selections, onSelectionsChange],
  )

  const expandAll = () => {
    const all = new Set<number>()
    const walk = (n: YangNode) => {
      if (n.children.length) all.add(n.id)
      n.children.forEach(walk)
    }
    modules.forEach((m) => m.children.forEach(walk))
    setExpanded(all)
  }

  if (!yangsets.data?.length) {
    return (
      <EmptyState
        icon={<Layers className="size-8" />}
        title="No YANG sets yet"
        hint="A YANG set is the group of modules you want to work with. Create one from a repository on the Models page."
      />
    )
  }

  const stats = tree.data?.stats
  const diagnostics = tree.data?.diagnostics ?? []
  const errorCount = diagnostics.filter((d) => d.level === 'error').length

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={yangsetSlug}
          onChange={(e) => onYangsetChange(e.target.value)}
          className="h-9 rounded-md border border-line bg-surface px-2 text-sm text-ink"
        >
          <option value="">Choose a YANG set…</option>
          {yangsets.data.map((ys) => (
            <option key={ys.slug} value={ys.slug}>
              {ys.name} ({ys.module_count})
            </option>
          ))}
        </select>

        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-faint" />
          <Input
            value={filters.query}
            onChange={(e) => setFilters((f) => ({ ...f, query: e.target.value }))}
            placeholder="Filter by name, path, type or description…"
            className="pl-8"
          />
          {filters.query ? (
            <button
              onClick={() => setFilters((f) => ({ ...f, query: '' }))}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-ink-faint hover:text-ink"
              aria-label="Clear filter"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>

        <Button size="sm" variant="ghost" onClick={expandAll} title="Expand all">
          <ChevronsUpDown className="size-3.5" />
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setExpanded(new Set())} title="Collapse all">
          <ChevronsDownUp className="size-3.5" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => tree.refetch()}
          loading={tree.isFetching}
          title="Re-parse this set"
        >
          <RefreshCw className="size-3.5" />
        </Button>
      </div>

      {/* Facet chips */}
      <div className="flex flex-wrap items-center gap-1.5">
        {NODE_TYPES.map((type) => {
          const on = filters.nodetypes.has(type)
          const style = nodeStyle(type)
          return (
            <button
              key={type}
              onClick={() =>
                setFilters((f) => {
                  const next = new Set(f.nodetypes)
                  if (next.has(type)) next.delete(type)
                  else next.add(type)
                  return { ...f, nodetypes: next }
                })
              }
              className={clsx(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                on ? 'border-brand bg-brand/15 text-ink' : 'border-line bg-surface text-ink-muted hover:bg-raised',
              )}
            >
              <span style={{ color: style.color }}>{style.glyph}</span>
              {type}
              {stats?.by_nodetype[type] ? (
                <span className="text-ink-faint">{stats.by_nodetype[type]}</span>
              ) : null}
            </button>
          )
        })}

        <span className="mx-1 h-4 w-px bg-line" />

        {(['all', 'read-write', 'read-only'] as const).map((value) => (
          <button
            key={value}
            onClick={() => setFilters((f) => ({ ...f, access: value as Access | 'all' }))}
            className={clsx(
              'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
              filters.access === value
                ? 'border-brand bg-brand/15 text-ink'
                : 'border-line bg-surface text-ink-muted hover:bg-raised',
            )}
          >
            {value === 'all' ? 'all' : value === 'read-write' ? 'config' : 'state'}
          </button>
        ))}

        <span className="flex-1" />

        {hasActiveFilters(filters) ? (
          <>
            <Badge className="border-brand/40 bg-brand/10 text-ink">
              {matchCount} match{matchCount === 1 ? '' : 'es'}
            </Badge>
            <Button size="sm" variant="ghost" onClick={() => setFilters(emptyFilters())}>
              Reset
            </Button>
          </>
        ) : stats ? (
          <span className="text-[11px] text-ink-faint">
            {stats.nodes.toLocaleString()} nodes · {stats.modules} module
            {stats.modules === 1 ? '' : 's'} · parsed in {stats.parse_ms} ms
          </span>
        ) : null}

        {errorCount > 0 ? (
          <button
            onClick={() => setShowDiagnostics((v) => !v)}
            className="inline-flex items-center gap-1 rounded-full border border-danger/40 bg-danger/10 px-2 py-0.5 text-[11px] text-danger"
          >
            <AlertTriangle className="size-3" />
            {errorCount} parse error{errorCount === 1 ? '' : 's'}
          </button>
        ) : null}
      </div>

      {showDiagnostics && diagnostics.length ? (
        <div className="max-h-40 overflow-y-auto rounded-md border border-line bg-surface p-2">
          {diagnostics.map((d, i) => (
            <p key={i} className="font-mono text-[11px] text-ink-muted">
              <span className={d.level === 'error' ? 'text-danger' : 'text-warn'}>{d.level}</span>{' '}
              {d.module}:{d.line} — {d.message}
            </p>
          ))}
        </div>
      ) : null}

      {/* Workspace. The tree is anchored narrow and the detail column takes
          the remainder — you navigate in the tree briefly but read and build
          requests in the panels, so extra width belongs on the right. Both
          dividers are draggable and remember where you put them. */}
      <Split
        direction="row"
        anchor="leading"
        storageKey="explore.tree"
        defaultSize={330}
        minLeading={200}
        minTrailing={420}
        className="flex-1"
      >
        <Panel className="group min-h-0 flex-1 overflow-hidden">
          {!yangsetSlug ? (
            <EmptyState
              icon={<Layers className="size-8" />}
              title="Choose a YANG set to begin"
              hint="Everything else follows from this: the tree, search, and the request builder all work on the set you pick."
            />
          ) : tree.isLoading ? (
            <Spinner label="Parsing modules…" />
          ) : tree.isError ? (
            <EmptyState
              icon={<FileWarning className="size-8" />}
              title="Could not parse this set"
              hint={String((tree.error as Error).message)}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              title="Nothing matches those filters"
              hint="Try a shorter search term, or reset the filters."
              action={<Button size="sm" onClick={() => setFilters(emptyFilters())}>Reset filters</Button>}
            />
          ) : (
            <TreeView
              rows={rows}
              expanded={expanded}
              onToggle={toggleExpand}
              activeId={activeId}
              onActivate={(node) => setActiveId(node.id)}
              selectedPaths={selectedPaths}
              onToggleSelect={toggleSelect}
              query={filters.query}
              cursor={cursor}
              onCursorChange={setCursor}
            />
          )}

          {/* The tree is keyboard-driven, but only while it has focus — which
              is invisible unless we say so. The legend lives here rather than
              on the panel the keys affect, and lights up when the keys are
              actually live. */}
          {rows.length > 0 ? (
            <div className="shrink-0 border-t border-line-soft px-2 py-1.5">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-ink-faint opacity-55 transition-opacity group-focus-within:text-ink-muted group-focus-within:opacity-100">
                <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
                <span className="flex items-center gap-1"><Kbd>→</Kbd><Kbd>←</Kbd> open / close</span>
                <span className="flex items-center gap-1"><Kbd>Enter</Kbd> inspect</span>
                <span className="flex items-center gap-1"><Kbd>Space</Kbd> add to request</span>
                <span className="flex-1" />
                <span className="hidden text-ink-faint group-focus-within:inline">keys active</span>
              </div>
            </div>
          ) : null}
        </Panel>

        {/* One Split, always mounted. Maximising collapses the node pane to its
            header rather than swapping to a different tree — swapping would
            remount the request builder and throw away the reply it just
            fetched, and hiding the pane outright leaves you wondering where it
            went. */}
        <Split
          direction="column"
          storageKey="explore.node-request"
          defaultSize={210}
          minLeading={160}
          minTrailing={120}
          collapseLeading={requestMaximized}
          className="flex-1"
        >
          <Panel
            title={
              requestMaximized ? (
                <span className="flex items-center gap-1.5">
                  Node
                  <span className="text-[11px] font-normal text-ink-faint">
                    {activeNode ? activeNode.name : 'nothing selected'}
                  </span>
                </span>
              ) : (
                'Node'
              )
            }
            className="min-h-0 flex-1 overflow-hidden"
            actions={
              requestMaximized ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setRequestMaximized(false)}
                  title="Show the node panel again"
                >
                  <ChevronsUpDown className="size-3.5" />
                  Expand
                </Button>
              ) : null
            }
          >
            <NodeDetail
              node={activeNode}
              isSelected={activeNode ? selectedPaths.has(activeNode.xpath_pfx) : false}
              onToggleSelect={toggleSelect}
            />
          </Panel>

          <Panel
            title="Request"
            className="min-h-0 flex-1 overflow-hidden"
            actions={
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setRequestMaximized((v) => !v)}
                title={requestMaximized ? 'Restore the node panel' : 'Give the request and reply the full column'}
              >
                {requestMaximized ? (
                  <Minimize2 className="size-3.5" />
                ) : (
                  <Maximize2 className="size-3.5" />
                )}
              </Button>
            }
          >
            <RequestBuilder
              selections={selections}
              onChange={onSelectionsChange}
              namespaces={namespaces}
              devices={devices.data ?? []}
              onReveal={reveal}
              onRan={() => setRequestMaximized(true)}
              yangsetSlug={yangsetSlug}
            />
          </Panel>
        </Split>
      </Split>
    </div>
  )
}

export type { NodeType }
