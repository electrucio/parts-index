/**
 * The sheet's figures, each beside the same graph drawn for a model by the bench: the crop of the page
 * on the left, our plot on the same axes on the right — same quantities, same scales, same series — so
 * a reader compares the two by eye. Nothing is fitted or scored here.
 */
import { useEffect, useState } from 'preact/hooks'

import { DATA } from './data'
import { Fold } from './fold'
import { fmt } from './models'
import type { Axis, ChecksBlock, CurvesFile, PartModel, SheetFigure } from './types'

const W = 340
const H = 250
const M = { l: 46, r: 10, t: 10, b: 40 }
const COLOURS = ['#e0864f', '#8fbde0', '#6fcf97', '#e2b451', '#c792ea', '#f07b83']

/** Where a value lands along an axis of `size` pixels. */
export function place(axis: Axis, value: number, size: number): number {
  const [, , scale, lo, hi] = axis
  const f = scale === 'log' ? (Math.log10(value) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) : (value - lo) / (hi - lo)
  return f * size
}

/** The series whose every point lies outside the sheet's axes, with the range of their values: drawn on
 *  the sheet's scale they would be invisible, and a reader would take them for not simulated. */
export function offScale(fig: SheetFigure, curves?: Record<string, [number, number][]>): [string, number, number][] {
  const [, , , ylo, yhi] = fig.y!
  const [, , , xlo, xhi] = fig.x!
  const out: [string, number, number][] = []
  for (const [name] of fig.series ?? []) {
    const pts = (curves?.[name] ?? []).filter((p) => p[0] >= xlo && p[0] <= xhi && Number.isFinite(p[1]))
    if (pts.length && pts.every((p) => p[1] < ylo || p[1] > yhi)) {
      const ys = pts.map((p) => p[1])
      out.push([name, Math.min(...ys), Math.max(...ys)])
    }
  }
  return out
}

/** Tick values: 1-2-5 per decade on a log axis, round steps on a linear one; `major` ones are labelled. */
export function ticks(axis: Axis): { v: number; major: boolean }[] {
  const [, , scale, lo, hi] = axis
  const out: { v: number; major: boolean }[] = []
  if (scale === 'log') {
    const decades = Math.log10(hi / lo)
    for (let d = Math.floor(Math.log10(lo)); d <= Math.ceil(Math.log10(hi)); d++) {
      for (const m of [1, 2, 5]) {
        const v = m * 10 ** d
        if (v >= lo * 0.999 && v <= hi * 1.001) out.push({ v, major: m === 1 || decades <= 2 })
      }
    }
    return out
  }
  const raw = (hi - lo) / 5
  const p = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((k) => k * p).find((k) => k >= raw) ?? raw
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push({ v: Number(v.toPrecision(10)), major: true })
  return out
}

function label(axis: Axis): string {
  return axis[1] ? `${axis[0]} (${axis[1]})` : axis[0]
}

function Plot({ fig, mine, others }: {
  fig: SheetFigure
  mine?: Record<string, [number, number][]>
  others: Record<string, [number, number][]>[]
}) {
  const x = fig.x!
  const y = fig.y!
  const pw = W - M.l - M.r
  const ph = H - M.t - M.b
  const px = (v: number) => M.l + place(x, v, pw)
  const py = (v: number) => M.t + ph - place(y, v, ph)
  const ok = (p: [number, number]) => (x[2] !== 'log' || p[0] > 0) && (y[2] !== 'log' || p[1] > 0) && Number.isFinite(p[1])
  const path = (pts: [number, number][]) => pts.filter(ok).map((p, k) => `${k ? 'L' : 'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join('')
  const clip = `clip${fig.n}`
  const series = fig.series ?? []
  return (
    <svg class="fig" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Figure ${fig.n} simulated`}>
      <defs><clipPath id={clip}><rect x={M.l} y={M.t} width={pw} height={ph} /></clipPath></defs>
      <rect x={M.l} y={M.t} width={pw} height={ph} class="frame" />
      {ticks(x).map((t) => <line key={`x${t.v}`} x1={px(t.v)} x2={px(t.v)} y1={M.t} y2={M.t + ph} class={t.major ? 'grid major' : 'grid'} />)}
      {ticks(y).map((t) => <line key={`y${t.v}`} y1={py(t.v)} y2={py(t.v)} x1={M.l} x2={M.l + pw} class={t.major ? 'grid major' : 'grid'} />)}
      {ticks(x).filter((t) => t.major).map((t) => <text key={`xl${t.v}`} x={px(t.v)} y={M.t + ph + 12} class="tick" text-anchor="middle">{fmt(t.v)}</text>)}
      {ticks(y).filter((t) => t.major).map((t) => <text key={`yl${t.v}`} x={M.l - 4} y={py(t.v) + 3} class="tick" text-anchor="end">{fmt(t.v)}</text>)}
      <text x={M.l + pw / 2} y={H - 6} class="axis" text-anchor="middle">{label(x)}</text>
      <text x={11} y={M.t + ph / 2} class="axis" text-anchor="middle" transform={`rotate(-90 11 ${M.t + ph / 2})`}>{label(y)}</text>
      <g clip-path={`url(#${clip})`}>
        {others.map((o, k) => Object.values(o).map((pts, j) => <path key={`o${k}.${j}`} d={path(pts)} class="other" />))}
        {mine && series.map(([name, style], k) => mine[name] && (
          <path key={name} d={path(mine[name])} class="mine" stroke={COLOURS[k % COLOURS.length]}
            stroke-dasharray={style === 'dashed' ? '6 4' : undefined} />
        ))}
      </g>
    </svg>
  )
}

