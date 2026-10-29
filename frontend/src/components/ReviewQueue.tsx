import { useEffect, useRef, useState } from "react"
import type { ApiResult, Caller, Media } from "../api/types"
import { isAdmin } from "../domain/caller"
import { reviewView, reviewViewBroken, type ReviewInput } from "../domain/reviewView"
import { logStep } from "../lib/log"

type ReviewAction = { id: string; status: string }

export type ReviewClient = {
  getReview: (caller: Caller) => Promise<ApiResult<Media[]>>
  approve: (caller: Caller, id: string) => Promise<ApiResult<ReviewAction>>
  reject: (caller: Caller, id: string) => Promise<ApiResult<ReviewAction>>
}

type ReviewQueueProps = {
  client: ReviewClient
  caller: Caller
  refreshKey?: number
}

export function ReviewQueue({ client, caller, refreshKey = 0 }: ReviewQueueProps) {
  const [input, setInput] = useState<ReviewInput>({ kind: "loading" })
  const [actionFailures, setActionFailures] = useState<Record<string, number>>({})
  const [showBroken] = useState(() => new URLSearchParams(window.location.search).get("reviewBug") === "1")
  const toView = showBroken ? reviewViewBroken : reviewView
  const request = useRef(0)

  function loadReview() {
    const mine = request.current + 1
    request.current = mine
    setInput({ kind: "loading" })
    logStep("review", { state: "loading" })
    void client.getReview(caller).then((result) => {
      if (request.current !== mine) {
        return
      }
      const next: ReviewInput = result.ok
        ? { kind: "ready", items: result.data }
        : { kind: "error", status: result.status }
      setInput(next)
      logStep("review", { state: toView(next).kind })
    })
  }

  useEffect(() => {
    if (!isAdmin(caller.userId)) {
      request.current += 1
      return
    }
    loadReview()
  }, [caller, client, refreshKey])

  async function onAction(id: string, action: "approve" | "reject") {
    const result = action === "approve" ? await client.approve(caller, id) : await client.reject(caller, id)
    if (!result.ok || result.status !== 200) {
      setActionFailures((current) => ({ ...current, [id]: result.status }))
      return
    }
    const mine = request.current + 1
    request.current = mine
    const again = await client.getReview(caller)
    if (request.current !== mine) {
      return
    }
    const next: ReviewInput = again.ok
      ? { kind: "ready", items: again.data }
      : { kind: "error", status: again.status }
    setInput(next)
    logStep("review", { state: toView(next).kind })
    setActionFailures((current) => {
      const rest = { ...current }
      delete rest[id]
      return rest
    })
  }

  if (!isAdmin(caller.userId)) {
    return (
      <section>
        <h2>Review</h2>
        <p>Review is for workspace admins</p>
      </section>
    )
  }

  const view = toView(input)
  return (
    <section>
      <h2>Review</h2>
      {view.kind === "loading" ? <p>{view.text}</p> : null}
      {view.kind === "failed" ? (
        <>
          <p>{view.text}</p>
          <p>{view.status}</p>
          <button type="button" onClick={() => loadReview()}>
            Try again
          </button>
        </>
      ) : null}
      {view.kind === "empty" ? <p>{view.text}</p> : null}
      {view.kind === "list" ? (
        <ul>
          {view.items.map((item) => (
            <li key={item.id}>
              <span>{item.id}</span> <span>{item.status}</span> <span>{item.reasons.join(", ")}</span>
              <button type="button" onClick={() => void onAction(item.id, "approve")}>
                Approve
              </button>
              <button type="button" onClick={() => void onAction(item.id, "reject")}>
                Reject
              </button>
              {actionFailures[item.id] !== undefined ? <p>Action failed {actionFailures[item.id]}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
