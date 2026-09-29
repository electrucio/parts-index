/**
 * The parts browser: a list on the left, the part on the right.
 *
 * The shape is the previous site's, which is the one worth keeping — a list you can read down while a
 * part stays open beside it, rather than a search box that answers nothing until you type. What is
 * different is what it is built from: 15,558 parts instead of the 1,712 that have a model, because this
 * index also knows where a part is *used*, and that is most of what there is to say about a part.
 *
 * `parts.json` is 61 KB gzipped and holds all of them, so filtering and sorting never ask the server.
 * Opening a part is one request for a file the build already joined and grouped.
 */
import { Fragment } from 'preact'
import { useEffect, useMemo, useRef, useState } from 'preact/hooks'

import { AboutPart, Databooks, PartName } from './about'
import { DATA, loadIndex, reloadIndex } from './data'
import { Fold } from './fold'
import { forViewer } from './links'
import { ModelChecks } from './models'
import type { DeviceKind, PageUse, PartIndex, PartPage, PartRow, UseKind } from './types'
export const n = (v: number) => v.toLocaleString('en-GB')

export type Sort = 'documents' | 'models' | 'sheets' | 'name'
export type Dir = 'asc' | 'desc'

/** The list's columns, each a way of ordering it. A count starts from the most; a name from A. */
const COLUMNS: { key: Sort; label: string; title: string; num: boolean }[] = [
  { key: 'name', label: 'Part', title: 'Part number', num: false },
  { key: 'documents', label: 'Mentions', title: 'Documents that print it', num: true },
  { key: 'models', label: 'SPICE', title: 'SPICE models found for it', num: true },
  { key: 'sheets', label: 'Sheets', title: 'Data sheets and databook pages linked for it', num: true },
]
export const NATURAL: Record<Sort, Dir> = { name: 'asc', documents: 'desc', models: 'desc', sheets: 'desc' }
const PAGE = 300

/**
 * What kind of part a row is: the entries of the device menu it answers to, the same ones the filter
 * uses — every one it could be, so a D model nothing narrows says "Diodes / Germanium diodes".
 */
export function typeOf(r: PartRow, menu: DeviceKind[]): string {
  return menu.filter((_, i) => (r[4] & (1 << i)) !== 0).map((d) => d.label).join(' / ')
}

const COUNT: Record<Exclude<Sort, 'name'>, (r: PartRow) => number> = {
  documents: (r) => r[1],
  models: (r) => r[3],
  sheets: (r) => r[6] ?? 0,
}

/** The order asked for, and inside a tie the most used first, then the most models, then by name. */
export function compare(by: Sort, dir: Dir = NATURAL[by]): (a: PartRow, b: PartRow) => number {
  const sign = dir === 'asc' ? 1 : -1
  return (a, b) => (by === 'name' ? sign * a[0].localeCompare(b[0]) : sign * (COUNT[by](a) - COUNT[by](b)))
    || b[1] - a[1] || b[3] - a[3] || a[0].localeCompare(b[0])
}

/**
 * What a query matches, best first: the part itself, then what starts with it, then what contains it —
 * and inside each of those, whatever order was asked for. The chosen sort used to be dropped as soon as
 * anything was typed, which put parts with no use at all above parts with hundreds of them, because the
 * relevance weight it fell back to counted one SPICE model as twenty-five documents.
 *
 * Last, what the query starts with: somebody who types the order code off a reel — AD817ARZ, TL072CP,
 * LM4562NA — is asking for the type, and the corpus mostly prints the type alone. A key has to be four
 * characters or more to count as the head of a query, so BC does not answer for BC108B.
 */
/**
 * Where a part's page is served from. The builder writes APT1608LSECK/J3-PRV as part/APT1608LSECK/J3-PRV.json,
 * a file inside a directory, so the request has to say the slash as a slash: a static host (GitHub Pages)
 * does not turn %2F into a directory separator, and 267 parts carry one.
 */
