import { afterEach, expect, test, vi } from "vitest"
import { createClient } from "./client"

const caller = { workspaceId: "ws_verified" as const, userId: "member_v" as const }

afterEach(() => {
  vi.unstubAllGlobals()
})

test("test_client_sends_caller_headers", async () => {
  const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
    Response.json({ id: "m1", status: "published", reasons: [] }),
  )
  vi.stubGlobal("fetch", fetchMock)
  const client = createClient("http://api.test")
  await client.getMedia(caller, "m1")
  const [url, init] = fetchMock.mock.calls[0]
  const headers = init.headers as Record<string, string>
  expect(url).toBe("http://api.test/media/m1")
  expect(headers["X-User-Id"]).toBe("member_v")
  expect(headers["X-Workspace-Id"]).toBe("ws_verified")
})

test("test_review_503_is_not_a_list", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("down", { status: 503 })))
  const result = await createClient("http://api.test").getReview(caller)
  expect(result.ok).toBe(false)
  expect(result.status).toBe(503)
  expect("data" in result).toBe(false)
})

test("test_review_200_empty_array_is_ok", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json([])))
  const result = await createClient("http://api.test").getReview(caller)
  expect(result.ok).toBe(true)
  if (result.ok) {
    expect(result.data).toEqual([])
  }
})

test("test_post_media_sends_json", async () => {
  const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
    Response.json({ id: "m1", status: "pending" }, { status: 202 }),
  )
  vi.stubGlobal("fetch", fetchMock)
  const result = await createClient("http://api.test").postMedia(caller, { type: "image" })
  const init = fetchMock.mock.calls[0][1]
  const headers = init.headers as Record<string, string>
  expect(headers["Content-Type"]).toBe("application/json")
  expect(result.ok).toBe(true)
})
test("test_network_error_is_status_zero", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("offline")
    }),
  )
  const result = await createClient("http://api.test").getReview(caller)
  expect(result.ok).toBe(false)
  expect(result.status).toBe(0)
})
