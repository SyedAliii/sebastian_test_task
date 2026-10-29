import { useEffect, useRef, useState } from "react"
import type { ApiResult, Caller, Media } from "../api/types"
import { EXPLICIT_IMAGE, NEEDS_REVIEW, SAFE_IMAGE, VIDEO_LAST_FRAME_EXPLICIT } from "../domain/examples"
import { buildMediaBody, type How } from "../domain/mediaBody"
import { logStep } from "../lib/log"

type PendingCreated = { id: string; status: "pending" }

export type SubmitClient = {
  postMedia: (caller: Caller, body: unknown) => Promise<ApiResult<PendingCreated>>
  getMedia: (caller: Caller, id: string) => Promise<ApiResult<Media>>
}

type SubmitFormProps = {
  client: SubmitClient
  caller: Caller
  onSettled?: () => void
}

type View =
  | { kind: "idle" }
  | { kind: "bad-json" }
  | { kind: "refused"; reasons: string[] }
  | { kind: "submit-failed"; status: number }
  | { kind: "status"; id: string; status: string; reasons: string[] }
  | { kind: "still" }
  | { kind: "status-failed"; status: number }

const EXAMPLES = [
  ["Safe image", SAFE_IMAGE],
  ["Explicit image", EXPLICIT_IMAGE],
  ["Needs review", NEEDS_REVIEW],
  ["Video, last frame explicit", VIDEO_LAST_FRAME_EXPLICIT],
] as const

function readFrames(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text)
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return null
    }
    if (!Array.isArray((parsed as { frames?: unknown }).frames)) {
      return null
    }
    return parsed as Record<string, unknown>
  } catch {
    return null
  }
}

export function SubmitForm({ client, caller, onSettled }: SubmitFormProps) {
  const [how, setHow] = useState<How>("upload")
  const [prompt, setPrompt] = useState("two adults on a beach at sunset")
  const [frames, setFrames] = useState(SAFE_IMAGE)
  const [view, setView] = useState<View>({ kind: "idle" })
  const busy = useRef(false)
  const timer = useRef<number | null>(null)
  const active = useRef(0)

  useEffect(() => {
    return () => {
      active.current += 1
      busy.current = false
      if (timer.current !== null) {
        clearInterval(timer.current)
        timer.current = null
      }
    }
  }, [caller])

  async function onSubmit() {
    if (busy.current) {
      return
    }
    const parsed = readFrames(frames)
    if (parsed === null) {
      setView({ kind: "bad-json" })
      return
    }
    const result = await client.postMedia(caller, buildMediaBody(parsed, how, prompt))
    logStep("submit", { media_id: result.ok ? result.data.id : "-", status: result.status })
    if (!result.ok) {
      if (result.status === 422) {
        setView({ kind: "refused", reasons: result.reasons ?? [] })
      } else {
        setView({ kind: "submit-failed", status: result.status })
      }
      return
    }
    const id = result.data.id
    setView({ kind: "status", id, status: "pending", reasons: [] })
    busy.current = true
    const token = active.current
    let tries = 0
    timer.current = setInterval(() => {
      const attempt = tries + 1
      tries = attempt
      void (async () => {
        const media = await client.getMedia(caller, id)
        if (active.current !== token) {
          return
        }
        if (!media.ok) {
          clearInterval(timer.current ?? undefined)
          timer.current = null
          busy.current = false
          setView({ kind: "status-failed", status: media.status })
          return
        }
        if (media.data.status !== "pending") {
          clearInterval(timer.current ?? undefined)
          timer.current = null
          busy.current = false
          setView({ kind: "status", id, status: media.data.status, reasons: media.data.reasons })
          onSettled?.()
          return
        }
        if (attempt >= 20) {
          clearInterval(timer.current ?? undefined)
          timer.current = null
          busy.current = false
          setView({ kind: "still" })
        }
      })()
    }, 1000)
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void onSubmit()
      }}
    >
      <label htmlFor="how">How</label>
      <select
        id="how"
        value={how}
        onChange={(event) => setHow(event.target.value as How)}
      >
        <option value="upload">upload</option>
        <option value="generation">generation</option>
      </select>
      {how === "generation" ? (
        <>
          <label htmlFor="prompt">Prompt</label>
          <input id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
        </>
      ) : null}
      <div>
        {EXAMPLES.map(([label, value]) => (
          <button key={label} type="button" onClick={() => setFrames(value)}>
            {label}
          </button>
        ))}
      </div>
      <label htmlFor="frames">Frames</label>
      <textarea id="frames" value={frames} onChange={(event) => setFrames(event.target.value)} />
      <button type="submit">Submit</button>
      {view.kind === "bad-json" ? <p>Could not read the JSON</p> : null}
      {view.kind === "refused" ? (
        <p>
          Refused {view.reasons.join(", ")}
        </p>
      ) : null}
      {view.kind === "submit-failed" ? <p>Submit failed {view.status}</p> : null}
      {view.kind === "status" ? (
        <p>
          Accepted {view.id} {view.status}
          {view.reasons.length > 0 ? ` ${view.reasons.join(", ")}` : ""}
        </p>
      ) : null}
      {view.kind === "still" ? <p>Still pending</p> : null}
      {view.kind === "status-failed" ? <p>Status check failed {view.status}</p> : null}
    </form>
  )
}
