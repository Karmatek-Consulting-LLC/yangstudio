/** Repositories and YANG sets: getting models in, then choosing what to load. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  CheckCircle2, Database, FolderGit2, Layers, Plus, Search, Trash2, Upload, Wand2,
} from 'lucide-react'
import { useMemo, useRef, useState } from 'react'

import { Split } from '@/components/Split'
import { Badge, Button, EmptyState, Input, Panel, Spinner } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { ModuleInfo } from '@/lib/types'

export function Models({ onExplore }: { onExplore: (slug: string) => void }) {
  const qc = useQueryClient()
  const [repoSlug, setRepoSlug] = useState('')
  const [moduleFilter, setModuleFilter] = useState('')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  // Sets created from a device get a generic name; renaming is the first thing
  // most people want to do with one.
  const [renaming, setRenaming] = useState<string | null>(null)
  const [draftName, setDraftName] = useState('')
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const repos = useQuery({ queryKey: ['repositories'], queryFn: api.listRepositories })
  const yangsets = useQuery({ queryKey: ['yangsets'], queryFn: api.listYangSets })
  const repo = useQuery({
    queryKey: ['repository', repoSlug],
    queryFn: () => api.getRepository(repoSlug),
    enabled: Boolean(repoSlug),
  })

  const notify = (kind: 'ok' | 'error', text: string) => {
    setMessage({ kind, text })
    setTimeout(() => setMessage(null), 5000)
  }
  const fail = (error: unknown) =>
    notify('error', error instanceof ApiError ? error.message : String(error))

  const createRepo = useMutation({
    mutationFn: (name: string) => api.createRepository(name),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ['repositories'] })
      setRepoSlug(created.slug)
      notify('ok', `Repository “${created.name}” created`)
    },
    onError: fail,
  })

  const upload = useMutation({
    mutationFn: (files: File[]) => api.uploadToRepository(repoSlug, files),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['repository', repoSlug] })
      qc.invalidateQueries({ queryKey: ['repositories'] })
      const skipped = result.skipped.length ? `, ${result.skipped.length} skipped` : ''
      notify('ok', `Added ${result.added.length} module${result.added.length === 1 ? '' : 's'}${skipped}`)
    },
    onError: fail,
  })

  const importGit = useMutation({
    mutationFn: (vars: { url: string; subdirectory: string }) =>
      api.importGit(repoSlug, vars.url, '', vars.subdirectory),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['repository', repoSlug] })
      qc.invalidateQueries({ queryKey: ['repositories'] })
      notify('ok', `Imported ${result.copied} files — ${result.module_count} modules indexed`)
    },
    onError: fail,
  })

  const createSet = useMutation({
    mutationFn: async (name: string) => {
      const modules = [...picked].map((key) => {
        const [moduleName, revision = ''] = key.split('@')
        return { name: moduleName, revision }
      })
      const created = await api.createYangSet(name, repoSlug, modules)
      // Pull in imports straight away: a set that cannot resolve its imports
      // fails to parse, and that is the single most common first-run problem.
      const resolved = await api.resolveDependencies(created.slug)
      return { created, resolved }
    },
    onSuccess: ({ created, resolved }) => {
      qc.invalidateQueries({ queryKey: ['yangsets'] })
      setPicked(new Set())
      notify(
        'ok',
        `Created “${created.name}”${resolved.added ? ` and pulled in ${resolved.added} dependenc${resolved.added === 1 ? 'y' : 'ies'}` : ''}`,
      )
    },
    onError: fail,
  })

  const renameSet = useMutation({
    mutationFn: (vars: { slug: string; name: string }) =>
      api.updateYangSet(vars.slug, { name: vars.name }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ['yangsets'] })
      setRenaming(null)
      notify('ok', `Renamed to “${updated.name}”`)
    },
    onError: (error) => {
      setRenaming(null)
      fail(error)
    },
  })

  const deleteSet = useMutation({
    mutationFn: (slug: string) => api.deleteYangSet(slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['yangsets'] }),
    onError: fail,
  })

  const deleteRepo = useMutation({
    mutationFn: (slug: string) => api.deleteRepository(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['repositories'] })
      setRepoSlug('')
    },
    onError: fail,
  })

  const filteredModules = useMemo(() => {
    const modules = repo.data?.modules ?? []
    const needle = moduleFilter.trim().toLowerCase()
    if (!needle) return modules
    return modules.filter(
      (m) =>
        m.name.toLowerCase().includes(needle) ||
        m.namespace.toLowerCase().includes(needle) ||
        m.organization.toLowerCase().includes(needle),
    )
  }, [repo.data, moduleFilter])

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      {message ? (
        <div
          className={clsx(
            'rounded-md border px-3 py-2 text-xs',
            message.kind === 'ok'
              ? 'border-ok/40 bg-ok/10 text-ok'
              : 'border-danger/40 bg-danger/10 text-danger',
          )}
        >
          {message.text}
        </div>
      ) : null}

      <Split
        direction="row"
        anchor="leading"
        storageKey="models.repos"
        defaultSize={280}
        minLeading={200}
        minTrailing={520}
        className="flex-1"
      >
        {/* Repositories */}
        <Panel
          title="Repositories"
          className="min-h-0 flex-1 overflow-hidden"
          actions={
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const name = window.prompt('Repository name')
                if (name?.trim()) createRepo.mutate(name.trim())
              }}
            >
              <Plus className="size-3.5" />
            </Button>
          }
        >
          <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
            {repos.isLoading ? <Spinner /> : null}
            {repos.data?.length === 0 ? (
              <EmptyState
                icon={<Database className="size-7" />}
                title="No repositories"
                hint="A repository is a folder of .yang files. Create one, then upload files or import from git."
              />
            ) : null}
            {repos.data?.map((r) => (
              <button
                key={r.slug}
                onClick={() => setRepoSlug(r.slug)}
                className={clsx(
                  'group flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm',
                  repoSlug === r.slug ? 'bg-brand/15 text-ink' : 'text-ink-muted hover:bg-raised',
                )}
              >
                <Database className="size-3.5 shrink-0 text-ink-faint" />
                <span className="min-w-0 flex-1 truncate">{r.name}</span>
                <Badge>{r.module_count}</Badge>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm(`Delete repository “${r.name}” and all its files?`)) {
                      deleteRepo.mutate(r.slug)
                    }
                  }}
                  className="hidden rounded p-0.5 text-ink-faint hover:text-danger group-hover:block"
                >
                  <Trash2 className="size-3" />
                </span>
              </button>
            ))}
          </div>
        </Panel>

        <Split
          direction="row"
          storageKey="models.yangsets"
          defaultSize={300}
          minLeading={320}
          minTrailing={220}
          className="flex-1"
        >
          {/* Modules in the selected repository */}
          <Panel
          title={repo.data ? `Modules in ${repo.data.name}` : 'Modules'}
          className="min-h-0 flex-1 overflow-hidden"
          actions={
            repoSlug ? (
              <>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept=".yang"
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? [])
                    if (files.length) upload.mutate(files)
                    e.target.value = ''
                  }}
                />
                <Button size="sm" variant="ghost" loading={upload.isPending} onClick={() => fileRef.current?.click()}>
                  <Upload className="size-3.5" /> Upload
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={importGit.isPending}
                  onClick={() => {
                    const url = window.prompt(
                      'Git repository URL',
                      'https://github.com/YangModels/yang',
                    )
                    if (!url?.trim()) return
                    const subdirectory = window.prompt(
                      'Subdirectory to import (blank = whole repo)',
                      'standard/ietf/RFC',
                    )
                    importGit.mutate({ url: url.trim(), subdirectory: subdirectory?.trim() ?? '' })
                  }}
                >
                  <FolderGit2 className="size-3.5" /> Import
                </Button>
              </>
            ) : null
          }
        >
          {!repoSlug ? (
            <EmptyState title="Select a repository" hint="Its modules will be listed here." />
          ) : repo.isLoading ? (
            <Spinner label="Indexing modules…" />
          ) : (
            <>
              <div className="flex items-center gap-2 border-b border-line-soft p-2">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-faint" />
                  <Input
                    value={moduleFilter}
                    onChange={(e) => setModuleFilter(e.target.value)}
                    placeholder="Filter modules…"
                    className="h-8 pl-8 text-xs"
                  />
                </div>
                <Badge>{filteredModules.length} shown</Badge>
                {picked.size ? (
                  <Button
                    size="sm"
                    variant="primary"
                    loading={createSet.isPending}
                    onClick={() => {
                      const name = window.prompt(`Name for a set of ${picked.size} module(s)`)
                      if (name?.trim()) createSet.mutate(name.trim())
                    }}
                  >
                    <Wand2 className="size-3" /> Create set ({picked.size})
                  </Button>
                ) : null}
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto">
                {filteredModules.length === 0 ? (
                  <EmptyState
                    title="No modules here yet"
                    hint="Upload .yang files, or import them from a git repository."
                  />
                ) : (
                  filteredModules.map((m) => (
                    <ModuleRow
                      key={m.key + m.path}
                      module={m}
                      checked={picked.has(m.key)}
                      onToggle={() =>
                        setPicked((prev) => {
                          const next = new Set(prev)
                          if (next.has(m.key)) next.delete(m.key)
                          else next.add(m.key)
                          return next
                        })
                      }
                    />
                  ))
                )}
              </div>
            </>
          )}
        </Panel>

          {/* YANG sets */}
          <Panel title="YANG sets" className="min-h-0 flex-1 overflow-hidden">
          <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
            {yangsets.data?.length === 0 ? (
              <EmptyState
                icon={<Layers className="size-7" />}
                title="No sets yet"
                hint="Tick modules in the middle column, then create a set. Imports are pulled in automatically."
              />
            ) : null}
            {yangsets.data?.map((ys) => (
              <div
                key={ys.slug}
                className="group mb-1 rounded border border-line-soft bg-raised/40 p-2"
              >
                <div className="flex items-center gap-1.5">
                  <Layers className="size-3.5 shrink-0 text-ink-faint" />
                  {renaming === ys.slug ? (
                    <Input
                      autoFocus
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onBlur={() => setRenaming(null)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && draftName.trim()) {
                          renameSet.mutate({ slug: ys.slug, name: draftName.trim() })
                        }
                        if (e.key === 'Escape') setRenaming(null)
                      }}
                      className="h-6 flex-1 px-1.5 text-sm"
                    />
                  ) : (
                    <button
                      onClick={() => {
                        setRenaming(ys.slug)
                        setDraftName(ys.name)
                      }}
                      title="Rename this set"
                      className="min-w-0 flex-1 truncate text-left text-sm text-ink hover:text-brand"
                    >
                      {ys.name}
                    </button>
                  )}
                  <Badge>{ys.module_count}</Badge>
                </div>
                <p className="mt-0.5 truncate text-[11px] text-ink-faint">from {ys.repository}</p>
                <div className="mt-1.5 flex gap-1">
                  <Button size="sm" variant="primary" className="flex-1" onClick={() => onExplore(ys.slug)}>
                    Explore
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm(`Delete set “${ys.name}”?`)) deleteSet.mutate(ys.slug)
                    }}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
          </Panel>
        </Split>
      </Split>
    </div>
  )
}

