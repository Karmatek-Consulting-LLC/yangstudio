/**
 * Everything known about one node, in one place.
 *
 * Upstream scatters this across tooltips and popups; the point here is that
 * selecting a node shows its type, constraints, allowed values, documentation
 * and both paths without any further clicking.
 */
import clsx from 'clsx'
import { Check, Copy, Crosshair, Plus, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Badge, Button, EmptyState } from './ui'
import { accessClass, accessLabel, nodeStyle } from '@/lib/nodeStyle'
import type { YangNode } from '@/lib/types'

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        void navigator.clipboard?.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1200)
      }}
      title={`Copy ${label}`}
      className="shrink-0 rounded p-1 text-ink-faint hover:bg-raised hover:text-ink"
    >
      {copied ? <Check className="size-3 text-ok" /> : <Copy className="size-3" />}
    </button>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[92px_1fr] items-start gap-2 px-3 py-1.5">
      <dt className="pt-0.5 text-[11px] font-medium text-ink-faint">{label}</dt>
      <dd className="min-w-0 text-[12.5px] text-ink">{children}</dd>
    </div>
  )
}

function PathRow({ label, value }: { label: string; value: string }) {
  return (
    <Field label={label}>
      <div className="flex items-start gap-1">
        <code className="min-w-0 flex-1 break-all font-mono text-[11.5px] text-ink-muted">
          {value}
        </code>
        <CopyButton value={value} label={label} />
      </div>
    </Field>
  )
}

interface Props {
  node: YangNode | null
  isSelected: boolean
  onToggleSelect: (node: YangNode) => void
  /** Make this node the root of the tree — only offered when it has children. */
  onFocus?: (node: YangNode) => void
  /** The module owning this node's parent, when it differs — i.e. this is a graft point. */
  parentModule?: string
}

