/**
 * The virtualised schema tree.
 *
 * Only the visible window is rendered, so a set with 100k+ nodes scrolls at
 * full speed. Rows are keyboard navigable: arrows move and open/close, Enter
 * selects, Space toggles the node into the RPC basket.
 */
import { useVirtualizer } from '@tanstack/react-virtual'
import clsx from 'clsx'
import { ChevronRight, Key, Lock } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'

import { Highlight } from './ui'
import { nodeStyle } from '@/lib/nodeStyle'
import type { Row } from '@/lib/tree'
import type { YangNode } from '@/lib/types'

const ROW_HEIGHT = 28
const INDENT = 14

interface Props {
  rows: Row[]
  expanded: Set<number>
  onToggle: (id: number) => void
  activeId: number | null
  onActivate: (node: YangNode) => void
  selectedPaths: Set<string>
  onToggleSelect: (node: YangNode) => void
  query: string
  cursor: number
  onCursorChange: (index: number) => void
}

export function TreeView({
  rows, expanded, onToggle, activeId, onActivate,
  selectedPaths, onToggleSelect, query, cursor, onCursorChange,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 18,
  })

  // Keep the keyboard cursor in view as it moves.
  useEffect(() => {
    if (cursor >= 0 && cursor < rows.length) virtualizer.scrollToIndex(cursor, { align: 'auto' })
  }, [cursor, rows.length, virtualizer])

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (rows.length === 0) return
      const row = rows[cursor]

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault()
          onCursorChange(Math.min(cursor + 1, rows.length - 1))
          break
        case 'ArrowUp':
          event.preventDefault()
          onCursorChange(Math.max(cursor - 1, 0))
          break
        case 'ArrowRight':
          event.preventDefault()
          if (!row) break
          if (row.node.children.length && !expanded.has(row.node.id)) onToggle(row.node.id)
          else onCursorChange(Math.min(cursor + 1, rows.length - 1))
          break
        case 'ArrowLeft': {
          event.preventDefault()
          if (!row) break
          if (row.node.children.length && expanded.has(row.node.id)) {
            onToggle(row.node.id)
            break
          }
          // Jump to the parent row.
          const parentId = row.parents.at(-1)
          if (parentId !== undefined) {
            const parentIndex = rows.findIndex((r) => r.node.id === parentId)
            if (parentIndex >= 0) onCursorChange(parentIndex)
          }
          break
        }
        case 'Enter':
          event.preventDefault()
          if (row) onActivate(row.node)
          break
        case ' ':
          event.preventDefault()
          if (row) onToggleSelect(row.node)
          break
        case 'Home':
          event.preventDefault()
          onCursorChange(0)
          break
        case 'End':
          event.preventDefault()
          onCursorChange(rows.length - 1)
          break
      }
    },
    [rows, cursor, expanded, onToggle, onActivate, onToggleSelect, onCursorChange],
  )

  return (
    <div
      ref={parentRef}
      tabIndex={0}
      role="tree"
      aria-label="YANG schema tree"
      onKeyDown={handleKeyDown}
      className="flex-1 overflow-auto focus:outline-none"
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((item) => {
          const row = rows[item.index]
          if (!row) return null
          const { node, depth, isMatch } = row
          const style = nodeStyle(node.nodetype)
          const isOpen = expanded.has(node.id)
          const isActive = activeId === node.id
          const isCursor = cursor === item.index
          const isSelected = selectedPaths.has(node.xpath_pfx)
          const isKey = Boolean(
            row.parents.length && node.nodetype === 'leaf' && node.mandatory && node.name,
          )

          return (
            <div
              key={node.id}
              role="treeitem"
              aria-level={depth + 1}
              aria-expanded={node.children.length ? isOpen : undefined}
              aria-selected={isActive}
              onClick={() => {
                onCursorChange(item.index)
                onActivate(node)
              }}
              onDoubleClick={() => node.children.length && onToggle(node.id)}
              className={clsx(
                'group absolute inset-x-0 flex items-center gap-1 pr-2 text-[13px] cursor-pointer',
                'border-l-2',
                isActive
                  ? 'border-l-brand bg-brand/12'
                  : isCursor
                    ? 'border-l-brand/40 bg-raised'
                    : 'border-l-transparent hover:bg-raised/70',
                !isMatch && 'opacity-45',
              )}
              style={{
                height: ROW_HEIGHT,
                transform: `translateY(${item.start}px)`,
                paddingLeft: 6 + depth * INDENT,
              }}
            >
              {/* Expander */}
              {node.children.length ? (
                <button
                  aria-label={isOpen ? 'Collapse' : 'Expand'}
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggle(node.id)
                  }}
                  className="grid size-4 shrink-0 place-items-center rounded text-ink-faint hover:bg-overlay hover:text-ink"
                >
                  <ChevronRight
                    className={clsx('size-3 transition-transform', isOpen && 'rotate-90')}
                  />
                </button>
              ) : (
                <span className="size-4 shrink-0" />
              )}

              {/* Selection checkbox — appears on hover or when already picked. */}
              <button
                aria-label={isSelected ? 'Remove from request' : 'Add to request'}
                onClick={(e) => {
                  e.stopPropagation()
                  onToggleSelect(node)
                }}
                className={clsx(
                  'grid size-4 shrink-0 place-items-center rounded-[3px] border text-[9px] font-bold',
                  isSelected
                    ? 'border-brand bg-brand text-canvas'
                    : 'border-line text-transparent opacity-0 group-hover:opacity-100 hover:border-brand',
                )}
              >
                ✓
              </button>

              {/* Type glyph */}
              <span
                className="w-3 shrink-0 text-center text-[11px] leading-none"
                style={{ color: style.color }}
                title={style.label}
              >
                {style.glyph}
              </span>

              {/* Name */}
              <span className={clsx('truncate', isActive ? 'text-ink' : 'text-ink')}>
                <Highlight text={node.name} query={query} />
              </span>

              {/* Inline metadata */}
              {node.datatype ? (
                <span className="shrink-0 truncate font-mono text-[10.5px] text-ink-faint">
                  {node.datatype}
                </span>
              ) : null}
              {node.keys?.length ? (
                <span
                  className="flex shrink-0 items-center gap-0.5 text-[10px] text-type-list"
                  title={`key: ${node.keys.join(', ')}`}
                >
                  <Key className="size-2.5" />
                  {node.keys.join(', ')}
                </span>
              ) : null}
              {node.access === 'read-only' ? (
                <Lock className="size-2.5 shrink-0 text-ink-faint" aria-label="read-only state" />
              ) : null}
              {node.mandatory && !isKey ? (
                <span className="shrink-0 text-[10px] font-semibold text-warn" title="mandatory">
                  required
                </span>
              ) : null}
              {node.status ? (
                <span className="shrink-0 text-[10px] text-danger" title={`status: ${node.status}`}>
                  {node.status}
                </span>
              ) : null}

              <span className="flex-1" />
              {/* Path shown on hover, right-aligned; the single most-asked-for value. */}
              <span className="hidden shrink-0 truncate font-mono text-[10px] text-ink-faint group-hover:block max-w-[42%]">
                {node.xpath}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
