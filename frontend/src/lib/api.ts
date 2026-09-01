/** Typed wrapper around the HTTP API. */
import type {
  Capabilities, Device, Job, RepositoryDetail, RepositorySummary, RpcResult,
  RestRequest, RestRunResult, Selection, SetCreated, Transport, TreeResponse,
  ValidationReport, YangSetDetail, YangSetSummary,
} from './types'

/**
 * Ceiling on any single request. Set above the backend's own RPC timeout so
 * that a slow device produces the server's explanatory error rather than an
 * opaque browser-level abort.
 */
const REQUEST_TIMEOUT_MS = 120_000

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: {
        ...(init?.body && !(init.body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...init?.headers,
      },
    })
  } catch (cause) {
    // fetch rejects for aborts and for connection-level failures. Neither
    // carries a status, and "NetworkError" on its own tells nobody anything.
    if (cause instanceof DOMException && cause.name === 'TimeoutError') {
      throw new ApiError(
        `The request to ${path} took longer than ${REQUEST_TIMEOUT_MS / 1000}s and was ` +
          'given up on. The device may be slow to answer, or the selection may be too broad.',
        0,
      )
    }
    throw new ApiError(
      `Could not reach the YANG Studio API (${path}). Is the backend still running? ` +
        'If it restarted while this request was in flight, retrying should work.',
      0,
    )
  }

  if (!response.ok) {
    // FastAPI puts the human-readable reason in `detail`.
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).join('; ')
    } catch {
      /* Non-JSON error body; keep the status line. */
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) })