export function NodeDetail({ node, isSelected, onToggleSelect, onFocus, parentModule }: Props) {
  if (!node) {
    return (
      <EmptyState
        title="No node selected"
        hint="Pick a node in the tree to see its type, constraints, allowed values and paths."
      />
    )
  }

  const style = nodeStyle(node.nodetype)
  const constraints: [string, string][] = []
  if (node.range) constraints.push(['range', node.range])
  if (node.length) constraints.push(['length', node.length])
  if (node.min_elements) constraints.push(['min-elements', node.min_elements])
  if (node.max_elements) constraints.push(['max-elements', node.max_elements])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 border-b border-line-soft bg-surface px-3 py-2.5">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 text-sm leading-none" style={{ color: style.color }}>
            {style.glyph}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-ink">{node.name}</h3>
            <p className="mt-0.5 flex flex-wrap items-center gap-1">
              <Badge className={clsx('border', style.className)}>{node.nodetype}</Badge>
              <Badge className={accessClass(node.access)}>{accessLabel(node.access)}</Badge>
              {node.mandatory ? (
                <Badge className="border-warn/40 bg-warn/10 text-warn">required</Badge>
              ) : null}
              {node.status ? (
                <Badge className="border-danger/40 bg-danger/10 text-danger">{node.status}</Badge>
              ) : null}
              {node.deviation ? (
                <Badge className="border-danger/40 bg-danger/10 text-danger">{node.deviation}</Badge>
              ) : null}
              {node.presence ? <Badge>presence</Badge> : null}
            </p>
          </div>
          {onFocus && node.children.length ? (
            <Button size="sm" variant="ghost" onClick={() => onFocus(node)} title="Show only this subtree">
              <Crosshair className="size-3" />
              Focus
            </Button>
          ) : null}
          <Button
            size="sm"
            variant={isSelected ? 'danger' : 'primary'}
            onClick={() => onToggleSelect(node)}
          >
            {isSelected ? <Trash2 className="size-3" /> : <Plus className="size-3" />}
            {isSelected ? 'Remove' : 'Add'}
          </Button>
        </div>
      </div>

      {/* Description first: it is what people actually came to read. */}
      {node.description ? (
        <p className="whitespace-pre-wrap border-b border-line-soft px-3 py-2.5 text-[12.5px] leading-relaxed text-ink-muted">
          {node.description}
        </p>
      ) : null}

      <dl className="divide-y divide-line-soft/60">
        {node.datatype ? (
          <Field label="Type">
            <code className="font-mono text-[12px] text-ink">{node.datatype}</code>
            {node.basetype && node.basetype !== node.datatype ? (
              <span className="ml-1.5 text-[11px] text-ink-faint">→ {node.basetype}</span>
            ) : null}
          </Field>
        ) : null}

        {node.union_types?.length ? (
          <Field label="Union of">
            <span className="font-mono text-[11.5px] text-ink-muted">
              {node.union_types.join(' | ')}
            </span>
          </Field>
        ) : null}

        {node.leafref_path ? (
          <Field label="References">
            <code className="break-all font-mono text-[11.5px] text-type-list">
              {node.leafref_path}
            </code>
          </Field>
        ) : null}

        {node.default ? (
          <Field label="Default">
            <code className="font-mono text-[12px] text-ok">{node.default}</code>
          </Field>
        ) : null}

        {node.units ? <Field label="Units">{node.units}</Field> : null}

        {node.keys?.length ? (
          <Field label="Keys">
            <span className="font-mono text-[12px] text-type-list">{node.keys.join(', ')}</span>
          </Field>
        ) : null}

        {constraints.map(([label, value]) => (
          <Field key={label} label={label}>
            <code className="font-mono text-[12px] text-ink-muted">{value}</code>
          </Field>
        ))}

        {node.patterns?.length ? (
          <Field label="Pattern">
            <div className="space-y-1">
              {node.patterns.map((p) => (
                <code key={p} className="block break-all font-mono text-[11px] text-ink-muted">
                  {p}
                </code>
              ))}
            </div>
          </Field>
        ) : null}

        {node.when?.length ? (
          <Field label="When">
            {node.when.map((w) => (
              <code key={w} className="block break-all font-mono text-[11px] text-warn">{w}</code>
            ))}
          </Field>
        ) : null}

        {node.must?.length ? (
          <Field label="Must">
            {node.must.map((m) => (
              <code key={m} className="block break-all font-mono text-[11px] text-warn">{m}</code>
            ))}
          </Field>
        ) : null}

        <PathRow label="XPath" value={node.xpath} />
        <PathRow label="Prefixed" value={node.xpath_pfx} />

        <Field label="Module">
          <span className="text-[12px]">
            {node.module}
            {node.revision ? (
              <span className="text-ink-faint"> @ {node.revision}</span>
            ) : null}
          </span>
          {parentModule && parentModule !== node.module ? (
            /* The answer to "why is this here when I never loaded that
               module": it was grafted in by an augment. */
            <p className="mt-0.5 text-[11px] text-ink-faint">
              augments <span className="font-mono">{parentModule}</span> here
            </p>
          ) : null}
        </Field>
        <PathRow label="Namespace" value={node.namespace} />

        {node.operations.length ? (
          <Field label="Operations">
            <div className="flex flex-wrap gap-1">
              {node.operations.map((op) => (
                <Badge key={op}>{op}</Badge>
              ))}
            </div>
          </Field>
        ) : null}
      </dl>

      {/* Allowed values last — it can be long (identityrefs run to hundreds). */}
      {node.options?.length ? (
        <div className="border-t border-line-soft">
          <p className="px-3 py-2 text-[11px] font-medium text-ink-faint">
            Allowed values
            <span className="ml-1 text-ink-faint/70">({node.options.length})</span>
          </p>
          <ul className="max-h-72 overflow-y-auto pb-2">
            {node.options.map((option) => (
              <li key={option.name} className="px-3 py-1">
                <div className="flex items-baseline gap-2">
                  <code className="font-mono text-[12px] text-ink">{option.name}</code>
                  {option.value ? (
                    <span className="text-[10px] text-ink-faint">= {option.value}</span>
                  ) : null}
                </div>
                {option.description ? (
                  <p className="mt-0.5 line-clamp-2 text-[11px] text-ink-faint">
                    {option.description}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
