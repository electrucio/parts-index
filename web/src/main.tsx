import { render } from 'preact'
import { useEffect, useState } from 'preact/hooks'

import { Browser, n } from './parts'
import { Sources } from './sources'
import './style.css'
import type { Manifest, Sources as SourceData } from './types'

const DATA = `${import.meta.env.BASE_URL}data`
type View = 'parts' | 'sources'

/**
 * Which part is open, and which view, kept in the URL.
 *
 * A result has to be linkable — half the point of an index is being able to send somebody a part — and
 * the back button has to mean what it says.
 */
function useRoute(): [View, string | null, (v: View, p?: string | null) => void] {
  const read = () => {
    const q = new URLSearchParams(location.search)
    return [(q.get('view') as View) || 'parts', q.get('part')] as const
  }
  const [[view, part], set] = useState(read)
  useEffect(() => {
    const onPop = () => set(read())
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])
  const go = (v: View, p: string | null = null) => {
    const q = new URLSearchParams()
    if (v !== 'parts') q.set('view', v)
    if (p) q.set('part', p)
    const s = q.toString()
    history.pushState({}, '', s ? `?${s}` : location.pathname)
    set([v, p] as const)
    scrollTo(0, 0)
  }
  return [view, part, go]
}

function Totals({ m }: { m: Manifest }) {
  const t = m.totals
  return (
    <div class="grid2">
      {[
        [n(m.parts ?? 0), 'parts indexed'],
        [n(t.items), 'documents found'],
        [n(t.sources), 'schematic sources'],
        [n(t.definitions), 'SPICE definitions'],
        [n(t.modelSources), 'model sources'],
        [n(t.ocr), 'documents read by OCR'],
      ].map(([v, label]) => (
        <div class="panel" key={label}>
          <div class="pn" style={{ font: '700 2rem var(--display)' }}>{v}</div>
          <div class="muted small">{label}</div>
        </div>
      ))}
    </div>
  )
}

function App() {
  const [data, setData] = useState<{ m: Manifest; s: SourceData } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, part, go] = useRoute()

  useEffect(() => {
    Promise.all([
      fetch(`${DATA}/manifest.json`).then((r) => r.json() as Promise<Manifest>),
      fetch(`${DATA}/sources.json`).then((r) => r.json() as Promise<SourceData>),
    ])
      .then(([m, s]) => setData({ m, s }))
      .catch(() => setError('Could not load the data. Run `make web-data` to build it.'))
  }, [])

  return (
    <>
      <header class="top">
        <div class="wrap row">
          <a
            class="brand"
            href="?"
            onClick={(e) => { e.preventDefault(); go('parts') }}
          >
            parts<span>-index</span>
          </a>
          <nav class="main">
            {([['parts', 'Parts'], ['sources', 'Sources']] as [View, string][]).map(([v, label]) => (
              <a
                key={v}
                href={v === 'parts' ? '?' : `?view=${v}`}
                aria-current={view === v ? 'page' : undefined}
                onClick={(e) => { e.preventDefault(); go(v) }}
              >
                {label}
              </a>
            ))}
          </nav>
          {data && <span class="stamp">built {data.m.built}</span>}
        </div>
      </header>

      <main class="wrap">
        {error && <p class="muted">{error}</p>}
        {!error && !data && <p class="muted">Loading…</p>}
        {data && view === 'parts' && <Browser part={part} onPick={(p) => go('parts', p)} />}
        {data && view === 'sources' && (
          <div class="stack">
            <div class="stack-s prose">
              <p class="eyebrow">Coverage</p>
              <h2>Where all of this comes from</h2>
              <p class="lede">
                Every source is crawled, read and indexed once, and what has been done is recorded per
                item so nothing is processed twice. This is that record.
              </p>
            </div>
            <Totals m={data.m} />
            <Sources data={data.s} />
          </div>
        )}
      </main>

      <footer class="wrap muted small" style={{ paddingBlock: '24px 48px' }}>
        Built from the committed dataset. This project stores links, never documents.{' '}
        <a href="https://github.com/electrucio/parts-index">Source</a>.
      </footer>
    </>
  )
}

render(<App />, document.getElementById('app')!)