export function Figures({ block, cols, part }: { block: ChecksBlock; cols: (readonly [PartModel, number])[]; part: string }) {
  const figs = block.figures ?? []
  const doc = block.sheet?.doc
  if (!figs.length || !doc) return null
  return (
    <Fold level={2} summary={<>The sheet's figures ({figs.length}) <span class="muted small">— each beside the same graph simulated</span></>}>
      {() => <FigureList figs={figs} cols={cols} part={part} doc={doc} />}
    </Fold>
  )
}

function FigureList({ figs, cols, part, doc }: { figs: SheetFigure[]; cols: (readonly [PartModel, number])[]; part: string; doc: string }) {
  const [file, setFile] = useState<CurvesFile | null | undefined>(undefined)
  const [pick, setPick] = useState<number | null>(null)
  const [all, setAll] = useState(false)
  useEffect(() => {
    fetch(`${DATA}/curves/${encodeURIComponent(part)}.json`).then((r) => (r.ok ? r.json() : null)).then(setFile, () => setFile(null))
  }, [part])
  const drawn = cols.filter(([, i]) => file?.models[String(i)])
  const chosen = pick ?? drawn[0]?.[1] ?? null
  const mine = chosen === null ? undefined : file?.models[String(chosen)]
  return (
    <div class="stack-s">
      {drawn.length > 0 && (
        <p class="small">
          Simulated with {file?.engine}, for{' '}
          <select value={String(chosen)} onChange={(e) => setPick(Number((e.target as HTMLSelectElement).value))}>
            {drawn.map(([mo, i]) => <option key={i} value={String(i)}>{mo.source} · {mo.name}</option>)}
          </select>{' '}
          <label><input type="checkbox" checked={all} onChange={(e) => setAll((e.target as HTMLInputElement).checked)} /> the other models too, in grey</label>
        </p>
      )}
      <div class="figgrid">
        {figs.map((f) => {
          const others = all ? drawn.filter(([, i]) => i !== chosen).map(([, i]) => file?.models[String(i)]?.[String(f.n)] ?? {}) : []
          return (
            <div key={f.n} class="figcard">
              <h4>Figure {f.n}. {f.caption}</h4>
              <div class="figpair">
                <div>
                  {f.crop && <img src={`${DATA}/crops/${doc}/f${f.n}.webp`} alt={`Figure ${f.n} as printed`}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />}
                  <div class="muted small">the sheet, page {f.page}</div>
                </div>
                <div>
                  {f.kind === 'circuit'
                    ? <p class="muted small">The test circuit of the rows {(f.rows ?? []).join(', ')}: the bench builds it as drawn, and their values are in the table above.</p>
                    : f.simulated && f.x && f.y
                      ? <>
                          <Plot fig={f} mine={mine?.[String(f.n)]} others={others} />
                          <ul class="figkey small">{(f.series ?? []).map(([name, style], k) => (
                            <li key={name}><span class="swatch" style={{ background: COLOURS[k % COLOURS.length] }} />{name}{style === 'dashed' ? ' (dashed)' : ''}</li>))}
                          </ul>
                          {offScale(f, mine?.[String(f.n)]).map(([name, lo, hi]) => (
                            <div key={name} class="small offscale">{name}: off the sheet's scale, {fmt(lo)} to {fmt(hi)} {f.y![1]}</div>))}
                          {f.normalised && <div class="muted small">normalised {f.normalised}</div>}
                        </>
                      : <p class="muted small">{f.bench?.startsWith('none') ? `Not simulated: ${f.bench.replace(/^none( yet)? — /, '')}.` : 'Not simulated for this part.'}</p>}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
