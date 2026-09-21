/**
 * The link a result points at, and where on the page to look.
 *
 * The other half of `src/parts_index/core/links.py`. The export writes the link Chrome's way, because
 * only one form can be written to a file; this side, which is the only place that knows which viewer is
 * about to open it, flips it where Firefox needs the mirror image.
 *
 *     Chrome / PDFium   top is measured DOWNWARDS from the top of the page (Adobe's specification)
 *     Firefox / pdf.js  top is a PDF user-space y, measured UPWARDS from the bottom
 *
 * The page height rides along as `&h=`, a key neither viewer knows and both ignore, so the flip is
 * `h - top` and needs nothing the link does not already carry.
 *
 * `tests/fixtures/links_cases.json` is read by this file's test and by the Python one. Two
 * implementations of a single URL must not drift apart; add a case there before changing either.
 */

export const ZOOM = 200
/** Start the view slightly left of and above the label, so it is not pressed against the edge. */
export const MARGIN = 0.06

export interface LinkDoc {
  public_url?: string | null
  page_url_tpl?: string | null
  page_offset?: number | null
  w_pt?: number | null
  h_pt?: number | null
}

/** Fill one of the four templates in use: none, `#page=`, archive.org's leaf counter, or a `?q=` search. */
export function pageUrl(doc: LinkDoc, n: number, q = ''): string {
  const tpl = doc.page_url_tpl
  const url = doc.public_url ?? ''
  if (!tpl) return url
  const leaf = n - 1 + (doc.page_offset ?? 0)
  return tpl
    .replace('{url}', url)
    .replace('{n}', String(n))
    .replace('{leaf}', String(leaf))
    .replace('{q}', q)
}

/** …and, where the viewer can be told, the first box the part was read in. */
export function partUrl(doc: LinkDoc, n: number, boxes?: number[][] | string | null, q = ''): string {
  const url = pageUrl(doc, n, q)
  if (!url.includes('#page=') || !boxes) return url
  let box: number[] | undefined
  try {
    const parsed = typeof boxes === 'string' ? JSON.parse(boxes) : boxes
    box = parsed?.[0]
  } catch {
    return url
  }
  const { w_pt: w, h_pt: h } = doc
  const x0 = box?.[0]
  const y0 = box?.[1]
  if (x0 === undefined || y0 === undefined || !w || !h) return url
  const left = Math.max(0, x0 / 1000 - MARGIN) * w
  const top = Math.max(0, y0 / 1000 - MARGIN) * h // downwards from the top: Chrome's reading
  return `${url}&zoom=${ZOOM},${Math.round(left)},${Math.round(top)}&h=${Math.round(h)}`
}

/**
 * Turn a link written for Chrome into the same view in Firefox.
 *
 * A link with no `zoom` has nothing to flip, and one with no `&h=` cannot be flipped at all — the height
 * is what the mirror is taken about — so both are returned untouched rather than guessed at.
 */
export function forFirefox(url: string): string {
  const m = url.match(/&zoom=(\d+),(-?[\d.]+),(-?[\d.]+)&h=([\d.]+)/)
  if (!m) return url
  const [, zoom, left, top, h] = m
  const flipped = Math.max(0, Math.round(Number(h) - Number(top)))
  return url.replace(m[0], `&zoom=${zoom},${left},${flipped}`)
}

/** True when this browser measures `top` from the bottom of the page. */
export function needsFlip(ua: string = navigator.userAgent): boolean {
  return /firefox|seamonkey/i.test(ua)
}

/** The link to hand this visitor. */
export function forViewer(url: string, ua?: string): string {
  return needsFlip(ua) ? forFirefox(url) : url
}
