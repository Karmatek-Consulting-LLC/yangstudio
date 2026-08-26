/**
 * A two-pane split with a draggable divider.
 *
 * The trailing pane is the one with a stored pixel size; the leading pane takes
 * whatever is left. That matches how these layouts are actually used — the
 * detail panel is the thing you want a specific width for, and the tree should
 * absorb the remainder as the window changes.
 *
 * Sizes persist per key, the divider is keyboard operable, and a double-click
 * restores the default.
 */
import clsx from 'clsx'
import {
  useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode,
} from 'react'

type Direction = 'row' | 'column'

interface Props {
  /** 'row' places panes side by side (vertical divider); 'column' stacks them. */
  direction: Direction
  /**
   * Which pane carries the stored pixel size. The other takes the remainder.
   * Size the pane you want to stay put — a fixed-width sidebar is 'leading',
   * a detail panel beside a growing tree is 'trailing'.
   */
  anchor?: 'leading' | 'trailing'
  /** localStorage key; omit to keep the size for this mount only. */
  storageKey?: string
  /** Starting size of the trailing pane, in pixels. */
  defaultSize: number
  /** Smallest the leading pane may become. */
  minLeading?: number
  /** Smallest the trailing pane may become. */
  minTrailing?: number
  /**
   * Shrink the leading pane to `collapsedLeadingSize` and give the rest to the
   * trailing one, without unmounting either — swapping to a different element
   * tree would remount the children and destroy their state.
   */
  collapseLeading?: boolean
  /** How much of the leading pane survives collapsing; enough for its header. */
  collapsedLeadingSize?: number
  className?: string
  children: [ReactNode, ReactNode]
}

const DIVIDER = 7          // Hit area; the visible line is thinner.
const KEY_STEP = 24

function readStored(key: string | undefined, fallback: number): number {
  if (!key) return fallback
  try {
    const raw = localStorage.getItem(`yangstudio.split.${key}`)
    const value = raw === null ? NaN : Number(raw)
    return Number.isFinite(value) ? value : fallback
  } catch {
    return fallback
  }
}

