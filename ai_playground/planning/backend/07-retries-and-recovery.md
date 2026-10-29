# Phase 7 — Retries and recovery

Phase 6 is committed and the tests pass. Do this phase only. Stop at the end.

## Goal

A provider failure is not a decision. Timeout, `429`, `500`, and a bad body each wait differently, then stop. The media becomes `held` with `hold_reason` `no_decision`. When a later call succeeds, the parked jobs go back on the queue without an admin.

`SCREENING_MODE=broken` is unchanged. It may still publish on timeout. These retries apply only when mode is `fixed`.

## Do not

- Do not read the provider's `POST /_control`. A successful score is the only signal that the provider is back.
- Do not let an admin approve a `no_decision` row. That stays `409` from phase 4.
- Do not publish when the reply is `malformed`, even if some labels look safe.

## What each reply does

After a failed reply, in one transaction: finish the attempt row, set `jobs.state` to `retry_wait`, set `available_at`, clear the lease, and keep `needs_enqueue` false. The scheduler sets it true when the wait is over. Do not change `media.status` yet. It stays `pending`.

Broken mode keeps its phase 4 behavior. The scheduler runs in both modes. It is not one of the incident bugs.

"Tries" is the total number of provider calls in one round. `attempts_used` already counts this call, because the claim added 1. After a failure:

- `attempts_used` is below the limit for that reply: `retry_wait`, with the wait below.
- `attempts_used` has reached the limit: park.

| Reply | Tries (setting) | Wait after the failed call |
| --- | --- | --- |
| `timeout` | 3 (`RETRY_TIMEOUT_MAX`) | `RETRY_BASE_SECONDS * 2 ** (attempts_used - 1)`: 1 second, then 2, then park |
| `http_429` | 3 (`RETRY_429_MAX`) | The larger of `Retry-After` and `RETRY_429_MIN_SECONDS` (5). Always longer than a `500` wait |
| `http_500` | 2 (`RETRY_500_MAX`) | 1 second, then park |
| `malformed` | 2 (`RETRY_MALFORMED_MAX`) | 1 second, then park. Repeating a bad body rarely helps |

The limit used is the one for the latest reply. Tests set `RETRY_BASE_SECONDS` and `RETRY_429_MIN_SECONDS` to `0`.

To park:

- `jobs.state = parked`
- `needs_enqueue = false`
- `media.status = held`
- `media.hold_reason = no_decision`
- `media.reasons = ["no_decision"]`
- No `screening_decisions` row

`GET /review` does not return this row, because the query requires `hold_reason = review`.

## Scheduler

`scheduler_main.py` stops being an empty sleep. Every `SCHEDULER_INTERVAL_SECONDS` it runs `tick` once.

`tick` is a fixed number of statements, whatever the number of jobs. It never runs one query per job.

1. One `UPDATE` marks every job that is due again, and commits:

```sql
update jobs
set state = 'queued', needs_enqueue = true, lease_owner = null, lease_until = null
where (state = 'retry_wait' and available_at <= now())
   or (state = 'running' and lease_until < now())
   or (state = 'awaiting_callback' and available_at <= now())
```

   Those three cases are a finished backoff, a dead worker, and a late callback. The media stays `pending`.

2. One `SELECT id, workspace_id FROM jobs WHERE needs_enqueue = true`. That also picks up a push that failed at upload time (phase 3), and the jobs released after an outage.
3. One Redis pipeline: `RPUSH` each id onto `queue:{workspace_id}`.
4. If the pipeline succeeded, one `UPDATE jobs SET needs_enqueue = false WHERE id = ANY(:ids)`. If it failed, skip this step. The next tick pushes them again.

Log `system_info` with the count only when it is above 0.

A worker that pops a stale copy of an id loses the claim and skips it. That is harmless, and it is why a duplicate on the list never means a duplicate provider call.

## Probe

While other jobs are still retrying, their next success is enough to detect recovery. A probe is only needed when nothing else would call the provider.

Once every `PROBE_INTERVAL_SECONDS`, if no job is in `queued`, `running`, `retry_wait`, or `awaiting_callback`, take one parked job:

```sql
update jobs
set state = 'queued', attempts_used = 0, needs_enqueue = true, available_at = now()
where id = (
  select id from jobs where state = 'parked' order by updated_at limit 1
)
returning id, workspace_id
```

Also set that job's media back to `pending` with `hold_reason` null, in the same transaction, so `GET /media/{id}` shows it is being screened again. Step 2 of the next tick pushes it.

If the probe fails, it goes through the normal retries and parks again.

When any provider reply is `scored` or a valid callback is saved, the same transaction also runs:

```sql
update jobs
set state = 'queued', attempts_used = 0, needs_enqueue = true, available_at = now()
where state = 'parked'
returning id, workspace_id
```

Then one statement for their media:

```sql
update media
set status = 'pending', hold_reason = null, reasons = '[]', updated_at = now()
where id in (select media_id from jobs where id = any(:released_ids))
  and status = 'held' and hold_reason = 'no_decision'
```

Not one update per id inside Python. The scheduler's next tick pushes the jobs, because `needs_enqueue` is true. No admin click.

## Callback wait

On provider `202`, set `state = awaiting_callback`, `available_at = now() + CALLBACK_DEADLINE_SECONDS`, `lease_owner` null, `lease_until` null. The worker is then free to take another job. The attempt result is `accepted_async`.

A callback that arrives after the deadline is still applied when no provider decision exists. The claim rules do not apply to the callback. The unique provider-decision index stops a second write.

## Tests

File `tests\test_retries.py`. All waits are `0` except one test that checks the `429` wait is longer than the `500` wait.

| Test | Assert |
| --- | --- |
| `test_timeout_then_success_publishes` | First reply timeout, second reply a safe score. End status `published`. One provider decision. |
| `test_three_timeouts_hold` | Three timeouts. Status `held`, `hold_reason` `no_decision`. Not in `GET /review`. |
| `test_429_records_retry_after` | Reply `429` with `Retry-After: 9`. The job `available_at` is about 9 seconds ahead. Status stays `pending`. |
| `test_malformed_does_not_publish` | A `200` body with one label. Status is not `published`. After the second bad body, status is `held` / `no_decision`. |
| `test_500_parks_sooner_than_timeout` | Two `500` replies park the job. A timeout job is not parked after only two failures. |
| `test_callback_deadline_requeues` | Job `awaiting_callback` with `available_at` in the past. `tick` sets it `queued` and the Redis list contains the id. |
| `test_probe_success_releases_parked` | Two jobs parked. A third job then scores successfully. Both parked jobs become `queued` and their media is `pending`. |

## Done when

- Pytest passes, including phase 5 and 6.
- A timeout in `fixed` mode never writes `published`.
- `GET /review` still excludes `no_decision`.

## Report, then stop

```text
Phase 7 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