function ModuleRow({
  module, checked, onToggle,
}: { module: ModuleInfo; checked: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={clsx(
        'flex w-full items-center gap-2 border-b border-line-soft/50 px-2 py-1.5 text-left',
        checked ? 'bg-brand/10' : 'hover:bg-raised',
      )}
    >
      <span
        className={clsx(
          'grid size-4 shrink-0 place-items-center rounded-[3px] border text-[9px] font-bold',
          checked ? 'border-brand bg-brand text-canvas' : 'border-line text-transparent',
        )}
      >
        ✓
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5">
          <span className="truncate text-[13px] text-ink">{module.name}</span>
          {module.revision ? (
            <span className="shrink-0 font-mono text-[10px] text-ink-faint">{module.revision}</span>
          ) : null}
          {module.kind === 'submodule' ? <Badge>submodule</Badge> : null}
          {module.errors.length ? (
            <Badge className="border-danger/40 text-danger">error</Badge>
          ) : null}
        </p>
        <p className="truncate text-[10.5px] text-ink-faint">
          {module.namespace || module.organization || '—'}
        </p>
      </div>
      {module.imports.length ? (
        <Badge title={`imports: ${module.imports.join(', ')}`}>
          {module.imports.length} imp
        </Badge>
      ) : null}
      {checked ? <CheckCircle2 className="size-3.5 shrink-0 text-brand" /> : null}
    </button>
  )
}
