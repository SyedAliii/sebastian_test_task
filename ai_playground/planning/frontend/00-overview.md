# Frontend overview

This is the one page the task asks for. React and TypeScript match the task. Nothing in the task asks for a different UI stack.

The page does not decide whether an item is published, held, or blocked. It sends the JSON the person typed, then shows the status the API returns.

The page has no database and no Redis. Do not open DBeaver. Do not open Redis Insight. Do not add an Alembic migration. Do not add a Postman collection. The backend collection already calls the API. This page is not an API.

Do not start until the backend is running and `GET http://127.0.0.1:8000/health` returns ok. This plan does not rebuild the API or the provider.

## What the person sees

One page, three parts:

1. Who you are. A workspace and a user. There is no password. The page sends `X-Workspace-Id` and `X-User-Id` on every API call.
2. Submit. Upload or generation. The person edits JSON frames. A generation also has a prompt. The page shows the id and the status the API returns.
3. Review. For an admin, loads the held items for that workspace. This part must show three different things: still loading, the request failed, and the list is really empty. A member sees `Review is for workspace admins`, and the page does not call `GET /review` for them.

The four people already in the database:

| Workspace | User | Role |
| --- | --- | --- |
| `ws_verified` | `admin_v` | admin |
| `ws_verified` | `member_v` | member |
| `ws_unverified` | `admin_u` | admin |
| `ws_unverified` | `member_u` | member |

## ASCII flow

```text
Browser  :3000
  |
  |  pick workspace and user
  |
  |  POST /media     headers X-User-Id, X-Workspace-Id
  |-------------------------------> nginx on the same origin
  |                                   proxies to API :8000
  |<------------------------------- 202 pending, or 422 reasons
  |
  |  GET /media/{id}   once a second, until it is not pending
  |<------------------------------- published, held, or blocked
  |
  |  GET /review       one request for the whole list
  |
  |     waiting on the network -------- "Loading review queue"
  |     status is not 200 ------------- "Review queue failed" + Try again
  |     200 and [] -------------------- "Nothing to review"
  |     200 and rows ------------------ each row, Approve and Reject for an admin
  |
  |  POST /review/{id}/approve or /reject
  |  then ONE more GET /review
```

The browser never calls port 8000 or 8001 itself. Nginx, and the Vite dev server, forward `/media`, `/review`, and `/health` to the API. That avoids a cross-origin setup. Nginx looks up the API's address again every 10 seconds, so stopping and starting the API in phase 7 does not leave the page stuck on `502`.

A reply that arrives after you switched user is dropped, so one workspace's queue never shows under another.

One `GET /review` returns every row. Do not call `GET /media/{id}` once per row. That would be the frontend version of an N+1 query. After approve or reject, call `GET /review` once more.

## The incident on this page

The broken page treats a failed review request as an empty list, so it says "Nothing to review" while items are waiting. Phase 4 builds that bug on purpose. Phase 5 adds tests that fail. Phase 6 makes a failure look like a failure.

The words must stay different:

| State | Exact text |
| --- | --- |
| Loading | `Loading review queue` |
| Failed | `Review queue failed` |
| Empty | `Nothing to review` |

The failed box also shows the status code, such as `503`, and a `Try again` button. It must not contain the words `Nothing to review`.

`200` and `[]` is the only empty state. `403`, `401`, `500`, `502`, `503`, and a network error are all failed.

A status poll that is still `pending` after 20 seconds shows `Still pending`, not an error and not published. During a provider outage, retries can take that long.

## Code layout

```text
component  ->  hook  ->  api client  ->  fetch
                |
                +-> reviewView()   pure function, no fetch
```

| Folder | May do | Must not do |
| --- | --- | --- |
| `src/api` | `fetch`, attach the two headers, return ok or the status code | Turn a failed response into `[]`. Decide published or blocked. |
| `src/domain` | `reviewView`, example JSON | Call `fetch`. |
| `src/components` | Render the text and call a hook | Call `fetch` directly. Hide an error as an empty list. |
| `src/lib` | A few `console` lines | Copy the Python logger. Log frame JSON. |

## Logging

`ai_playground/logger_prompt.md` is a Python logger for the API process. Do not port it into the browser. The API already logs workspace, media, job, and attempt.

The page only writes short `console.info` lines: `step=submit media_id=... status=...` and `step=review state=loading|failed|empty|list`. No frames, no prompt text, no signatures.

## Env

File: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend\.env.example`

| Name | Value | Why |
| --- | --- | --- |
| `VITE_API_BASE_URL` | empty | Empty means same origin. Vite and nginx forward the API paths. Set `http://127.0.0.1:8000` only if you are not using that proxy. |

No database URL. No Redis URL. No HMAC secret.

## API the page calls

| Call | What the page does with it |
| --- | --- |
| `POST /media` | `202` show id and `pending`, then poll. `422` show `reasons` and stop. |
| `GET /media/{id}` | Show `status` and `reasons`. Poll while `pending`. |
| `GET /review` | Pass the status and the list to `reviewView`. |
| `POST /review/{id}/approve` | On `200`, load the list once more. On failure, show the status under that row. |
| `POST /review/{id}/reject` | Same as approve. |

`GET /review` returns a JSON array of `{id, status, reasons}`. `reasons` is an array of strings.

## Phases

Do them in order. Stop at the end of each one.

### Phase 1 — Skeleton

Vite, TypeScript, one blank page, Docker on port 3000. Done when the browser shows the page title.

### Phase 2 — Who and the API client

The two dropdowns and the only `fetch` wrapper. Done when a test proves the two headers are sent, and a failed response is not turned into a list.

### Phase 3 — Submit

The form, example JSON buttons, and polling one id. Done when a refused prompt shows the reasons and does not poll.

### Phase 4 — Review, broken

The review box. A failed request shows "Nothing to review". This is the bug. Do not fix it.

### Phase 5 — Failing tests

Tests for the three states. They fail. Save the output. Commit. Do not change the page to make them pass.

### Phase 6 — Fix the three states

A failure shows "Review queue failed". An empty `200` still shows "Nothing to review". Commit.

### Phase 7 — Manual check

Click through the page in the browser, including stopping the API so the review box fails.

## How a phase run must end

```text
Phase N done.
Files affected:
- d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend\...
Tests: npm test
Result: pass or fail, with the failing name if any
```

Use the full path of every file created or edited.
