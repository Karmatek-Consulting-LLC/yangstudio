/**
 * Where one module puts its nodes.
 *
 * On a vendor model this is the question people actually have: not "what does
 * Cisco-IOS-XE-vlan contain" but "where in native does it land". Each graft
 * point is a link into the tree, and can be focused on its own — the pyang
 * --tree-path workflow, one click instead of a flag.
 */
import { Crosshair, X } from 'lucide-react'

import { Badge, Button } from './ui'
import type { ModuleContribution } from '@/lib/tree'

interface Props {
  contribution: ModuleContribution
  onReveal: (id: number) => void
  onFocus: (id: number) => void
  onClear: () => void
}

export function ModuleSummary({ contribution, onReveal, onFocus, onClear }: Props) {
  const roots = contribution.grafts.filter((g) => g.kind === 'root')
  const augments = contribution.grafts.filter((g) => g.kind === 'augment')

  return (
    <div className="rounded-md border border-brand/30 bg-brand/5 px-3 py-2 text-[12px]">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-mono text-[12px] font-semibold text-ink">{contribution.name}</span>
        <span className="text-ink-muted">
          contributes {contribution.count.toLocaleString()} node{contribution.count === 1 ? '' : 's'}
          {roots.length ? ` — defines ${roots.length} root${roots.length === 1 ? '' : 's'}` : ''}
          {augments.length
            ? `${roots.length ? ',' : ' —'} augments ${augments.length} place${augments.length === 1 ? '' : 's'}`
            : ''}
          {!roots.length && !augments.length ? ' — only through groupings other modules use' : ''}
        </span>
        <span className="flex-1" />
        <Button size="sm" variant="ghost" onClick={onClear} title="Show every module again">
          <X className="size-3.5" />
          Clear
        </Button>
      </div>

      {contribution.grafts.length ? (
        <ul className="mt-1.5 flex max-h-28 flex-wrap gap-1.5 overflow-y-auto">
          {contribution.grafts.map((graft) => (
            <li key={graft.id} className="flex items-center gap-0.5">
              <button
                onClick={() => onReveal(graft.id)}
                title={`Show ${graft.xpath_pfx} in the tree`}
                className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-0.5 font-mono text-[11px] text-ink hover:border-brand hover:bg-raised"
              >
                {graft.kind === 'root' ? (
                  <Badge className="border-brand/40 bg-brand/10 text-ink">root</Badge>
                ) : null}
                {graft.xpath}
                <span className="text-ink-faint">{graft.count.toLocaleString()}</span>
              </button>
              <button
                onClick={() => onFocus(graft.id)}
                title={`Focus the tree on ${graft.xpath}`}
                aria-label={`Focus on ${graft.xpath}`}
                className="rounded p-0.5 text-ink-faint hover:bg-raised hover:text-ink"
              >
                <Crosshair className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
