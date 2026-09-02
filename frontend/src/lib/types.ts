/** Shapes returned by the YANG Studio API. */

export type NodeType =
  | 'container' | 'list' | 'leaf' | 'leaf-list'
  | 'choice' | 'case'
  | 'rpc' | 'action' | 'input' | 'output'
  | 'notification' | 'anyxml' | 'anydata'

export type Access = 'read-write' | 'read-only' | 'write'

export interface EnumOption {
  name: string
  value?: string
  description?: string
}

/** One schema node. Mirrors the backend's node dictionary. */
export interface YangNode {
  id: number
  name: string
  nodetype: NodeType
  module: string
  prefix: string
  namespace: string
  revision: string
  xpath: string
  xpath_pfx: string
  schema_id: string
  access: Access
  operations: string[]
  description?: string
  status?: string
  deviation?: string
  datatype?: string
  basetype?: string
  default?: string
  units?: string
  keys?: string[]
  presence?: string
  ordered_by?: string
  min_elements?: string
  max_elements?: string
  mandatory?: boolean
  must?: string[]
  when?: string[]
  options?: EnumOption[]
  identity_bases?: string[]
  union_types?: string[]
  leafref_path?: string
  range?: string
  length?: string
  patterns?: string[]
  children: YangNode[]
  has_children: boolean
}

/** A node flattened for search results — same fields, no children. */
export type FlatNode = Omit<YangNode, 'children'> & { depth: number }

export interface ModuleTree {
  name: string
  prefix: string
  namespace: string
  revision: string
  organization: string
  description: string
  yang_version: string
  /** Counts of what the module defines besides data — groupings, typedefs… */
  defines?: Record<string, number>
  children: YangNode[]
}

export interface Diagnostic {
  level: 'error' | 'warning'
  module: string
  line: number
  message: string
}

export interface TreeStats {
  modules: number
  nodes: number
  by_nodetype: Record<string, number>
  by_access: Record<string, number>
  errors: number
  warnings: number
  parse_ms: number
}

export interface TreeResponse {
  yangset: { slug: string; name: string }
  modules: ModuleTree[]
  diagnostics: Diagnostic[]
  stats: TreeStats
}

export interface ModuleInfo {
  name: string
  revision: string
  namespace: string
  prefix: string
  kind: 'module' | 'submodule'
  belongs_to: string
  organization: string
  description: string
  yang_version: string
  imports: string[]
  includes: string[]
  revisions: string[]
  path: string
  errors: string[]
  key: string
}

export interface RepositorySummary {
  slug: string
  name: string
  description: string
  created: string
  module_count: number
}

export interface RepositoryDetail extends RepositorySummary {
  modules: ModuleInfo[]
}

export interface YangSetSummary {
  slug: string
  name: string
  repository: string
  module_count: number
  modified: string
}

export interface YangSetDetail extends YangSetSummary {
  modules: { name: string; revision: string }[]
  created: string
}

export interface ValidationReport {
  ok: boolean
  missing: { name: string; revision: string }[]
  unresolved_dependencies: {
    required_by: string
    module: string
    available_in_repo: boolean
  }[]
  /** The same module pinned at two revisions — it cannot parse. */
  conflicting_revisions: { module: string; revisions: string[] }[]
}

/** Result of building a set from a download or a device's capabilities. */
export interface SetCreated {
  slug: string
  name: string
  repository: string
  module_count: number
  dependencies_added: number
  validation: ValidationReport
  skipped?: string[]
  not_in_repository?: string[]
}

export interface Device {
  slug: string
  name: string
  address: string
  username: string
  password: string
  has_password?: boolean
  description: string
  variant: string
  protocols: Record<string, Record<string, unknown>>
  created: string
  modified: string
}

/** Which protocol to discover and download a device's models over. */
export type Transport = 'netconf' | 'restconf'

export interface Capabilities {
  session_id: number | null
  base_capabilities: string[]
  modules: { name: string; revision: string; features: string[]; deviations: string[] }[]
  module_count: number
  supports_candidate: boolean
  supports_startup: boolean
  supports_validate: boolean
  supports_netconf_monitoring: boolean
  // Only RESTCONF discovery fills these in.
  transport?: Transport
  yang_library?: string
  restconf_root?: string
  downloadable?: number
  submodule_count?: number
}

/** A node the user has picked, plus the value/operation they gave it. */
export interface Selection {
  xpath: string
  value: string
  operation: string
  nodetype: string
  datatype: string
  is_key: boolean
}

export interface RpcResult {
  ok: boolean
  elapsed_ms: number
  reply?: string
  rpc_xml?: string
  error?: {
    type?: string
    tag?: string
    severity?: string
    path?: string
    message: string
    info?: string
  }
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

/** A background task, as reported by the server's job registry. */
export interface Job {
  id: string
  kind: string
  label: string
  status: JobStatus
  total: number
  done: number
  percent: number
  current: string
  message: string
  errors: Record<string, string>
  result: Record<string, unknown>
  created: string
  started: string
  finished: string
}

export const JOB_ACTIVE: JobStatus[] = ['queued', 'running']

export const isJobActive = (job: Job): boolean =>
  job.status === 'queued' || job.status === 'running'

/** One planned RESTCONF call. */
export interface RestRequest {
  method: string
  path: string
  query: string
  url: string
  body: string
  content_type: string
  /** Data paths this call covers — several leaves can fold into one request. */
  covers: string[]
  /** What the selection asked for that RESTCONF cannot express. */
  notes?: string[]
}

export interface RestResult {
  ok: boolean
  status: number
  reason?: string
  elapsed_ms: number
  reply?: string
  content_type?: string
  error?: { message: string }
  request: RestRequest
}

export interface RestRunResult {
  results: RestResult[]
  ok: boolean
  elapsed_ms: number
}

export type Protocol = 'netconf' | 'restconf'
