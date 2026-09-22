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
import type preact from 'preact'
import { useEffect, useMemo, useState } from 'preact/hooks'

import { forViewer } from './links'
import type { DeviceKind, PartIndex, PartModel, PartPage, PartRow } from './types'

const DATA = `${import.meta.env.BASE_URL}data`
export const n = (v: number) => v.toLocaleString('en-GB')

type Sort = 'documents' | 'models' | 'name'
type Filter = '' | 'models' | 'verified' | 'nomodel'

const SORTS: { key: Sort; label: string }[] = [
  { key: 'documents', label: 'Most used first' },
  { key: 'models', label: 'Most SPICE models first' },
  { key: 'name', label: 'By part number' },
]
const FILTERS: { key: Filter; label: string }[] = [
  { key: '', label: 'all' },
  { key: 'models', label: 'with a model' },
  { key: 'nomodel', label: 'without one' },
]
const PAGE = 300

/** What a query matches, best first: the part itself, then what starts with it, then what contains it. */
export function search(rows: PartRow[], q: string): PartRow[] {
  const needle = q.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
  if (needle.length < 2) return []
  const exact: PartRow[] = []
  const starts: PartRow[] = []
  const has: PartRow[] = []
  for (const r of rows) {
    const key = r[0].toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (key === needle) exact.push(r)
    else if (key.startsWith(needle)) starts.push(r)
    else if (key.includes(needle)) has.push(r)
  }
  const weight = (r: PartRow) => -(r[1] * 2 + r[3] * 50)
  for (const g of [starts, has]) g.sort((a, b) => weight(a) - weight(b) || a[0].localeCompare(b[0]))
  return [...exact, ...starts, ...has]
}

/** All the parts, in the order asked for. Sorting 15,558 rows is cheap; rendering them is not. */
export function order(rows: PartRow[], by: Sort): PartRow[] {
  const cmp: Record<Sort, (a: PartRow, b: PartRow) => number> = {
    documents: (a, b) => b[1] - a[1] || b[3] - a[3] || a[0].localeCompare(b[0]),
    models: (a, b) => b[3] - a[3] || b[1] - a[1] || a[0].localeCompare(b[0]),
    name: (a, b) => a[0].localeCompare(b[0]),
  }
  return [...rows].sort(cmp[by])
}