export function Split({
  direction, anchor = 'trailing', storageKey, defaultSize,
  minLeading = 240, minTrailing = 220,
  collapseLeading = false, collapsedLeadingSize = 44,
  className, children,
}: Props) {
  const isRow = direction === 'row'
  const anchorLeading = anchor === 'leading'
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState(() => readStored(storageKey, defaultSize))
  const [dragging, setDragging] = useState(false)
  // Mirrors `size` so the drag handler can persist the final value without
  // doing side effects inside a state updater (StrictMode double-invokes those).
  const sizeRef = useRef(size)
  sizeRef.current = size
  // preventDefault() on pointerdown (needed to stop text selection while
  // dragging) also suppresses the compatibility mouse events, so `dblclick`
  // never fires on the divider. Detect the double tap ourselves instead.
  const lastDownRef = useRef(0)

  /** Clamp against the live container so a pane can never vanish. */
  const clamp = useCallback(
    (value: number) => {
      const el = containerRef.current
      if (!el) return value
      const extent = isRow ? el.clientWidth : el.clientHeight
      // The sized pane's own minimum is its floor; the other pane's minimum
      // sets the ceiling.
      const own = anchorLeading ? minLeading : minTrailing
      const other = anchorLeading ? minTrailing : minLeading
      const upper = Math.max(own, extent - DIVIDER - other)
      return Math.min(Math.max(value, own), upper)
    },
    [isRow, anchorLeading, minLeading, minTrailing],
  )

  // Re-clamp on mount and whenever the container resizes, so shrinking the
  // window cannot leave the trailing pane wider than the whole layout.
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const apply = () => setSize((current) => clamp(current))
    apply()
    const observer = new ResizeObserver(apply)
    observer.observe(el)
    return () => observer.disconnect()
  }, [clamp])

  const persist = useCallback(
    (value: number) => {
      if (!storageKey) return
      try {
        localStorage.setItem(`yangstudio.split.${storageKey}`, String(value))
      } catch {
        /* Persisting the layout is a convenience, not a requirement. */
      }
    },
    [storageKey],
  )

  const reset = useCallback(() => {
    const clamped = clamp(defaultSize)
    sizeRef.current = clamped
    setSize(clamped)
    persist(clamped)
  }, [clamp, defaultSize, persist])

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault()

    const now = event.timeStamp
    if (now - lastDownRef.current < 350) {
      lastDownRef.current = 0
      reset()
      return
    }
    lastDownRef.current = now

    const start = isRow ? event.clientX : event.clientY
    const startSize = size
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)
    setDragging(true)

    const move = (e: PointerEvent) => {
      // A trailing pane grows as the pointer moves toward the start edge;
      // a leading pane grows as it moves away.
      const travelled = (isRow ? e.clientX : e.clientY) - start
      const delta = anchorLeading ? travelled : -travelled
      const next = clamp(startSize + delta)
      sizeRef.current = next
      setSize(next)
    }
    const finish = () => {
      setDragging(false)
      if (target.hasPointerCapture(event.pointerId)) {
        target.releasePointerCapture(event.pointerId)
      }
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', finish)
      target.removeEventListener('pointercancel', finish)
      persist(sizeRef.current)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', finish)
    target.addEventListener('pointercancel', finish)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    const towardsStart = isRow ? 'ArrowLeft' : 'ArrowUp'
    const towardsEnd = isRow ? 'ArrowRight' : 'ArrowDown'
    const grow = anchorLeading ? towardsEnd : towardsStart
    const shrink = anchorLeading ? towardsStart : towardsEnd
    let next: number | null = null
    if (event.key === grow) next = size + KEY_STEP
    else if (event.key === shrink) next = size - KEY_STEP
    else if (event.key === 'Home') next = 10_000        // Clamped to max.
    else if (event.key === 'End') next = 0              // Clamped to min.
    if (next === null) return
    event.preventDefault()
    const clamped = clamp(next)
    sizeRef.current = clamped
    setSize(clamped)
    persist(clamped)
  }

  // While dragging, suppress selection everywhere and keep the resize cursor.
  useEffect(() => {
    if (!dragging) return
    const previousCursor = document.body.style.cursor
    document.body.style.cursor = isRow ? 'col-resize' : 'row-resize'
    document.body.style.userSelect = 'none'
    return () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = ''
    }
  }, [dragging, isRow])

  return (
    <div
      ref={containerRef}
      className={clsx('grid min-h-0 min-w-0', className)}
      style={
        (() => {
          const track = collapseLeading
            ? `${collapsedLeadingSize}px 0px minmax(0,1fr)`
            : anchorLeading
              ? `${size}px ${DIVIDER}px minmax(0,1fr)`
              : `minmax(0,1fr) ${DIVIDER}px ${size}px`
          return isRow ? { gridTemplateColumns: track } : { gridTemplateRows: track }
        })()
      }
    >
      <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
        {children[0]}
      </div>

      <div
        role="separator"
        tabIndex={collapseLeading ? -1 : 0}
        aria-orientation={isRow ? 'vertical' : 'horizontal'}
        aria-valuenow={Math.round(size)}
        aria-label={isRow ? 'Resize panel width' : 'Resize panel height'}
        title="Drag to resize · double-click to reset"
        onPointerDown={onPointerDown}
        onKeyDown={onKeyDown}
        className={clsx(
          'group relative flex items-center justify-center overflow-hidden',
          collapseLeading && 'pointer-events-none',
          isRow ? 'cursor-col-resize' : 'cursor-row-resize',
        )}
      >
        {/* A thin line that thickens on hover, so the target is easy to hit
            without the divider being visually heavy at rest. */}
        <span
          className={clsx(
            'rounded-full transition-colors',
            isRow ? 'h-full w-px' : 'h-px w-full',
            dragging ? 'bg-brand' : 'bg-line group-hover:bg-brand/60',
          )}
        />
        <span
          className={clsx(
            'absolute rounded-full transition-opacity',
            isRow ? 'h-8 w-1' : 'h-1 w-8',
            dragging ? 'bg-brand opacity-100' : 'bg-ink-faint opacity-0 group-hover:opacity-70',
          )}
        />
      </div>

      <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">{children[1]}</div>
    </div>
  )
}
