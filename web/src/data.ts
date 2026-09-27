/**
 * The two files every view may need, fetched once and shared. The search index is 61 KB gzipped and the
 * catalogue a few more; asking twice for either would be the only cost of opening a family page from a
 * part page, so neither is asked twice.
 */
import type { Catalogue, PartIndex } from './types'

export const DATA = `${import.meta.env.BASE_URL}data`

let index: Promise<PartIndex> | null = null
let catalogue: Promise<Catalogue> | null = null

export function loadIndex(): Promise<PartIndex> {
  index ??= fetch(`${DATA}/parts.json`)
    .then((r) => (r.ok ? (r.json() as Promise<PartIndex>) : Promise.reject(r.status)))
    .catch(() => ({ schema: 0, sources: [], kinds: [], deviceKinds: [], parts: [] }))
  return index
}

export function loadCatalogue(): Promise<Catalogue> {
  catalogue ??= fetch(`${DATA}/catalogue.json`)
    .then((r) => (r.ok ? (r.json() as Promise<Catalogue>) : Promise.reject(r.status)))
    .catch(() => ({ families: [], makers: {}, schemes: {}, refs: {}, listings: {} }))
  return catalogue
}

/**
 * Move to another view of the site without a reload. The router in main.tsx listens for popstate, so a
 * link anywhere — a family named on a part's page, a maker in a family's — needs only its href.
 */
export function go(href: string) {
  history.pushState({}, '', href)
  dispatchEvent(new PopStateEvent('popstate'))
  scrollTo(0, 0)
}

/** An <a> that follows `go` instead of reloading, and still opens in a new tab when asked. */
export function follow(e: MouseEvent, href: string) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  go(href)
}
