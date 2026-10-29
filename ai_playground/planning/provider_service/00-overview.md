# Provider service overview

This service is the fake moderation provider. It does not decide whether an item is published, held, or blocked. It echoes scores, counts calls, and can be made slow, silent, or failing.

The task asks for Python 3.12 and FastAPI. Nothing in the task disagrees with that. Use those.

Build only this service. Do not build the backend, the React page, Postgres, or Redis in these phases.

The provider does not have a database. The task's `GET /_stats` is an invoice kept in memory. A restart resets the counts. That is expected. The `repo` folder is still used: it is the only place that touches that memory. Routes never touch it directly.

## What this service is for

The backend worker will send the frames for one media item here. This service:

1. Counts that call against the media id.
2. Fills in any missing label with `0`.
3. Returns every frame, not only the first 8.
4. For 30 frames or fewer, returns the scores in the same call.
5. For more than 30 frames, returns `202` (accepted) and later posts the scores to the backend callback.
6. Signs that callback with HMAC-SHA256.
7. Can be switched to slow, timeout, or error without a restart.

The first-8-frames bug, the timeout-as-pass bug, and the prompt check belong to the backend. Do not put those bugs in this service.

## ASCII flow

```text
Backend worker                         Provider  :8001
      |                                      |
      |  POST /score                         |
      |  {media_id, frames}                  |
      |------------------------------------->|
      |                                      | validate body
      |                                      | calls[media_id] += 1
      |                                      | read mode once
      |                                      |
      |          mode = timeout ------------ | wait, then 504, no scores
      |          mode = error -------------- | 500, or 429, or a bad 200
      |                                      |
      |          mode = ok or slow           |
      |          frames <= 30                |
      |          wait delay_ms               |
      |<-------------------------------------| 200 {media_id, frames}
      |          every label on every frame  |
      |                                      |
      |          mode = ok or slow           |
      |          frames > 30                 |
      |<-------------------------------------| 202 {media_id, status: accepted}
      |                                      | wait delay_ms
      |                                      | sign the raw body
      |  POST /provider/callback             |
      |  header X-Signature                  |
      |<-------------------------------------| {media_id, frames}
      |                                      |

Grader
      |  POST /_control {mode, delay_ms}     |
      |------------------------------------->| save mode in memory
      |  GET /_stats                         |
      |------------------------------------->| {"calls": {"media id": 1}}
```

`POST /_control` and `GET /_stats` are not scoring calls. They do not increase `calls`.

## Decisions the task left open

These are not written in the task. They are fixed here so the backend can be built against them later. Do not rename them in a later phase.

| Topic | Choice |
| --- | --- |
| Score route | `POST /score` on port 8001 |
| Callback body | Same JSON as a normal `200` score response |
| Signature | Lowercase hex HMAC-SHA256 of the raw body. Header name `X-Signature`. No prefix. |
| Shared secret | Env `PROVIDER_HMAC_SECRET`, default `test-secret` |
| 30 frames | 30 or fewer is a direct `200`. 31 or more is `202` plus a callback. |
| Labels, in this order | `minor`, `sexual_violence`, `bestiality`, `self_harm`, `real_person`, `explicit` |
| Missing label on input | Fill `0` before echoing. |
| Bad provider reply | Not used for normal scoring. Only `mode=error` with `error_kind=malformed` returns a bad body on purpose. |
| `error` with no extra field | HTTP `500` |
| `429` and malformed | Optional `error_kind` on `POST /_control`. Their grader can ignore it. |
| Call count | Increase once the body is valid, before the mode runs. Errors and timeouts still count. Invalid bodies do not. |
| Duplicate calls | Count every one. This service does not dedupe. |
| Prompt field | Ignore it if a caller sends one. Prompt refusal is the backend's job. |

One extension, called out so it is not mistaken for a task route: `error_kind` may be `http_500`, `http_429`, or `malformed`. If the field is absent, `error` means HTTP `500`. Their published body is only `mode` and `delay_ms`.

## Routes

| Route | Response |
| --- | --- |
| `GET /health` | `200` `{"status": "ok"}` |
| `POST /_control` | `200` with the saved mode. `422` if `mode` is not one of the four. |
| `GET /_stats` | `200` `{"calls": {"<media id>": 1}}` |
| `POST /score`, 1 to 30 frames, mode ok or slow | `200` with `media_id` and filled frames |
| `POST /score`, 31 or more frames, mode ok or slow | `202` `{"media_id", "status": "accepted"}`, then the callback |
| `POST /score`, mode timeout | Wait, then `504` `{"detail": "provider timeout"}`. No callback. |
| `POST /score`, mode error | `500`, `429`, or a bad `200`. No callback. |
| Bad score body | `422`. Call count unchanged. |

Control body their grader will send:

```json
{"mode": "ok", "delay_ms": 0}
```

