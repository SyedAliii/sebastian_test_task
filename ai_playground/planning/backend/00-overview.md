# Backend overview

This is the API on port **8000**, plus the worker and the scheduler. It stores workspaces, media, and the proof that an item was screened. It does not score frames itself. It asks the fake provider on port **8001**.

Python 3.12, FastAPI, Postgres, and Redis match the task. Nothing in the task asks for a different stack.

Do not build the React page in these phases. The page is a later plan. This plan still includes `GET /review`, because that route is part of the API the grader will call.

Do not rebuild the provider. It already has its own plan in `ai_playground/planning/provider_service`. If `provider_service\app\main.py` does not exist yet, stop and finish that plan first.

## What the backend decides

A caller sends JSON, not a real image. The API saves it as `pending` and returns `202` (accepted). A worker later asks the provider for scores. The backend then sets one status:

| Status | Meaning |
| --- | --- |
| `pending` | Saved, not decided yet |
| `published` | Allowed to go live |
| `held` | Not live. Either a person must review it, or the provider never answered |
| `blocked` | Not allowed |

`held` has two reasons, stored on the row:

- `review` — a prohibited score from 0.5 up to 0.8. The workspace admin approves or rejects it.
- `no_decision` — the provider never gave a usable answer. An admin cannot approve it. It is sent again when the provider works.

A job marked finished is not proof of screening. `published` is allowed only when a provider decision row exists, or when an admin approves a `review` hold that already has one.

## ASCII flow

```text
Caller
  |  headers X-User-Id, X-Workspace-Id
  |  POST /media  {type, source, prompt?, frames}
  |-------------------------------> API :8000
  |                                 | prompt bad?  422 (refused), nothing saved
  |                                 | else insert media pending + job
  |                                 | push job id to Redis list for that workspace
  |<------------------------------- | 202 (accepted) {id, status: pending}
  |
Worker                                Redis                         Postgres
  |  take one id, alternating workspaces
  |---------------------------------->|
  |  claim that job (one update)
  |------------------------------------------------------------------>|
  |  no row back: another worker owns it, stop
  |  POST /score {media_id, frames}          Provider :8001
  |----------------------------------------->|
  |       200 scores, or 202, or 429/500/504/bad body
  |<-----------------------------------------|
  |
  |  200 and usable scores: one transaction
  |     decision row + media status + job succeeded
  |------------------------------------------------------------------>|
  |
  |  202 (accepted): job awaiting_callback, worker is free
  |
Provider later
  |  POST /provider/callback
  |  header X-Signature = hex hmac of the raw body
  |-------------------------------> API
  |                                 | bad signature: 401, write nothing
  |                                 | good signature: same decision transaction

Scheduler, every second
  |  jobs whose wait is over, whose worker died, or whose callback is late
  |  push those ids to Redis again
  |  sometimes push one parked job, as a probe
```

Two Redis lists, not one:

```text
queue:ws_verified      image, image, ...
queue:ws_unverified    video, video, video, ...   (the burst of 200)

Worker pop order when both have work:  verified, unverified, verified, unverified
```

A burst in one workspace must not make the other workspace wait behind all of it.

## Routes the grader will call

| Route | Success | Failure |
| --- | --- | --- |
| `POST /media` | `202` `{"id", "status": "pending"}` | `422` `{"reasons"}` when a generation prompt is refused |
| `GET /media/{id}` | `200` `{"id", "status", "reasons"}` for a user in that workspace | `404` for everyone else |
| `GET /review` | `200` list of that workspace's `review` holds. `[]` only when there truly are none | `403` for a member, `503` when the query fails |
| `POST /review/{id}/approve` and `.../reject` | `200` `{"id", "status"}` for that workspace's admin | `403` for a member, `404` for another workspace, `409` if it is not a `review` hold |
| `POST /provider/callback` | `200` | `401` when the signature does not match |

`GET /health` is extra. It is only for Docker. The grader does not need it.

## Decisions the task left open

