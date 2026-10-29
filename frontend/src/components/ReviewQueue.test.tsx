import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, test, vi } from "vitest"
import type { ApiResult, Caller, Media } from "../api/types"
import { ReviewQueue, type ReviewClient } from "./ReviewQueue"

const admin: Caller = { workspaceId: "ws_verified", userId: "admin_v" }
const member: Caller = { workspaceId: "ws_verified", userId: "member_v" }
const otherAdmin: Caller = { workspaceId: "ws_unverified", userId: "admin_u" }

const held = (id: string): Media => ({ id, status: "held", reasons: ["self_harm"] })

function client(overrides: Partial<ReviewClient> = {}): ReviewClient {
  return {
    getReview: vi.fn(async () => ({ ok: true as const, status: 200, data: [] as Media[] })),
    approve: vi.fn(async () => ({ ok: true as const, status: 200, data: { id: "x", status: "published" } })),
    reject: vi.fn(async () => ({ ok: true as const, status: 200, data: { id: "x", status: "blocked" } })),
    ...overrides,
  }
}

test("test_member_does_not_call_review", () => {
  const api = client()
  render(<ReviewQueue client={api} caller={member} />)
  expect(screen.getByText("Review is for workspace admins")).toBeInTheDocument()
  expect(api.getReview).not.toHaveBeenCalled()
})

test("test_list_shows_rows", async () => {
  const getReview = vi.fn(async () => ({ ok: true as const, status: 200, data: [held("held-1"), held("held-2")] }))
  render(<ReviewQueue client={client({ getReview })} caller={admin} />)
  expect(await screen.findByText("held-1")).toBeInTheDocument()
  expect(screen.getByText("held-2")).toBeInTheDocument()
  expect(screen.getAllByRole("button", { name: "Approve" })).toHaveLength(2)
  expect(screen.getAllByRole("button", { name: "Reject" })).toHaveLength(2)
  expect(getReview).toHaveBeenCalledTimes(1)
})

test("test_approve_reloads_once", async () => {
  const getReview = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, status: 200, data: [held("held-1"), held("held-2")] })
    .mockResolvedValueOnce({ ok: true, status: 200, data: [held("held-2")] })
  const approve = vi.fn(async () => ({ ok: true as const, status: 200, data: { id: "held-1", status: "published" } }))
  const user = userEvent.setup()
  render(<ReviewQueue client={client({ getReview, approve })} caller={admin} />)
  expect(await screen.findByText("held-1")).toBeInTheDocument()
  await user.click(screen.getAllByRole("button", { name: "Approve" })[0])
  await waitFor(() => expect(getReview).toHaveBeenCalledTimes(2))
  expect(approve).toHaveBeenCalledTimes(1)
  expect(approve).toHaveBeenCalledWith(admin, "held-1")
})

test("test_stale_reply_is_ignored", async () => {
  let resolveFirst: (value: ApiResult<Media[]>) => void = () => {}
  let resolveSecond: (value: ApiResult<Media[]>) => void = () => {}
  const first = new Promise<ApiResult<Media[]>>((resolve) => {
    resolveFirst = resolve
  })
  const second = new Promise<ApiResult<Media[]>>((resolve) => {
    resolveSecond = resolve
  })
  const getReview = vi.fn().mockImplementationOnce(() => first).mockImplementationOnce(() => second)
  const { rerender } = render(<ReviewQueue client={client({ getReview })} caller={admin} />)
  rerender(<ReviewQueue client={client({ getReview })} caller={otherAdmin} />)
  resolveSecond({ ok: true, status: 200, data: [] })
  expect(await screen.findByText("Nothing to review")).toBeInTheDocument()
  resolveFirst({ ok: true, status: 200, data: [held("from-verified")] })
  await act(async () => {
    await Promise.resolve()
  })
  expect(screen.queryByText("from-verified")).not.toBeInTheDocument()
  expect(screen.getByText("Nothing to review")).toBeInTheDocument()
})

test("test_try_again_loads_once_more", async () => {
  const getReview = vi
    .fn()
    .mockResolvedValueOnce({ ok: false as const, status: 503, message: "response status 503" })
    .mockResolvedValueOnce({ ok: true as const, status: 200, data: [] as Media[] })
  const user = userEvent.setup()
  render(<ReviewQueue client={client({ getReview })} caller={admin} />)
  expect(await screen.findByText("Review queue failed")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "Try again" }))
  expect(await screen.findByText("Nothing to review")).toBeInTheDocument()
  expect(getReview).toHaveBeenCalledTimes(2)
})

test("test_failed_request_shows_failure_not_empty", async () => {
  const getReview = vi.fn(async () => ({ ok: false as const, status: 503, message: "response status 503" }))
  render(<ReviewQueue client={client({ getReview })} caller={admin} />)
  await waitFor(() => expect(screen.queryByText("Loading review queue")).not.toBeInTheDocument())
  expect(screen.getByText("Review queue failed")).toBeInTheDocument()
  expect(screen.getByText("503")).toBeInTheDocument()
  expect(screen.queryByText("Nothing to review")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument()
})