`mode` is `ok`, `slow`, `timeout`, or `error`. If `delay_ms` is missing, use `0`.

Stats body:

```json
{"calls": {}}
```

Score request:

```json
{"media_id": "demo-1", "frames": [{"explicit": 0.02}]}
```

Score success body:

```json
{"media_id": "demo-1", "frames": [{"minor": 0.0, "sexual_violence": 0.0, "bestiality": 0.0, "self_harm": 0.0, "real_person": 0.0, "explicit": 0.02}]}
```

## Code layout

```text
HTTP route  ->  service  ->  repo (memory only)
                  |
                  +-> signature helper
                  +-> callback dispatcher  ->  callback sender (httpx)
```

`create_app(settings=None)` builds one app with its own settings, store, and callback dispatcher. `app.main` also has a module-level `app = create_app()` so `uvicorn app.main:app` works. Tests call `create_app(Settings(...))` with their own values, so they never depend on `.env`.

The callback dispatcher starts each callback with `asyncio.create_task` and keeps the task in a set until it finishes. It does not use FastAPI `BackgroundTasks`. The httpx test client waits for `BackgroundTasks` before it returns a response, which would hide whether `202` really comes back first. Tests call `await dispatcher.drain()` to wait for callbacks they want to check.

| Folder | May do | Must not do |
| --- | --- | --- |
| `app/api` | Read the HTTP body, call one service method, turn the result into a status code. `/_control` and `/_stats` are plain reads and writes, so those two routes may call one repo method directly. | Touch the call dict. Decide publish or block. Loop over frames. Call the repo from `/score`. |
| `app/services` | Count the call through the repo, fill labels, apply the mode, sign, send one callback | Return FastAPI response objects. Hold state of its own. Open SQL. |
| `app/repo` | Get and set the mode. Add 1 to one media id. Return the whole call map. | Make an HTTP call. Know about HMAC. |
| `app/domain` | Hold the label list and the request shapes | Hold mutable counts. |

No N+1: there is no SQL. Each score request takes one lock and updates one counter. Do not call the repo once per frame. Do not add Postgres to this service.

## Env

File: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\.env`

| Name | Value for local run | Why |
| --- | --- | --- |
| `PROVIDER_HOST` | `0.0.0.0` | Listen on all interfaces inside Docker |
| `PROVIDER_PORT` | `8001` | Fixed by the task |
| `PROVIDER_HMAC_SECRET` | `test-secret` | Same value the backend will use later |
| `CALLBACK_BASE_URL` | `http://127.0.0.1:9000` | Where async results are posted. `9000` is the catcher in the manual test when the provider runs with uvicorn on your machine. In Docker, `127.0.0.1` is the container itself: use `http://host.docker.internal:9000` for the catcher, and later the backend's compose service, for example `http://api:8000`. |
| `CALLBACK_PATH` | `/provider/callback` | Fixed by the task |
| `TIMEOUT_HOLD_SECONDS` | `120` | How long timeout mode holds the connection before `504` |
| `RETRY_AFTER_SECONDS` | `2` | Sent as the `Retry-After` header on `429` |
| `LOG_LEVEL` | `INFO` | Log each score with `media_id`, mode, frame count, and outcome |

## Phases

Do them in order. After each one, stop and show the file list. Do not start the next phase in the same run.

### Phase 1 — Skeleton

Create the folder, the settings, `GET /health`, Docker, and an empty test that passes. No scoring yet. Done when `GET http://127.0.0.1:8001/health` returns `{"status": "ok"}` and `pytest` passes.

### Phase 2 — Mode and invoice

Add the in-memory repo, `POST /_control`, and `GET /_stats`. Done when a control call is saved, a bad mode is refused without overwriting the saved one, and control calls never add media ids to `/_stats`.

### Phase 3 — Direct score

Add `POST /score` for 1 to 30 frames in `ok` mode. Fill missing labels with `0`. Count every valid call, including a second call for the same id. Done when a one-frame body comes back with all six labels and `calls` is `1`, then `2` on the next call.

### Phase 4 — Long video

31 or more frames returns `202` and later posts a signed body to the callback. The signature is checked in the test by recomputing it. Done when the test receiver accepts the raw bytes and the hex signature.

### Phase 5 — Slow, timeout, error

`delay_ms` waits before a direct score, and before a callback. Timeout returns no scores. Error returns `500` unless `error_kind` asks for `429` or a bad body. All of these still increase `calls`. Done when each mode has a passing test and `/_stats` shows the count.

### Phase 6 — Manual check

Add the Postman collection and a small callback catcher. Follow the written clicks and curls. This phase adds no new behavior. Done when the checklist at the end of that file has been run.

## How a phase run must end

The implementing model prints this and stops:

```text
Phase N done.
Files affected:
- d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\...
Tests: python -m pytest
Result: pass or fail, with the failing name if any
```

Use the full path of every file created or edited.
