import { render } from 'preact'
import { useEffect, useState } from 'preact/hooks'

import { FamilyPage, MakerPage, SchemePage } from './about'
import { DATA } from './data'
import { Browser } from './parts'
import { Report } from './report'
import './style.css'
import type { Manifest } from './types'

/** A page of the catalogue, when one is open: a family, a naming scheme or an organisation. */
type Topic = { family?: string; scheme?: string; maker?: string }

/**
 * Which part is open, kept in the URL, or which catalogue page a part linked to.
 *
 * A result has to be linkable — half the point of an index is being able to send somebody a part — and
 * the back button has to mean what it says.
 */
function useRoute(): [string | null, Topic, (p?: string | null) => void] {
  const read = () => {
    const q = new URLSearchParams(location.search)
    const topic: Topic = {
      family: q.get('family') ?? undefined, scheme: q.get('scheme') ?? undefined, maker: q.get('maker') ?? undefined,
    }
    return [q.get('part'), topic] as const
  }
  const [[part, topic], set] = useState(read)
  useEffect(() => {
    const onPop = () => set(read())
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])
  const go = (p: string | null = null) => {
    history.pushState({}, '', p ? `?part=${encodeURIComponent(p)}` : location.pathname)
    set([p, {}] as const)
    scrollTo(0, 0)
  }
  return [part, topic, go]
}

function App() {
  const [data, setData] = useState<{ m: Manifest } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [part, topic, go] = useRoute()
  const onTopic = Boolean(topic.family || topic.scheme || topic.maker)

  useEffect(() => {
    fetch(`${DATA}/manifest.json`)
      .then((r) => r.json() as Promise<Manifest>)
      .then((m) => setData({ m }))
      .catch(() => setError('Could not load the data. Run `make web-data` to build it.'))
  }, [])

  return (
    <>
      <header class="top">
        <div class="wrap row">
          <a
            class="brand"
            href="?"
            onClick={(e) => { e.preventDefault(); go() }}
          >
            parts<span>-index</span>
          </a>
          {data && <span class="stamp">built {data.m.built}</span>}
        </div>
      </header>

      <main class="wrap">
        {error && <p class="muted">{error}</p>}
        {!error && !data && <p class="muted">Loading…</p>}
        {data && topic.family && <FamilyPage id={topic.family} />}
        {data && topic.scheme && <SchemePage id={topic.scheme} />}
        {data && topic.maker && <MakerPage id={topic.maker} />}
        {data && !onTopic && <Browser part={part} onPick={go} />}
      </main>

      <footer class="wrap muted small" style={{ paddingBlock: '24px 48px' }}>
        Built from the committed dataset. This project stores links, never documents.{' '}
        <a href="https://github.com/electrucio/parts-index">Source</a>. <Report />
      </footer>
    </>
  )
}

// The page ships a "Loading…" placeholder for the moment before this script runs. Preact renders beside
// what is already there rather than over it, so the placeholder is cleared first or it stays under the footer.
const root = document.getElementById('app')!
root.textContent = ''
render(<App />, root)
