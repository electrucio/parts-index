/** Filtering and ordering the parts list, which is the only logic the browser still does for itself. */
import { describe, expect, it } from 'vitest'

import { keep, order, search } from './parts'
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
})

describe('the order of the list', () => {
  it('puts the most used first by default, which is what the front page shows', () => {
    expect(order(rows, 'documents').map((r) => r[0])[0]).toBe('12AX7')    // 2,478 documents
  })

  it('breaks a tie on documents by models, and then by name', () => {
    const tied: PartRow[] = [['B', 10, 0, 1], ['A', 10, 0, 1], ['C', 10, 0, 5]]
    expect(order(tied, 'documents').map((r) => r[0])).toEqual(['C', 'A', 'B'])
  })

  it('can be asked for the parts with the most models instead', () => {
    expect(order(rows, 'models').map((r) => r[0])[0]).toBe('2N3055')      // 9 models
  })

  it('can be asked for plain alphabetical order', () => {
    expect(order(rows, 'name').map((r) => r[0])).toEqual(
      [...rows].map((r) => r[0]).sort((a, b) => a.localeCompare(b)),
    )
  })

  it('leaves the rows it was given alone', () => {
    const before = rows.map((r) => r[0])
    order(rows, 'name')
    expect(rows.map((r) => r[0])).toEqual(before)
  })
})

describe('the filter chips', () => {
  it('keeps everything by default', () => {
    expect(keep(rows, '')).toHaveLength(rows.length)
  })

  it('can show only the parts a model exists for, or only the ones still without', () => {
    expect(keep(rows, 'models').map((r) => r[0])).toEqual(['12AX7', 'ECC83', 'BC108B', '2N3055'])
    expect(keep(rows, 'nomodel').map((r) => r[0])).toEqual(['12AX7A', 'BC108'])
  })

  it('and the two halves add up to the whole', () => {
    expect(keep(rows, 'models').length + keep(rows, 'nomodel').length).toBe(rows.length)
  })
})
