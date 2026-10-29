import { expect, test } from "vitest"
import { reviewView } from "./reviewView"

test("test_broken_error_looks_empty", () => {
  const view = reviewView({ kind: "error", status: 503 })
  expect(view.kind).toBe("empty")
  if (view.kind === "empty") {
    expect(view.text).toBe("Nothing to review")
  }
})
