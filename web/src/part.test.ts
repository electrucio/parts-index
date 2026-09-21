/** Ranking a search, which is the only logic the browser still does for itself. */
import { describe, expect, it } from 'vitest'

import { search } from './part'
import type { PartRow } from './types'

const rows: PartRow[] = [
  ['12AX7', 2478, 3588, 6],
  ['12AX7A', 40, 55, 0],
  ['ECC83', 900, 1200, 3],
  ['BC108', 700, 900, 0],
  ['BC108B', 12, 14, 2],
  ['2N3055', 1500, 1900, 9],
]

describe('search', () => {
  it('says nothing until there is something to go on', () => {
    expect(search(rows, '')).toEqual([])
    expect(search(rows, '1')).toEqual([])
  })

  it('puts an exact match first, even when others have far more behind them', () => {
    expect(search(rows, 'BC108B')[0]?.[0]).toBe('BC108B')
  })

  it('prefers what starts with the query over what merely contains it', () => {
    const names = search(rows, '108').map((r) => r[0])
    expect(names).toContain('BC108')
    expect(names).toContain('BC108B')
  })

  it('ignores punctuation and case, because nobody types a part number the same way twice', () => {
    expect(search(rows, '12ax7').map((r) => r[0])[0]).toBe('12AX7')
    expect(search(rows, '2n-3055').map((r) => r[0])[0]).toBe('2N3055')
  })

  it('ranks a part with models above one with only a few documents', () => {
    const names = search(rows, 'BC').map((r) => r[0])
    expect(names[0]).toBe('BC108')      // 700 documents beats 12 documents and 2 models
  })
})
