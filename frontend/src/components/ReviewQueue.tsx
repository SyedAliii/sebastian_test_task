import { useEffect, useRef, useState } from "react"
import type { ApiResult, Caller, Media } from "../api/types"
import { isAdmin } from "../domain/caller"
import { reviewView, type ReviewInput } from "../domain/reviewView"
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
}

export function ReviewQueue({ client, caller }: ReviewQueueProps) {
  const [input, setInput] = useState<ReviewInput>({ kind: "loading" })
  const [actionFailures, setActionFailures] = useState<Record<string, number>>({})
  const request = useRef(0)

  useEffect(() => {
    const mine = request.current + 1
    request.current = mine
    if (!isAdmin(caller.userId)) {
      return
    }
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
      logStep("review", { state: reviewView(next).kind })
    })
  }, [caller, client])

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
    logStep("review", { state: reviewView(next).kind })
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

  const view = reviewView(input)
  return (
    <section>
      <h2>Review</h2>
      {view.kind === "loading" || view.kind === "empty" ? <p>{view.text}</p> : null}
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
