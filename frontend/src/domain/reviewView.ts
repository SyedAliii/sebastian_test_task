import type { Media } from "../api/types"

export type ReviewInput =
  | { kind: "loading" }
  | { kind: "error"; status: number }
  | { kind: "ready"; items: Media[] }

export type ReviewView =
  | { kind: "loading"; text: "Loading review queue" }
  | { kind: "failed"; text: "Review queue failed"; status: number }
  | { kind: "empty"; text: "Nothing to review" }
  | { kind: "list"; items: Media[] }

export function reviewView(input: ReviewInput): ReviewView {
  if (input.kind === "loading") {
    return { kind: "loading", text: "Loading review queue" }
  }
  // Incident bug: a failed review request looks empty.
  if (input.kind === "error") {
    return { kind: "empty", text: "Nothing to review" }
  }
  if (input.items.length === 0) {
    return { kind: "empty", text: "Nothing to review" }
  }
  return { kind: "list", items: input.items }
}
