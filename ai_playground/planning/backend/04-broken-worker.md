# Phase 4 — Broken worker

Phase 3 must already pass. Do this phase only. Stop at the end.

## Goal

The worker pulls a job and calls the provider. The handler is the incident, on purpose. `SCREENING_MODE=broken` is the default for this phase.

These five bugs must be present at the end of the phase:

1. A provider timeout is saved as `published`. No decision row is written.
2. Only the first 8 frames are sent to the provider.
3. A generation prompt is never checked. `16-year-old` still returns `202` (accepted).
4. The worker does not claim the job. A second worker can call the provider for the same id.
5. `GET /review` catches any error and returns `200` with `[]`.

Do not fix any of these. Phase 6 fixes them. If you notice one and remove it, put it back.

## Do not

- Do not add the lease update.
- Do not refuse prompts.
- Do not send frame 9 or later.
- Do not treat a timeout as `held`.

## Provider client

`app\clients\provider_client.py` is the only file that calls the provider.

`post_score(media_id, frames) -> ProviderReply`.

- URL is `{PROVIDER_BASE_URL}/score`.
- Body is `{"media_id", "frames"}` only. Do not send the prompt.
- Timeout is `PROVIDER_HTTP_TIMEOUT_SECONDS`.
- On `httpx.TimeoutException`, return a reply with `kind="timeout"`. Do not turn that into scores.
- On status `200`, return `kind="scored"` and the JSON.
- On status `202`, return `kind="accepted"` and no frames.
- On status `429`, return `kind="http_429"` and the `Retry-After` header if it is an integer.
- On status `500` or `504`, return `kind="http_500"` for 500 and `kind="timeout"` for 504.
- On status `200` whose `frames` is missing, not a list, a different length from the frames that were sent, or a frame missing any of the six labels, return `kind="malformed"`. Compare with the length of the list passed to `post_score`, not with `media.frame_count`. In broken mode that list has 8 items, and the provider correctly echoes 8.
- Any other status, or a connection error, returns `kind="http_500"`.
- Log `api_request_out` before the call and `api_response_in` after, with the elapsed time. Do not log the secret.

Use one httpx client per call, created inside the function, so tests can mock it with respx.

## Broken policy

`app\domain\policy.py`:

```python
def frames_for_provider(frames: list, mode: str) -> list:
    if mode == "broken":
        return frames[:8]
    return list(frames)
```

```python
def timeout_publishes(mode: str) -> bool:
    return mode == "broken"
```

`prompt_refusal(prompt) -> list[str]` exists but the route does not call it while mode is `broken`. Leave the function returning `[]` for now. Phase 6 fills it in. Do not call it from `POST /media` in this phase.

## Worker

`app\services\worker_service.py` has `process_one(session_factory, queues, provider, settings) -> bool`.

It takes the session factory, not one session, and opens a short session for each step. Two `process_one` calls running at the same time then use two connections, the same as two real workers. Do not hold a transaction open while the provider call is in flight.

`worker_main.py` loops: call `process_one`, and if it returns false, sleep 0.2 seconds.

`process_one` while mode is `broken`:

