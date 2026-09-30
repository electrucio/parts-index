import { describe, expect, it } from 'vitest'
import { FIELD, reportBody } from './report'

describe('a report', () => {
  it('carries the message, the part and the page, each under its own question', () => {
    const body = reportBody('  Wrong pinout on page 3\n', 'BC547', 'https://example.org/?part=BC547')
    expect(body.get(FIELD.message)).toBe('Wrong pinout on page 3')
    expect(body.get(FIELD.part)).toBe('BC547')
    expect(body.get(FIELD.page)).toBe('https://example.org/?part=BC547')
  })

  it('from the footer names no part', () => {
    expect(reportBody('Search is slow', undefined, 'https://example.org/').get(FIELD.part)).toBe('')
  })

  it('names three different questions', () => {
    expect(new Set(Object.values(FIELD)).size).toBe(3)
  })
})
