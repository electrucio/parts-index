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
  indexed: number
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
  have: { sources: boolean; index: boolean; models: boolean; datasheets: boolean }
  sizes: Record<string, number>
}
