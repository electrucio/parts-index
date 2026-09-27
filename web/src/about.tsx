/**
 * What a part is, and the pages that explain it: families, naming schemes, organisations.
 *
 * Everything shown here names where it came from. A part's name is read under a standard, and the page
 * links the standard; a family comes from a maker's sheet or from the kind the part is filed as, and the
 * page says which; a date is the oldest dated document in this index that prints the part, and says it
 * is a floor. A piece nothing vouches for is not drawn at all — the absence is the honest answer.
 */
import type preact from 'preact'
import { Fragment } from 'preact'
import { useEffect, useMemo, useState } from 'preact/hooks'

import { follow, loadCatalogue, loadIndex } from './data'
import type { Catalogue, Family, PartIndex, PartPage, PartRow } from './types'

const nf = (v: number) => v.toLocaleString('en-GB')
export const partHref = (p: string) => `?part=${encodeURIComponent(p)}`

/** The families by id. The catalogue sends them as a list to keep their order. */
const byId = new WeakMap<Catalogue, Record<string, Family>>()
function fams(cat: Catalogue): Record<string, Family> {
  let m = byId.get(cat)
  if (!m) {
    m = Object.fromEntries(cat.families.map((f) => [f.id, f]))
    byId.set(cat, m)
  }
  return m
}

export function useCatalogue(): Catalogue | null {
  const [cat, setCat] = useState<Catalogue | null>(null)
  useEffect(() => { loadCatalogue().then(setCat) }, [])
  return cat
}

function useIndex(): PartIndex | null {
  const [idx, setIdx] = useState<PartIndex | null>(null)
  useEffect(() => { loadIndex().then(setIdx) }, [])
  return idx
}

/** A link inside the site: no reload, and a middle click still opens a tab. */
export function A({ href, children }: { href: string; children: preact.ComponentChildren }) {
  return <a href={href} onClick={(e) => follow(e as unknown as MouseEvent, href)}>{children}</a>
}

/** The references behind a statement, as their ids, each linking to the source with its title on hover. */
function Refs({ ids, cat }: { ids?: string[]; cat: Catalogue }) {
  const known = (ids ?? []).flatMap((id) => { const r = cat.refs[id]; return r ? [[id, r] as const] : [] })
  if (!known.length) return null
  return (
    <span class="refs">
      {known.map(([id, r], i) => {
        return (
          <span key={id}>
            {i > 0 && ' '}
            <a href={r.url} target="_blank" rel="noopener" title={`${r.title} — ${r.author}`}>{id}</a>
          </span>
        )
      })}
    </span>
  )
}

/** A source that is not in the reference list: a page read for one fact. */
function Source({ src, cat }: { src?: string; cat: Catalogue }) {
  if (!src) return null
  if (cat.refs[src]) return <Refs ids={[src]} cat={cat} />
  let host = src
  try { host = new URL(src).hostname.replace(/^www\./, '') } catch { /* not a URL */ }
  return <a class="refs" href={src} target="_blank" rel="noopener">{host}</a>
}

function MakerName({ id, cat }: { id: string; cat: Catalogue }) {
  const m = cat.makers[id]
  if (!m) return <>{id}</>
  return (
    <>
      <A href={`?maker=${id}`}>{m.name}</A>
      {m.country && <span class="muted"> ({m.country})</span>}
    </>
  )
}

/** A manufacturer's production status as a colour: still made, winding down, or gone. */
const STATUS_PILL: Record<string, string> = { ACTIVE: 'pass', PREVIEW: 'acc', NRND: 'off', LIFEBUY: 'off', OBSOLETE: 'fail', DISCONTINUED: 'fail' }

/** How a relation reads from the part on the page: from the part in its first column, or towards it. */
const RELATION: Record<string, Record<'out' | 'in' | 'both', string>> = {
  next_generation_of: { out: 'The next generation of', in: 'Its next generation is', both: 'Same generation as' },
  replacement_for: { out: 'Offered by its maker as a replacement for', in: 'Its maker\'s declared replacement is', both: '' },
  same_product_as: { out: 'Sold as one product with', in: 'Sold as one product with', both: 'Sold as one product with' },
  same_datasheet: { out: 'Documented in one datasheet with', in: 'Documented in one datasheet with', both: 'In one datasheet with' },
}

const label = (id: string, cat: Catalogue) => fams(cat)[id]?.label ?? id

