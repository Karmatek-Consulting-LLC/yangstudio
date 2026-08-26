/** The visual vocabulary for node types — one definition, used everywhere. */
import type { Access, NodeType } from './types'

interface NodeStyle {
  label: string
  /** Short glyph shown in the tree gutter. */
  glyph: string
  color: string
  /** Tailwind text colour class backed by a theme token. */
  className: string
}

const STYLES: Record<string, NodeStyle> = {
  container:    { label: 'container',    glyph: '▤', color: 'var(--color-type-container)',    className: 'text-type-container' },
  list:         { label: 'list',         glyph: '☰', color: 'var(--color-type-list)',         className: 'text-type-list' },
  leaf:         { label: 'leaf',         glyph: '•', color: 'var(--color-type-leaf)',         className: 'text-type-leaf' },
  'leaf-list':  { label: 'leaf-list',    glyph: '⋮', color: 'var(--color-type-leaflist)',     className: 'text-type-leaflist' },
  choice:       { label: 'choice',       glyph: '◇', color: 'var(--color-type-choice)',       className: 'text-type-choice' },
  case:         { label: 'case',         glyph: '◈', color: 'var(--color-type-choice)',       className: 'text-type-choice' },
  rpc:          { label: 'rpc',          glyph: '▶', color: 'var(--color-type-rpc)',          className: 'text-type-rpc' },
  action:       { label: 'action',       glyph: '▶', color: 'var(--color-type-rpc)',          className: 'text-type-rpc' },
  input:        { label: 'input',        glyph: '→', color: 'var(--color-type-rpc)',          className: 'text-type-rpc' },
  output:       { label: 'output',       glyph: '←', color: 'var(--color-type-rpc)',          className: 'text-type-rpc' },
  notification: { label: 'notification', glyph: '◔', color: 'var(--color-type-notification)', className: 'text-type-notification' },
  anyxml:       { label: 'anyxml',       glyph: '?', color: 'var(--color-ink-faint)',         className: 'text-ink-faint' },
  anydata:      { label: 'anydata',      glyph: '?', color: 'var(--color-ink-faint)',         className: 'text-ink-faint' },
}

const FALLBACK: NodeStyle = {
  label: 'node', glyph: '·', color: 'var(--color-ink-faint)', className: 'text-ink-faint',
}

export const nodeStyle = (type: NodeType | string): NodeStyle => STYLES[type] ?? FALLBACK

/** All node types, in the order they should appear in filter chips. */
export const NODE_TYPES: NodeType[] = [
  'container', 'list', 'leaf', 'leaf-list', 'choice', 'rpc', 'notification',
]

export const accessLabel = (access: Access): string =>
  access === 'read-write' ? 'config' : access === 'read-only' ? 'state' : 'rpc data'

export const accessClass = (access: Access): string =>
  access === 'read-write'
    ? 'text-ok border-ok/30 bg-ok/10'
    : access === 'read-only'
      ? 'text-ink-muted border-line bg-raised'
      : 'text-type-rpc border-type-rpc/30 bg-type-rpc/10'
