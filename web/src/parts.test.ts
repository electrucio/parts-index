/** Filtering and ordering the parts list, which is the only logic the browser still does for itself. */
import { describe, expect, it } from 'vitest'

import { keep, ofDevice, order, pageHref, search } from './parts'
import type { PartRow } from './types'

/** The last number is an index into `KINDS`, the way the built index carries it. */
const KINDS = ['tube', 'bjt', 'bjt/jfet/mosfet', '']
const rows: PartRow[] = [
  ['12AX7', 2478, 3588, 6, 0],
  ['12AX7A', 40, 55, 0, 0],
  ['ECC83', 900, 1200, 3, 0],
  ['BC108', 700, 900, 0, 1],
  ['BC108B', 12, 14, 2, 1],
  ['2N3055', 1500, 1900, 9, 2],
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
    const tied: PartRow[] = [['B', 10, 0, 1, 3], ['A', 10, 0, 1, 3], ['C', 10, 0, 5, 3]]
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

describe('the link to a page', () => {
  const doc = 'https://e.org/amp.pdf'

  it('is rebuilt from the document it belongs to', () => {
    expect(pageHref(doc, '#page=2&zoom=200,55,523&h=792'))
      .toBe('https://e.org/amp.pdf#page=2&zoom=200,55,523&h=792')
  })

  it('is left alone when it was stored whole', () => {
    expect(pageHref(doc, 'https://elsewhere.org/x.pdf#page=9'))
      .toBe('https://elsewhere.org/x.pdf#page=9')
  })

  it('is the document itself when there is no suffix', () => {
    expect(pageHref(doc, '')).toBe(doc)
  })

  it('does not mistake a fragment that looks like a scheme', () => {
    expect(pageHref(doc, '/page/n4/mode/2up')).toBe('https://e.org/amp.pdf/page/n4/mode/2up')
  })
})

describe('filtering by kind of device', () => {
  it('shows only that kind', () => {
    expect(ofDevice(rows, 'tube', KINDS).map((r) => r[0])).toEqual(['12AX7', '12AX7A', 'ECC83'])
  })

  it('keeps an ambiguous part in every group it could belong to', () => {
    // 2N3055 is a JEDEC number, and the family pattern cannot tell a transistor from a JFET.
    expect(ofDevice(rows, 'bjt', KINDS).map((r) => r[0])).toContain('2N3055')
    expect(ofDevice(rows, 'fet', KINDS).map((r) => r[0])).toContain('2N3055')
  })

  it('leaves everything alone when no kind is chosen', () => {
    expect(ofDevice(rows, '', KINDS)).toHaveLength(rows.length)
  })

  it('returns nothing rather than everything for a kind this index has none of', () => {
    expect(ofDevice(rows, 'opto', KINDS)).toEqual([])
  })
})
