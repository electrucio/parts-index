// The shape of what `pidx web build` writes into public/data. Kept by hand for now; once the
// exporters land these are generated from the Python models so the two can never drift.

export interface SchematicSource {
  source: string
  kind: 'site' | 'factory' | 'magazine' | 'book' | 'reference' | 'forum'
  status: 'active' | 'proposed' | 'paused' | 'blocked' | 'excluded'
  items: number
  download: number
  ocr: number
  index: number
  linkcheck: number
  skipped: number
  last: string
  next: string
}

export interface ModelSource {
  source: string
  status: string
  fetch: string
  files: number
  scanned: number
  with_defs: number
  defs: number
  unavailable: number
  not_tried: number
  licence: string
  last: string
  next: string
}

export interface Sources {
  schematics: SchematicSource[]
  models: ModelSource[]
}

export interface Manifest {
  schema: number
  built: string
  totals: {
    sources: number
    items: number
    indexed: number
    ocr: number
    modelSources: number
    modelFiles: number
    definitions: number
  }
  /** Which exports exist yet. The site renders what is present and says what is not. */
  have: { sources: boolean; index: boolean; parts: boolean; models: boolean; datasheets: boolean }
  sizes: Record<string, number>
}

/** One row of the search index: part, documents, uses, model candidates. */
export type PartRow = [string, number, number, number]

export interface PartIndex {
  schema: number
  /** The source names, once. A document names its source by position in this list. */
  sources: string[]
  parts: PartRow[]
}

export interface PartModel {
  source: string
  name: string
  def: string
  type?: string
  pins?: string[]
  verbatim?: boolean
  symbol?: string
  get: { url?: string; member?: string; installed_with?: string; file?: string; how?: string }
  score?: number
  /** pass, marginal, fail — the datasheet rows this model was judged against. */
  rows?: [number, number, number]
}

export interface PartPage {
  part: string
  docs: {
    /** Index into `PartIndex.sources`. */
    s: number
    t: string
    u: string
    y: string
    schematic: number
    /** page number, link, nearby designators, times on the page */
    p: [number, string, string, number][]
    more?: number
    also?: string[]
  }[]
  n: { documents: number; shown: number; copies: number }
  models?: {
    kind: string
    preferred: string
    why: string
    models: PartModel[]
    datasheet?: { url: string; maker?: string; doc?: string; date?: string }
  }
}
