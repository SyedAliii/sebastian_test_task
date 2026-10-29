import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"
import type { Caller } from "../api/types"
import { SubmitForm, type SubmitClient } from "./SubmitForm"

const caller: Caller = { workspaceId: "ws_verified", userId: "admin_v" }

afterEach(() => {
  vi.useRealTimers()
})

test("test_refused_prompt_does_not_poll", async () => {
  const postMedia = vi.fn<SubmitClient["postMedia"]>(async () => ({
    ok: false,
    status: 422,
    message: "minor",
    reasons: ["minor"],
  }))
  const getMedia = vi.fn<SubmitClient["getMedia"]>()
  render(<SubmitForm client={{ postMedia, getMedia }} caller={caller} />)
  await userEvent.click(screen.getByRole("button", { name: "Submit" }))
  expect(screen.getByText(/Refused/)).toBeInTheDocument()
  expect(screen.getByText(/minor/)).toBeInTheDocument()
  expect(getMedia).not.toHaveBeenCalled()
})

test("test_accepted_then_published", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] })
  const postMedia = vi.fn<SubmitClient["postMedia"]>(async () => ({
    ok: true,
    status: 202,
    data: { id: "abc", status: "pending" },
  }))
  const getMedia = vi
    .fn<SubmitClient["getMedia"]>()
    .mockResolvedValueOnce({ ok: true, status: 200, data: { id: "abc", status: "pending", reasons: [] } })
    .mockResolvedValueOnce({ ok: true, status: 200, data: { id: "abc", status: "published", reasons: [] } })
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  render(<SubmitForm client={{ postMedia, getMedia }} caller={caller} />)
  await user.click(screen.getByRole("button", { name: "Submit" }))
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000)
  })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000)
  })
  expect(screen.getByText(/published/)).toBeInTheDocument()
  expect(getMedia).toHaveBeenCalledTimes(2)
  for (const call of getMedia.mock.calls) {
    expect(call[1]).toBe("abc")
  }
  vi.useRealTimers()
})

test("test_bad_json_does_not_call", async () => {
  const postMedia = vi.fn<SubmitClient["postMedia"]>()
  const getMedia = vi.fn<SubmitClient["getMedia"]>()
  const user = userEvent.setup()
  render(<SubmitForm client={{ postMedia, getMedia }} caller={caller} />)
  await user.clear(screen.getByLabelText("Frames"))
  await user.type(screen.getByLabelText("Frames"), "not json")
  await user.click(screen.getByRole("button", { name: "Submit" }))
  expect(postMedia).not.toHaveBeenCalled()
  expect(screen.getByText("Could not read the JSON")).toBeInTheDocument()
})

test("test_safe_image_button_fills_the_box", async () => {
  const user = userEvent.setup()
  render(
    <SubmitForm
      client={{ postMedia: vi.fn(), getMedia: vi.fn() }}
      caller={caller}
    />,
  )
  await user.clear(screen.getByLabelText("Frames"))
  await user.click(screen.getByRole("button", { name: "Safe image" }))
  expect((screen.getByLabelText("Frames") as HTMLTextAreaElement).value).toMatch(/"type":\s*"image"/)
})

test("test_still_pending_after_twenty_tries", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] })
  const postMedia = vi.fn<SubmitClient["postMedia"]>(async () => ({
    ok: true,
    status: 202,
    data: { id: "abc", status: "pending" },
  }))
  const getMedia = vi.fn<SubmitClient["getMedia"]>(async () => ({
    ok: true,
    status: 200,
    data: { id: "abc", status: "pending", reasons: [] },
  }))
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  render(<SubmitForm client={{ postMedia, getMedia }} caller={caller} />)
  await user.click(screen.getByRole("button", { name: "Submit" }))
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
  }
  expect(screen.getByText("Still pending")).toBeInTheDocument()
  expect(getMedia).toHaveBeenCalledTimes(20)
  await vi.advanceTimersByTimeAsync(1000)
  expect(getMedia).toHaveBeenCalledTimes(20)
  vi.useRealTimers()
})
