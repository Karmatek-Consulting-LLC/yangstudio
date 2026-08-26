/** Turning the nested module trees into a flat, windowable row list. */
import type { Access, FlatNode, ModuleTree, NodeType, YangNode } from './types'

/** One rendered row: a node plus where it sits visually. */
export interface Row {
  node: YangNode
  depth: number
  /** Path of ancestor ids, used to draw indent guides and to expand parents. */
  parents: number[]
  moduleName: string
  /** True when this row matched the active query (as opposed to being an ancestor of a match). */
  isMatch: boolean
}

export interface TreeFilters {
  query: string
  nodetypes: Set<NodeType>
  access: Access | 'all'
  /** Hide nodes marked deprecated or obsolete. */
  hideDeprecated: boolean
}

export const emptyFilters = (): TreeFilters => ({
  query: '',
  nodetypes: new Set<NodeType>(),
  access: 'all',
  hideDeprecated: false,
})

export const hasActiveFilters = (f: TreeFilters): boolean =>
  f.query.trim() !== '' || f.nodetypes.size > 0 || f.access !== 'all' || f.hideDeprecated

/** Does this node itself satisfy the non-text filters? */
function passesFacets(node: YangNode, f: TreeFilters): boolean {
  if (f.nodetypes.size > 0 && !f.nodetypes.has(node.nodetype)) return false
  if (f.access !== 'all' && node.access !== f.access) return false
  if (f.hideDeprecated && (node.status === 'deprecated' || node.status === 'obsolete')) return false
  return true
}

/** Does this node match the free-text query? */
function passesQuery(node: YangNode, needle: string): boolean {
  if (!needle) return true
  return (
    node.name.toLowerCase().includes(needle) ||
    node.xpath.toLowerCase().includes(needle) ||
    (node.datatype?.toLowerCase().includes(needle) ?? false) ||
    (node.description?.toLowerCase().includes(needle) ?? false)
  )
}

/**
 * Compute the set of node ids to keep when filtering.
 *
 * A node is kept if it matches, or if any descendant matches — otherwise
 * filtering would orphan every result from its context. Matches are tracked
 * separately so the UI can highlight the real hits and dim the scaffolding.
 */
function computeVisible(
  modules: ModuleTree[],
  filters: TreeFilters,
): { keep: Set<number>; matched: Set<number> } {
  const keep = new Set<number>()
  const matched = new Set<number>()
  const needle = filters.query.trim().toLowerCase()

  const walk = (node: YangNode): boolean => {
    let anyChildKept = false
    for (const child of node.children) {
      if (walk(child)) anyChildKept = true
    }
    const selfMatches = passesFacets(node, filters) && passesQuery(node, needle)
    if (selfMatches) matched.add(node.id)
    if (selfMatches || anyChildKept) {
      keep.add(node.id)
      return true
    }
    return false
  }

  for (const module of modules) for (const child of module.children) walk(child)
  return { keep, matched }
}

/**
 * Flatten the visible portion of the tree into rows for the virtualiser.
 *
 * When a filter is active, ancestors of matches are force-expanded so results
 * are visible without the user clicking through — collapsing is still honoured
 * for branches that contain no matches.
 */
export function buildRows(
  modules: ModuleTree[],
  expanded: Set<number>,
  filters: TreeFilters,
): { rows: Row[]; matchCount: number; totalCount: number } {
  const filtering = hasActiveFilters(filters)
  const { keep, matched } = filtering
    ? computeVisible(modules, filters)
    : { keep: null as Set<number> | null, matched: new Set<number>() }

  const rows: Row[] = []
  let totalCount = 0

  const walk = (node: YangNode, depth: number, parents: number[], moduleName: string) => {
    totalCount++
    if (keep && !keep.has(node.id)) return

    rows.push({
      node,
      depth,
      parents,
      moduleName,
      isMatch: !filtering || matched.has(node.id),
    })

    if (node.children.length === 0) return
    // While filtering, open any branch that leads to a match.
    const isOpen = filtering ? true : expanded.has(node.id)
    if (!isOpen) return

    const nextParents = [...parents, node.id]
    for (const child of node.children) walk(child, depth + 1, nextParents, moduleName)
  }

  for (const module of modules) {
    for (const child of module.children) walk(child, 0, [], module.name)
  }

  return { rows, matchCount: matched.size, totalCount }
}

/** Count every node in the tree, for the header stat. */
export function countNodes(modules: ModuleTree[]): number {
  let total = 0
  const walk = (n: YangNode) => {
    total++
    n.children.forEach(walk)
  }
  modules.forEach((m) => m.children.forEach(walk))
  return total
}

/** Collect the ids of every node from the roots down to `target`. */
export function ancestorsOf(modules: ModuleTree[], targetId: number): number[] {
  const path: number[] = []
  const walk = (node: YangNode, trail: number[]): boolean => {
    if (node.id === targetId) {
      path.push(...trail)
      return true
    }
    const next = [...trail, node.id]
    return node.children.some((c) => walk(c, next))
  }
  for (const m of modules) for (const c of m.children) if (walk(c, [])) break
  return path
}

/** Every prefix→namespace pair in the loaded modules, for RPC building. */
export function namespaceMap(modules: ModuleTree[]): Record<string, string> {
  const map: Record<string, string> = {}
  const walk = (n: YangNode) => {
    if (n.prefix && n.namespace) map[n.prefix] = n.namespace
    n.children.forEach(walk)
  }
  for (const m of modules) {
    if (m.prefix && m.namespace) map[m.prefix] = m.namespace
    m.children.forEach(walk)
  }
  return map
}

/** Flat list of all nodes — used by the command palette. */
export function flattenAll(modules: ModuleTree[]): FlatNode[] {
  const out: FlatNode[] = []
  const walk = (node: YangNode, depth: number) => {
    const { children, ...rest } = node
    out.push({ ...rest, depth })
    children.forEach((c) => walk(c, depth + 1))
  }
  modules.forEach((m) => m.children.forEach((c) => walk(c, 0)))
  return out
}
