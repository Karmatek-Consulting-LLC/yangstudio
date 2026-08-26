/**
 * A collapsible drawer of background tasks, pinned to the bottom of the window.
 *
 * Long work (fetching a few hundred schemas is minutes) runs server-side as a
 * job, so it survives navigating away or reloading the page. The drawer is the
 * one place that work is visible from, whichever page you are on.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Ban, CheckCircle2, ChevronDown, ChevronUp, Layers, Loader2,
  Trash2, XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { MissingImports, missingImports } from './MissingImports'
import { Badge, Button } from './ui'
import { api, ApiError } from '@/lib/api'
import { isJobActive, type Job, type SetCreated } from '@/lib/types'

const OPEN_KEY = 'yangstudio.tasks.open'

export function TaskDrawer({ onOpenSet }: { onOpenSet?: (slug: string) => void }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    try {
      setOpen(localStorage.getItem(OPEN_KEY) === '1')
    } catch {
      /* Storage is a convenience here; default to collapsed. */
    }
  }, [])

  const toggle = () => {
    setOpen((wasOpen) => {
      const next = !wasOpen
      try {
        localStorage.setItem(OPEN_KEY, next ? '1' : '0')
      } catch { /* ignore */ }
      return next
    })
  }

  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: api.listJobs,
    // Poll only while something is in flight; a finished list is static until
    // a new job is started, and starting one invalidates this query.
    refetchInterval: (query) =>
      (query.state.data ?? []).some(isJobActive) ? 1000 : false,
  })

  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })

  const clear = useMutation({
    mutationFn: () => api.clearFinishedJobs(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })

  // When a download finishes, the repository it wrote into has new modules.
  const finishedCount = (jobs.data ?? []).filter((j) => !isJobActive(j)).length
  useEffect(() => {
    if (finishedCount > 0) {
      qc.invalidateQueries({ queryKey: ['repositories'] })
    }
  }, [finishedCount, qc])

  const list = jobs.data ?? []
  if (list.length === 0) return null      // Nothing to show, no chrome.

  const active = list.filter(isJobActive)
  const failed = list.filter((j) => j.status === 'failed').length
  const newest = list[0]

  return (
    <div className="shrink-0 border-t border-line bg-surface">
      {/* Collapsed bar — always present once there are jobs. */}
      <button
        onClick={toggle}
        className="flex h-8 w-full items-center gap-2 px-3 text-left hover:bg-raised"
        aria-expanded={open}
      >
        {active.length ? (
          <Loader2 className="size-3.5 shrink-0 animate-spin text-brand" />
        ) : failed ? (
          <AlertTriangle className="size-3.5 shrink-0 text-danger" />
        ) : (
          <CheckCircle2 className="size-3.5 shrink-0 text-ok" />
        )}

        <span className="text-[12px] font-medium text-ink">
          {active.length
            ? `${active.length} task${active.length === 1 ? '' : 's'} running`
            : 'Tasks'}
        </span>

        {/* A one-line summary of the newest job so the bar is useful closed. */}
        <span className="min-w-0 flex-1 truncate text-[11px] text-ink-faint">
          {active.length
            ? `${newest.current || newest.label} — ${newest.done}/${newest.total}`
            : newest.message || newest.label}
        </span>

        {active.length ? (
          <span className="hidden w-28 shrink-0 sm:block">
            <ProgressBar percent={newest.percent} />
          </span>
        ) : null}

        <Badge>{list.length}</Badge>
        {open ? (
          <ChevronDown className="size-3.5 shrink-0 text-ink-faint" />
        ) : (
          <ChevronUp className="size-3.5 shrink-0 text-ink-faint" />
        )}
      </button>

      {/* Expanded list */}
      {open ? (
        <div className="max-h-64 overflow-y-auto border-t border-line-soft">
          <div className="flex items-center gap-2 px-3 py-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
              Background tasks
            </span>
            <span className="flex-1" />
            {list.some((j) => !isJobActive(j)) ? (
              <Button size="sm" variant="ghost" onClick={() => clear.mutate()}>
                <Trash2 className="size-3" /> Clear finished
              </Button>
            ) : null}
          </div>
          {list.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onCancel={() => cancel.mutate(job.id)}
              onOpenSet={onOpenSet}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function ProgressBar({ percent }: { percent: number }) {
  return (
    <span className="block h-1 w-full overflow-hidden rounded-full bg-line">
      <span
        className="block h-full rounded-full bg-brand transition-[width] duration-300"
        style={{ width: `${percent}%` }}
      />
    </span>
  )
}

function JobRow({
  job, onCancel, onOpenSet,
}: { job: Job; onCancel: () => void; onOpenSet?: (slug: string) => void }) {
  const active = isJobActive(job)
  const errorCount = Object.keys(job.errors).length

  // A finished download already knows exactly which modules it fetched and
  // where they went, so it can become a set without asking again.
  const downloaded = (job.result?.downloaded as string[] | undefined) ?? []
  const repository = (job.result?.repository as string | undefined) ?? ''
  const canMakeSet =
    job.kind === 'download-schemas' &&
    job.status === 'succeeded' &&
    downloaded.length > 0 &&
    Boolean(repository)

  return (
    <div className="border-b border-line-soft/50 px-3 py-2 last:border-0">
      <div className="flex items-center gap-2">
        <StatusIcon job={job} />
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{job.label}</span>
        {job.total ? (
          <span className="shrink-0 font-mono text-[10.5px] text-ink-faint">
            {job.done}/{job.total}
          </span>
        ) : null}
        {active ? (
          <Button size="sm" variant="ghost" onClick={onCancel} title="Cancel this task">
            <Ban className="size-3" />
          </Button>
        ) : null}
      </div>

      {active ? (
        <div className="mt-1.5 flex items-center gap-2">
          <span className="flex-1"><ProgressBar percent={job.percent} /></span>
          <span className="w-9 shrink-0 text-right font-mono text-[10px] text-ink-faint">
            {job.percent}%
          </span>
        </div>
      ) : null}

      <p className="mt-0.5 truncate text-[11px] text-ink-faint">
        {active ? job.current || 'Starting…' : job.message}
      </p>

      {canMakeSet ? (
        <SetHandoff
          label={job.label}
          modules={downloaded}
          repository={repository}
          deviceSlug={(job.result?.device as string | undefined) ?? undefined}
          onOpenSet={onOpenSet}
        />
      ) : null}

      {errorCount ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-[10.5px] text-warn">
            {errorCount} module{errorCount === 1 ? '' : 's'} failed
          </summary>
          <div className="mt-1 max-h-24 overflow-y-auto">
            {Object.entries(job.errors).map(([name, message]) => (
              <p
                key={name}
                title={message}
                className="truncate font-mono text-[10px] text-ink-faint"
              >
                {name}: {message}
              </p>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  )
}

function StatusIcon({ job }: { job: Job }) {
  if (isJobActive(job)) return <Loader2 className="size-3.5 shrink-0 animate-spin text-brand" />
  if (job.status === 'succeeded') return <CheckCircle2 className="size-3.5 shrink-0 text-ok" />
  if (job.status === 'cancelled') return <Ban className="size-3.5 shrink-0 text-ink-faint" />
  return <XCircle className="size-3.5 shrink-0 text-danger" />
}


/**
 * The bridge from "files downloaded" to "something you can explore".
 *
 * A repository is storage; a set is a coherent, parseable selection. The
 * download knows both the modules and the destination, so the only thing
 * missing is a name.
 */
function SetHandoff({
  label, modules, repository, deviceSlug, onOpenSet,
}: {
  label: string
  modules: string[]
  repository: string
  deviceSlug?: string
  onOpenSet?: (slug: string) => void
}) {
  const qc = useQueryClient()
  const [result, setResult] = useState<SetCreated | null>(null)
  const [error, setError] = useState('')

  const create = useMutation({
    mutationFn: () => {
      // "12 schemas from edge-router-1 → repo" reads better as just the device name.
      const source = label.split(' from ')[1]?.split(' →')[0] ?? 'download'
      return api.createYangSetFromModules(source, repository, modules)
    },
    onSuccess: (created) => {
      setResult(created)
      setError('')
      qc.invalidateQueries({ queryKey: ['yangsets'] })
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : String(e)),
  })

  const missing = result ? missingImports(result.validation) : []

  if (result) {
    return (
      <div className="mt-1.5 rounded border border-line bg-raised/50 p-2">
        <p className="flex items-center gap-1.5 text-[11px]">
          <Layers className="size-3 shrink-0 text-brand" />
          <span className="text-ink">
            Set “{result.name}” · {result.module_count} modules
            {result.dependencies_added
              ? ` (${result.dependencies_added} pulled in)`
              : ''}
          </span>
          <span className="flex-1" />
          {onOpenSet ? (
            <Button size="sm" variant="primary" onClick={() => onOpenSet(result.slug)}>
              Explore
            </Button>
          ) : null}
        </p>
        {missing.length ? (
          <MissingImports
            validation={result.validation}
            repository={repository}
            deviceSlug={deviceSlug}
          />
        ) : null}
      </div>
    )
  }

  return (
    <div className="mt-1.5 flex items-center gap-2">
      <Button size="sm" variant="outline" loading={create.isPending} onClick={() => create.mutate()}>
        <Layers className="size-3" /> Create set from these {modules.length}
      </Button>
      {error ? <span className="text-[10.5px] text-danger">{error}</span> : null}
    </div>
  )
}
