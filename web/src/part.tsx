/**
 * Search by part number, and the page for one part.
 *
 * `parts.json` is 61 KB gzipped and holds every part with just enough to rank it, so typing is answered
 * without a request. A part's own page is one request for a file the build already joined, grouped and
 * sorted — the median is 629 bytes.
 *
 * Nothing here is a document: every result is a link to where the document lives.
 */
import { useEffect, useMemo, useState } from 'preact/hooks'

import { forViewer } from './links'
import type { PartIndex, PartPage, PartRow } from './types'

const DATA = `${import.meta.env.BASE_URL}data`
const n = (v: number) => v.toLocaleString('en-GB')
const MAX_RESULTS = 40

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
  // Within each group, the part with more behind it first: documents, then models.
  const weight = (r: PartRow) => -(r[1] * 2 + r[3] * 50)
  for (const g of [starts, has]) g.sort((a, b) => weight(a) - weight(b) || a[0].localeCompare(b[0]))
  return [...exact, ...starts, ...has].slice(0, MAX_RESULTS)
}

function Result({ row, onPick }: { row: PartRow; onPick: (p: string) => void }) {
  const [part, docs, , models] = row
  return (
    <li>
      <button class="result" onClick={() => onPick(part)}>
        <b>{part}</b>
        <span class="counts">
          {docs > 0 && <span>{n(docs)} document{docs === 1 ? '' : 's'}</span>}
          {models > 0 && <span>{models} model{models === 1 ? '' : 's'}</span>}
          {docs === 0 && models === 0 && <span>listed</span>}
        </span>
      </button>
    </li>
  )
}

