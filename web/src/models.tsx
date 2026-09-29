/**
 * Each model against the part's data sheet: the sheet's rows as printed, one column per model, and under
 * them what is known of each model — where it runs, what its card lacks, what its author declares. Folded
 * by default: the part page reads as before until someone asks.
 *
 * Numbers, not judgements. A value is coloured only by the sheet's own limits, and every value can be
 * traced to the netlist that produced it (`data/bench/<PART>.json`, fetched on demand).
 */
import { Fragment } from 'preact'
import { useState } from 'preact/hooks'

import { CLAIM_LABEL, LIMIT_LABEL } from './behaviours'
import { DATA } from './data'
import { Fold } from './fold'
import type { BenchFile, Cell, ChecksBlock, EngineRun, PartModel, PartPage, SheetRow } from './types'

const REPO = 'https://github.com/electrucio/parts-index'
const DIALECT_SHORT: Record<string, string> = {
  'unit-a': 'A unit', 'catalogue-fields': 'mfg=…', 'nk-above-1': 'NK>1', 'jfet-extensions': 'isr, nr…',
  'ltspice-diode': 'Ron, Roff…',
}

/** A number as a data sheet prints it: at most four significant figures, no exponent in range. */
export function fmt(x: number): string {
  if (x === 0) return '0'
  const a = Math.abs(x)
  if (a >= 1e-3 && a < 1e5) return String(Number(x.toPrecision(4)))
  return x.toExponential(2).replace('e+', 'e')
}

export function cellText(c: Cell): string {
  switch (c[0]) {
    case 'in': case 'out': case 'grade': return fmt(c[1])
    case 'typ': return fmt(c[1])
    case 'card': return c[1].length ? `n.m. card: ${c[1].join(', ')}` : 'n.m. card'
    case 'author': return 'n.m. author'
    case 'err': return typeof c[1] === 'number' ? fmt(c[1]) : c[1]
    default: return '—'
  }
}

export function cellTitle(c: Cell, row: SheetRow): string {
  switch (c[0]) {
    case 'in': return `inside the sheet's limits for ${row[2]}`
    case 'out': return `${c[2]} the sheet's limit for ${row[2]}`
    case 'typ': return c[2] == null ? 'the sheet gives no limit' : `×${c[2]} the sheet's typical value (a typical is one device, not a limit)`
    case 'grade': return `the sheet's row for grade ${c[2]}: this model is not of that grade, so it is not judged`
    case 'card': return c[1].length
      ? `the card has no ${c[1].join(' and no ')}: it cannot represent this row`
      : 'its model family has no parameter for this row'
    case 'author': return `its author declares ${c[1].map((x) => CLAIM_LABEL[x] ?? x).join(', ')} not modelled`
    case 'err': return 'the simulation failed, or gave a value no device has'
    default: return 'not measured'
  }
}

function engineText(e: EngineRun): string {
  return typeof e.version === 'string' ? (e.version.split(' : ')[0] ?? e.version) : `${e.version.exe} sha256 ${e.version.sha256.slice(0, 12)}…`
}

function pageLink(url: string, page: number): string {
  return `${url}#page=${page}`
}

export function ModelChecks({ page }: { page: PartPage }) {
  const m = page.models
  const block = m?.check
  if (!m || !block) return null
  const sheet = block.sheet
  const cols = m.models.map((mo, i) => [mo, i] as const).filter(([mo]) => mo.chk)
  const summary = sheet
    ? <>Data sheet vs models <span class="muted small">— {sheet.maker} {sheet.title} · {sheet.rows.length} rows · {cols.length} models</span></>
    : <>Models: what their cards and authors state <span class="muted small">— {cols.length} {cols.length === 1 ? 'model' : 'models'}</span></>
  return (
    <section class="stack-s checks">
      <Fold level={1} summary={summary}>
        {() => <Checks block={block} cols={cols} part={page.part} />}
      </Fold>
    </section>
  )
}

