import { expect, test } from "vitest"
import type { Media } from "../api/types"
import { reviewView } from "./reviewView"

const oneItem: Media = { id: "held-1", status: "held", reasons: ["self_harm"] }

test("test_loading_is_its_own_state", () => {
  const view = reviewView({ kind: "loading" })
  expect(view.kind).toBe("loading")
  if (view.kind === "loading") {
    expect(view.text).toBe("Loading review queue")
  }
})

test("test_error_is_not_empty", () => {
  const view = reviewView({ kind: "error", status: 503 })
  expect(view).toMatchObject({ kind: "failed", text: "Review queue failed", status: 503 })
  expect("text" in view ? view.text : "").not.toContain("Nothing to review")
})

test("test_network_error_is_not_empty", () => {
  const view = reviewView({ kind: "error", status: 0 })
  expect(view.kind).toBe("failed")
  expect(view.kind).not.toBe("empty")
})

test("test_forbidden_is_not_empty", () => {
  const view = reviewView({ kind: "error", status: 403 })
  expect(view).toMatchObject({ kind: "failed", status: 403 })
})

test("test_real_empty_stays_empty", () => {
  const view = reviewView({ kind: "ready", items: [] })
  expect(view.kind).toBe("empty")
  if (view.kind === "empty") {
    expect(view.text).toBe("Nothing to review")
  }
})

test("test_rows_stay_a_list", () => {
  const view = reviewView({ kind: "ready", items: [oneItem] })
  expect(view.kind).toBe("list")
  if (view.kind === "list") {
    expect(view.items[0]?.id).toBe("held-1")
  }
})