/** The families above this one, outermost first. */
function lineage(id: string, cat: Catalogue): string[] {
  const out: string[] = []
  let at: string | undefined = id
  while (at && fams(cat)[at] && !out.includes(at)) {
    out.unshift(at)
    at = fams(cat)[at]?.broader
  }
  return out
}

function NameReading({ page, cat }: { page: PartPage; cat: Catalogue }) {
  const r = page.about?.name
  if (!r) return null
  return (
    <section class="stack-s">
      <h3>What the name says</h3>
      <div class="segs">
        {r.segments.map(([text, field, meaning], i) => (
          <div class="seg" key={i}>
            <code>{text}</code>
            <span class="f">{field}</span>
            <span class="m">{meaning}</span>
          </div>
        ))}
      </div>
      <p class="muted small">
        Read under <A href={`?scheme=${r.scheme}`}>{r.label}</A>. {r.caveats[0]} <Refs ids={r.refs} cat={cat} />
      </p>
    </section>
  )
}

function Facts({ page, cat, sources }: { page: PartPage; cat: Catalogue; sources: string[] }) {
  const a = page.about
  if (!a) return null
  const fam = a.family && fams(cat)[a.family[0]]
  const rows: [string, preact.ComponentChildren][] = []
  if (a.family && fam) {
    const chain = lineage(a.family[0], cat)
    rows.push(['Family', (
      <>
        <A href={`?family=${a.family[0]}`}>{fam.label}</A>
        {chain.length > 1 && (
          <span class="muted small"> · in {chain.slice(0, -1).reverse().map((id, i) => (
            <span key={id}>{i > 0 && ' › '}<A href={`?family=${id}`}>{label(id, cat)}</A></span>
          ))}</span>
        )}
        <div class="small">{fam.definition}</div>
        {a.family[1] === 'documented' && a.documented ? (
          <div class="muted small">
            The maker's sheet: {a.documented.note}. <Refs ids={a.documented.refs} cat={cat} />
            {a.documented.status === 'draft' && <> <span class="pill na">not yet reviewed</span></>}
          </div>
        ) : a.family[1] === 'name' ? (
          <div class="muted small">From the letters of its name, read above.</div>
        ) : (
          <div class="muted small">From the kind of device it is filed as, not from a document about this part.</div>
        )}
      </>
    )])
  }
  if (a.maker) {
    const [id, related] = a.maker
    const sheet = page.models?.datasheet
    rows.push(['Datasheet', (
      <>
        {sheet?.url ? <a href={sheet.url} target="_blank" rel="noopener">{sheet.doc || 'the sheet'}</a> : 'published'}
        {' '}by <MakerName id={id} cat={cat} />
        {sheet?.date && <span class="muted"> · {sheet.date}</span>}
        {related.length > 0 && (
          <div class="muted small">
            Lineage: {related.map((r, i) => <span key={r}>{i > 0 && ', '}<MakerName id={r} cat={cat} /></span>)}
          </div>
        )}
      </>
    )])
  }
  if (a.catalogue?.length) {
    rows.push(["Maker's catalogue", (
      <>
        {a.catalogue.map(([, maker, category, status, title, rev, url, pageUrl, checked, name], i) => (
          <div key={i}>
            <MakerName id={maker} cat={cat} /> files it under <b>{category || 'no category'}</b>
            {status && <> · <span class={`pill ${STATUS_PILL[status] ?? 'na'}`}>{status.toLowerCase()}</span></>}
            {' · '}<a href={pageUrl} target="_blank" rel="noopener">their page</a>
            {name && <div class="small">Their title for it: {name}</div>}
            {(title || url) && (
              <div class="small">
                Data sheet: {url ? <a href={url} target="_blank" rel="noopener">{title || 'on their site'}</a> : title}
                {rev && <span class="muted">, revision {rev}</span>}
              </div>
            )}
            <div class="muted small">Read from the maker's page on {checked}; the maker's own words, not this project's.</div>
          </div>
        ))}
      </>
    )])
  }
  const shown = new Set((a.catalogue ?? []).map((c) => c[1]))
  // An archive's listing is already a link under "Data sheets"; a catalogue already read is a row of its own.
  const listed = (a.listed ?? []).filter(([src]) =>
    cat.listings[src]?.kind !== 'datasheet archive' && !shown.has(cat.listings[src]?.maker ?? ''))
  if (listed.length) {
    rows.push(['Listed by', (
      <>
        {listed.map(([src, url], i) => {
          const l = cat.listings[src]
          return (
            <div key={i}>
              {l?.maker ? <MakerName id={l.maker} cat={cat} /> : (l?.title ?? src)}
              {' · '}<a href={url} target="_blank" rel="noopener">{l?.kind === 'datasheet archive' ? 'data sheet' : 'their page'}</a>
            </div>
          )
        })}
        <div class="muted small">A catalogue that lists a part today; not necessarily who designed it.</div>
      </>
    )])
  }
  if (a.related?.length) {
    rows.push(['Related', (
      <>
        {a.related.map(([rel, other, dir, refs, note, status], i) => (
          <div key={i}>
            {RELATION[rel]?.[dir] ?? rel} <A href={partHref(other)}>{other}</A>
            {' '}<Refs ids={refs} cat={cat} />
            {status === 'draft' && <> <span class="pill na">not yet reviewed</span></>}
            {dir !== 'both' && <div class="muted small">{note}</div>}
          </div>
        ))}
        <div class="muted small">Each relation is what its source says, and only that: none makes two parts interchangeable.</div>
      </>
    )])
  }
  if (a.first) {
    const [year, title, si, url] = a.first
    rows.push(['First printed here', (
      <>
        {year}
        {' · '}{url ? <a href={url} target="_blank" rel="noopener">{title || url}</a> : title}
        {sources[si] && <span class="muted small"> ({sources[si]})</span>}
        <div class="muted small">The oldest dated document in this index that prints it. The part may well be older.</div>
      </>
    )])
  }
  if (a.base || a.variants?.length) {
    rows.push([a.base ? 'Same type as' : 'Variants', (
      <>
        {a.base && <><A href={partHref(a.base)}>{a.base}</A>{a.variants?.length ? ', ' : ''}</>}
        {(a.variants ?? []).map((v, i) => <span key={v}>{i > 0 && ', '}<A href={partHref(v)}>{v}</A></span>)}
        <div class="muted small">
          {a.base ? 'A letter after the type number: a grade, package or revision the maker defines.'
            : 'The same type number with a grade, package or revision letter after it.'}
        </div>
      </>
    )])
  }
  if (!rows.length) return null
  return (
    <section class="stack-s">
      <h3>What it is</h3>
      <dl class="kv">
        {rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
      </dl>
    </section>
  )
}

/** What each source of a data sheet is, in words. */
const VIA: Record<string, string> = {
  models: 'the model curation',
  ti_products: "TI's product page",
  renesas_products: "Renesas' product page",
  ti_datasheets: "TI's data sheet index",
  frank_pocnet: "Frank Philipse's tube archive",
  onsemi_docs: "onsemi's data sheet list, read",
  nxp_docs: "NXP's data sheet list, read",
  that_datasheets: "THAT's data sheet page, read",
  jj_datasheets: "JJ's download page, read",
  linearsystems_datasheets: "Linear Systems' product pages, read",
  diotec_products: "Diotec's product tables",
  toshiba_parametric: "Toshiba's parametric tables",
  infineon_tables: "Infineon's product tables",
  st_wayback: "ST's addresses in the Internet Archive, read",
  adi_wayback: "Analog Devices' addresses in the Internet Archive, read",
  archive_databooks: "a databook the Internet Archive holds",
  archive_databooks_more: "a databook the Internet Archive holds",
  cq_tables: "CQ Publishing's device tables, in the Internet Archive",
  data_tables: "D.A.T.A. device tables, in the Internet Archive",
  wrh_books: "a data book World Radio History holds",
  archive_manuallib: "a single sheet the Internet Archive holds",
  datasheet_live: "a copy held by datasheet.live (not the maker's file)",
}

function fileName(url: string): string {
  try { return decodeURIComponent(new URL(url).pathname.split('/').pop() || url) } catch { return url }
}

/**
 * Every data sheet known for the part, grouped by the company that printed it.
 *
 * All of them, not the best one: the same valve described by General Electric, Tung-Sol and Philips is
 * three chances to catch a misprint, and the later work of measuring a model against its sheet wants
 * exactly that redundancy. Each link says where it was found.
 */
const KIN: Record<string, string> = {
  grade: 'the type this is a selected grade of',
  packing: 'the same part, packed differently',
  package: 'the same part in another package',
  brand: 'the type this is a brand of',
  envelope: 'the same valve, filed by its envelope or revision',
  "maker's name": "a maker's name for this number",
}

/** Sheets that document the part under another name: its type, or a maker's name for the bare number. */
function KinSheets({ page }: { page: PartPage }) {
  const kin = page.about?.kin
  if (!kin?.length) return null
  return (
    <section class="stack-s">
      <h3>Sheets under another name</h3>
      <ul class="uselist">
        {kin.map(([name, why, rows]) => (
          <li key={name}>
            <strong><a href={`?part=${encodeURIComponent(name)}`}>{name}</a></strong>
            <span class="muted small"> · {KIN[why] ?? why}</span>
            <ul class="sheetlist">
              {rows.map(([url, maker, text, title, via, , copy], i) => (
                <li key={i}>
                  <a href={url} target="_blank" rel="noopener">{title || fileName(url)}</a>
                  <span class="muted small"> · {maker || text || 'maker not stated'} · via {VIA[via] ?? via}
                    {copy && <> · <a href={copy} target="_blank" rel="noopener">archived copy</a></>}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Datasheets({ page, cat }: { page: PartPage; cat: Catalogue }) {
  const sheets = page.about?.sheets
  if (!sheets?.length) return null
  const groups = new Map<string, typeof sheets>()
  for (const s of sheets) {
    const key = s[1] || s[2] || 'unknown'
    const g = groups.get(key)
    if (g) g.push(s)
    else groups.set(key, [s])
  }
  const ordered = [...groups.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
  return (
    <section class="stack-s">
      <h3>Data sheets <span class="count">{sheets.length} from {ordered.length} {ordered.length === 1 ? 'maker' : 'makers'}</span></h3>
      <ul class="uselist">
        {ordered.map(([key, rows]) => (
          <li key={key}>
            <strong>{cat.makers[key] ? <MakerName id={key} cat={cat} /> : (rows[0]?.[2] || 'Maker not stated')}</strong>
            <ul class="sheetlist">
              {rows.map(([url, , , title, via, note, copy], i) => (
                <li key={i}>
                  <a href={url} target="_blank" rel="noopener">{title || fileName(url)}</a>
                  <span class="muted small"> · via {VIA[via] ?? via}{note && <> · {note}</>}
                    {copy && <> · <a href={copy} target="_blank" rel="noopener">archived copy</a></>}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <p class="muted small">
        Links only: each sheet stays where its publisher or archive keeps it.{' '}
        <a href={`https://www.alldatasheet.com/view.jsp?Searchword=${encodeURIComponent(page.part)}`} target="_blank" rel="noopener">Search alldatasheet</a>
        {' '}or{' '}
        <a href={`https://www.datasheetarchive.com/?q=${encodeURIComponent(page.part.toLowerCase())}`} target="_blank" rel="noopener">Datasheet Archive</a>
        {' '}for more — searches, not checked links.
      </p>
    </section>
  )
}

/** The top of a part's page: its name read letter by letter, then what it is and who says so. */
export function AboutPart({ page, sources }: { page: PartPage; sources: string[] }) {
  const cat = useCatalogue()
  if (!cat || !page.about) return null
  return (
    <>
      <NameReading page={page} cat={cat} />
      <Facts page={page} cat={cat} sources={sources} />
      <Datasheets page={page} cat={cat} />
      <KinSheets page={page} />
    </>
  )
}

// --- the pages the part page links to -------------------------------------------------------------

function children(id: string, cat: Catalogue): string[] {
  return cat.families.map((f) => f.id).filter((k) => fams(cat)[k]?.broader === id)
}

function below(id: string, cat: Catalogue): Set<string> {
  const out = new Set([id])
  for (const c of children(id, cat)) for (const d of below(c, cat)) out.add(d)
  return out
}

function members(id: string, cat: Catalogue, idx: PartIndex): PartRow[] {
  const ids = below(id, cat)
  const at = new Set((idx.families ?? []).flatMap((f, i) => (ids.has(f) ? [i] : [])))
  return idx.parts.filter((r) => r.length > 5 && at.has(r[5] as number)).sort((a, b) => b[1] - a[1])
}

function PartList({ rows, limit = 120 }: { rows: PartRow[]; limit?: number }) {
  if (!rows.length) return <p class="muted">No part in this index is filed here yet.</p>
  return (
    <>
      <ul class="uselist cols">
        {rows.slice(0, limit).map((r) => (
          <li key={r[0]}>
            <A href={partHref(r[0])}>{r[0]}</A>
            <span class="muted small"> · {nf(r[1])} doc{r[1] === 1 ? '' : 's'}{r[3] ? ` · ${r[3]}m` : ''}</span>
          </li>
        ))}
      </ul>
      {rows.length > limit && <p class="muted small">and {nf(rows.length - limit)} more, most used first.</p>}
    </>
  )
}

function RefList({ ids, cat }: { ids?: string[]; cat: Catalogue }) {
  const known = (ids ?? []).flatMap((id) => { const r = cat.refs[id]; return r ? [[id, r] as const] : [] })
  if (!known.length) return null
  return (
    <section class="stack-s">
      <h3>Sources</h3>
      <ul class="uselist">
        {known.map(([id, r]) => {
          return (
            <li key={id}>
              <span class="chip">{id}</span> <a href={r.url} target="_blank" rel="noopener">{r.title}</a>
              <span class="muted"> — {r.author}</span>
              <div class="muted small">{r.consulted}{r.link !== 'ok' && <> · link: {r.link}</>}</div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Examples({ label, parts, idx, note }: { label: string; parts?: string[]; idx: PartIndex | null; note?: string }) {
  if (!parts?.length) return null
  const have = new Set(idx?.parts.map((r) => r[0]) ?? [])
  return (
    <p>
      <b>{label}</b>{' '}
      {parts.map((p, i) => (
        <span key={p}>{i > 0 && ', '}{have.has(p) ? <A href={partHref(p)}>{p}</A> : p}</span>
      ))}
      {note && <span class="muted small"> — {note}</span>}
    </p>
  )
}

export function FamilyPage({ id }: { id: string }) {
  const cat = useCatalogue()
  const idx = useIndex()
  const list = useMemo(() => (cat && idx ? members(id, cat, idx) : []), [cat, idx, id])
  if (!cat) return <p class="muted">Loading…</p>
  const f: Family | undefined = fams(cat)[id]
  if (!f) return <p class="muted">No family called {id}. <A href="?view=families">All families</A>.</p>
  const chain = lineage(id, cat)
  const kids = children(id, cat)
  return (
    <div class="stack prose-wide">
      <div class="stack-s">
        <p class="eyebrow">
          <A href="?view=families">Families</A>
          {chain.slice(0, -1).map((c) => <span key={c}> › <A href={`?family=${c}`}>{label(c, cat)}</A></span>)}
        </p>
        <h2>{f.label}</h2>
        <p class="lede">{f.definition}</p>
        {f.question && <p class="why">{f.question}</p>}
      </div>
      {f.key_params?.length ? (
        <section class="stack-s">
          <h3>What to compare</h3>
          <p>{f.key_params.map((k) => <span key={k} class="chip">{k}</span>).reduce<preact.ComponentChildren[]>((a, c, i) => (i ? [...a, ' ', c] : [c]), [])}</p>
        </section>
      ) : null}
      <Examples label="Examples:" parts={f.examples} idx={idx} />
      <Examples label="Outside this index:" parts={f.external} idx={null} note="worth knowing, not yet in any document indexed here" />
      {kids.length > 0 && (
        <section class="stack-s">
          <h3>Inside this family</h3>
          <ul class="uselist cols">
            {kids.map((k) => (
              <li key={k}><A href={`?family=${k}`}>{label(k, cat)}</A>
                <div class="muted small">{fams(cat)[k]?.definition}</div></li>
            ))}
          </ul>
        </section>
      )}
      <section class="stack-s">
        <h3>Parts filed here</h3>
        <p class="muted small">
          {idx ? `${nf(list.length)} parts, by the family their maker's sheet gives or, failing that, the kind they are filed as.` : 'Loading…'}
        </p>
        {idx && <PartList rows={list} />}
      </section>
      <RefList ids={f.refs} cat={cat} />
    </div>
  )
}

export function FamiliesPage() {
  const cat = useCatalogue()
  const idx = useIndex()
  const counts = useMemo(() => {
    const c = new Map<string, number>()
    if (!idx?.families) return c
    for (const r of idx.parts) {
      const f = r.length > 5 ? idx.families[r[5] as number] : undefined
      if (f) c.set(f, (c.get(f) ?? 0) + 1)
    }
    return c
  }, [idx])
  if (!cat) return <p class="muted">Loading…</p>
  const total = (id: string) => [...below(id, cat)].reduce((t, k) => t + (counts.get(k) ?? 0), 0)
  const Tree = ({ ids }: { ids: string[] }) => (
    <ul class="tree">
      {ids.map((k) => (
        <li key={k}>
          <A href={`?family=${k}`}>{label(k, cat)}</A>
          <span class="count"> {idx ? nf(total(k)) : ''}</span>
          <span class="muted small"> — {fams(cat)[k]?.definition}</span>
          {children(k, cat).length > 0 && <Tree ids={children(k, cat)} />}
        </li>
      ))}
    </ul>
  )
  const top = cat.families.map((f) => f.id).filter((k) => !fams(cat)[k]?.broader)
  return (
    <div class="stack prose-wide">
      <div class="stack-s">
        <p class="eyebrow">Families</p>
        <h2>What kinds of part there are</h2>
        <p class="lede">
          Each family says what its parts are, what choosing one comes down to, and which datasheet figures
          are worth comparing. The count is the parts of this index filed under it.
        </p>
      </div>
      <Tree ids={top} />
    </div>
  )
}

export function SchemePage({ id }: { id: string }) {
  const cat = useCatalogue()
  if (!cat) return <p class="muted">Loading…</p>
  const s = cat.schemes[id]
  if (!s) return <p class="muted">No naming scheme called {id}.</p>
  const others = Object.keys(cat.schemes).filter((k) => k !== id)
  return (
    <div class="stack prose-wide">
      <div class="stack-s">
        <p class="eyebrow">How part numbers are made</p>
        <h2>{s.label}</h2>
        <p class="lede">{s.summary}</p>
        <p class="muted small">
          For example {s.forms.map((f, i) => <span key={f.example}>{i > 0 && ', '}<A href={partHref(f.example)}>{f.example}</A></span>)}.
        </p>
      </div>
      {s.fields.map(([key, f]) => {
        const table = f.values ?? f.each ?? f.tokens
        return (
          <section class="stack-s" key={key}>
            <h3>{f.label}</h3>
            {f.meaning && <p>{f.meaning}{f.optional && <span class="muted small"> (not always there)</span>}</p>}
            {f.each && <p class="muted small">One letter for each part of the device, in alphabetical order.</p>}
            {table && (
              <div class="tablewrap">
                <table>
                  <tbody>
                    {Object.entries(table).map(([k, v]) => (
                      <tr key={k}><td><code>{k === '' ? '(none)' : k}</code></td><td>{v}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {f.ranges && (
              <div class="tablewrap">
                <table>
                  <tbody>
                    {f.ranges.map(([lo, hi, m]) => (
                      <tr key={lo}><td><code>{lo === hi ? lo : `${lo}–${hi}`}</code></td><td>{m}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )
      })}
      {s.caveats?.length ? (
        <section class="stack-s">
          <h3>What the code does not say</h3>
          <ul>{s.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </section>
      ) : null}
      <RefList ids={s.refs} cat={cat} />
      <p class="muted small">
        Other schemes: {others.map((k, i) => <span key={k}>{i > 0 && ' · '}<A href={`?scheme=${k}`}>{cat.schemes[k]?.label ?? k}</A></span>)}
      </p>
    </div>
  )
}

export function MakerPage({ id }: { id: string }) {
  const cat = useCatalogue()
  if (!cat) return <p class="muted">Loading…</p>
  const m = cat.makers[id]
  if (!m) return <p class="muted">No organisation called {id}.</p>
  const named = new Set((m.events ?? []).map((e) => e[2]))
  const mentioned = Object.entries(cat.makers)
    .filter(([k, o]) => k !== id && !named.has(k) && (o.events ?? []).some((e) => e[2] === id))
  return (
    <div class="stack prose-wide">
      <div class="stack-s">
        <p class="eyebrow">Organisation</p>
        <h2>{m.name}</h2>
        <dl class="kv">
          {m.country && <><dt>Headquarters</dt><dd>{m.country}{m.hq_as_of && <span class="muted small"> · read {m.hq_as_of}</span>}</dd></>}
          {m.founded && <><dt>Founded</dt><dd>{m.founded}</dd></>}
          {m.source && <><dt>Source</dt><dd><Source src={m.source} cat={cat} /></dd></>}
        </dl>
        {!m.country && !m.founded && <p class="muted">Nothing is recorded about it yet beyond its name.</p>}
        <p class="muted small">Where an organisation is headquartered is not where a given part was made.</p>
      </div>
      {m.events?.length ? (
        <section class="stack-s">
          <h3>What happened to it</h3>
          <ul class="uselist">
            {m.events.map(([year, what, other, src], i) => (
              <li key={i}>
                <b>{year ?? 'undated'}</b> {what}{other && <> <MakerName id={other} cat={cat} /></>}
                {' '}<Source src={src} cat={cat} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {mentioned.length > 0 && (
        <p class="muted small">
          Also in the history of {mentioned.map(([k], i) => <span key={k}>{i > 0 && ', '}<MakerName id={k} cat={cat} /></span>)}.
        </p>
      )}
    </div>
  )
}
