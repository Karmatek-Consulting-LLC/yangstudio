/**
 * Is RESTCONF actually available on this device?
 *
 * NETCONF announces itself by opening a session; RESTCONF has no equivalent
 * handshake, so without checking you only find out when a request fails. This
 * asks the device directly — its root, and the optional capabilities that
 * decide whether a plan is even expressible (``fields`` is the one that lets
 * several leaves collapse into one call).
 */
import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, Globe, XCircle } from 'lucide-react'

import { Badge, Button } from './ui'
import { api, ApiError } from '@/lib/api'

/** Trim a capability URI down to the part worth reading. */
function shortLabel(uri: string): string {
  const match = /capability:([\w-]+)/.exec(uri)
  if (match) return match[1]
  try {
    return new URL(uri).pathname.split('/').filter(Boolean).slice(-2).join('/')
  } catch {
    return uri.slice(0, 32)
  }
}

export function RestconfProbe({ deviceSlug }: { deviceSlug: string }) {
  const probe = useMutation({
    mutationFn: () => api.probeRestconf(deviceSlug),
  })

  const result = probe.data
  const error = probe.error

  return (
    <div className="border-b border-line-soft px-2 py-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" variant="ghost" loading={probe.isPending} onClick={() => probe.mutate()}>
          <Globe className="size-3.5" />
          Check RESTCONF
        </Button>

        {result ? (
          <>
            <Badge
              className={clsx(
                'border',
                result.reachable
                  ? 'border-ok/40 bg-ok/10 text-ok'
                  : 'border-danger/40 bg-danger/10 text-danger',
              )}
            >
              {result.reachable ? (
                <CheckCircle2 className="mr-1 size-2.5" />
              ) : (
                <XCircle className="mr-1 size-2.5" />
              )}
              {result.reachable ? 'reachable' : 'not reachable'}
            </Badge>
            <Badge title={result.base_url}>
              <span className="font-mono">{result.root}</span>
            </Badge>
            {result.capabilities.slice(0, 6).map((cap) => (
              <Badge key={cap} title={cap}>{shortLabel(cap)}</Badge>
            ))}
            {result.capabilities.length > 6 ? (
              <span className="text-[10px] text-ink-faint">
                +{result.capabilities.length - 6} more
              </span>
            ) : null}
          </>
        ) : null}

        {error ? (
          <span className="text-[11px] text-danger">
            {error instanceof ApiError ? error.message : String(error)}
          </span>
        ) : null}
      </div>
    </div>
  )
}
