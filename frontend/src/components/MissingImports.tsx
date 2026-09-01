/**
 * Recovery for the commonest failure in this flow: you downloaded the module
 * you wanted but not the modules it imports, so the set will not parse.
 *
 * The device advertises those imports too, so the fix is one more download —
 * there is no reason to make the user work out which files are missing.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'

import { Button } from './ui'
import { api, ApiError } from '@/lib/api'
import type { Transport, ValidationReport } from '@/lib/types'

/** Unique module names the set needs but the repository does not hold. */
export function missingImports(validation: ValidationReport): string[] {
  return [...new Set(validation.unresolved_dependencies.map((d) => d.module))].sort()
}

export function MissingImports({
  validation, repository, deviceSlug, transport = 'netconf',
}: {
  validation: ValidationReport
  repository: string
  deviceSlug?: string
  transport?: Transport
}) {
  const qc = useQueryClient()
  const [started, setStarted] = useState(false)
  const [error, setError] = useState('')
  const missing = missingImports(validation)

  const fetchMissing = useMutation({
    mutationFn: () => api.downloadSchemas(deviceSlug!, missing, repository, transport),
    onSuccess: () => {
      setStarted(true)
      setError('')
      qc.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : String(e)),
  })

  if (missing.length === 0) return null

  return (
    <div className="mt-1 space-y-1">
      <p className="text-[10.5px] text-warn">
        Will not parse yet — {missing.length} import{missing.length === 1 ? '' : 's'} missing:{' '}
        <span className="font-mono">{missing.slice(0, 4).join(', ')}</span>
        {missing.length > 4 ? ` +${missing.length - 4} more` : ''}
      </p>
      {started ? (
        <p className="text-[10.5px] text-ok">
          Fetching them — watch the task bar, then make the set again.
        </p>
      ) : deviceSlug ? (
        <Button
          size="sm"
          variant="outline"
          loading={fetchMissing.isPending}
          onClick={() => fetchMissing.mutate()}
        >
          <Download className="size-3" />
          Download the {missing.length} missing
        </Button>
      ) : null}
      {error ? <p className="text-[10.5px] text-danger">{error}</p> : null}
    </div>
  )
}
