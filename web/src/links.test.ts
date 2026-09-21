/**
 * The TypeScript half of the link builder, checked against the same fixture as the Python half.
 *
 * If one of these fails and the Python one passes, the two have drifted: fix the one that is wrong,
 * and add the case that caught it to the fixture rather than to this file.
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import { forFirefox, forViewer, MARGIN, needsFlip, pageUrl, partUrl, ZOOM } from './links'

const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/links_cases.json', import.meta.url), 'utf8'))

it('agrees with the Python half on its constants', () => {
  expect(ZOOM).toBe(fixture.zoom)
  expect(MARGIN).toBe(fixture.margin)
})

describe('the link to a part', () => {
  for (const c of fixture.cases) {
    it(c.name, () => {
      expect(partUrl(c.doc, c.page, c.boxes ?? null, c.q ?? '')).toBe(c.expect)
    })
  }
})

describe('flipping a Chrome link for Firefox', () => {
  for (const c of fixture.firefox_flip.cases) {
    it(c.name, () => {
      expect(forFirefox(c.url)).toBe(c.expect)
    })
  }
})

it('asks the page, not the box, which page a document is on', () => {
  const doc = { public_url: 'https://e.org/a.pdf', page_url_tpl: '{url}#page={n}', w_pt: 612, h_pt: 792 }
  expect(pageUrl(doc, 2)).toBe('https://e.org/a.pdf#page=2')
  expect(partUrl(doc, 2, [[150, 720, 210, 745]])).toContain('zoom')
})

it('recognises the viewers that measure from the other edge', () => {
  expect(needsFlip('Mozilla/5.0 (X11; Linux x86_64; rv:155.0) Gecko/20100101 Firefox/155.0')).toBe(true)
  expect(needsFlip('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153.0 Safari/537.36')).toBe(false)
})

it('hands each visitor the link their viewer understands', () => {
  const chrome = 'https://e.org/a.pdf#page=2&zoom=200,55,523&h=792'
  expect(forViewer(chrome, 'Chrome/153.0')).toBe(chrome)
  expect(forViewer(chrome, 'Firefox/155.0')).toBe('https://e.org/a.pdf#page=2&zoom=200,55,269')
})
