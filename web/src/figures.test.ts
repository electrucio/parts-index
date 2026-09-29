/** A simulated curve on the sheet's own axes. */
import { describe, expect, it } from 'vitest'
import { offScale, place, ticks } from './figures'
import type { SheetFigure } from './types'

const fig: SheetFigure = {
  n: 18, caption: 'Temperature Coefficients', page: 6, kind: 'graph', crop: true,
  x: ['collector current', 'mA', 'lin', 0, 200], y: ['coefficient', 'mV/°C', 'lin', -2, 1],
  series: [['θVC', 'solid'], ['θVB', 'solid']],
}

describe('the sheet\'s axes', () => {
  it('place a value by the axis\'s own scale', () => {
    expect(place(['i', 'mA', 'log', 0.1, 10], 1, 100)).toBeCloseTo(50)
    expect(place(['v', 'V', 'lin', 0, 1.2], 0.6, 100)).toBeCloseTo(50)
  })
  it('tick 1-2-5 per decade on a log axis and round steps on a linear one', () => {
    expect(ticks(['i', 'mA', 'log', 0.1, 10]).map((t) => t.v)).toEqual([0.1, 0.2, 0.5, 1, 2, 5, 10])
    expect(ticks(['v', 'V', 'lin', 0, 1.2]).map((t) => t.v)).toEqual([0, 0.5, 1])
  })
})

describe('a curve the sheet\'s scale cannot show', () => {
  it('is named with its range instead of vanishing', () => {
    const got = offScale(fig, { 'θVC': [[10, -1.5], [200, -1.4]], 'θVB': [[10, -3.2], [200, -2.3]] })
    expect(got).toEqual([['θVB', -3.2, -2.3]])
  })
})
