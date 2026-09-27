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
  /** How many parts have a page. */
  parts?: number
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

/** One entry of the device filter: what it is called and how many parts answer to it. */
export interface DeviceKind {
  key: string
  label: string
  n: number
}

/** One row of the search index: part, documents, uses, model candidates, devices, family.
 *  Devices is a bit per entry of `PartIndex.deviceKinds`, because a part can answer to several; family
 *  is a position in `PartIndex.families`, or -1 when nothing says which. */
export type PartRow = [string, number, number, number, number] | [string, number, number, number, number, number]

export interface PartIndex {
  schema: number
  /** The source names, once. A document names its source by position in this list. */
  sources: string[]
  /** What each of those sources is — site, factory, magazine, book — by the same position. */
  kinds: string[]
  /** The device filter's menu, in menu order. A part row carries one bit per entry. */
  deviceKinds: DeviceKind[]
  /** Family ids, in the order a part row names one. */
  families?: string[]
  parts: PartRow[]
}

export interface PartModel {
  source: string
  name: string
  def: string
  type?: string
  pins?: string[]
  verbatim?: boolean
  /** Our named fixups, when the text was not used as published. */
  changes?: string[]
  symbol?: string
  get: { url?: string; member?: string; installed_with?: string; file?: string; how?: string }
  /** The same model in other sources, each with its own link. */
  copies?: { source: string; name: string; url?: string; member?: string; installed_with?: string }[]
  score?: number
  /** pass, marginal, fail — the datasheet rows this model was judged against. */
  rows?: [number, number, number]
}

/** What one page's use of the part was read as: a circuit, a technique, a table, an advert, a part
 *  named but not used, or a number that is not a component at all. */
export type UseKind = 'project' | 'technique' | 'reference' | 'advert' | 'mention' | 'none'

export type PageUse = [number, string, string, number] | [number, string, string, number, string, UseKind]

export interface PartPage {
  part: string
  docs: {
    /** Index into `PartIndex.sources`. */
    s: number
    t: string
    u: string
    y: string
    schematic: number
    /** page number, link, nearby designators, times on the page — then, once the page has been
     *  summarised, the line saying what the part does there and the kind of use it is. */
    p: PageUse[]
    more?: number
    also?: string[]
  }[]
  /** Who vouches for this part: a shop that sells it, a databook, an article. */
  listed?: { source: string; category?: string; note?: string }[]
  /** `owner/repo`, sheets that place the part, then stars, forks and watchers. */
  repos?: [string, number, number, number, number][]
  n: { documents: number; shown: number; copies: number; repos?: number }
  models?: {
    kind: string
    preferred: string
    why: string
    models: PartModel[]
    datasheet?: { url: string; maker?: string; doc?: string; date?: string }
  }
  /** What the part is, each piece present only when something says so. */
  about?: About
}

/** A part number read under the standard that assigned it: text, what the piece is, what it says. */
export interface NameReading {
  scheme: string
  label: string
  segments: [string, string, string][]
  caveats: string[]
  refs: string[]
}

export interface About {
  name?: NameReading
  /** The family, and what says so: a maker's sheet, the letters of the name, or the part's kind. */
  family?: [string, 'documented' | 'name' | 'kind']
  documented?: { note: string; refs: string[]; status: 'draft' | 'reviewed' }
  /** Who published the sheet the models were measured against, and the organisations it descends from. */
  maker?: [string, string[]]
  /** What a manufacturer's catalogue says: source, maker id, category, status, data sheet title,
   *  revision, data sheet link, catalogue page, date read, and the product's own title where the page
   *  gives one instead of the data sheet's. */
  catalogue?: [string, string, string, string, string, string, string, string, string, string][]
  /** Every data sheet known: link, maker id, maker as the source writes it, title, where it came from
   *  ("models", a register or census source, an archive), a note (language, how the archive filed it). */
  /** link, maker id, maker as written, title, where it came from, a note, and an archived copy when the
   *  maker's own address refuses scripts. */
  sheets?: [string, string, string, string, string, string, string?][]
  /** Catalogues that list the part today: census source, link. */
  listed?: [string, string][]
  /** The oldest dated document here that prints it: year, title, source position, link. */
  first?: [number, string, number, string]
  /** [relation, other part, "out" read from this part, "in" read from the other, "both" for a shared
   *  sheet; references; what the source says; draft or reviewed] */
  related?: [string, string, 'out' | 'in' | 'both', string[], string, 'draft' | 'reviewed'][]
  /** Sheets of other names that document this one too: the type it is a package, packing, grade or
   *  brand of, or a maker's name for a bare number (7812 -> L7812). [name, why, sheets] */
  kin?: [string, string, [string, string, string, string, string, string, string?][]][]
  /** The type this number is a grade or package of. */
  base?: string
  variants?: string[]
}

export interface Family {
  id: string
  label: string
  broader?: string
  definition: string
  question?: string
  key_params?: string[]
  examples?: string[]
  external?: string[]
  kinds?: string[]
  refs?: string[]
}

/** [year, what happened, the other organisation's id, source] */
export type MakerEvent = [number | null, string, string, string]

export interface Maker {
  name: string
  country?: string
  hq_as_of?: string
  founded?: number
  events?: MakerEvent[]
  source?: string
}

export interface SchemeField {
  label: string
  values?: Record<string, string>
  each?: Record<string, string>
  tokens?: Record<string, string>
  ranges?: [number, number, string][]
  meaning?: string
  first?: Record<string, string>
  optional?: boolean
}

export interface Scheme {
  label: string
  summary: string
  applies_to: string[]
  forms: { example: string; pattern: string }[]
  /** In the order the parts of a number are read. */
  fields: [string, SchemeField][]
  caveats?: string[]
  refs?: string[]
}

export interface Reference {
  title: string
  author: string
  url: string
  consulted: string
  link: string
}

export interface Catalogue {
  /** In the order of the file: broad before narrow, the way the menu reads. */
  families: Family[]
  makers: Record<string, Maker>
  schemes: Record<string, Scheme>
  refs: Record<string, Reference>
  listings: Record<string, { title: string; kind: string; maker: string }>
}
