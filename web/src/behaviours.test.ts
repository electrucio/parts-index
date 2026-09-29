/** Every id the Python side can publish has its words here: the fixture is the Python module's own copy. */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { CLAIM_LABEL, LIMIT_LABEL } from './behaviours'

const vocab = JSON.parse(readFileSync(new URL('../../tests/fixtures/behaviours.json', import.meta.url), 'utf8')) as {
  claims: Record<string, string>
  limits: Record<string, string>
}

describe('the words for what an author declares', () => {
  it('cover every claim and every limit, and nothing else', () => {
    expect(Object.keys(CLAIM_LABEL).sort()).toEqual(Object.keys(vocab.claims).sort())
    expect(Object.keys(LIMIT_LABEL).sort()).toEqual(Object.keys(vocab.limits).sort())
  })
})
