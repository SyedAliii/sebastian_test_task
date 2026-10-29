import type { ApiFailure, ApiResult, Caller, Media } from "./types"

type PendingMedia = { id: string; status: "pending" }
type ReviewAction = { id: string; status: string }

function failure(status: number, message = `response status ${status}`, reasons?: string[]): ApiFailure {
  if (reasons === undefined) {
    return { ok: false, status, message }
  }
  return { ok: false, status, message, reasons }
}

export function createClient(baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "") {
  async function call(path: string, caller: Caller, init: RequestInit): Promise<Response | ApiFailure> {
    try {
      return await fetch(`${baseUrl}${path}`, {
        ...init,
        headers: {
          ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
          "X-User-Id": caller.userId,
          "X-Workspace-Id": caller.workspaceId,
        },
      })
    } catch {
      return failure(0, "network error")
    }
  }

  function isFailure(outcome: Response | ApiFailure): outcome is ApiFailure {
    return !(outcome instanceof Response)
  }

  async function postAction(path: string, caller: Caller): Promise<ApiResult<ReviewAction>> {
    const outcome = await call(path, caller, { method: "POST" })
    if (isFailure(outcome)) {
      return outcome
    }
    if (!outcome.ok) {
      return failure(outcome.status)
    }
    const data = (await outcome.json()) as ReviewAction
    return { ok: true, status: outcome.status, data }
  }

  return {
    async postMedia(caller: Caller, body: unknown): Promise<ApiResult<PendingMedia>> {
      const outcome = await call("/media", caller, { method: "POST", body: JSON.stringify(body) })
      if (isFailure(outcome)) {
        return outcome
      }
      if (outcome.status === 202) {
        const data = (await outcome.json()) as PendingMedia
        return { ok: true, status: 202, data }
      }
      if (outcome.status === 422) {
        const payload = (await outcome.json()) as { reasons?: string[] }
        const reasons = Array.isArray(payload.reasons) ? payload.reasons : []
        return failure(422, reasons.join(", "), reasons)
      }
      return failure(outcome.status)
    },

    async getMedia(caller: Caller, id: string): Promise<ApiResult<Media>> {
      const outcome = await call(`/media/${id}`, caller, { method: "GET" })
      if (isFailure(outcome)) {
        return outcome
      }
      if (!outcome.ok) {
        return failure(outcome.status)
      }
      const data = (await outcome.json()) as Media
      return { ok: true, status: outcome.status, data }
    },

    async getReview(caller: Caller): Promise<ApiResult<Media[]>> {
      const outcome = await call("/review", caller, { method: "GET" })
      if (isFailure(outcome)) {
        return outcome
      }
      if (!outcome.ok) {
        return failure(outcome.status)
      }
      const data: unknown = await outcome.json()
      if (!Array.isArray(data)) {
        return failure(outcome.status, "review payload was not a list")
      }
      return { ok: true, status: outcome.status, data: data as Media[] }
    },

    approve(caller: Caller, id: string): Promise<ApiResult<ReviewAction>> {
      return postAction(`/review/${id}/approve`, caller)
    },

    reject(caller: Caller, id: string): Promise<ApiResult<ReviewAction>> {
      return postAction(`/review/${id}/reject`, caller)
    },
  }
}
