import { expect, test } from "vitest"
import { buildMediaBody } from "./mediaBody"

test("test_upload_body_has_no_prompt", () => {
  const body = buildMediaBody(
    { type: "image", source: "generation", prompt: "a 16-year-old", frames: [{ explicit: 0.1 }] },
    "upload",
    "ignored",
  )
  expect(body.source).toBe("upload")
  expect(body).not.toHaveProperty("prompt")
})

test("test_generation_body_has_prompt", () => {
  const body = buildMediaBody(
    { type: "image", source: "upload", frames: [{ explicit: 0.1 }] },
    "generation",
    "two adults on a beach at sunset",
  )
  expect(body.source).toBe("generation")
  expect(body.prompt).toBe("two adults on a beach at sunset")
})
