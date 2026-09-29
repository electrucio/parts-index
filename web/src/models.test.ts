/** How a value and a cell read on the page. */
import { describe, expect, it } from 'vitest'
import { cellText, cellTitle, fmt } from './models'
import type { SheetRow } from './types'

const row: SheetRow = [5, 2, 'Cobo', 'VCB=5.0V', '', '', '4.0', 'pF', '', '', true]

describe('a value as a data sheet prints it', () => {
  it('keeps four significant figures and no exponent where the sheet would not use one', () => {
    expect(fmt(2.02734)).toBe('2.027')
    expect(fmt(-0.3446)).toBe('-0.3446')
    expect(fmt(144.83)).toBe('144.8')
    expect(fmt(1.799e-14)).toBe('1.80e-14')
    expect(fmt(0)).toBe('0')
  })
})

describe('a cell', () => {
  it('says why a model has no value', () => {
    expect(cellText(['card', ['CJC']])).toBe('n.m. card: CJC')
    expect(cellText(['card', []])).toBe('n.m. card')
    expect(cellText(['author', ['distortion']])).toBe('n.m. author')
    expect(cellTitle(['author', ['distortion']], row)).toContain('distortion not modelled')
    expect(cellText(['none'])).toBe('—')
  })
  it('names a typical for what it is', () => {
    expect(cellTitle(['typ', 29.35, 1.47], row)).toContain('one device, not a limit')
  })
})
