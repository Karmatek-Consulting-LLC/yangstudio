/**
 * Confirmation shown after a set is created, with the name editable in place.
 *
 * Sets built from a device are named after it, which is a reasonable default
 * and almost never what someone wants to keep. Renaming here costs one click,
 * and ignoring it costs none.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Layers, Pencil } from 'lucide-react'
import { useState } from 'react'

import { MissingImports } from './MissingImports'
import { Button, Input } from './ui'
import { api, ApiError } from '@/lib/api'
import type { SetCreated as SetCreatedResult } from '@/lib/types'

export function SetCreated({
  created, repository, deviceSlug, onOpenSet,
}: {
  created: SetCreatedResult
  repository: string
  deviceSlug?: string
  onOpenSet?: (slug: string) => void
}) {
  const qc = useQueryClient()
  const [name, setName] = useState(created.name)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(created.name)
  const [error, setError] = useState('')

  const rename = useMutation({
    mutationFn: (next: string) => api.updateYangSet(created.slug, { name: next }),
    onSuccess: (updated) => {
      setName(updated.name)
      setEditing(false)
      setError('')
      qc.invalidateQueries({ queryKey: ['yangsets'] })
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : String(e)),
  })

  const save = () => {
    const next = draft.trim()
    if (!next || next === name) {
      setEditing(false)
      return
    }
    rename.mutate(next)
  }

  return (
    <div className="mt-1.5 rounded border border-line bg-raised/50 p-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <Layers className="size-3 shrink-0 text-brand" />

        {editing ? (
          <>
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') save()
                if (e.key === 'Escape') setEditing(false)
              }}
              placeholder="Name this set"
              className="h-6 min-w-0 flex-1 px-1.5 text-[12px]"
            />
            <Button size="sm" variant="primary" loading={rename.isPending} onClick={save}>
              <Check className="size-3" />
            </Button>
          </>
        ) : (
          <>
            <span className="text-[11px] text-ink">
              Set “{name}” · {created.module_count} modules
              {created.dependencies_added
                ? ` (${created.dependencies_added} pulled in)`
                : ''}
            </span>
            <button
              onClick={() => {
                setDraft(name)
                setEditing(true)
              }}
              title="Rename this set"
              className="rounded p-0.5 text-ink-faint hover:bg-overlay hover:text-ink"
            >
              <Pencil className="size-3" />
            </button>
            <span className="flex-1" />
            {onOpenSet ? (
              <Button size="sm" variant="primary" onClick={() => onOpenSet(created.slug)}>
                Explore
              </Button>
            ) : null}
          </>
        )}
      </div>

      {error ? <p className="mt-1 text-[10.5px] text-danger">{error}</p> : null}

      {created.not_in_repository?.length ? (
        <p className="mt-1 text-[10.5px] text-warn">
          {created.not_in_repository.length} advertised module
          {created.not_in_repository.length === 1 ? '' : 's'} not downloaded yet, so
          left out.
        </p>
      ) : null}

      {!created.validation.ok ? (
        <MissingImports
          validation={created.validation}
          repository={repository}
          deviceSlug={deviceSlug}
        />
      ) : null}
    </div>
  )
}
