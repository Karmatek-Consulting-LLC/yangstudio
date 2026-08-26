/**
 * Cmd/Ctrl-K palette.
 *
 * The single biggest navigation fix: every page, every loaded node, and every
 * common action is reachable by typing, so nobody has to learn where a feature
 * lives in the menu structure.
 */
import { ArrowRight, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Highlight, Kbd } from './ui'
import { nodeStyle } from '@/lib/nodeStyle'
import type { FlatNode } from '@/lib/types'

export interface Command {
  id: string
  label: string
  hint?: string
  group: string
  run: () => void
}

interface Props {
  open: boolean
  onClose: () => void
  commands: Command[]
  nodes: FlatNode[]
  onPickNode: (node: FlatNode) => void
}

const MAX_NODE_RESULTS = 40

export function CommandPalette({ open, onClose, commands, nodes, onPickNode }: Props) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQuery('')
      setCursor(0)
      // Focus after paint so the input exists.
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const needle = query.trim().toLowerCase()

  const matchedCommands = useMemo(
    () =>
      commands.filter(
        (c) => !needle || c.label.toLowerCase().includes(needle) || c.group.toLowerCase().includes(needle),
      ),
    [commands, needle],
  )

  const matchedNodes = useMemo(() => {
    if (!needle) return []
    const scored: [number, FlatNode][] = []
    for (const node of nodes) {
      const name = node.name.toLowerCase()
      let score = 0
      if (name === needle) score = 1000
      else if (name.startsWith(needle)) score = 800
      else if (name.includes(needle)) score = 600
      else if (node.xpath.toLowerCase().includes(needle)) score = 300
      if (score) scored.push([score, node])
      if (scored.length > 600) break   // Enough to rank well; keep it snappy.
    }
    scored.sort((a, b) => b[0] - a[0] || a[1].xpath.length - b[1].xpath.length)
    return scored.slice(0, MAX_NODE_RESULTS).map(([, n]) => n)
  }, [nodes, needle])

  const total = matchedCommands.length + matchedNodes.length

  useEffect(() => {
    setCursor((c) => Math.min(c, Math.max(total - 1, 0)))
  }, [total])

  if (!open) return null

  const choose = (index: number) => {
    if (index < matchedCommands.length) {
      matchedCommands[index]?.run()
    } else {
      const node = matchedNodes[index - matchedCommands.length]
      if (node) onPickNode(node)
    }
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[12vh]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
        className="animate-in w-full max-w-2xl overflow-hidden rounded-xl border border-line bg-overlay shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-line-soft px-3">
          <Search className="size-4 shrink-0 text-ink-faint" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setCursor((c) => Math.min(c + 1, total - 1))
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setCursor((c) => Math.max(c - 1, 0))
              } else if (e.key === 'Enter') {
                e.preventDefault()
                choose(cursor)
              } else if (e.key === 'Escape') {
                onClose()
              }
            }}
            placeholder="Jump to a page, a node, or an action…"
            className="h-12 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
          />
          <Kbd>esc</Kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto py-1">
          {total === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-ink-faint">No matches</p>
          ) : null}

          {matchedCommands.length ? (
            <Group label="Actions">
              {matchedCommands.map((command, index) => (
                <Item
                  key={command.id}
                  active={cursor === index}
                  onHover={() => setCursor(index)}
                  onClick={() => choose(index)}
                >
                  <ArrowRight className="size-3 shrink-0 text-ink-faint" />
                  <span className="flex-1 truncate">
                    <Highlight text={command.label} query={query} />
                  </span>
                  <span className="shrink-0 text-[10px] text-ink-faint">{command.group}</span>
                </Item>
              ))}
            </Group>
          ) : null}

          {matchedNodes.length ? (
            <Group label={`Nodes (${matchedNodes.length})`}>
              {matchedNodes.map((node, i) => {
                const index = matchedCommands.length + i
                const style = nodeStyle(node.nodetype)
                return (
                  <Item
                    key={node.id}
                    active={cursor === index}
                    onHover={() => setCursor(index)}
                    onClick={() => choose(index)}
                  >
                    <span className="shrink-0 text-[11px]" style={{ color: style.color }}>
                      {style.glyph}
                    </span>
                    <span className="shrink-0 font-medium">
                      <Highlight text={node.name} query={query} />
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-ink-faint">
                      {node.xpath}
                    </span>
                    {node.datatype ? (
                      <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                        {node.datatype}
                      </span>
                    ) : null}
                  </Item>
                )
              })}
            </Group>
          ) : null}
        </div>

        <div className="flex items-center gap-3 border-t border-line-soft px-3 py-1.5 text-[10px] text-ink-faint">
          <span className="flex items-center gap-1"><Kbd>↑↓</Kbd> navigate</span>
          <span className="flex items-center gap-1"><Kbd>↵</Kbd> open</span>
          <span className="flex items-center gap-1"><Kbd>⌘K</Kbd> toggle</span>
        </div>
      </div>
    </div>
  )
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="py-1">
      <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
        {label}
      </p>
      {children}
    </div>
  )
}

function Item({
  active, onHover, onClick, children,
}: {
  active: boolean; onHover: () => void; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      onMouseEnter={onHover}
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] ${
        active ? 'bg-brand/15 text-ink' : 'text-ink-muted hover:bg-raised'
      }`}
    >
      {children}
    </button>
  )
}