| Topic | Choice |
| --- | --- |
| Missing headers, or a user not in that workspace | `401` |
| `GET /review` when the database query fails | `503` `{"detail": "review queue unavailable"}`. Never `200` with `[]` |
| Approve or reject when the item is not a `review` hold | `409`. The task says the review route returns held media, and also says an item with no decision is never published. `GET /review` returns only `review` holds, so an outage hold cannot be approved onto the site. Say this in the README. |
| Provider score route | `POST http://provider:8001/score` |
| Signature | Lowercase hex HMAC-SHA256 of the raw callback body. Header `X-Signature`. Secret `test-secret`. |
| Labels | `minor`, `sexual_violence`, `bestiality`, `self_harm`, `real_person`, `explicit` |
| `explicit` below 0.8 | No effect by itself |
| `explicit` 0.8 or more | Published in `ws_verified`, blocked in `ws_unverified` |
| Prohibited label 0.8 or more | Blocked in both workspaces |
| Prohibited label from 0.5 up to 0.8 | `held` / `review` |
| Below 0.5 | No effect |
| Several rules at once | `blocked` beats `held`, `held` beats `published` |
| Provider reply missing a label, or with the wrong number of frames | Not a score of 0. It is a bad reply. Retry, then `held` / `no_decision` |
| `error` from the provider with no extra field | HTTP `500` |
| `error_kind` `http_429` or `malformed` | Optional, from the provider plan. Handle them differently from `500` |
| Prompt check | A word and phrase list in code, including `16-year-old`. Not a model. Not a 30% similarity score |

## Code layout

```text
route  ->  service  ->  repo  ->  Postgres
                |
                +-> provider client  ->  provider :8001
                +-> queue repo       ->  Redis
```

| Folder | May do | Must not do |
| --- | --- | --- |
| `app/api` | Read headers and body, call one service method, return the status code | Write SQL. Loop over rows and query. Call Redis or the provider. |
| `app/services` | Apply the rules, open one transaction, call repos | Build SQL strings. Hide a provider error and publish. |
| `app/repo` | One query, or one update, per method | Call HTTP. Decide published or blocked. |
| `app/domain` | Pure functions: prompts, scores, signatures | Open a database connection. |
| `app/core/logging` | The shared logger | Be called with the HMAC secret or `X-Signature`. |

No N+1 means: a list route runs one query that returns all the rows. Do not load each media item, then query its job, then query its user. The review list reads `media` only. The reasons are already on that row.

Schema changes happen only in Alembic files. Seed rows happen only in `app/db/seed.py`, called on startup. Do not type `INSERT` or `ALTER` in DBeaver.

## Logging

Use the style in `ai_playground/logger_prompt.md`, but only the methods this service needs. Do not add websocket, cache, or auth log methods. There is no login.

Put it in `backend\app\core\logging\`.

| Method | When |
| --- | --- |
| `log_level_banner` | Once at startup. Always prints the level |
| `server_request_in` / `server_response_out` | Every API call except `/health`. Same correlation id. Response header `X-Correlation-ID` |
| `api_request_out` / `api_response_in` | The provider HTTP call, with elapsed time |
| `webhook_in` / `webhook_fail` | Callback accepted, or signature rejected |
| `job_start` / `job_end` | One worker attempt |
| `pipeline` | Steps inside the attempt |
| `business_flow` | The decision: status and reasons |
| `warning` | Retry, lost claim, callback deadline |
| `error_trace` | Unexpected exception |
| `system_info` | Scheduler tick that actually moved jobs |

Every pipeline and job line includes `workspace_id`, `media_id`, `job_id`, and `attempt` as `key=value`. That is what the task means by following one item through a failure and a recovery.

Payloads are the low detail level only, truncated. Never log `PROVIDER_HMAC_SECRET`, `X-Signature`, or `Authorization`.

Env: `LOG_DETAIL_LEVEL=mid`, `LOG_ENABLE_EMOJIS=true`. `mid` shows requests, provider calls, and job start/end. `low` also shows payloads.

## Env

File: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\.env`

