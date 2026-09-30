import { useRef, useState } from 'preact/hooks'

/**
 * "Report a problem": a dialog whose text reaches the maintainer through a Google Form.
 *
 * A static site has nobody to post to, so the form's own endpoint takes the message and the answers land
 * in the maintainer's sheet. The dialog and its button are this site's; nothing of Google is shown. Google
 * does not allow the page to read its answer (`no-cors`), so a network failure is seen and a refusal is
 * not: "sent" means the request left. The form must stay published and must not ask anyone to sign in,
 * or every report is silently refused.
 */
export const FORM = 'https://docs.google.com/forms/d/e/1FAIpQLSdqgUQ9-yQNItSrEm8BDsEKQox0ZFR9IxfKDaCmzMDSwmsuqg/formResponse'

/** The form's three questions by the id Google gave each: what the reader wrote, and where they were. */
export const FIELD = { message: 'entry.371536136', part: 'entry.1742682148', page: 'entry.712592962' }

export function reportBody(message: string, part: string | undefined, page: string): URLSearchParams {
  return new URLSearchParams({
    [FIELD.message]: message.trim(),
    [FIELD.part]: part ?? '',
    [FIELD.page]: page,
  })
}

type State = 'writing' | 'sending' | 'sent' | 'failed'

/** A flag, the usual sign for "tell someone about this". */
function Flag() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 14.5V2" />
      <path d="M3 2.5h8.5l-2 3 2 3H3" />
    </svg>
  )
}

/**
 * The button and the dialog it opens. `part` names the part the report is about; without it the report
 * is about the site, and the button is a line of text for the footer.
 */
export function Report({ part }: { part?: string }) {
  const [state, setState] = useState<State>('writing')
  const [text, setText] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const box = useRef<HTMLTextAreaElement>(null)
  const downOutside = useRef(false)

  const open = () => {
    if (state === 'sent') setState('writing')
    dialog.current?.showModal()
    box.current?.focus()
  }
  const close = () => dialog.current?.close()

  const send = async (e: Event) => {
    e.preventDefault()
    // A field no person sees: whatever fills it is a bot, and it is told it succeeded.
    const trap = (e.currentTarget as HTMLFormElement).elements.namedItem('website') as HTMLInputElement
    if (trap.value) return setState('sent')
    setState('sending')
    try {
      await fetch(FORM, { method: 'POST', mode: 'no-cors', body: reportBody(text, part, location.href) })
      setText('')
      setState('sent')
    } catch {
      setState('failed')
    }
  }

  return (
    <>
      {part ? (
        <button type="button" class="report-btn" onClick={open} title={`Report a problem with ${part}`}>
          <Flag /> Report
        </button>
      ) : (
        <button type="button" class="linkish" onClick={open}>Report a problem with the site</button>
      )}
      {/* The dialog is its own backdrop's target: a click that lands on it and not on the panel inside
          was outside the panel, so it closes — if it also began there, or selecting text in the box and
          letting go outside would throw the dialog away. */}
      <dialog
        ref={dialog}
        class="report"
        onMouseDown={(e) => { downOutside.current = e.target === dialog.current }}
        onClick={(e) => downOutside.current && e.target === dialog.current && close()}
      >
        <div class="panel-in">
          <h3>Report a problem {part ? <>with <span class="pn">{part}</span></> : 'with the site'}</h3>
          {state === 'sent' ? (
            <>
              <p>Thanks — sent.</p>
              <div class="row"><span /><button type="button" class="send" onClick={close}>Close</button></div>
            </>
          ) : (
            <form onSubmit={send}>
              <textarea
                ref={box}
                aria-label="What is wrong or missing"
                placeholder="What is wrong or missing? A page number or a link helps."
                value={text}
                onInput={(e) => setText(e.currentTarget.value)}
              />
              <input name="website" class="hp" tabIndex={-1} autocomplete="off" aria-hidden="true" />
              <p class="small faint">
                {state === 'failed'
                  ? 'Could not send — check the connection and try again.'
                  : 'Goes to the maintainer through a Google Form, with this page’s address. Add an e-mail if you would like a reply.'}
              </p>
              <div class="row">
                <span />
                <button type="button" class="linkish" onClick={close}>Cancel</button>
                <button class="send" disabled={state === 'sending' || !text.trim()}>
                  {state === 'sending' ? 'Sending…' : 'Send'}
                </button>
              </div>
            </form>
          )}
        </div>
      </dialog>
    </>
  )
}
