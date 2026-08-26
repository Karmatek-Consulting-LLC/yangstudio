/**
 * Shown when a set parses cleanly but contributes no data nodes.
 *
 * This is a real and fairly common situation rather than a failure: vendor
 * modules ending in -common or -types are frequently libraries of groupings
 * and typedefs, meant to be imported by other modules rather than browsed on
 * their own. A blank tree with no explanation looks like a broken app, so say
 * what the modules actually contain and what to do about it.
 */
import { Boxes } from 'lucide-react'

import { Badge, EmptyState } from './ui'
import type { ModuleTree } from '@/lib/types'

/** "4 groupings and 1 extension" from {grouping: 4, extension: 1}. */
function describe(defines: Record<string, number>): string {
  const parts = Object.entries(defines)
    .filter(([, n]) => n > 0)
    .map(([kind, n]) => `${n} ${kind}${n === 1 ? '' : kind === 'identity' ? 'ies' : 's'}`)
  if (parts.length === 0) return 'nothing'
  if (parts.length === 1) return parts[0]
  return `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}`
}

export function EmptyTree({ modules }: { modules: ModuleTree[] }) {
  const described = modules.filter((m) => m.defines && Object.keys(m.defines).length > 0)

  return (
    <EmptyState
      icon={<Boxes className="size-8" />}
      title="No data nodes in this set"
      hint={
        <span className="flex flex-col gap-2">
          <span>
            The modules parsed without errors, but none of them define data of
            their own — so there is no tree to show.
          </span>
          {described.length ? (
            <span className="flex flex-col gap-1">
              {described.map((m) => (
                <span key={m.name} className="flex flex-wrap items-baseline gap-1.5">
                  <code className="font-mono text-[11px] text-ink">{m.name}</code>
                  <span>defines {describe(m.defines!)}</span>
                </span>
              ))}
            </span>
          ) : null}
          <span>
            Modules like these are libraries — other modules import their
            groupings and types rather than the modules appearing in the tree
            themselves. Vendor names ending in{' '}
            <Badge>-common</Badge> or <Badge>-types</Badge> are usually this
            kind.
          </span>
          <span>
            To see a tree, add a module that <em>uses</em> them and rebuild the
            set — on IOS-XE that is typically{' '}
            <code className="font-mono text-[11px] text-ink">
              Cisco-IOS-XE-native
            </code>{' '}
            or one of the feature modules.
          </span>
        </span>
      }
    />
  )
}