export function keep(rows: PartRow[], f: Filter): PartRow[] {
  if (f === 'models') return rows.filter((r) => r[3] > 0)
  if (f === 'nomodel') return rows.filter((r) => r[3] === 0)
  return rows
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

/** A model's agreement with its datasheet, as the bar the previous site used. */
function Score({ m }: { m: PartModel }) {
  if (m.score === undefined || !m.rows) return <span class="pill na">not measured</span>
  const [pass, off, fail] = m.rows
  const total = pass + off + fail || 1
  const pct = (v: number) => `${(v / total) * 100}%`
  return (
    <span class="legend">
      <span class="bar" title={`${pass} pass, ${off} marginal, ${fail} fail`}>
        <i class="p" style={{ width: pct(pass) }} />
        <i class="o" style={{ width: pct(off) }} />
        <i class="f" style={{ width: pct(fail) }} />
      </span>
      <span class="count">{Math.round(m.score * 100)}%</span>
    </span>
  )
}

function Models({ page }: { page: PartPage }) {
  const m = page.models
  if (!m) return null
  return (
    <section class="stack-s">
      <h3>Where the model comes from</h3>
      <p class="muted small">
        Every model is linked to its source with a checksum and the lines that hold it. The file itself is
        not hosted here: almost every vendor forbids that, and forbidding redistribution does not forbid
        saying exactly where to look.
      </p>
      <div class="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Source</th><th>Name</th><th>Kind</th>
              <th>Datasheet agreement</th><th>Changed</th><th>Get it</th>
            </tr>
          </thead>
          <tbody>
            {m.models.map((mo, i) => (
              <tr key={i} class={mo.source === m.preferred ? 'sel' : undefined}>
                <td>
                  {mo.source}
                  {mo.source === m.preferred && <> <span class="pill acc">preferred</span></>}
                </td>
                <td><code>{mo.name}</code></td>
                <td>{mo.type || mo.def}</td>
                <td><Score m={mo} /></td>
                <td>
                  {mo.verbatim
                    ? <span class="muted small">verbatim</span>
                    : <span class="chip">{(mo.changes ?? []).join(' ') || 'changed'}</span>}
                </td>
                <td>
                  {mo.get.url ? <a href={mo.get.url}>download</a>
                    : mo.get.installed_with ? <span class="muted small">ships with {mo.get.installed_with}</span>
                      : <span class="muted small">origin not recorded</span>}
                  {mo.get.member && <span class="muted small"> · {mo.get.member}</span>}
                  {mo.symbol && <> · <span class="chip">symbol</span></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.why && <p class="why"><b>{m.preferred}</b> — {m.why}</p>}
      {m.datasheet && (
        <p class="muted small">
          Measured against <a href={m.datasheet.url}>{m.datasheet.doc || 'the datasheet'}</a>
          {m.datasheet.maker && <> · {m.datasheet.maker}</>}
          {m.datasheet.date && <> · {m.datasheet.date}</>}
        </p>
      )}
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

function PageLink({ p, docUrl }: { p: [number, string, string, number]; docUrl: string }) {
  return (
    <li>
      <a href={forViewer(pageHref(docUrl, p[1]))} target="_blank" rel="noopener">page {p[0]}</a>
      {p[2] && <span class="muted small"> beside {p[2]}</span>}
    </li>
  )
}

/**
 * A `<details>` whose contents are built the first time it is opened.
 *
 * Nothing is cut from a part's page, so the 1N4148's holds 3,574 documents and 9,344 page links.
 * Building all of that as DOM up front costs far more than downloading it. The previous site did the
 * same thing for the same reason.
 */
function Fold({
  summary, level, open = false, children,
}: {
  summary: preact.ComponentChildren
  /** 1 the kind of source, 2 the source, 3 the document. Each reads differently or the nesting is invisible. */
  level: 1 | 2 | 3
  open?: boolean
  children: () => preact.ComponentChildren
}) {
  const [shown, setShown] = useState(open)
  return (
    <details
      class={`uses lv${level}`}
      open={open}
      onToggle={(e) => setShown((e.target as HTMLDetailsElement).open)}
    >
      <summary>{summary}</summary>
      {shown ? children() : null}
    </details>
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
        <ul class="uselist cols">
          {d.p.map((p, j) => <PageLink key={j} p={p} docUrl={d.u} />)}
        </ul>
      )}
    </Fold>
  )
}

/** A group of documents, folded by source: a part with three thousand hits has to stay readable. */
function Group({
  title, note, docs, sources, open,
}: {
  title: string; note: string; docs: PartPage['docs']; sources: string[]; open: boolean
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
          {() => ds.map((d, i) => <Document key={i} d={d} />)}
        </Fold>
      ))}
    </Fold>
  )
}

function Repos({ page }: { page: PartPage }) {
  const repos = page.repos
  if (!repos?.length) return null
  const total = page.n.repos ?? repos.length
  const summary = (
    <>
      <strong>Open-source projects</strong>
      <span class="count">{n(total)}</span>
      <span class="small muted">KiCad and Eagle sheets that place this part</span>
    </>
  )
  return (
    <Fold summary={summary} level={1}>
      {() => (
      <ul class="uselist cols">
        {repos.map(([repo, sheets], i) => (
          <li key={i}>
            <a href={`https://github.com/${repo}`} target="_blank" rel="noopener">{repo}</a>
            {sheets > 1 && <span class="muted small"> · {sheets} sheets</span>}
          </li>
        ))}
        {total > repos.length && (
          <li class="muted small">and {n(total - repos.length)} more on GitHub</li>
        )}
      </ul>
      )}
    </Fold>
  )
}

const SITE_KINDS = new Set(['site', 'factory', 'reference'])
const PAPER_KINDS = new Set(['magazine', 'book'])

function Uses({ page, sources, kinds }: { page: PartPage; sources: string[]; kinds: string[] }) {
  const kindOf = (d: PartPage['docs'][0]) => kinds[d.s] ?? ''
  const built = page.docs.filter((d) => SITE_KINDS.has(kindOf(d)))
  const paper = page.docs.filter((d) => PAPER_KINDS.has(kindOf(d)))
  const rest = page.docs.filter((d) => !SITE_KINDS.has(kindOf(d)) && !PAPER_KINDS.has(kindOf(d)))
  if (page.docs.length === 0 && !page.repos?.length) return null
  const { documents, shown, copies } = page.n
  return (
    <section class="stack-s">
      <h3>Where it is used</h3>
      <p class="muted small">
        {n(documents)} document{documents === 1 ? '' : 's'}
        {shown < documents && <> · showing the {n(shown)} most likely to help</>}
        {copies > 0 && <> · {n(copies)} duplicate cop{copies === 1 ? 'y' : 'ies'} folded in</>}
        {' '}· a page link opens the sheet where the part is, not at the front.
      </p>
      <Group
        title="Projects and factory schematics" open
        note="project sites, factory archives and reference works"
        docs={built} sources={sources}
      />
      <Group
        title="Magazines and books" open={built.length === 0}
        note="the exact page of the PDF; pages with a schematic first"
        docs={paper} sources={sources}
      />
      <Group
        title="Other sources" open={false} note=""
        docs={rest} sources={sources}
      />
      <Repos page={page} />
    </section>
  )
}

export function Detail({ part, sources, kinds }: { part: string; sources: string[]; kinds: string[] }) {
  const [page, setPage] = useState<PartPage | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    setPage(null)
    setError(false)
    fetch(`${DATA}/part/${encodeURIComponent(part)}.json`)
      .then((r) => (r.ok ? (r.json() as Promise<PartPage>) : Promise.reject(r.status)))
      .then(setPage)
      .catch(() => setError(true))
  }, [part])

  return (
    <section class="evidence stack">
      <div class="ptitle">
        <h1>{part}</h1>
        {page?.models?.kind && <span class="chip">{page.models.kind}</span>}
      </div>
      {error && <p class="muted">Nothing is published for {part} yet.</p>}
      {!error && !page && <p class="muted">Loading…</p>}
      {page && (
        <>
          <Models page={page} />
          <Uses page={page} sources={sources} kinds={kinds} />
          {page.docs.length === 0 && !page.models && (
            <p class="muted">This part is in the dictionary, but nothing is published for it yet.</p>
          )}
        </>
      )}
    </section>
  )
}

