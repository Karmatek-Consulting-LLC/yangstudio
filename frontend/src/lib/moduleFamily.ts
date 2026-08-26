/** Grouping advertised device modules into families you'd actually filter by.
 *
 * A real IOS-XE box advertises ~500 modules, and roughly a third are legacy
 * SNMP MIBs that are useless for YANG work. Without a way to tell them apart,
 * the list is unusable and "download everything" is the only option.
 */

export type FamilyId = 'iosxe' | 'openconfig' | 'ietf' | 'cisco' | 'mib' | 'other'

export const FAMILY_LABELS: Record<FamilyId, string> = {
  iosxe: 'IOS-XE',
  openconfig: 'OpenConfig',
  ietf: 'IETF / IANA',
  cisco: 'Cisco other',
  mib: 'SNMP MIB',
  other: 'Other',
}

/** Order matters: the first match wins, so specific tests precede general ones. */
export function moduleFamily(name: string): FamilyId {
  if (name.endsWith('-MIB') || name.endsWith('-TC')) return 'mib'
  if (name.startsWith('Cisco-IOS-XE-')) return 'iosxe'
  if (name.startsWith('openconfig-')) return 'openconfig'
  if (name.startsWith('ietf-') || name.startsWith('iana-')) return 'ietf'
  if (/^cisco-/i.test(name)) return 'cisco'
  return 'other'
}

/** Families present in a list, with counts, in a stable display order. */
export function familyCounts(names: string[]): { id: FamilyId; count: number }[] {
  const counts = new Map<FamilyId, number>()
  for (const name of names) {
    const family = moduleFamily(name)
    counts.set(family, (counts.get(family) ?? 0) + 1)
  }
  const order: FamilyId[] = ['iosxe', 'openconfig', 'ietf', 'cisco', 'other', 'mib']
  return order
    .filter((id) => counts.has(id))
    .map((id) => ({ id, count: counts.get(id)! }))
}