function Models({ page }: { page: PartPage }) {
  const m = page.models
  if (!m) return null
  return (
    <section>
      <h3>SPICE models</h3>
      <p class="note">
        Every model is linked to its source with a checksum and the lines that hold it. The file itself
        is not hosted here unless its licence allows it.
      </p>
      <table>
        <thead>
          <tr><th>Source</th><th>Name</th><th>Type</th><th class="num">Datasheet agreement</th><th>Get it</th></tr>
        </thead>
        <tbody>
          {m.models.map((mo, i) => (
            <tr key={i} class={mo.source === m.preferred ? 'preferred' : undefined}>
              <td>{mo.source}{mo.source === m.preferred && <span class="tag">preferred</span>}</td>
              <td><code>{mo.name}</code></td>
              <td>{mo.type || mo.def}</td>
              <td class="num">
                {mo.score === undefined ? <span class="note">not measured</span>
                  : <>{Math.round(mo.score * 100)}%{mo.rows && <span class="note"> {mo.rows[0]}/{mo.rows[0] + mo.rows[1] + mo.rows[2]} rows</span>}</>}
              </td>
              <td>
                {mo.get.url ? <a href={mo.get.url}>download</a>
                  : mo.get.installed_with ? <span class="note">ships with {mo.get.installed_with}</span>
                    : <span class="note">origin not recorded</span>}
                {mo.get.member && <span class="note"> · {mo.get.member}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {m.why && <p class="note"><b>{m.preferred}</b> preferred: {m.why}</p>}
      {m.datasheet && (
        <p class="note">Measured against <a href={m.datasheet.url}>{m.datasheet.doc || 'the datasheet'}</a>.</p>
      )}
    </section>
  )
}

function Uses({ page, sources }: { page: PartPage; sources: string[] }) {
  if (page.docs.length === 0) return null
  const { documents, shown, copies } = page.n
  return (
    <section>
      <h3>Where it is used</h3>
      <p class="note">
        {n(documents)} document{documents === 1 ? '' : 's'}
        {shown < documents && <> · showing the {n(shown)} most likely to help</>}
        {copies > 0 && <> · {n(copies)} duplicate cop{copies === 1 ? 'y' : 'ies'} folded in</>}
      </p>
      <ul class="uses">
        {page.docs.map((d, i) => (
          <li key={i}>
            <a href={d.u}>{d.t || d.u}</a>
            <span class="note"> {sources[d.s]}{d.y ? ` · ${d.y}` : ''}{d.schematic ? ' · schematic' : ''}</span>
            {d.also && <span class="note"> · also at {d.also.join(', ')}</span>}
            <span class="pages">
              {d.p.map((p, j) => (
                <a key={j} href={forViewer(p[1])} title={p[2] ? `beside ${p[2]}` : undefined}>
                  p.{p[0]}{p[2] && <span class="near"> {p[2]}</span>}
                </a>
              ))}
              {d.more ? <span class="note">+{d.more} more</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Part({ part, onBack }: { part: string; onBack: () => void }) {
  const [page, setPage] = useState<PartPage | null>(null)
  const [sources, setSources] = useState<string[]>([])
  const [error, setError] = useState(false)

  useEffect(() => {
    setPage(null)
    setError(false)
    Promise.all([
      fetch(`${DATA}/part/${encodeURIComponent(part)}.json`).then((r) => r.json() as Promise<PartPage>),
      fetch(`${DATA}/parts.json`).then((r) => r.json() as Promise<PartIndex>),
    ])
      .then(([p, i]) => { setPage(p); setSources(i.sources) })
      .catch(() => setError(true))
  }, [part])

  return (
    <section class="part">
      <p><button class="back" onClick={onBack}>← search</button></p>
      <h2>{part}</h2>
      {error && <p class="pending">Nothing published for {part} yet.</p>}
      {!error && !page && <p class="note">Loading…</p>}
      {page && (
        <>
          <Models page={page} />
          <Uses page={page} sources={sources} />
          {page.docs.length === 0 && !page.models && (
            <p class="note">This part is in the dictionary, but nothing is published for it yet.</p>
          )}
        </>
      )}
    </section>
  )
}

type Sort = 'documents' | 'models' | 'name'

const SORTS: { key: Sort; label: string }[] = [
  { key: 'documents', label: 'Most used first' },
  { key: 'models', label: 'Most SPICE models first' },
  { key: 'name', label: 'By part number' },
]

/** All the parts, in the order asked for. Sorting 15,558 rows is cheap; rendering them is not. */
export function order(rows: PartRow[], by: Sort): PartRow[] {
  const cmp: Record<Sort, (a: PartRow, b: PartRow) => number> = {
    documents: (a, b) => b[1] - a[1] || b[3] - a[3] || a[0].localeCompare(b[0]),
    models: (a, b) => b[3] - a[3] || b[1] - a[1] || a[0].localeCompare(b[0]),
    name: (a, b) => a[0].localeCompare(b[0]),
  }
  return [...rows].sort(cmp[by])
}

const PAGE = 100

/**
 * The landing view: every part, most used first.
 *
 * A search box that answers nothing until you type is a worse front page than the list itself — the
 * question "what is in here" is asked more often than any single part number. Typing filters the same
 * list, so search is a narrowing of what is already on screen rather than a different mode.
 */
export function Browse({ onPick }: { onPick: (p: string) => void }) {
  const [rows, setRows] = useState<PartRow[] | null>(null)
  const [q, setQ] = useState('')
  const [by, setBy] = useState<Sort>('documents')
  const [shown, setShown] = useState(PAGE)

  useEffect(() => {
    fetch(`${DATA}/parts.json`)
      .then((r) => r.json() as Promise<PartIndex>)
      .then((i) => setRows(i.parts))
      .catch(() => setRows([]))
  }, [])

  const searching = q.trim().length >= 2
  const list = useMemo(() => {
    if (!rows) return []
    return searching ? search(rows, q) : order(rows, by)
  }, [rows, q, by, searching])
  useEffect(() => setShown(PAGE), [q, by])

  return (
    <section class="browse">
      <div class="controls">
        <input
          type="search"
          value={q}
          placeholder="Part number — 12AX7, BC108, TL072…"
          aria-label="Search by part number"
          onInput={(e) => setQ((e.target as HTMLInputElement).value)}
        />
        <select
          aria-label="Order of the list"
          value={by}
          disabled={searching}
          onChange={(e) => setBy((e.target as HTMLSelectElement).value as Sort)}
        >
          {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </div>

      {!rows && <p class="note">Loading…</p>}
      {rows && (
        <p class="note">
          {searching
            ? `${n(list.length)} of ${n(rows.length)} parts match ${q}`
            : `${n(rows.length)} parts. Most used first: how many documents show the part.`}
        </p>
      )}

      <ul class="results">
        {list.slice(0, shown).map((r) => <Result key={r[0]} row={r} onPick={onPick} />)}
      </ul>

      {list.length > shown && (
        <button class="more" onClick={() => setShown((v) => v + PAGE * 2)}>
          Show {n(Math.min(PAGE * 2, list.length - shown))} more of {n(list.length - shown)}
        </button>
      )}
    </section>
  )
}