export function partPath(part: string): string {
  return part.split('/').map(encodeURIComponent).join('/')
}

export function search(rows: PartRow[], q: string, by: Sort = 'documents', dir: Dir = NATURAL[by]): PartRow[] {
  const needle = q.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
  if (needle.length < 2) return []
  const exact: PartRow[] = []
  const starts: PartRow[] = []
  const has: PartRow[] = []
  const heads: PartRow[] = []
  for (const r of rows) {
    const key = r[0].toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (key === needle) exact.push(r)
    else if (key.startsWith(needle)) starts.push(r)
    else if (key.includes(needle)) has.push(r)
    else if (key.length >= 4 && needle.startsWith(key)) heads.push(r)
  }
  for (const g of [exact, starts, has, heads]) g.sort(compare(by, dir))
  heads.sort((a, b) => b[0].length - a[0].length)     // the longest head is the nearest: BC108B before BC108 for BC108BZ
  return [...exact, ...starts, ...has, ...heads]
}

/** All the parts, in the order asked for. Sorting 15,558 rows is cheap; rendering them is not. */
export function order(rows: PartRow[], by: Sort, dir: Dir = NATURAL[by]): PartRow[] {
  return [...rows].sort(compare(by, dir))
}

/**
 * The rows that answer to the chosen device. An empty choice means all of them.
 *
 * A part carries one bit per device, because it can answer to more than one: a JEDEC number like
 * `2N3904` or `2N5457` could be a transistor, a JFET or a MOSFET and the family pattern cannot tell,
 * so it appears under all three rather than being guessed into one.
 */
export function ofDevice(rows: PartRow[], device: string, menu: DeviceKind[]): PartRow[] {
  const at = menu.findIndex((d) => d.key === device)
  if (at < 0) return rows
  const bit = 1 << at
  return rows.filter((r) => (r[4] & bit) !== 0)
}

/** Where one file is had: its download link, the member inside an archive, or the simulator it ships with. */
function Get({ url, member, installed }: { url?: string; member?: string; installed?: string }) {
  return (
    <>
      {url ? <a href={url}>download</a>
        : installed ? <span class="muted small">ships with {installed}</span>
          : <span class="muted small">origin not recorded</span>}
      {member && <span class="muted small"> · {member}</span>}
    </>
  )
}