export function Browser({ part, onPick }: { part: string | null; onPick: (p: string | null) => void }) {
  const [index, setIndex] = useState<PartIndex | null>(null)
  const [q, setQ] = useState('')
  const [by, setBy] = useState<Sort>('documents')
  const [filter, setFilter] = useState<Filter>('')
  const [device, setDevice] = useState('')
  const [shown, setShown] = useState(PAGE)

  useEffect(() => {
    fetch(`${DATA}/parts.json`)
      .then((r) => r.json() as Promise<PartIndex>)
      .then(setIndex)
      .catch(() => setIndex({ schema: 0, sources: [], kinds: [], deviceKinds: [], parts: [] }))
  }, [])

  const searching = q.trim().length >= 2
  const list = useMemo(() => {
    if (!index) return []
    const kept = keep(ofDevice(index.parts, device, index.deviceKinds), filter)
    return searching ? search(kept, q) : order(kept, by)
  }, [index, q, by, filter, device, searching])
  useEffect(() => setShown(PAGE), [q, by, filter, device])

  return (
    <div class={`browser${part ? ' has-part' : ''}`}>
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
        <div class="filters">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <select
          aria-label="Order of the list"
          value={by}
          disabled={searching}
          onChange={(e) => setBy((e.target as HTMLSelectElement).value as Sort)}
        >
          {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <p class="count">
          {!index ? 'loading…'
            : searching ? `${n(list.length)} match ${q}`
              : `${n(list.length)} parts · most used first is how many documents show it`}
        </p>
        <div class="plist">
          {list.slice(0, shown).map((r) => (
            <a
              key={r[0]}
              href={`?part=${encodeURIComponent(r[0])}`}
              aria-current={r[0] === part ? 'true' : undefined}
              onClick={(e) => { e.preventDefault(); onPick(r[0]) }}
            >
              <span class={`dot ${r[3] > 0 ? 'v' : 'n'}`} />
              <span class="pn">{r[0]}</span>
              <span class="meta">{r[1] ? n(r[1]) : '—'}{r[3] > 0 ? ` · ${r[3]}m` : ''}</span>
            </a>
          ))}
          {list.length > shown && (
            <button class="more" onClick={() => setShown((v) => v + PAGE * 2)}>
              {n(list.length - shown)} more
            </button>
          )}
        </div>
      </aside>

      {part ? (
        <Detail part={part} sources={index?.sources ?? []} kinds={index?.kinds ?? []} />
      ) : (
        <section class="evidence stack-s prose">
          <p class="eyebrow">All parts</p>
          <h2>Pick a part from the list</h2>
          <p class="muted">
            Each one shows where it is used in real schematics — with a link that opens the sheet at the
            place the part is, not at the front — and which SPICE models exist for it, where each comes
            from and how far each agrees with the datasheet.
          </p>
          <p class="legend">
            <span><span class="dot v" /> has a model</span>
            <span><span class="dot n" /> indexed, no model yet</span>
          </p>
        </section>
      )}
      <button class="back" onClick={() => onPick(null)}>← all parts</button>
    </div>
  )
}
