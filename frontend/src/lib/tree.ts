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
  /**
   * Keep only nodes contributed by this module — '' means any. On IOS-XE the
   * feature modules graft into Cisco-IOS-XE-native, so this is how you see
   * "just what the vlan module adds" without losing where it lands.
   */
  module: string
}

export const emptyFilters = (): TreeFilters => ({
  query: '',
  nodetypes: new Set<NodeType>(),
  access: 'all',
  hideDeprecated: false,
  module: '',
})

export const hasActiveFilters = (f: TreeFilters): boolean =>
  f.query.trim() !== '' || f.nodetypes.size > 0 || f.access !== 'all' || f.hideDeprecated
  || f.module !== ''

/** A query that starts with "/" is a path from the root, not a word to find. */
export const isPathQuery = (query: string): boolean => query.trim().startsWith('/')

/** Does this node itself satisfy the non-text filters? */
function passesFacets(node: YangNode, f: TreeFilters): boolean {
  if (f.nodetypes.size > 0 && !f.nodetypes.has(node.nodetype)) return false
  if (f.access !== 'all' && node.access !== f.access) return false
  if (f.hideDeprecated && (node.status === 'deprecated' || node.status === 'obsolete')) return false
  if (f.module && node.module !== f.module) return false
  return true
}

/** Does this node match the free-text query? */
function passesQuery(node: YangNode, needle: string): boolean {
  if (!needle) return true
  if (needle.startsWith('/')) {
    // Anchored: "/native/vlan" keeps that node and everything under it, and
    // nothing that merely mentions vlan elsewhere (/native/interface/Vlan).
    // A trailing slash pins it to exactly that subtree.
    return node.xpath.toLowerCase().startsWith(needle)
  }
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
  roots: TreeRoot[],
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

  for (const root of roots) walk(root.node)
  return { keep, matched }
}

/** A top-level node to render from, with the module tree it belongs to. */
export interface TreeRoot {
  node: YangNode
  moduleName: string
}

/**
 * What the tree renders from: every module's top-level nodes, or — when a
 * node is focused — just that node, the way pyang's --tree-path shows one
 * subtree without the rest of the model around it.
 */
export function rootsOf(modules: ModuleTree[], focusId: number | null): TreeRoot[] {
  if (focusId !== null) {
    for (const module of modules) {
      const found = findNode(module.children, focusId)
      if (found) return [{ node: found, moduleName: module.name }]
    }
  }
  return modules.flatMap((m) => m.children.map((node) => ({ node, moduleName: m.name })))
}

function findNode(nodes: YangNode[], id: number): YangNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const hit = findNode(node.children, id)
    if (hit) return hit
  }
  return null
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
  focusId: number | null = null,
): { rows: Row[]; matchCount: number; totalCount: number } {
  const roots = rootsOf(modules, focusId)
  const filtering = hasActiveFilters(filters)
  const { keep, matched } = filtering
    ? computeVisible(roots, filters)
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

  for (const root of roots) walk(root.node, 0, [], root.moduleName)

  return { rows, matchCount: matched.size, totalCount }
}

/** One place a module puts nodes into the tree. */
export interface GraftPoint {
  id: number
  xpath: string
  xpath_pfx: string
  /** 'root' when the module defines this top-level node; 'augment' when it reaches into another module's tree. */
  kind: 'root' | 'augment'
  /** Nodes from this module at and below this point. */
  count: number
}

/** Everything one module contributes to the assembled tree. */
export interface ModuleContribution {
  name: string
  count: number
  grafts: GraftPoint[]
}

/**
 * Which module put each part of the tree there.
 *
 * The parsed tree is the union of every module in the set, and on a vendor
 * model nearly all of it is augments: Cisco-IOS-XE-vlan owns no root of its
 * own, it reaches into native at /native/vlan and /native/interface/Vlan.
 * A graft point is any node whose owning module differs from its parent's,
 * so listing them per module answers "where does this module put its stuff".
 */
export function moduleContributions(modules: ModuleTree[]): ModuleContribution[] {
  const byModule = new Map<string, ModuleContribution>()
  const entry = (name: string): ModuleContribution => {
    let found = byModule.get(name)
    if (!found) {
      found = { name, count: 0, grafts: [] }
      byModule.set(name, found)
    }
    return found
  }

  const countOwned = (node: YangNode, owner: string): number => {
    let total = node.module === owner ? 1 : 0
    for (const child of node.children) total += countOwned(child, owner)
    return total
  }

  const walk = (node: YangNode, parentModule: string, topLevel: boolean) => {
    const owner = entry(node.module)
    owner.count++
    if (node.module !== parentModule || topLevel) {
      owner.grafts.push({
        id: node.id,
        xpath: node.xpath,
        xpath_pfx: node.xpath_pfx,
        kind: topLevel ? 'root' : 'augment',
        count: countOwned(node, node.module),
      })
    }
    for (const child of node.children) walk(child, node.module, false)
  }

  for (const module of modules) {
    for (const child of module.children) walk(child, module.name, true)
  }

  const out = [...byModule.values()]
  for (const c of out) c.grafts.sort((a, b) => b.count - a.count || a.xpath.localeCompare(b.xpath))
  out.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
  return out
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
