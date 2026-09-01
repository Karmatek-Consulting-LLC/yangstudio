/**
 * Browse and selectively download the schemas a device advertises.
 *
 * A device typically advertises hundreds of modules, most of which you do not
 * want. Selection is per-module, with family filters to cut the list down
 * first, and the download target is picked — or created — without leaving here.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Download, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { RestconfProbe } from './RestconfProbe'
import { Badge, Button, EmptyState, Input, Spinner } from './ui'
import { api, ApiError } from '@/lib/api'
import { FAMILY_LABELS, familyCounts, moduleFamily, type FamilyId } from '@/lib/moduleFamily'
import type { Capabilities, Transport } from '@/lib/types'

/** Sentinel value for the picker's "create one" option. */
const NEW_REPOSITORY = '__new__'

export function CapabilityBrowser({
  capabilities, deviceSlug, transport = 'netconf', onRepositoriesChanged,
}: {
  capabilities: Capabilities
  deviceSlug: string
  transport?: Transport
  onRepositoriesChanged: () => void
}) {
  const [filter, setFilter] = useState('')
  const [family, setFamily] = useState<FamilyId | 'all'>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [repository, setRepository] = useState('')
  const [started, setStarted] = useState('')
  const [error, setError] = useState('')
  const [creatingRepo, setCreatingRepo] = useState(false)
  const [newRepoName, setNewRepoName] = useState('')
  const [repoError, setRepoError] = useState('')
  const qc = useQueryClient()

  const repositories = useQuery({ queryKey: ['repositories'], queryFn: api.listRepositories })

  const families = useMemo(
    () => familyCounts(capabilities.modules.map((m) => m.name)),
    [capabilities.modules],
  )

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return capabilities.modules.filter((m) => {
      if (family !== 'all' && moduleFamily(m.name) !== family) return false
      if (needle && !m.name.toLowerCase().includes(needle)) return false
      return true
    })
  }, [capabilities.modules, filter, family])

  // "Select all" applies to what is currently visible, not the whole list —
  // selecting 507 hidden modules from a filtered view would be a nasty surprise.
  const visibleNames = useMemo(() => visible.map((m) => m.name), [visible])
  const allVisibleSelected =
    visibleNames.length > 0 && visibleNames.every((n) => selected.has(n))

  const toggleAllVisible = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allVisibleSelected) visibleNames.forEach((n) => next.delete(n))
      else visibleNames.forEach((n) => next.add(n))
      return next
    })
  }

  const createRepository = useMutation({
    mutationFn: (name: string) => api.createRepository(name),
    onSuccess: (created) => {
      // Select it straight away so the download can proceed in one step.
      qc.invalidateQueries({ queryKey: ['repositories'] })
      setRepository(created.slug)
      setCreatingRepo(false)
      setNewRepoName('')
      setRepoError('')
      onRepositoriesChanged()
    },
    onError: (e: unknown) =>
      setRepoError(e instanceof ApiError ? e.message : String(e)),
  })

  const submitNewRepo = () => {
    const name = newRepoName.trim()
    if (name) createRepository.mutate(name)
  }

  const download = useMutation({
    mutationFn: () =>
      api.downloadSchemas(deviceSlug, [...selected], repository, transport),
    onSuccess: (job) => {
      // The work now lives in the task drawer, so this panel is free again.
      setStarted(job.label)
      setError('')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['jobs'] })
      onRepositoriesChanged()
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : String(e)),
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Session summary */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line-soft p-2">
        {/* NETCONF has a session to name; RESTCONF has the library it read. */}
        <Badge className="border-ok/40 bg-ok/10 text-ok">
          {capabilities.session_id !== null
            ? `session ${capabilities.session_id}`
            : (capabilities.yang_library ?? 'restconf')}
        </Badge>
        <Badge>{capabilities.module_count} modules</Badge>
        {/* Listing a module and being able to fetch its source are different
            things: some devices publish a library with no download URLs. Say
            so here rather than letting the download discover it. */}
        {capabilities.downloadable !== undefined
          && capabilities.downloadable < capabilities.module_count ? (
          <Badge
            className="border-warn/40 bg-warn/10 text-warn"
            title={
              capabilities.downloadable === 0
                ? 'The device lists these modules but publishes no download '
                  + 'URL for any of them. Fetch the source over NETCONF, or '
                  + 'upload the models to a repository yourself.'
                : 'Some modules have no download URL and cannot be fetched '
                  + 'over RESTCONF.'
            }
          >
            {capabilities.downloadable} downloadable
          </Badge>
        ) : null}
        {capabilities.supports_candidate ? <Badge>candidate</Badge> : null}
        {capabilities.supports_startup ? <Badge>startup</Badge> : null}
        {capabilities.supports_validate ? <Badge>validate</Badge> : null}
      </div>

      <RestconfProbe deviceSlug={deviceSlug} />

      {/* Family filters */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line-soft px-2 py-1.5">
        <button
          onClick={() => setFamily('all')}
          className={clsx(
            'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
            family === 'all'
              ? 'border-brand bg-brand/15 text-ink'
              : 'border-line bg-surface text-ink-muted hover:bg-raised',
          )}
        >
          All {capabilities.modules.length}
        </button>
        {families.map(({ id, count }) => (
          <button
            key={id}
            onClick={() => setFamily(id)}
            className={clsx(
              'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
              family === id
                ? 'border-brand bg-brand/15 text-ink'
                : 'border-line bg-surface text-ink-muted hover:bg-raised',
              // MIBs are rarely wanted; de-emphasise unless chosen.
              id === 'mib' && family !== id && 'opacity-60',
            )}
          >
            {FAMILY_LABELS[id]} {count}
          </button>
        ))}
      </div>

      {/* Search + select-all */}
      <div className="flex items-center gap-2 border-b border-line-soft p-2">
        <button
          onClick={toggleAllVisible}
          disabled={visibleNames.length === 0}
          title={allVisibleSelected ? 'Deselect these' : `Select these ${visibleNames.length}`}
          className={clsx(
            'grid size-4 shrink-0 place-items-center rounded-[3px] border text-[9px] font-bold',
            allVisibleSelected
              ? 'border-brand bg-brand text-canvas'
              : 'border-line text-transparent hover:border-brand',
          )}
        >
          ✓
        </button>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-faint" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter advertised modules…"
            className="h-8 pl-8 text-xs"
          />
        </div>
        <Badge>{visible.length} shown</Badge>
        {selected.size ? (
          <Badge className="border-brand/40 bg-brand/10 text-ink">{selected.size} selected</Badge>
        ) : null}
      </div>

      {/* Module list */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {visible.length === 0 ? (
          <EmptyState title="No modules match" hint="Try a different filter or family." />
        ) : (
          visible.map((m) => {
            const isSelected = selected.has(m.name)
            return (
              <button
                key={m.name + m.revision}
                onClick={() =>
                  setSelected((prev) => {
                    const next = new Set(prev)
                    if (next.has(m.name)) next.delete(m.name)
                    else next.add(m.name)
                    return next
                  })
                }
                className={clsx(
                  'flex w-full items-center gap-2 border-b border-line-soft/50 px-2 py-1.5 text-left',
                  isSelected ? 'bg-brand/10' : 'hover:bg-raised',
                )}
              >
                <span
                  className={clsx(
                    'grid size-4 shrink-0 place-items-center rounded-[3px] border text-[9px] font-bold',
                    isSelected ? 'border-brand bg-brand text-canvas' : 'border-line text-transparent',
                  )}
                >
                  ✓
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{m.name}</span>
                {m.revision ? (
                  <span className="shrink-0 font-mono text-[10px] text-ink-faint">{m.revision}</span>
                ) : null}
                {m.features.length ? (
                  <Badge title={m.features.join(', ')}>{m.features.length} feat</Badge>
                ) : null}
                {m.deviations.length ? (
                  <Badge className="border-warn/40 text-warn" title={m.deviations.join(', ')}>
                    {m.deviations.length} dev
                  </Badge>
                ) : null}
              </button>
            )
          })
        )}
      </div>

      {/* Download bar */}
      <div className="shrink-0 border-t border-line-soft p-2">
        <div className="flex items-center gap-2">
          <select
            value={repository}
            onChange={(e) => {
              if (e.target.value === NEW_REPOSITORY) {
                setCreatingRepo(true)
                setRepoError('')
                return
              }
              setRepository(e.target.value)
            }}
            className="h-8 min-w-0 flex-1 rounded border border-line bg-surface px-1.5 text-xs text-ink"
          >
            <option value="">Save into which repository?…</option>
            {repositories.data?.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name} ({r.module_count})
              </option>
            ))}
            <option value={NEW_REPOSITORY}>+ New repository…</option>
          </select>
          <Button
            size="sm"
            variant="primary"
            disabled={selected.size === 0 || !repository}
            loading={download.isPending}
            onClick={() => download.mutate()}
          >
            <Download className="size-3" />
            Download {selected.size || ''}
          </Button>
          {selected.size ? (
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
          ) : null}
        </div>

        {creatingRepo ? (
          <div className="mt-1.5 flex items-center gap-1.5">
            <Input
              autoFocus
              value={newRepoName}
              onChange={(e) => setNewRepoName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitNewRepo()
                if (e.key === 'Escape') {
                  setCreatingRepo(false)
                  setRepoError('')
                }
              }}
              placeholder="New repository name, e.g. IOS-XE 17.9 schemas"
              className="h-8 text-xs"
            />
            <Button
              size="sm"
              variant="primary"
              loading={createRepository.isPending}
              disabled={!newRepoName.trim()}
              onClick={submitNewRepo}
            >
              Create
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setCreatingRepo(false)
                setRepoError('')
              }}
            >
              Cancel
            </Button>
          </div>
        ) : null}

        {repoError ? (
          <p className="mt-1.5 flex items-start gap-1 text-[11px] text-danger">
            <AlertTriangle className="mt-px size-3 shrink-0" />
            {repoError}
          </p>
        ) : null}

        {!repositories.data?.length && !creatingRepo ? (
          <p className="mt-1.5 text-[11px] text-ink-faint">
            No repositories yet —{' '}
            <button
              onClick={() => {
                setCreatingRepo(true)
                setRepoError('')
              }}
              className="text-brand underline underline-offset-2 hover:opacity-80"
            >
              create one here
            </button>{' '}
            to download into. Your selection is kept.
          </p>
        ) : selected.size === 0 && !creatingRepo ? (
          <p className="mt-1.5 text-[11px] text-ink-faint">
            Tick the modules you want — anything they import is fetched with them.
            Downloading all {capabilities.modules.length} takes a while and pulls in{' '}
            {families.find((f) => f.id === 'mib')?.count ?? 0} SNMP MIBs you probably don't need.
          </p>
        ) : null}


        {error ? (
          <p className="mt-1.5 flex items-start gap-1 text-[11px] text-danger">
            <AlertTriangle className="mt-px size-3 shrink-0" />
            {error}
          </p>
        ) : null}

        {started ? (
          <p className="mt-1.5 flex items-start gap-1 text-[11px] text-ok">
            <CheckCircle2 className="mt-px size-3 shrink-0" />
            Started “{started}”. It runs in the background — follow it in the task bar
            at the bottom, which will offer to make a set from these modules when it
            finishes. You can leave this page.
          </p>
        ) : null}
      </div>
    </div>
  )
}

export function CapabilityPlaceholder({ state }: { state: 'idle' | 'loading' }) {
  return state === 'loading' ? <Spinner label="Opening NETCONF session…" /> : null
}