| Name | Local value | Why |
| --- | --- | --- |
| `API_HOST` | `0.0.0.0` | Listen inside Docker |
| `API_PORT` | `8000` | Fixed by the task |
| `DATABASE_URL` | `postgresql+asyncpg://moderation:moderation@127.0.0.1:5432/moderation` | App connection. Inside Compose the host is `postgres`, not `127.0.0.1` |
| `ALEMBIC_DATABASE_URL` | `postgresql+psycopg://moderation:moderation@127.0.0.1:5432/moderation` | Migrations use a sync driver |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Inside Compose the host is `redis` |
| `PROVIDER_BASE_URL` | `http://127.0.0.1:8001` | Inside Compose: `http://provider:8001` |
| `PROVIDER_HMAC_SECRET` | `test-secret` | Same secret as the provider |
| `PROVIDER_HTTP_TIMEOUT_SECONDS` | `10` | Client gives up. A timeout is not a score |
| `SCREENING_MODE` | `fixed` after phase 6. Phase 4 and 5 use `broken` | Lets you rerun the incident |
| `LEASE_SECONDS` | `30` | How long a claim lasts before refresh |
| `CALLBACK_DEADLINE_SECONDS` | `30` | How long to wait for a long-video callback |
| `WORKER_ID` | empty | Empty means use the container host name, so two worker containers never share an id |
| `SCHEDULER_INTERVAL_SECONDS` | `1` | How often the scheduler looks for due jobs |
| `PROBE_INTERVAL_SECONDS` | `10` | How often one parked job is tried when nothing else is running |
| `RETRY_TIMEOUT_MAX` / `RETRY_429_MAX` / `RETRY_500_MAX` / `RETRY_MALFORMED_MAX` | `3` / `3` / `2` / `2` | Tries before the job is parked |
| `RETRY_BASE_SECONDS` | `1` | First backoff. Doubles each try. Tests set `0` |
| `RETRY_429_MIN_SECONDS` | `5` | A `429` waits at least this long, or longer when `Retry-After` says so |
| `DATABASE_URL_TEST` | `postgresql+asyncpg://moderation:moderation@127.0.0.1:5432/moderation_test` | Pytest only |
| `ALEMBIC_DATABASE_URL_TEST` | `postgresql+psycopg://moderation:moderation@127.0.0.1:5432/moderation_test` | Pytest runs migrations on the test database |
| `REDIS_URL_TEST` | `redis://127.0.0.1:6379/1` | Pytest only. Database `1`, so the running worker on database `0` never takes a test job |
| `LOG_DETAIL_LEVEL` | `mid` | |
| `LOG_ENABLE_EMOJIS` | `true` | |
| `LOG_JSON_MAX_SIZE` | `50000` | |
| `LOG_JSON_MAX_DEPTH` | `10` | |

Compose overrides the host names (`postgres`, `redis`, `provider`) so containers can see each other. The `.env` values above are for running a command on your machine against published ports.

`SCREENING_MODE` is read by the API (prompt check) and the worker (timeout and frames). Compose passes `${SCREENING_MODE:-fixed}` to both, so one shell variable switches the whole stack. To change it, recreate those containers. A restart of only the API is not enough.

## Phases

Do them in order. Stop at the end of each one. The report format is at the bottom of every phase file.

### Phase 1 — Skeleton

Folders, settings, logger, `GET /health`, and Docker Compose for Postgres, Redis, provider, API, worker, and scheduler. Done when `/health` returns `200` and Postgres accepts a connection.

### Phase 2 — Tables and seed

One Alembic migration and `seed.py`. Done when DBeaver shows the six tables and the four users.

### Phase 3 — Accept media

`POST /media` and `GET /media/{id}`. Saves `pending` and pushes the job id. No provider call yet. Done when an upload returns `202` (accepted) and the other workspace gets `404`.

### Phase 4 — Broken worker

The worker calls the provider with the incident bugs left in on purpose: timeout counts as published, only 8 frames are sent, prompts are not checked, a second worker can call too, and a failed review query returns an empty list. Done when those bugs are visible. Do not fix them in this phase.

### Phase 5 — Failing tests

Add the tests for the safe rules. Run them. They must fail. Save the output. Commit. Do not change the worker to make them pass.

### Phase 6 — Fix the rules

Remove the five bugs. Prompts return `422` (refused). Every frame is scored. No answer means `held`. One claim per job. Review errors stay errors. Commit. Done when the phase 5 tests pass.

### Phase 7 — Retries and recovery

Different waits for timeout, `429`, `500`, and a bad body. Park after the limit. Probe one parked job until a success puts the rest back. A late or missing callback is retried. Done when a timeout no longer publishes and a later success publishes without an admin.

### Phase 8 — Fairness, crash, numbers

The other workspace's image is taken while a burst is waiting. A worker that dies after the provider answers does not publish. A script prints the three numbers the README needs. Done when the small fairness test passes.

### Phase 9 — Postman and manual check

Postman collection, then DBeaver, Redis Insight, and a short click-through. Done when the checklist has been run.

## How a phase run must end

```text
Phase N done.
Files affected:
- d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\...
Tests: python -m pytest
Result: pass or fail, with the failing name if any
```

Use the full path of every file created or edited.
