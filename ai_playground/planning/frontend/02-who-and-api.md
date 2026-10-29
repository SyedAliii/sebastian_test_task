# Phase 2 — Who and the API client

Phase 1 must already pass. Do this phase only. Stop at the end.

## Goal

The page lets you pick one of the four seeded users. All HTTP goes through one client. A failed response stays a failure. It is never rewritten as an empty list.

## Do not

- Do not add the submit form or the review box yet.
- Do not call `fetch` from a component.
- Do not read or write Postgres.

## API client

`src\api\types.ts`:

```ts
export type Caller = {
  workspaceId: "ws_verified" | "ws_unverified"
  userId: "admin_v" | "member_v" | "admin_u" | "member_u"
}

export type Media = {
  id: string
  status: "pending" | "published" | "held" | "blocked"
  reasons: string[]
}

export type ApiSuccess<T> = { ok: true; status: number; data: T }
export type ApiFailure = { ok: false; status: number; message: string }
export type ApiResult<T> = ApiSuccess<T> | ApiFailure
```

`src\api\client.ts` exports `createClient(baseUrl: string)`.

- `baseUrl` defaults to `import.meta.env.VITE_API_BASE_URL ?? ""`.
- Every method takes a `Caller` and sets `X-User-Id` and `X-Workspace-Id`.
- Methods: `postMedia`, `getMedia`, `getReview`, `approve`, `reject`.
- `getReview` returns `ApiResult<Media[]>`.
- On a response that is not ok, return `{ ok: false, status, message }`. `message` is `response status <code>`. Do not parse a failure body into a list.
- On a network throw, return `{ ok: false, status: 0, message: "network error" }`.
- On `200`, parse JSON once. If `getReview` gets `200` and the body is not an array, return `ok: false` with status `200` and message `review payload was not a list`. Do not substitute `[]`.
- `postMedia` returns `ApiResult<{ id: string; status: "pending" }>` for `202`, and `ApiFailure` for anything else. When the status is `422`, put the `reasons` array into `message` joined by commas, and also return them on the failure as `reasons: string[]`. Add `reasons?: string[]` to `ApiFailure`.
- `approve` and `reject` call `POST /review/{id}/approve` and `POST /review/{id}/reject` with an empty body.

No method loops. One call does one `fetch`.

`src\lib\log.ts` has `logStep(step: string, fields: Record<string, string | number>)`. It prints one `console.info` line of `key=value`. It has no other methods. Do not import the Python logger.

## Who picker

`src\components\WhoSelect.tsx`.

Two `<select>` elements.

- Workspace label `Workspace`. Options `ws_verified` and `ws_unverified`.
- User label `User`. Options depend on the workspace. Verified: `admin_v`, `member_v`. Unverified: `admin_u`, `member_u`.
- Changing workspace resets the user to that workspace's admin.

`App` holds the `Caller` in state. Default `ws_verified` and `admin_v`. Pass the caller down. Render the heading `Moderation` and the picker. Show the text `Signed in as admin_v in ws_verified`, using the real selected ids.

`src\domain\caller.ts`:

```ts
export function isAdmin(userId: Caller["userId"]): boolean {
  return userId.startsWith("admin_")
}
```

## Tests

Use `fetch` mocked with `vi.stubGlobal`. Restore it after each test.

| Test | Assert |
| --- | --- |
| `test_client_sends_caller_headers` | `getMedia` sends `X-User-Id: member_v` and `X-Workspace-Id: ws_verified`. |
| `test_review_503_is_not_a_list` | `fetch` resolves `503`. `getReview` is `ok: false`, status `503`. The result has no array. |
| `test_review_200_empty_array_is_ok` | Body `[]`. `ok: true` and `data` is `[]`. |
| `test_network_error_is_status_zero` | `fetch` rejects. `ok: false`, status `0`. |
| `test_switching_workspace_picks_that_admin` | Render `App`. Choose `ws_unverified`. The user select's value is `admin_u`. The signed-in text includes `admin_u` and `ws_unverified`. |

## Done when

- `npm test` passes.
- A component file does not contain `fetch`.
- `getReview` cannot return `ok: true` for a `503`.

## Report, then stop

```text
Phase 2 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: <pass or fail>
```