function Models({ page }: { page: PartPage }) {
  const m = page.models
  if (!m) return null
  return (
    <section class="stack-s">
      <h3>Where the model comes from</h3>
      <p class="muted small">
        Every model is linked to its source with a checksum and the lines that hold it, and so is every
        other place the same model can be had — the rows marked ↳. The file itself is not hosted here:
        almost every vendor forbids that, and forbidding redistribution does not forbid saying exactly
        where to look.
      </p>
      <div class="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Source</th><th>Name</th><th>Kind</th><th>Changed</th><th>Get it</th>
            </tr>
          </thead>
          <tbody>
            {m.models.map((mo, i) => (
              <Fragment key={i}>
                <tr>
                  <td>{mo.source}</td>
                  <td>
                    <code>{mo.name}</code>
                    {mo.standin && <> <span class="chip">model of {mo.standin}</span></>}
                    {mo.alias && <> <span class="chip">listed as {mo.alias}</span></>}
                  </td>
                  <td>{mo.type || mo.def}</td>
                  <td>
                    {mo.verbatim
                      ? <span class="muted small">verbatim</span>
                      : <span class="chip">{(mo.changes ?? []).join(' ') || 'changed'}</span>}
                  </td>
                  <td>
                    <Get url={mo.get.url} member={mo.get.member} installed={mo.get.installed_with} />
                    {mo.symbol && <> · <span class="chip">symbol</span></>}
                  </td>
                </tr>
                {(mo.copies ?? []).map((c, j) => (
                  <tr key={`${i}.${j}`} class="copy">
                    <td><span class="muted">↳</span> {c.source}</td>
                    <td><code>{c.name}</code></td>
                    <td colSpan={2}><span class="muted small">the same model as {mo.source}'s</span></td>
                    <td><Get url={c.url} member={c.member} installed={c.installed_with} /></td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/**
 * The link to one page, rebuilt from the document's own.
 *
 * The build stores `#page=47&zoom=200,55,523&h=792` rather than the whole address, because that is what
 * it is: all 94,170 page links in the index are a suffix of their document's URL, and writing them out
 * was three quarters of the URL text on a part's page. One that is not a suffix is stored whole and
 * says so by starting with a scheme.
 */
export function pageHref(docUrl: string, suffix: string): string {
  return /^[a-z]+:/i.test(suffix) ? suffix : docUrl + suffix
}

/** The kinds of use worth a word beside the line, because they say "not here, really". */
const KIND_LABEL: Partial<Record<UseKind, string>> = {
  mention: 'mentioned',
  advert: 'advert',
  none: 'not this part',
  reference: 'listed',
}

/**
 * One page: the link, and the line saying what the part does there.
 *
 * The line was read off the page by a language model on the maintainer's machine, one call per page. It
 * is reliable about where the part sits — the stage, the board, the list — and was told not to say what
 * the device is for, which it would guess from the type number. A page not summarised yet shows the
 * designators beside the part instead, which is all the index knew before.
 */
function PageLink({ p, docUrl }: { p: PageUse; docUrl: string }) {
  const line = p[4]
  const kind = p[5]
  const label = kind && KIND_LABEL[kind]
  return (
    <li>
      <a href={forViewer(pageHref(docUrl, p[1]))} target="_blank" rel="noopener">page {p[0]}</a>
      {label && <> <span class={`pill ${kind === 'reference' ? 'na' : 'off'}`}>{label}</span></>}
      {line
        ? <span class="line"> {line}</span>
        : p[2] && <span class="muted small"> beside {p[2]}</span>}
    </li>
  )
}

function Document({ d }: { d: PartPage['docs'][0] }) {
  const summary = (
    <>
      <strong>{d.t || d.u}</strong>
      <span class="count">{n(d.p.length)} {d.p.length === 1 ? 'page' : 'pages'}</span>
      {d.schematic ? <span class="pill acc">schematic</span> : null}
      {d.y ? <span class="small muted">{d.y}</span> : null}
      {d.also ? <span class="small muted">also at {d.also.join(', ')}</span> : null}
    </>
  )
  return (
    <Fold summary={summary} level={3}>
      {() => (
        // No link to the document on its own: every page link opens it, at a more useful place.
        // Pages with a line each take a row; bare page links still fit several to a row.
        <ul class={d.p.some((p) => p[4]) ? 'uselist' : 'uselist cols'}>
          {d.p.map((p, j) => <PageLink key={j} p={p} docUrl={d.u} />)}
        </ul>
      )}
    </Fold>
  )
}

/** A group of documents, folded by source: a part with three thousand hits has to stay readable. */
/**
 * A source's documents by date, oldest first: how a magazine's issues are read. The date is as precise
 * as the index has it — `1985-08` or `1985` — so it sorts as text; a document with none goes last, in
 * the order the build gave.
 */
export function byDate(docs: PartPage['docs']): PartPage['docs'] {
  return docs.map((d, i) => [d, i] as const)
    .sort(([a, i], [b, j]) => (a.y ? (b.y ? a.y.localeCompare(b.y) : -1) : (b.y ? 1 : 0)) || i - j)
    .map(([d]) => d)
}

function Group({
  title, note, docs, sources, open, dated = false,
}: {
  title: string; note: string; docs: PartPage['docs']; sources: string[]; open: boolean
  /** Each source's documents in date order, instead of the most useful first. */
  dated?: boolean
}) {
  if (docs.length === 0) return null
  const bySource = new Map<string, PartPage['docs']>()
  for (const d of docs) {
    const k = sources[d.s] ?? '?'
    const g = bySource.get(k)
    if (g) g.push(d)
    else bySource.set(k, [d])
  }
  const groups = [...bySource.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
  const pages = docs.reduce((t, d) => t + d.p.length, 0)
  const summary = (
    <>
      <strong>{title}</strong>
      <span class="count">{n(docs.length)} · {n(pages)} pages</span>
      <span class="small muted">{note}</span>
    </>
  )
  return (
    <Fold summary={summary} open={open} level={1}>
      {() => groups.map(([source, ds]) => (
        <Fold
          key={source}
          level={2}
          open={groups.length === 1}
          summary={<><strong>{source}</strong> <span class="count">{n(ds.length)}</span></>}
        >
          {() => (dated ? byDate(ds) : ds).map((d, i) => <Document key={i} d={d} />)}
        </Fold>
      ))}
    </Fold>
  )
}

const REPO_HOST = 'https://github.com/'

/** `owner/repo` of a GitHub address, or null for anything else. */
export function repoOf(url: string): string | null {
  if (!url.startsWith(REPO_HOST)) return null
  const [owner, repo] = url.slice(REPO_HOST.length).split('/')
  return owner && repo ? `${owner}/${repo}` : null
}

/**
 * Boards somebody is making: every GitHub repository that places the part, in one list, once each, the
 * most starred first.
 *
 * They are found two ways — sheets the index read page by page (the open-hardware crawls, a journal, a
 * site that links its boards) and projects the research datasets say place the part — and a reader has
 * no use for that distinction, so it is not shown. A repository whose sheets were read opens onto them,
 * each with its page links; the others link to the repository.
 */
function OpenSource({ page, docs }: { page: PartPage; docs: PartPage['docs'] }) {
  type Repo = { name: string; stars: number; forks: number; watchers: number; sheets: number; docs: PartPage['docs'] }
  const all = new Map<string, Repo>()
  const entry = (name: string) => {
    const k = name.toLowerCase()
    let r = all.get(k)
    if (!r) all.set(k, (r = { name, stars: 0, forks: 0, watchers: 0, sheets: 0, docs: [] }))
    return r
  }
  for (const [name, sheets, stars, forks, watchers] of page.repos ?? []) {
    Object.assign(entry(name), { stars, forks, watchers, sheets })
  }
  for (const d of docs) {
    const name = repoOf(d.u)
    if (name) entry(name).docs.push(d)
  }
  for (const [name, [stars, forks, watchers]] of Object.entries(page.stars ?? {})) {
    const r = all.get(name.toLowerCase())
    if (r && !r.stars) Object.assign(r, { stars, forks, watchers })
  }
  if (!all.size) return null
  const list = [...all.values()].sort((a, b) =>
    b.stars - a.stars || Math.max(b.docs.length, b.sheets) - Math.max(a.docs.length, a.sheets) || a.name.localeCompare(b.name))
  const more = Math.max(0, (page.n.repos ?? 0) - (page.repos?.length ?? 0))
  const summary = (
    <>
      <strong>Open-source projects</strong>
      <span class="count">{n(list.length + more)}</span>
      <span class="small muted">boards on GitHub that place this part, the most starred first</span>
    </>
  )
  const Stars = ({ r }: { r: Repo }) => (r.stars > 0
    ? <span class="muted small" title={`${n(r.stars)} stars, ${n(r.forks)} forks, ${n(r.watchers)} watching`}>★{n(r.stars)}</span>
    : null)
  const Out = ({ r }: { r: Repo }) => (
    <a class="out" href={`${REPO_HOST}${r.name}`} target="_blank" rel="noopener" title="Open the repository on GitHub"
      onClick={(e) => e.stopPropagation()}>↗ GitHub</a>
  )
  return (
    <Fold summary={summary} level={1} open={page.docs.length === docs.length}>
      {() => (
        <div class="repolist">
          {list.map((r) => {
            const sheets = Math.max(r.docs.length, r.sheets)
            const count = sheets > 1 && <span class="count">{n(sheets)} sheets</span>
            return r.docs.length ? (
              <Fold
                key={r.name} level={2} cls="repo"
                summary={<><strong>{r.name}</strong><Out r={r} /><Stars r={r} />{count}</>}
              >
                {() => r.docs.map((d, i) => <Document key={i} d={{ ...d, t: d.t.replace(`${r.name}: `, '') }} />)}
              </Fold>
            ) : (
              <div class="plain" key={r.name}>
                <strong>{r.name}</strong><Out r={r} /><Stars r={r} />{count}
              </div>
            )
          })}
          {more > 0 && <p class="muted small">and {n(more)} more on GitHub, with fewer stars</p>}
        </div>
      )}
    </Fold>
  )
}

const SITE_KINDS = new Set(['site', 'factory', 'reference'])
const PAPER_KINDS = new Set(['magazine', 'book'])

/**
 * Where the part is used, in three groups: what somebody built, what a magazine or a book printed, and
 * the boards on GitHub. A source of any other kind is not shown; the build already leaves those out.
 */
function Uses({ page, sources, kinds }: { page: PartPage; sources: string[]; kinds: string[] }) {
  const kindOf = (d: PartPage['docs'][0]) => kinds[d.s] ?? ''
  const repos = page.docs.filter((d) => repoOf(d.u))
  const others = page.docs.filter((d) => !repoOf(d.u))
  const built = others.filter((d) => SITE_KINDS.has(kindOf(d)))
  const paper = others.filter((d) => PAPER_KINDS.has(kindOf(d)))
  if (built.length + paper.length + repos.length === 0 && !page.repos?.length) return null
  const { documents, shown, copies } = page.n
  return (
    <section class="stack-s">
      <h3>Where it is used</h3>
      <p class="muted small">
        {n(documents)} document{documents === 1 ? '' : 's'}
        {shown < documents && <> · showing the {n(shown)} most likely to help</>}
        {copies > 0 && <> · {n(copies)} duplicate cop{copies === 1 ? 'y' : 'ies'} folded in</>}
        {' '}· a page link opens the sheet where the part is, not at the front, and the line beside it
        says what the part does there, read off the page by a language model: trust it about where,
        less about what.
      </p>
      <Group
        title="Projects and factory schematics" open
        note="project sites, factory archives and reference works"
        docs={built} sources={sources}
      />
      <Group
        title="Magazines and books" open={built.length === 0} dated
        note="the exact page of the PDF; each magazine's issues in date order"
        docs={paper} sources={sources}
      />
      <OpenSource page={page} docs={repos} />
    </section>
  )
}

/**
 * Who vouches for a part the index has nothing of its own for.
 *
 * Without this a reader who looks up an EFT83 is told nothing at all. "Sold by musikding.de under
 * Transistoren / Germanium Transistoren / Selektiert, PNP, hFE 40–50" is an answer, and it is also this
 * project's own note of what to look for next.
 */
function Listed({ page }: { page: PartPage }) {
  const listed = page.listed
  if (!listed?.length) return null
  return (
    <section class="stack-s">
      <h3>Who lists this part</h3>
      <ul class="uselist">
        {listed.map((l, i) => (
          <li key={i}>
            <strong>{l.source}</strong>
            {l.category && <span class="muted"> · {l.category}</span>}
            {l.note && <span class="muted"> · {l.note}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Whether a part page and the index it is read with were built from the same list of sources. A page
 *  without a stamp is from before there were stamps, and is read as it always was. */
export function sameSources(page: { ss?: string } | null, stamp: string | undefined): boolean {
  return !page?.ss || !stamp || page.ss === stamp
}

export function Detail({ part, sources, kinds, stamp, onStale }: {
  part: string; sources: string[]; kinds: string[]; stamp?: string; onStale?: (stamp: string) => void
}) {
  const [page, setPage] = useState<PartPage | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    setPage(null)
    setError(false)
    fetch(`${DATA}/part/${partPath(part)}.json`)
      .then((r) => (r.ok ? (r.json() as Promise<PartPage>) : Promise.reject(r.status)))
      .then(setPage)
      .catch(() => setError(true))
  }, [part])
  const fresh = sameSources(page, stamp)
  useEffect(() => {
    if (page?.ss && !fresh) onStale?.(page.ss)
  }, [page, fresh])

  return (
    <section class="evidence stack">
      <div class="ptitle">
        <PartName part={part} page={page} />
        {page?.models?.kind && <span class="chip">{page.models.kind}</span>}
      </div>
      {error && <p class="muted">Nothing is published for {part} yet.</p>}
      {!error && !page && <p class="muted">Loading…</p>}
      {page && (
        <>
          <AboutPart page={page} sources={fresh ? sources : []} />
          <Listed page={page} />
          <Models page={page} />
          <ModelChecks page={page} />
          {fresh ? <Uses page={page} sources={sources} kinds={kinds} /> : <p class="muted">Loading…</p>}
          <Databooks page={page} />
          {page.docs.length === 0 && !page.models && (
            <p class="muted">
              No SPICE model published and no schematic indexed yet
              {page.listed?.length ? ', which makes it one to look for.' : '.'}
            </p>
          )}
        </>
      )}
    </section>
  )
}

const SIDE = { min: 260, fallback: 480, key: 'pidx.side' }

/** The list's width, as the reader last left it. Kept in this browser only, and only as a convenience. */
function savedWidth(): number {
  try { return Number(localStorage.getItem(SIDE.key)) || SIDE.fallback } catch { return SIDE.fallback }
}

/**
 * The bar between the list and the part: drag it, or focus it and use the arrow keys.
 *
 * The width is a CSS variable on the browser, so the grid does the layout and nothing re-renders the
 * fifty thousand rows while it moves.
 */
function Splitter({ host, width, setWidth }: {
  host: { current: HTMLDivElement | null }; width: number; setWidth: (w: number) => void
}) {
  const clamp = (w: number) => Math.round(Math.min(Math.max(w, SIDE.min), innerWidth * 0.7))
  const commit = (w: number) => {
    setWidth(w)
    try { localStorage.setItem(SIDE.key, String(w)) } catch { /* private window: forget it */ }
  }
  const onDown = (e: PointerEvent) => {
    const bar = e.currentTarget as HTMLElement
    const left = host.current?.getBoundingClientRect().left ?? 0
    bar.setPointerCapture(e.pointerId)
    let w = width
    const move = (ev: PointerEvent) => {
      w = clamp(ev.clientX - left)
      host.current?.style.setProperty('--side', `${w}px`)
    }
    const up = () => {
      bar.removeEventListener('pointermove', move)
      bar.removeEventListener('pointerup', up)
      commit(w)
    }
    bar.addEventListener('pointermove', move)
    bar.addEventListener('pointerup', up)
    e.preventDefault()
  }
  const onKey = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 80 : 20
    if (e.key === 'ArrowLeft') commit(clamp(width - step))
    else if (e.key === 'ArrowRight') commit(clamp(width + step))
    else return
    e.preventDefault()
  }
  return (
    <div
      class="splitter" role="separator" aria-orientation="vertical" aria-label="Resize the list"
      aria-valuenow={width} tabIndex={0} onPointerDown={onDown} onKeyDown={onKey}
    />
  )
}

export function Browser({ part, onPick }: { part: string | null; onPick: (p: string | null) => void }) {
  const [index, setIndex] = useState<PartIndex | null>(null)
  const [q, setQ] = useState('')
  const [by, setBy] = useState<Sort>('documents')
  const [dir, setDir] = useState<Dir>(NATURAL.documents)
  const [device, setDevice] = useState('')
  const [shown, setShown] = useState(PAGE)
  const [width, setWidth] = useState(savedWidth)
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => { loadIndex().then(setIndex) }, [])

  const searching = q.trim().length >= 2
  const list = useMemo(() => {
    if (!index) return []
    const kept = ofDevice(index.parts, device, index.deviceKinds)
    return searching ? search(kept, q, by, dir) : order(kept, by, dir)
  }, [index, q, by, dir, device, searching])
  useEffect(() => setShown(PAGE), [q, by, dir, device])

  /** A column's header: the first click orders by it, the next turns the order round. */
  const sortBy = (key: Sort) => {
    if (key === by) setDir(dir === 'asc' ? 'desc' : 'asc')
    else { setBy(key); setDir(NATURAL[key]) }
  }

  return (
    <div
      ref={host}
      class={`browser${part ? ' has-part' : ''}`}
      style={{ '--side': `${width}px` } as Record<string, string>}
    >
      <aside class="side">
        <input
          type="search"
          value={q}
          placeholder="Part number — 12AX7, BC108, TL072…"
          aria-label="Search by part number"
          onInput={(e) => setQ((e.target as HTMLInputElement).value)}
        />
        <select
          aria-label="Kind of device"
          value={device}
          onChange={(e) => setDevice((e.target as HTMLSelectElement).value)}
        >
          <option value="">Every kind of device</option>
          {(index?.deviceKinds ?? []).map((d) => (
            d.n > 0 ? <option key={d.key} value={d.key}>{d.label} ({n(d.n)})</option> : null
          ))}
        </select>
        <p class="count">
          {!index ? 'loading…'
            : searching ? `${n(list.length)} match ${q} · closest first`
              : `${n(list.length)} parts · click a heading to sort`}
        </p>
        <div class="plist">
          <table>
            <thead>
              <tr>
                {COLUMNS.map((c) => [c.key === 'documents' && <th key="type" class="type">Type</th>,
                  <th
                    key={c.key}
                    class={c.num ? 'num' : undefined}
                    aria-sort={by === c.key ? (dir === 'asc' ? 'ascending' : 'descending') : undefined}
                  >
                    <button type="button" title={c.title} onClick={() => sortBy(c.key)}>
                      {c.label}
                      <span class="arrow" aria-hidden="true">{by === c.key ? (dir === 'asc' ? '▲' : '▼') : ''}</span>
                    </button>
                  </th>])}
              </tr>
            </thead>
            <tbody>
              {list.slice(0, shown).map((r) => (
                <tr
                  key={r[0]}
                  class={r[0] === part ? 'clickable sel' : 'clickable'}
                  onClick={() => onPick(r[0])}
                >
                  <td>
                    <a
                      class="pn"
                      href={`?part=${encodeURIComponent(r[0])}`}
                      aria-current={r[0] === part ? 'true' : undefined}
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onPick(r[0]) }}
                    >
                      {r[0]}
                    </a>
                  </td>
                  {(() => {
                    const t = index ? typeOf(r, index.deviceKinds) : ''
                    return <td class="type" title={t}>{t}</td>
                  })()}
                  <td class="num">{r[1] ? n(r[1]) : '—'}</td>
                  <td class="num">{r[3] ? n(r[3]) : '—'}</td>
                  <td class="num">{r[6] ? n(r[6]) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {list.length > shown && (
            <button class="more" onClick={() => setShown((v) => v + PAGE * 2)}>
              {n(list.length - shown)} more
            </button>
          )}
        </div>
      </aside>

      <Splitter host={host} width={width} setWidth={setWidth} />

      {part ? (
        <Detail
          part={part} sources={index?.sources ?? []} kinds={index?.kinds ?? []} stamp={index?.sourcesStamp}
          onStale={(s) => { reloadIndex(s).then(setIndex) }}
        />
      ) : (
        <section class="evidence stack-s prose">
          <p class="eyebrow">All parts</p>
          <h2>Pick a part from the list</h2>
          <p class="muted">
            Each one shows where it is used in real schematics — with a link that opens the sheet at the
            place the part is, not at the front — which SPICE models exist for it and where each comes
            from, and the data sheets that describe it.
          </p>
        </section>
      )}
      <button class="back" onClick={() => onPick(null)}>← all parts</button>
    </div>
  )
}
