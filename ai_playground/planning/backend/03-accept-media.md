# Phase 3 — Accept media

Phase 2 must already pass. Do this phase only. Stop at the end.

## Goal

A user can submit media and read it back. The API saves `pending`, creates a job, and pushes the job id to that workspace's Redis list. It does not call the provider. Prompts are stored and not judged yet. That gap is on purpose. Phase 4 leaves it broken, and phase 6 adds the refusal.

## Do not

- Do not call `POST /score`.
- Do not set status to anything but `pending`.
- Do not return `422` for a bad prompt yet.

## Headers

Every media route depends on `get_caller`.

- Missing `X-User-Id` or `X-Workspace-Id`: `401` and `{"detail": "missing caller"}`.
- The pair must match one `users` row: `401` and `{"detail": "unknown caller"}`.
- One query does this lookup. Not a query for the workspace and then another for the user.

## POST /media

Body:

```json
{"type": "image", "source": "upload", "frames": [{"explicit": 0.1}]}
```

Generation adds `"prompt": "two adults on a beach"`.

Validation, before any insert:

- `type` is `image` or `video`.
- `source` is `upload` or `generation`.
- `frames` has at least 1 object.
- `image` has exactly 1 frame. More than one is `422` `{"reasons": ["image_must_have_one_frame"]}`.
- `generation` requires a non-empty `prompt`. Missing it is `422` `{"reasons": ["prompt_required"]}`.
- `upload` must not include a prompt. If it does, `422` `{"reasons": ["upload_has_no_prompt"]}`.
- Each score is a number from 0 to 1. Reject `true` and `false` with a `mode="before"` validator, because pydantic would turn them into 1 and 0.
- Unknown label keys are kept in the stored JSON. The provider ignores them later. Do not drop them here.

A valid body, in one transaction:

1. Insert `media` with a new uuid, status `pending`, `hold_reason` null, `reasons` `[]`, `frame_count` equal to the list length.
2. Insert `jobs` with a new uuid, state `queued`, `attempts_used` 0, `available_at` now, `needs_enqueue` true.
3. Commit. The worker must never see an id whose row is not committed yet.
4. `RPUSH` the job id to `queue:{workspace_id}`.
5. If the push succeeded, one `UPDATE jobs SET needs_enqueue = false WHERE id = :id`, then commit.

If the Redis push fails, leave `needs_enqueue` true, log `warning`, and still return `202`. The scheduler pushes it in phase 7. Do not fail the HTTP call after the row is saved.

Response `202`:

```json
{"id": "<uuid>", "status": "pending"}
```

`id` is a string.

## GET /media/{id}

One query: `id` and `workspace_id` together.

- Found: `200` `{"id", "status", "reasons"}`.
- Not in this workspace, or no such id: `404` and `{"detail": "not found"}`. Same body for both, so a caller cannot learn that the id exists.

## Redis repo

`app\repo\queues.py` is the only file that talks to Redis.

- `enqueue(workspace_id, job_id)` does one `RPUSH` to `queue:{workspace_id}`.
- `length(workspace_id)` does one `LLEN`.

No method loops over frames. The key is exactly `queue:ws_verified` or `queue:ws_unverified`.

## Code placement

| File | Role |
| --- | --- |
| `app\domain\schemas.py` | `MediaIn`, `MediaCreated`, `MediaOut` |
| `app\repo\media_repo.py` | `insert_media`, `get_media_for_workspace` |
| `app\repo\job_repo.py` | `insert_job` |
| `app\services\media_service.py` | `create_media`, `get_media` |
| `app\api\routes\media.py` | The two routes. No SQL text. |
| `app\api\deps.py` | `get_session`, `get_caller`, `get_media_service`, `get_queues` |

The route calls `create_media` once. The service calls the two inserts and one enqueue. That is three round trips for one write, not N+1. N+1 would be a query per frame. Do not do that.

Log `business_flow` at low detail is optional here. Do log `pipeline` at mid with `workspace_id` and `media_id` and `step=accepted`.

## Tests

Use the database fixture and `redis_client` from phase 2. The app gets the test session factory and the Redis database `1` client through dependency overrides.

| Test | Assert |
| --- | --- |
| `test_upload_returns_pending` | `member_v` and `ws_verified` post an image. Status `202`. Body status `pending`. An id is present. |
| `test_owner_can_read` | The same caller `GET /media/{id}` is `200` and `pending`. |
| `test_other_workspace_is_404` | `member_u` and `ws_unverified` get `404` for that id. |
| `test_missing_header_is_401` | No headers. Status `401`. |
| `test_user_in_wrong_workspace_is_401` | `member_v` with `ws_unverified` is `401`. |
| `test_generation_is_stored` | A generation with a prompt returns `202`. This phase does not refuse the words `16-year-old`. |
| `test_image_with_two_frames_is_422` | Status `422` and reasons include `image_must_have_one_frame`. No media row. |
| `test_job_is_pushed` | After one upload, `LLEN queue:ws_verified` is 1. The other list is 0. |

To check rows, the test opens its own session from the factory after the request returns. To check Redis, it calls `LLEN` on the test client.

## Redis Insight

1. Compose must be running.
2. Open Redis Insight.
3. Add Redis database. Host `127.0.0.1`, port `6379`, name `local`. No username or password.
4. Add Database. Open it.
5. Browser. Make sure the database index at the top is `0`. Tests use index `1` and wipe it, so their keys do not stay.
6. Stop the worker for this check, or it will pop the id before you look: `docker compose stop worker`. Then post once with curl while the API is up:

```powershell
curl -X POST http://127.0.0.1:8000/media -H "Content-Type: application/json" -H "X-User-Id: member_v" -H "X-Workspace-Id: ws_verified" -d "{\"type\":\"image\",\"source\":\"upload\",\"frames\":[{\"explicit\":0.1}]}"
```

7. In Redis Insight, open `queue:ws_verified`. The list has one uuid. That uuid is a job id, not the media id.
8. In DBeaver, View Data on `media`. One row, status `pending`. View Data on `jobs`. One row, state `queued`, same workspace.
9. Do not delete the keys by hand unless you are resetting. Do not edit the table cells.
10. Start the worker again: `docker compose start worker`. In this phase the worker only logs that it started, so the id stays on the list until phase 4.

## Done when

- The eight tests pass.
- A cross-workspace read is `404`, not `403`.
- Redis has a list per workspace, not one shared list.
- The provider log shows no `/score` call from this phase.

## Report, then stop

```text
Phase 3 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
