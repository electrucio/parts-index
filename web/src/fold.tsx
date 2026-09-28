import type preact from 'preact'
import { useState } from 'preact/hooks'

/**
 * A `<details>` whose contents are built the first time it is opened.
 *
 * Nothing is cut from a part's page, so the 1N4148's holds 3,574 documents and 9,344 page links.
 * Building all of that as DOM up front costs far more than downloading it. The previous site did the
 * same thing for the same reason.
 */
export function Fold({
  summary, level, open = false, cls, children,
}: {
  summary: preact.ComponentChildren
  /** 1 the kind of source, 2 the source, 3 the document. Each reads differently or the nesting is invisible. */
  level: 1 | 2 | 3
  open?: boolean
  /** An extra class, for a level whose names must not be restyled — a repository keeps its case. */
  cls?: string
  children: () => preact.ComponentChildren
}) {
  const [shown, setShown] = useState(open)
  return (
    <details
      class={`uses lv${level}${cls ? ` ${cls}` : ''}`}
      open={open}
      onToggle={(e) => setShown((e.target as HTMLDetailsElement).open)}
    >
      <summary>{summary}</summary>
      {shown ? children() : null}
    </details>
  )
}