export const api = {
  health: () => request<{ status: string; data_root: string }>('/health'),

  // -- repositories --------------------------------------------------------
  listRepositories: () => request<RepositorySummary[]>('/repositories'),
  getRepository: (slug: string, refresh = false) =>
    request<RepositoryDetail>(`/repositories/${encodeURIComponent(slug)}?refresh=${refresh}`),
  createRepository: (name: string, description = '') =>
    request<RepositorySummary>('/repositories', { method: 'POST', ...json({ name, description }) }),
  deleteRepository: (slug: string) =>
    request<void>(`/repositories/${encodeURIComponent(slug)}`, { method: 'DELETE' }),
  uploadToRepository: (slug: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<{ added: { name: string; revision: string }[]; skipped: { file: string; reason: string }[] }>(
      `/repositories/${encodeURIComponent(slug)}/upload`,
      { method: 'POST', body: form },
    )
  },
  importGit: (slug: string, url: string, ref = '', subdirectory = '') =>
    request<{ copied: number; module_count: number }>(
      `/repositories/${encodeURIComponent(slug)}/import-git`,
      { method: 'POST', ...json({ url, ref, subdirectory }) },
    ),

  // -- yangsets ------------------------------------------------------------
  listYangSets: () => request<YangSetSummary[]>('/yangsets'),
  getYangSet: (slug: string) => request<YangSetDetail>(`/yangsets/${encodeURIComponent(slug)}`),
  createYangSet: (name: string, repository: string, modules: { name: string; revision: string }[]) =>
    request<YangSetSummary>('/yangsets', { method: 'POST', ...json({ name, repository, modules }) }),
  updateYangSet: (slug: string, patch: { name?: string; modules?: { name: string; revision: string }[] }) =>
    request<YangSetDetail>(`/yangsets/${encodeURIComponent(slug)}`, { method: 'PATCH', ...json(patch) }),
  deleteYangSet: (slug: string) =>
    request<void>(`/yangsets/${encodeURIComponent(slug)}`, { method: 'DELETE' }),
  /** Build a set from an explicit module list — e.g. a finished download. */
  createYangSetFromModules: (name: string, repository: string, modules: string[]) =>
    request<SetCreated>('/yangsets/from-modules', {
      method: 'POST', ...json({ name, repository, modules }),
    }),

  /** Build a set from what a device advertises, including its features. */
  createYangSetFromDevice: (
    name: string, repository: string, device: string, modules: string[] = [],
    transport: Transport = 'netconf',
  ) =>
    request<SetCreated>('/yangsets/from-device', {
      method: 'POST', ...json({ name, repository, device, modules, transport }),
    }),

  validateYangSet: (slug: string) =>
    request<ValidationReport>(`/yangsets/${encodeURIComponent(slug)}/validate`),
  resolveDependencies: (slug: string) =>
    request<{ added: number; validation: ValidationReport }>(
      `/yangsets/${encodeURIComponent(slug)}/resolve-dependencies`, { method: 'POST' },
    ),

  // -- explorer ------------------------------------------------------------
  getTree: (slug: string, modules: string[] = [], refresh = false) => {
    const params = new URLSearchParams()
    if (modules.length) params.set('modules', modules.join(','))
    if (refresh) params.set('refresh', 'true')
    return request<TreeResponse>(`/explore/${encodeURIComponent(slug)}/tree?${params}`)
  },

  // -- devices -------------------------------------------------------------
  listDevices: () => request<Device[]>('/devices'),
  createDevice: (device: Partial<Device>) =>
    request<Device>('/devices', { method: 'POST', ...json(device) }),
  updateDevice: (slug: string, patch: Partial<Device>) =>
    request<Device>(`/devices/${encodeURIComponent(slug)}`, { method: 'PATCH', ...json(patch) }),
  deleteDevice: (slug: string) =>
    request<void>(`/devices/${encodeURIComponent(slug)}`, { method: 'DELETE' }),

  // -- discovery -----------------------------------------------------------
  // Either protocol can list a device's modules and fetch their source, and
  // both answer in the same shape, so the transport is just part of the path.
  capabilities: (slug: string, transport: Transport = 'netconf') =>
    request<Capabilities>(`/${transport}/${encodeURIComponent(slug)}/capabilities`),
  /** Starts a background job and returns it immediately — does not wait. */
  downloadSchemas: (
    slug: string, modules: string[], repository = '', transport: Transport = 'netconf',
  ) =>
    request<Job>(
      `/${transport}/${encodeURIComponent(slug)}/download-schemas`,
      { method: 'POST', ...json({ modules, repository }) },
    ),

  // -- netconf -------------------------------------------------------------
  datastores: (slug: string) =>
    request<{ datastores: string[] }>(`/netconf/${encodeURIComponent(slug)}/datastores`),
  disconnect: (slug: string) =>
    request<{ closed: boolean }>(`/netconf/${encodeURIComponent(slug)}/disconnect`, { method: 'POST' }),

  // -- restconf ------------------------------------------------------------
  buildRestconf: (body: {
    yangset: string; operation: string; selections: Selection[]
  }) =>
    request<{ requests: RestRequest[]; count: number }>('/restconf/build', {
      method: 'POST', ...json(body),
    }),

  runRestconf: (body: {
    yangset: string; device: string; operation: string
    selections: Selection[]; only?: number
  }) => request<RestRunResult>('/restconf/run', { method: 'POST', ...json(body) }),

  probeRestconf: (slug: string) =>
    request<{
      reachable: boolean; root: string; well_known_status: number
      capabilities: string[]; base_url: string
    }>(`/restconf/${encodeURIComponent(slug)}/probe`),

  // -- jobs ----------------------------------------------------------------
  listJobs: () => request<Job[]>('/jobs'),
  getJob: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) =>
    request<{ cancelling: boolean }>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  clearFinishedJobs: () => request<{ cleared: number }>('/jobs', { method: 'DELETE' }),

  // -- rpc -----------------------------------------------------------------
  buildRpc: (body: {
    operation: string; datastore: string
    selections: Selection[]; namespaces: Record<string, string>
    with_defaults?: string
  }) => request<{ rpc_xml: string }>('/rpc/build', { method: 'POST', ...json(body) }),

  runRpc: (body: {
    device: string; operation: string; datastore: string
    selections: Selection[]; namespaces: Record<string, string>
    rpc_xml?: string
  }) => request<RpcResult>('/rpc/run', { method: 'POST', ...json(body) }),
}