function Checks({ block, cols, part }: { block: ChecksBlock; cols: (readonly [PartModel, number])[]; part: string }) {
  const [open, setOpen] = useState<number | null>(null)
  const [how, setHow] = useState<number | null>(null)
  const sheet = block.sheet
  const primary = block.primary ?? 'qspice'
  const eng = block.engines ?? {}
  return (
    <div class="stack-s">
      <p class="muted small">
        {sheet && <>Rows: <a href={sheet.url}>{sheet.maker} {sheet.title}</a> (sha256 <code>{sheet.sha256.slice(0, 12)}…</code>), {sheet.read_by === 'reference' ? 'read by hand' : `read by ${sheet.read_by}`} on {sheet.read_on}{sheet.checked_by ? `, checked by ${sheet.checked_by}` : ', not yet checked by a person'}. </>}
        {Object.keys(eng).length > 0 && <>Values: {Object.entries(eng).map(([k, e], i) => (
          <Fragment key={k}>{i ? ', ' : ''}{k === primary ? <b>{k}</b> : k} ({engineText(e)})</Fragment>))}
          , 25 °C, bench <a href={`${REPO}/tree/${eng[primary]?.bench.commit}/docker/sim/bench`}><code>{eng[primary]?.bench.commit.slice(0, 7)}</code></a>
          {' '}(<a href={`${REPO}/blob/main/docs/simulation-and-datasheets.md`}>method</a>). </>}
        {sheet && 'Click a row for the page it was read from.'}
      </p>
      <div class="tablewrap">
        <table class="chk">
          <thead>
            <tr>
              {sheet
                ? <><th class="stick">Quantity</th><th class="num">Min</th><th class="num">Typ</th><th class="num">Max</th><th>Unit</th></>
                : <th class="stick" colSpan={5} />}
              {cols.map(([mo, i]) => <th key={i} class="mcol" title={`${mo.source} · ${mo.name}`}><span class="muted">{mo.source}</span><br />{mo.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {sheet?.rows.map((r) => (
              <Fragment key={r[0]}>
                <tr class="clickable" onClick={() => setOpen(open === r[0] ? null : r[0])}>
                  <td class="stick">
                    <b>{r[2]}</b>{r[8] && <span class="muted"> {r[8]}</span>} <span class="muted small">{r[3]}</span>
                    {r[9] && <div class="faint small">{r[9]}</div>}
                  </td>
                  <td class="num">{r[4]}</td><td class="num">{r[5]}</td><td class="num">{r[6]}</td><td>{r[7]}</td>
                  {cols.map(([mo, i]) => {
                    const c = mo.chk?.cells?.[String(r[0])] ?? (['none'] as Cell)
                    return <td key={i} class={`num cc c-${c[0]}`} title={cellTitle(c, r)}>{cellText(c)}</td>
                  })}
                </tr>
                {open === r[0] && (
                  <tr class="crop">
                    <td colSpan={5 + cols.length}>
                      <div class="cropbox">
                        {r[10] && <img src={`${DATA}/crops/${sheet.doc}/r${r[0]}.webp`} alt={`row ${r[2]} as printed`}
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />}
                        <div class="muted small">{sheet.maker} {sheet.title}, page {r[1]} — <a href={pageLink(sheet.url, r[1])}>open the PDF at that page</a></div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            <Facts cols={cols} block={block} how={how} setHow={setHow} />
          </tbody>
        </table>
      </div>
      {sheet && <p class="muted small legend">
        <span class="c-in">inside the sheet's limits</span> · <span class="c-out">outside</span> · <span class="c-typ">typical only</span> ·
        {' '}n.m. card: the card lacks the parameter · n.m. author: declared not modelled by its author · —: not measured.
        Values in the sheet's units; hover a cell for its reading.
      </p>}
      {how !== null && <How part={part} index={how} model={cols.find(([, i]) => i === how)?.[0]} block={block} />}
    </div>
  )
}

function Facts({ cols, block, how, setHow }: {
  cols: (readonly [PartModel, number])[]; block: ChecksBlock; how: number | null; setHow: (i: number | null) => void
}) {
  // A fact no model has is not a row: the table stays as short as what is known.
  const row = (label: string, render: (mo: PartModel, i: number) => preact.ComponentChildren) => {
    const cells = cols.map(([mo, i]) => render(mo, i))
    if (cells.every((c) => c === '' || (Array.isArray(c) && c.length === 0))) return null
    return (
      <tr class="fact">
        <td class="stick" colSpan={5}><span class="muted small">{label}</span></td>
        {cells.map((c, k) => <td key={k} class="small">{c}</td>)}
      </tr>
    )
  }
  const list = (xs: string[] | undefined, labels: Record<string, string>) => (xs ?? []).map((x) => labels[x] ?? x).join(', ')
  return (
    <>
      {row('runs in', (mo) => mo.chk?.runs
        ? Object.entries(mo.chk.runs).map(([e, s]) => `${e} ${s === 'ok' ? '✓' : '✗'}`).join(' ')
          + (mo.chk.differs?.length ? ` · ngspice differs on ${mo.chk.differs.length}` : '')
        : '')}
      {row('not in card', (mo) => (mo.chk?.absent ?? []).join(', ') || (mo.chk?.family && !['gummel-poon', 'jfet', 'diode'].includes(mo.chk.family) ? mo.chk.family : ''))}
      {row('author: modelled', (mo) => list(mo.chk?.claims?.yes, CLAIM_LABEL))}
      {row('author: not modelled', (mo) => list(mo.chk?.claims?.no, CLAIM_LABEL))}
      {row('author: limits', (mo) => list(mo.chk?.claims?.limits, LIMIT_LABEL))}
      {row('written for', (mo) => mo.chk?.claims?.simulator ?? '')}
      {row('dialect', (mo) => (mo.chk?.dialect ?? []).map((d) => (
        <span key={d} class="chip" title={block.dialects[d]}>{DIALECT_SHORT[d] ?? d}</span>)))}
      {row('how measured', (mo, i) => mo.chk?.runs
        ? <a href="#" onClick={(e) => { e.preventDefault(); setHow(how === i ? null : i) }}>{how === i ? 'hide' : 'netlists'}</a>
        : '')}
    </>
  )
}

function How({ part, index, model, block }: { part: string; index: number; model?: PartModel; block: ChecksBlock }) {
  const [file, setFile] = useState<BenchFile | null | undefined>(undefined)
  if (file === undefined) {
    fetch(`${DATA}/bench/${encodeURIComponent(part)}.json`).then((r) => (r.ok ? r.json() : null)).then(setFile, () => setFile(null))
    return <p class="muted small">Loading…</p>
  }
  const mine = file?.models[String(index)]
  if (!file || !mine || !model) return <p class="muted small">No netlists for this model.</p>
  const g = model.get
  return (
    <div class="how stack-s">
      <h4>How {model.source} · {model.name} was measured</h4>
      <ol class="small">
        <li>Get the model: {g.url ? <a href={g.url}>{g.url}</a> : g.installed_with ? `installed with ${g.installed_with}` : 'origin not recorded'}
          {g.member && <> — member <code>{g.member}</code></>}; save its <code>.model</code> as <code>model.lib</code>.</li>
        <li>Change it as the bench did: {Object.values(mine.changes).flat().filter((v, i, a) => a.indexOf(v) === i)
          .map((c) => block.changes[c] ?? c).join('; ')}.</li>
        <li>Run each netlist below beside it, in the image the value came from:
          <ul>{Object.entries(file.engines).map(([e, x]) => (
            <li key={e}><b>{e}</b>: {engineText(x)}, image <code>{x.image.slice(7, 19)}</code>, bench <code>{x.bench.commit.slice(0, 7)}</code>{x.bench.clean ? '' : ' (with uncommitted changes)'}, {x.on}.<br /><code>{x.command}</code></li>))}
          </ul>
          The images are built from pinned inputs: <a href={`${REPO}/tree/main/docker/sim`}>docker/sim</a>.</li>
      </ol>
      {Object.entries(mine.netlists).map(([e, nets]) => (
        <Fold key={e} level={2} summary={<>{e}: {nets.length} netlists</>}>
          {() => nets.map((n, k) => <pre key={k} class="netlist">{n}</pre>)}
        </Fold>
      ))}
    </div>
  )
}
