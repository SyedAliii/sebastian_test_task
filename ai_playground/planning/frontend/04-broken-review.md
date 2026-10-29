# Phase 4 — Review, broken

Phase 3 must already pass. Do this phase only. Stop at the end.

## Goal

The page loads the review list. A failed request is shown as an empty list. That is the incident. Do not fix it in this phase.

## Do not

- Do not show the words `Review queue failed`.
- Do not add a Try again button.
- Do not call `GET /media` once per row.

## The view function

`src\domain\reviewView.ts` exports `reviewView`.

Input:

```ts
type ReviewInput =
  | { kind: "loading" }
  | { kind: "error"; status: number }
  | { kind: "ready"; items: Media[] }
```

Output:

```ts
type ReviewView =
  | { kind: "loading"; text: "Loading review queue" }
  | { kind: "failed"; text: "Review queue failed"; status: number }
  | { kind: "empty"; text: "Nothing to review" }
  | { kind: "list"; items: Media[] }
```

The broken function does this:

- `loading` returns the loading view.
- `error` returns the empty view. This is the bug. Status is ignored.
- `ready` with no items returns the empty view.
- `ready` with items returns the list view.

Leave a one-line comment above the error branch: `Incident bug: a failed review request looks empty.`

## The box

`src\components\ReviewQueue.tsx`.

- On mount, and when the caller changes, set the input to `loading`, then call `getReview` once.
- Ignore a reply that belongs to an earlier caller. Keep a request counter in a `useRef`, increase it before each call, and only apply the reply when its number is still the latest. Otherwise a slow `ws_verified` reply can land after you switched to `ws_unverified` and show the wrong workspace's queue.
- `ok: true` becomes `{ kind: "ready", items: data }`.
- `ok: false` becomes `{ kind: "error", status }`.
- Render through `reviewView`.
- Loading text is exactly `Loading review queue`.
- Empty text is exactly `Nothing to review`.
- Because of the bug, an error also renders `Nothing to review`.
- A list renders one row per item: the id, the status, and the reasons joined by commas.
- Each row has buttons `Approve` and `Reject`.
- Approve calls `approve` once. Reject calls `reject` once. On `200`, call `getReview` once more. On failure, show `Action failed <status>` under that row. Do not clear the list.
- Log `step=review` with `state` equal to the view kind. For this bug, an error logs `state=empty`.

The section heading is `Review`.

Put the component on `App` under the submit form.

The task makes review an admin route. When `isAdmin(caller.userId)` is false, the box shows only `Review is for workspace admins` and does not call `getReview`. Otherwise a member would always see a `403`, which says nothing useful about the queue. This is not part of the incident. The incident is an admin seeing an empty queue when the request failed.

A `403` can still reach an admin, for example if the seed data changed. The view function treats it like any other failure.

## Test that locks the bug

`src\domain\reviewView.test.ts`:

- `test_broken_error_looks_empty`. Input `{ kind: "error", status: 503 }`. The result kind is `empty` and the text is `Nothing to review`.

This test must pass in this phase. Phase 5 adds the tests that want the opposite, and those fail. Phase 6 changes this test to call `reviewViewBroken` instead.

`src\components\ReviewQueue.test.tsx`, which must also pass now:

| Test | Assert |
| --- | --- |
| `test_member_does_not_call_review` | Caller `member_v`. The page shows `Review is for workspace admins`. The fake `getReview` was not called. |
| `test_list_shows_rows` | Admin. `getReview` returns two items. Both ids show, each with `Approve` and `Reject`. `getReview` was called once. |
| `test_approve_reloads_once` | Click `Approve` on one row. `approve` was called once with that id. `getReview` was called exactly twice in total. |
| `test_stale_reply_is_ignored` | The first `getReview`, for `admin_v`, resolves only after the caller changes to `admin_u` and that second call has resolved with `[]`. The page shows the `admin_u` result, not the first reply's rows. Use two promises you resolve by hand. |

## Done when

- `npm test` passes, including `test_broken_error_looks_empty`.
- The page has no `Try again` button.
- The error branch still returns the empty view.

## Report, then stop

```text
Phase 4 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: <pass or fail>
Bug still present: a failed review request renders Nothing to review
```