1. `LPOP` `queue:ws_verified`. If empty, `LPOP` `queue:ws_unverified`. If both empty, return false.
2. Load the job and its media in one query (join). If the job is missing, return true and do nothing else.
3. Do not update `lease_owner`. Do not skip the job when its state is already `succeeded`. This is bug 4. A second copy of the same id on the list must call the provider again.
4. Send `frames_for_provider(media.frames, mode)`.
5. If the reply is `timeout` and `timeout_publishes`: set `media.status` to `published`, `reasons` to `[]`, job `state` to `succeeded`. Do not insert `screening_decisions`. This is bug 1.
6. If the reply is `scored`: insert a provider decision and set the media status with the real score rules below, using only the frames the provider returned. Because you only sent 8, a hit on frame 9 is invisible. This is bug 2.
7. If the reply is `accepted` (the provider's `202` for more than 30 frames): set the job `awaiting_callback` and `available_at` to now plus `CALLBACK_DEADLINE_SECONDS`. The callback route finishes it.
8. Any other reply: leave the media `pending`, set the job `retry_wait`, `available_at` now plus 1 second, and `needs_enqueue` false. Do not push it back to Redis here. Phase 7's scheduler does that. An immediate push would call a down provider in a tight loop. Until phase 7 these jobs simply wait. Do not publish them.

The real score rules, used only for a `scored` reply:

- Prohibited label 0.8 or more: `blocked`.
- Else prohibited label from 0.5 up to 0.8: `held` and `hold_reason` `review`.
- Else `explicit` 0.8 or more in an unverified workspace: `blocked`.
- Else `explicit` 0.8 or more in a verified workspace: `published`.
- Else `published`.
- `blocked` beats `held`.

Put those rules in `app\domain\decide.py` as a pure function `decide(frames, verified) -> Decision`. The worker calls it. The route does not. Unit-test this function in this phase. It is not one of the bugs. The bug is which frames reach it.

Write the decision, the media update, and the job update in one transaction. A timeout publish is the same transaction, but without a decision row.

Also insert one `attempts` row for every provider call, before the call, with `finished_at` null. After the reply, set `finished_at`, `result`, and `detail`. A worker that dies mid-call leaves `finished_at` null, which is the evidence.

`n` counts every attempt in the job's life. Do not use `attempts_used` for it: phase 7 resets `attempts_used` to 0 after an outage, and the unique `(job_id, n)` would then reject the next row. Compute `n` inside the insert:

```sql
insert into attempts (id, job_id, media_id, workspace_id, n, worker_id, started_at)
select :id, :job_id, :media_id, :workspace_id, coalesce(max(n), 0) + 1, :worker, now()
from attempts where job_id = :job_id
```

In broken mode, add 1 to `attempts_used` in the save transaction. In fixed mode, the claim already does it.

## Review route, broken

`GET /review` requires an admin of that workspace. A member gets `403` and `{"detail": "admin only"}`.

The admin path:

The route calls `review_service.list_held(workspace_id)`. In broken mode the service does:

```python
try:
    return await media_repo.list_review(session, workspace_id)
except SQLAlchemyError:
    return []
```

Phase 6 replaces the `except` with a domain error that the route turns into `503`.

`list_review` is one query: this workspace, `status = held`, `hold_reason = review`. It returns `id`, `status`, `reasons`. No second query per row.

Returning `[]` on any exception is bug 5. Keep it.

`POST /review/{id}/approve` and `reject` work for real in this phase, so phase 5 can tell a member `403` from a missing route:

- Admin, same workspace, `hold_reason = review`: approve sets `published`, reject sets `blocked`, `hold_reason` null, and inserts an admin decision. `200` `{"id", "status"}`.
- Member: `403`.
- Other workspace or unknown id: `404`.
- Not a `review` hold: `409`.

One transaction. The media update includes `and hold_reason = 'review'` so two admins cannot both approve.

## Callback route, correct already

`POST /provider/callback` in `app\api\routes\callback.py`:

1. Read `await request.body()` once. Do not parse first.
2. Compute the hex HMAC with `PROVIDER_HMAC_SECRET` and compare with `hmac.compare_digest` to the `X-Signature` header.
3. Missing or different: `401` and `{"detail": "bad signature"}`. Log `webhook_fail`. Write nothing.
4. Matching: parse the raw bytes as JSON. Load the media and its workspace in one join.
   - Unknown `media_id`, or not a uuid: `404`. Write nothing.
   - A provider decision already exists: `200` and write nothing.
   - Frames missing, a count different from `media.frame_count`, or a frame missing any of the six labels: `400` `{"detail": "malformed callback"}`. Write nothing. The job stays `awaiting_callback`, and the deadline in phase 7 retries it.
5. Otherwise run `decide` on the callback frames. In one transaction, insert the provider decision, update the media, and set the job `succeeded`. Log `webhook_in`.

A long video is always scored through this route, in both modes. The broken 8-frame cut applies to the direct path only, because the worker sends the cut list to the provider. Sending 8 frames means the provider answers directly, so a cut video never reaches the callback.

The signature check is not a bug. The incident does not break it. Tests for a bad signature should pass in the next phase. Do not weaken it.

## Tests that must pass in this phase

These tests lock the bugs in. They are not the safety tests. Phase 5 adds the safety tests, and those must fail.

| Test | Assert |
| --- | --- |
| `test_decide_blocks_at_0_8` | Pure function. `minor` 0.8 is blocked. `minor` 0.5 is review. `minor` 0.49 is published when nothing else is set. |
| `test_broken_sends_only_eight_frames` | respx records the body. A 9-frame video sends 8 frames. |
| `test_broken_timeout_publishes` | respx raises `httpx.TimeoutException`. Media becomes `published`. `screening_decisions` has no row. |
| `test_bad_signature_is_401` | Callback with no header is `401`. Media stays `pending`. |
| `test_member_cannot_approve` | Seed a `review` hold directly in the repo. `member_v` gets `403`. |

Default settings in these tests: `screening_mode="broken"`.

## Done when

- The five bug behaviors are still in the code.
- The tests in the table pass.
- `POST /media` with prompt `a 16-year-old` still returns `202`.

## Report, then stop

```text
Phase 4 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
Bugs still present: timeout publishes, 8 frames, no prompt check, no claim, review errors return []
```
