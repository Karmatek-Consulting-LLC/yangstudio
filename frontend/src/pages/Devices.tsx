/** Device profiles and live NETCONF capability inspection. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Plug, PlugZap, Plus, Router, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { CapabilityBrowser } from '@/components/CapabilityBrowser'
import { Split } from '@/components/Split'
import { Badge, Button, EmptyState, Input, Panel, Spinner } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { Capabilities, Device } from '@/lib/types'

const VARIANTS = ['generic', 'iosxe', 'iosxr', 'nxos', 'junos']

const BLANK: Partial<Device> = {
  name: '', address: '', username: '', password: '', description: '', variant: 'generic',
}

export function Devices({ onOpenSet }: { onOpenSet?: (slug: string) => void }) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<string>('')
  const [draft, setDraft] = useState<Partial<Device> | null>(null)
  const [error, setError] = useState('')

  const devices = useQuery({ queryKey: ['devices'], queryFn: api.listDevices })
  const device = devices.data?.find((d) => d.slug === selected)

  const capabilities = useQuery<Capabilities>({
    queryKey: ['capabilities', selected],
    queryFn: () => api.capabilities(selected),
    enabled: false,   // Only on explicit connect: it opens a real SSH session.
    retry: false,
  })

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e))

  const save = useMutation({
    mutationFn: (body: Partial<Device>) =>
      body.slug ? api.updateDevice(body.slug, body) : api.createDevice(body),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ['devices'] })
      setDraft(null)
      setSelected(saved.slug)
      setError('')
    },
    onError: fail,
  })

  const remove = useMutation({
    mutationFn: (slug: string) => api.deleteDevice(slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] })
      setSelected('')
    },
    onError: fail,
  })

  const editing = draft ?? (device ? { ...device } : null)

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      {error ? (
        <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </div>
      ) : null}

      <Split
        direction="row"
        anchor="leading"
        storageKey="devices.list"
        defaultSize={240}
        minLeading={180}
        minTrailing={520}
        className="flex-1"
      >
        {/* List */}
        <Panel
          title="Devices"
          className="min-h-0 flex-1 overflow-hidden"
          actions={
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setSelected('')
                setDraft({ ...BLANK })
              }}
            >
              <Plus className="size-3.5" />
            </Button>
          }
        >
          <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
            {devices.isLoading ? <Spinner /> : null}
            {devices.data?.length === 0 && !draft ? (
              <EmptyState
                icon={<Router className="size-7" />}
                title="No devices"
                hint="Add a device to inspect its capabilities and run requests against it."
              />
            ) : null}
            {devices.data?.map((d) => (
              <button
                key={d.slug}
                onClick={() => {
                  setSelected(d.slug)
                  setDraft(null)
                }}
                className={clsx(
                  'flex w-full items-center gap-2 rounded px-2 py-1.5 text-left',
                  selected === d.slug ? 'bg-brand/15 text-ink' : 'text-ink-muted hover:bg-raised',
                )}
              >
                <Router className="size-3.5 shrink-0 text-ink-faint" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink">{d.name}</p>
                  <p className="truncate text-[10.5px] text-ink-faint">{d.address || 'no address'}</p>
                </div>
                <Badge>{d.variant}</Badge>
              </button>
            ))}
          </div>
        </Panel>

        <Split
          direction="row"
          anchor="leading"
          storageKey="devices.editor"
          defaultSize={320}
          minLeading={260}
          minTrailing={280}
          className="flex-1"
        >
          {/* Editor */}
          <Panel
            title={editing?.slug ? 'Edit device' : 'New device'}
            className="min-h-0 flex-1 overflow-hidden"
          >
          {!editing ? (
            <EmptyState title="Select or add a device" />
          ) : (
            <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-3">
              <Labelled label="Name">
                <Input
                  value={editing.name ?? ''}
                  onChange={(e) => setDraft({ ...editing, name: e.target.value })}
                  placeholder="core-router-1"
                />
              </Labelled>
              <Labelled label="Address">
                <Input
                  value={editing.address ?? ''}
                  onChange={(e) => setDraft({ ...editing, address: e.target.value })}
                  placeholder="10.0.0.1"
                />
              </Labelled>
              <div className="grid grid-cols-2 gap-2">
                <Labelled label="Username">
                  <Input
                    value={editing.username ?? ''}
                    onChange={(e) => setDraft({ ...editing, username: e.target.value })}
                    autoComplete="off"
                  />
                </Labelled>
                <Labelled label="Password">
                  <Input
                    type="password"
                    value={editing.password ?? ''}
                    onChange={(e) => setDraft({ ...editing, password: e.target.value })}
                    autoComplete="new-password"
                  />
                </Labelled>
              </div>
              <Labelled label="Platform">
                <select
                  value={editing.variant ?? 'generic'}
                  onChange={(e) => setDraft({ ...editing, variant: e.target.value })}
                  className="h-9 w-full rounded-md border border-line bg-surface px-2 text-sm text-ink"
                >
                  {VARIANTS.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </Labelled>
              <Labelled label="NETCONF port">
                <Input
                  type="number"
                  value={String(editing.protocols?.netconf?.port ?? 830)}
                  onChange={(e) =>
                    setDraft({
                      ...editing,
                      protocols: {
                        ...editing.protocols,
                        netconf: {
                          ...(editing.protocols?.netconf ?? {}),
                          enabled: true,
                          port: Number(e.target.value) || 830,
                        },
                      },
                    })
                  }
                />
              </Labelled>
              <Labelled label="Description">
                <Input
                  value={editing.description ?? ''}
                  onChange={(e) => setDraft({ ...editing, description: e.target.value })}
                />
              </Labelled>

              <div className="flex gap-2 pt-1">
                <Button
                  variant="primary"
                  className="flex-1"
                  loading={save.isPending}
                  disabled={!editing.name?.trim()}
                  onClick={() => save.mutate(editing)}
                >
                  Save
                </Button>
                {editing.slug ? (
                  <Button
                    variant="danger"
                    onClick={() => {
                      if (window.confirm(`Delete “${editing.name}”?`)) remove.mutate(editing.slug!)
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                ) : null}
              </div>
            </div>
          )}
        </Panel>

        {/* Capabilities */}
        <Panel
          title="Capabilities"
          className="min-h-0 flex-1 overflow-hidden"
          actions={
            selected ? (
              <>
                <Button
                  size="sm"
                  variant="primary"
                  loading={capabilities.isFetching}
                  onClick={() => {
                    setError('')
                    capabilities.refetch()
                  }}
                >
                  <PlugZap className="size-3.5" /> Connect
                </Button>
                <Button size="sm" variant="ghost" onClick={() => api.disconnect(selected)}>
                  <Plug className="size-3.5" />
                </Button>
              </>
            ) : null
          }
        >
          {!selected ? (
            <EmptyState
              title="No device selected"
              hint="Connect to a device to list the YANG modules it advertises — then pick the ones you want and download them into a repository."
            />
          ) : capabilities.isFetching ? (
            <Spinner label="Opening NETCONF session…" />
          ) : capabilities.isError ? (
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              <p className="mb-2 text-sm font-medium text-danger">Could not connect</p>
              {/* Connection errors carry multi-line remediation steps; keep them readable. */}
              <pre className="whitespace-pre-wrap font-mono text-[11.5px] leading-relaxed text-ink-muted">
                {String((capabilities.error as Error).message)}
              </pre>
            </div>
          ) : !capabilities.data ? (
            <EmptyState
              title="Not connected"
              hint="Press Connect to open a NETCONF session and read the device's capabilities."
            />
          ) : (
            <CapabilityBrowser
              capabilities={capabilities.data}
              deviceSlug={selected}
              deviceName={device?.name ?? selected}
              onRepositoriesChanged={() =>
                qc.invalidateQueries({ queryKey: ['repositories'] })
              }
              onOpenSet={onOpenSet}
            />
          )}
          </Panel>
        </Split>
      </Split>
    </div>
  )
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-ink-faint">{label}</span>
      {children}
    </label>
  )
}
