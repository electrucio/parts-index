/**
 * What has been processed, per source.
 *
 * The coverage record: one row per site, magazine, book or vendor, with how far each item got. It is
 * read straight from the committed ledgers, so it is the same answer `make status` gives at a terminal.
 */
import { useState } from 'preact/hooks'

import { n } from './parts'
import type { SchematicSource, Sources as SourceData } from './types'

const KIND: Record<string, string> = {
  site: 'project site',
  factory: 'factory schematics',
  magazine: 'magazine',
  book: 'book',
  reference: 'reference',
  forum: 'forum',
}

/** How far a source's items got, ignoring the ones deliberately skipped. */
function share(row: SchematicSource, stage: 'download' | 'ocr' | 'index'): number {
  const total = row.items - row.skipped
  return total > 0 ? row[stage] / total : 0
}

function Bar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <span class="prog" title={`${pct}%`} aria-label={`${pct}%`}>
      <i style={{ width: `${pct}%` }} />
    </span>
  )
}

function Schematics({ rows }: { rows: SchematicSource[] }) {
  const [all, setAll] = useState(false)
  const active = rows.filter((r) => r.status === 'active')
  const rest = rows.filter((r) => r.status !== 'active')
  const shown = all ? [...active, ...rest] : active
  return (
    <section class="stack-s">
      <h3>Schematics and references</h3>
      <p class="muted small">
        A source with status <em>proposed</em> is one somebody suggested and nobody has run yet.
      </p>
      <div class="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Source</th><th>Kind</th><th class="num">Documents</th>
              <th>Read</th><th>Indexed</th><th>Next</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.source}>
                <td>
                  {r.source}
                  {r.status !== 'active' && <> <span class="pill na">{r.status}</span></>}
                </td>
                <td class="muted">{KIND[r.kind] ?? r.kind}</td>
                <td class="num">{n(r.items)}</td>
                <td><Bar value={share(r, 'ocr')} /></td>
                <td><Bar value={share(r, 'index')} /></td>
                <td class="muted small">{r.next}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!all && rest.length > 0 && (
        <p><button class="more" onClick={() => setAll(true)}>
          Show {rest.length} proposed, blocked and excluded sources
        </button></p>
      )}
    </section>
  )
}

function Models({ rows }: { rows: SourceData['models'] }) {
  const withFiles = rows.filter((r) => r.files > 0).sort((a, b) => b.defs - a.defs)
  const linkOnly = rows.length - withFiles.length
  return (
    <section class="stack-s">
      <h3>SPICE models</h3>
      <p class="muted small">
        Forbidding redistribution does not forbid indexing: every model is linked to its source with a
        checksum and a recipe for getting it. A file is hosted here only where the licence allows it.
      </p>
      <div class="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Source</th><th class="num">Files</th><th class="num">With models</th>
              <th class="num">Definitions</th><th>Licence</th><th>Next</th>
            </tr>
          </thead>
          <tbody>
            {withFiles.slice(0, 30).map((r) => (
              <tr key={r.source}>
                <td>{r.source}</td>
                <td class="num">{n(r.files)}</td>
                <td class="num">{n(r.with_defs)}</td>
                <td class="num">{n(r.defs)}</td>
                <td class="muted small">{r.licence}</td>
                <td class="muted small">{r.next}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p class="muted small">and {n(linkOnly)} more that we link to without holding a file.</p>
    </section>
  )
}

export function Sources({ data }: { data: SourceData }) {
  return (
    <>
      <Schematics rows={data.schematics} />
      <Models rows={data.models} />
    </>
  )
}
