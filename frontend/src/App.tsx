/** Application shell: navigation, theme, global shortcuts. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Database, Moon, Network, Router, Sun, TerminalSquare } from 'lucide-react'
import clsx from 'clsx'

import { CommandPalette, type Command } from '@/components/CommandPalette'
import { TaskDrawer } from '@/components/TaskDrawer'
import { Kbd } from '@/components/ui'
import { Devices } from '@/pages/Devices'
import { Explore } from '@/pages/Explore'
import { Models } from '@/pages/Models'
import { flattenAll } from '@/lib/tree'
import type { FlatNode, Selection, YangNode } from '@/lib/types'

type Page = 'explore' | 'models' | 'devices'

const NAV: { id: Page; label: string; icon: typeof Network }[] = [
  { id: 'explore', label: 'Explore', icon: Network },
  { id: 'models', label: 'Models', icon: Database },
  { id: 'devices', label: 'Devices', icon: Router },
]

const THEME_KEY = 'yangstudio.theme'
const YANGSET_KEY = 'yangstudio.yangset'

export default function App() {
  const [page, setPage] = useState<Page>('explore')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [yangsetSlug, setYangsetSlug] = useState('')
  const [selections, setSelections] = useState<Selection[]>([])
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [loadedNodes, setLoadedNodes] = useState<YangNode[]>([])
  const [jumpTo, setJumpTo] = useState<number | null>(null)

  // Restore preferences. Storage can throw in locked-down browsers.
  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem(THEME_KEY)
      if (savedTheme === 'light' || savedTheme === 'dark') setTheme(savedTheme)
      const savedSet = localStorage.getItem(YANGSET_KEY)
      if (savedSet) setYangsetSlug(savedSet)
    } catch {
      /* Preferences are a convenience; ignore storage failures. */
    }
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch { /* ignore */ }
  }, [theme])

  useEffect(() => {
    try {
      if (yangsetSlug) localStorage.setItem(YANGSET_KEY, yangsetSlug)
    } catch { /* ignore */ }
  }, [yangsetSlug])

  // Global shortcuts.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((open) => !open)
        return
      }
      if (event.key === 'Escape') setPaletteOpen(false)
      // Plain-key page switches, but never while typing in a field.
      const target = event.target as HTMLElement | null
      const typing =
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.tagName === 'SELECT' ||
        target?.isContentEditable
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return
      const index = Number(event.key)
      if (index >= 1 && index <= NAV.length) setPage(NAV[index - 1].id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const flatNodes: FlatNode[] = useMemo(
    () => flattenAll([{ name: '', prefix: '', namespace: '', revision: '', organization: '', description: '', yang_version: '', children: loadedNodes }]),
    [loadedNodes],
  )

  const commands: Command[] = useMemo(
    () => [
      ...NAV.map((item) => ({
        id: `nav-${item.id}`,
        label: `Go to ${item.label}`,
        group: 'Navigate',
        run: () => setPage(item.id),
      })),
      {
        id: 'theme',
        label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`,
        group: 'View',
        run: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
      },
      {
        id: 'clear-request',
        label: 'Clear the request basket',
        group: 'Request',
        run: () => setSelections([]),
      },
    ],
    [theme],
  )

  const registerNodes = useCallback((nodes: YangNode[]) => setLoadedNodes(nodes), [])

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface px-3">
        <div className="flex items-center gap-2">
          <TerminalSquare className="size-5 text-brand" />
          <span className="text-sm font-semibold tracking-tight text-ink">YANG Studio</span>
        </div>

        <nav className="ml-2 flex items-center gap-0.5">
          {NAV.map((item, index) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              className={clsx(
                'flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] transition-colors',
                page === item.id
                  ? 'bg-brand/15 text-ink'
                  : 'text-ink-muted hover:bg-raised hover:text-ink',
              )}
            >
              <item.icon className="size-3.5" />
              {item.label}
              <span className="ml-0.5 text-[10px] text-ink-faint">{index + 1}</span>
            </button>
          ))}
        </nav>

        <span className="flex-1" />

        {selections.length ? (
          <span className="text-[11px] text-ink-muted">
            {selections.length} node{selections.length === 1 ? '' : 's'} in request
          </span>
        ) : null}

        <button
          onClick={() => setPaletteOpen(true)}
          className="flex h-8 items-center gap-2 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink-faint hover:text-ink"
        >
          Search
          <Kbd>⌘K</Kbd>
        </button>

        <button
          onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
          className="grid size-8 place-items-center rounded-md text-ink-muted hover:bg-raised hover:text-ink"
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
      </header>

      {/* Pages are kept mounted so switching away does not throw away a parse. */}
      <main className="flex min-h-0 flex-1 flex-col">
        <div className={clsx('flex min-h-0 flex-1 flex-col', page !== 'explore' && 'hidden')}>
          <Explore
            yangsetSlug={yangsetSlug}
            onYangsetChange={setYangsetSlug}
            selections={selections}
            onSelectionsChange={setSelections}
            jumpTo={jumpTo}
            onJumpHandled={() => setJumpTo(null)}
            registerNodes={registerNodes}
          />
        </div>
        {page === 'models' ? (
          <Models
            onExplore={(slug) => {
              setYangsetSlug(slug)
              setPage('explore')
            }}
          />
        ) : null}
        {page === 'devices' ? <Devices /> : null}
      </main>

      {/* Background work is visible from every page, not just where it started. */}
      <TaskDrawer
        onOpenSet={(slug) => {
          setYangsetSlug(slug)
          setPage('explore')
        }}
      />

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
        nodes={flatNodes}
        onPickNode={(node) => {
          setPage('explore')
          setJumpTo(node.id)
        }}
      />
    </div>
  )
}
