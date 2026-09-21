import { render } from 'preact'
import { useEffect, useState } from 'preact/hooks'
import { Part, Search } from './part'
import type { Manifest, SchematicSource, Sources } from './types'
import './style.css'

const DATA = `${import.meta.env.BASE_URL}data`

const KIND_LABEL: Record<string, string> = {
  site: 'project site',
  factory: 'factory schematics',
  magazine: 'magazine',
  book: 'book',
  reference: 'reference',
  forum: 'forum',
}

const n = (v: number) => v.toLocaleString('en-GB')

/** Share of a source's items that reached a given stage, ignoring the ones deliberately skipped. */
function share(row: SchematicSource, stage: 'download' | 'ocr' | 'index'): number {
  const total = row.items - row.skipped
  return total > 0 ? row[stage] / total : 0
}

function Bar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <span class="bar" title={`${pct}%`} aria-label={`${pct}%`}>
      <span class="bar-fill" style={{ width: `${pct}%` }} />
    </span>
  )
}

function Totals({ m }: { m: Manifest }) {
  const t = m.totals
  return (
    <ul class="totals">
      <li><b>{n(t.items)}</b><span>documents found</span></li>
      <li><b>{n(t.indexed)}</b><span>indexed</span></li>
      <li><b>{n(t.sources)}</b><span>schematic sources</span></li>
      <li><b>{n(t.modelFiles)}</b><span>model files</span></li>
      <li><b>{n(t.definitions)}</b><span>SPICE definitions</span></li>
      <li><b>{n(t.modelSources)}</b><span>model sources</span></li>
    </ul>
  )
}

function Schematics({ rows }: { rows: SchematicSource[] }) {
  const [showAll, setShowAll] = useState(false)
  const active = rows.filter((r) => r.status === 'active')
  const rest = rows.filter((r) => r.status !== 'active')
  const shown = showAll ? [...active, ...rest] : active

  return (
    <section>
      <h2>Where the schematics come from</h2>
      <p class="note">
        Every source is crawled, read and indexed once; nothing is processed twice. A source with
        status <em>proposed</em> is one somebody suggested and nobody has run yet.
      </p>
      <table>
        <thead>
          <tr>
            <th>Source</th><th>Kind</th><th class="num">Documents</th>
            <th>Read</th><th>Indexed</th><th>Next</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.source} class={r.status === 'active' ? undefined : 'dim'}>
              <td>
                {r.source}
                {r.status !== 'active' && <span class={`tag tag-${r.status}`}>{r.status}</span>}
              </td>
              <td>{KIND_LABEL[r.kind] ?? r.kind}</td>
              <td class="num">{n(r.items)}</td>
              <td><Bar value={share(r, 'ocr')} /></td>
              <td><Bar value={share(r, 'index')} /></td>
              <td class="next">{r.next}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!showAll && rest.length > 0 && (
        <button onClick={() => setShowAll(true)}>
          Show {rest.length} proposed, blocked and excluded sources
        </button>
      )}
    </section>
  )
}

function Models({ rows }: { rows: Sources['models'] }) {
  const withFiles = rows.filter((r) => r.files > 0).sort((a, b) => b.defs - a.defs)
  const linkOnly = rows.length - withFiles.length
  return (
    <section>
      <h2>Where the SPICE models come from</h2>
      <p class="note">
        Forbidding redistribution does not forbid indexing: every model is linked to its source, with
        a checksum and a recipe for getting it. Files are hosted here only when the licence allows it —
        which is why every source below still reads <em>unreviewed</em>.
      </p>
      <table>
        <thead>
          <tr><th>Source</th><th class="num">Files</th><th class="num">Definitions</th><th>Licence</th><th>Next</th></tr>
        </thead>
        <tbody>
          {withFiles.slice(0, 20).map((r) => (
            <tr key={r.source}>
              <td>{r.source}</td>
              <td class="num">{n(r.files)}</td>
              <td class="num">{n(r.defs)}</td>
              <td>{r.licence}</td>
              <td class="next">{r.next}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p class="note">and {n(linkOnly)} more that we link to without holding a file.</p>
    </section>
  )
}

function Missing({ have }: { have: Manifest['have'] }) {
  const pending = [
    !have.index && 'the part index',
    !have.models && 'the model recipes',
    !have.datasheets && 'the datasheets',
  ].filter(Boolean) as string[]
  if (pending.length === 0) return null
  return (
    <p class="pending">
      Not built yet: {pending.join(', ')}. Everything else below is what has been processed so far.
    </p>
  )
}

/** The part currently open, kept in the URL so a result can be linked to and the back button works. */
function usePart(): [string | null, (p: string | null) => void] {
  const read = () => new URLSearchParams(location.search).get('part')
  const [part, set] = useState<string | null>(read)
  useEffect(() => {
    const onPop = () => set(read())
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])
  const go = (p: string | null) => {
    history.pushState({}, '', p ? `?part=${encodeURIComponent(p)}` : location.pathname)
    set(p)
  }
  return [part, go]
}

function App() {
  const [data, setData] = useState<{ m: Manifest; s: Sources } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [part, goPart] = usePart()

  useEffect(() => {
    Promise.all([
      fetch(`${DATA}/manifest.json`).then((r) => r.json() as Promise<Manifest>),
      fetch(`${DATA}/sources.json`).then((r) => r.json() as Promise<Sources>),
    ])
      .then(([m, s]) => setData({ m, s }))
      .catch(() => setError('Could not load the data. Run `make web` to build it.'))
  }, [])

  if (error) return <main><p class="pending">{error}</p></main>
  if (!data) return <main><p class="note">Loading…</p></main>

  return (
    <main>
      <header>
        <h1>parts-index</h1>
        <p class="lede">
          An open database for analog-audio electronics: for each part number, where it is used in real
          circuits, which SPICE models exist, and how far they can be trusted.
        </p>
      </header>
      {part ? (
        <Part part={part} onBack={() => goPart(null)} />
      ) : (
        <>
          {data.m.have.parts && <Search onPick={goPart} />}
          <Totals m={data.m} />
          <Missing have={data.m.have} />
          <Schematics rows={data.s.schematics} />
          <Models rows={data.s.models} />
        </>
      )}
      <footer>
        <p>
          Built {data.m.built} from the committed dataset. This project stores links, never documents.
          {' '}<a href="https://github.com/electrucio/parts-index">Source</a>.
        </p>
      </footer>
    </main>
  )
}

render(<App />, document.getElementById('app')!)
