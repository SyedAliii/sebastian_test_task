# Phase 8 — Fairness, crash, and the three numbers

Phase 7 must already pass. Do this phase only. Stop at the end.

## Goal

One workspace can submit a burst without freezing the other. A worker can die after the provider answers and the item still does not go live. You can print the three numbers the README asks for.

## Fair pop

Replace the phase 4 pop order. That order always tried `ws_verified` first, which is unfair the other way.

`queues.pop_fair(prefer: str | None) -> tuple[str, str] | None`.

- If `prefer` is `ws_unverified`, `LPOP` that list first, then the other.
- If `prefer` is `ws_verified` or `None`, `LPOP` `ws_verified` first, then the other.
- Return `(workspace_id, job_id)` or `None` when both are empty.
- The worker remembers the workspace it last popped and passes the other one as `prefer` next time.

Two lists with items therefore alternate. Do not use `BLPOP` with a fixed key order. Redis would always drain the first key.

One `LPOP` per attempt. Not one per frame.

## Fairness test

`tests\test_fairness.py`.

Push 10 job ids to `queue:ws_unverified` and 1 job id to `queue:ws_verified`. Call `pop_fair` 4 times, starting with prefer `ws_verified`.

The four workspaces are `ws_verified`, `ws_unverified`, `ws_verified`, `ws_unverified`. The single verified id is not last.

This test does not call the provider. It only checks the lists.

## Crash

`process_one` accepts an optional hook `after_provider_reply`. Tests pass a hook that raises `RuntimeError` after a scored reply and before the save transaction.

The production loop passes no hook.

| Test | Assert |
| --- | --- |
| `test_crash_before_save_does_not_publish` | The hook raises. Media stays `pending`. `screening_decisions` has no row. Job is not `succeeded`. |
| `test_expired_lease_is_picked_again` | Set that job's `lease_until` in the past and `state` `running`. `tick` makes it `queued`. A second `process_one` with a normal provider reply saves one decision. |

In the test docstring, write these two limits in plain sentences:

- The test proves a lost save does not publish the item, and that another attempt can finish it.
- The test does not prove the provider was called only once. The first call already happened. It also does not prove anything about a real disk crash.

When the hook, or any unexpected error, escapes `process_one`, do not try to clean up the job. A real crash cannot clean up either. Only stop the lease refresh task in a `finally`, then log `error_trace` in the worker loop and keep looping.

The job is left `running` with a lease that stops being refreshed. When `lease_until` passes, the scheduler tick moves it back to `queued` and pushes it. That is the same path a killed process takes, so the test covers the real recovery path, not a special one.

## The three numbers

`app\scripts\metrics.py` prints one JSON object. It is a script, not an HTTP route. The grader's route list stays exact.

```json
{"published_unchecked": 0, "provider_calls_per_upload": 0, "oldest_waiting_seconds": 0}
```

The script takes `--since <ISO time>`. Every number below only counts media created at or after that time. The workload script passes its own start time, so earlier manual uploads do not change the result, and the database does not have to be wiped between runs.

One SQL statement for the unchecked count (add `and m.created_at >= :since`):

```sql
select count(*)
from media m
where m.status = 'published'
and not exists (
  select 1 from screening_decisions d
  where d.media_id = m.id and d.source = 'provider'
)
```

One SQL statement for the age, from `db-design.md`: `now() - min(created_at)` for jobs whose state is not `succeeded`, again limited by `since`. When none are waiting, print `0`.

The broken handler publishes on timeout and marks the job `succeeded`, so during an outage its wait age looks low. That low number is a symptom, not good news. Say so in the README next to the numbers.

Provider calls: one query returns the media ids since `since`. One `GET {PROVIDER_BASE_URL}/_stats`. Sum the counts for those ids in Python, then divide by the number of ids. Zero media prints `0`. Do not call `/_stats` once per media id.

`python -m app.scripts.metrics` from `backend` with `.env` loaded.

## Workload script

`app\scripts\workload.py`. This is the repeatable burst. Default size is 200.

The script talks only to HTTP routes and the metrics function. It does not change `SCREENING_MODE`. You switch modes by recreating the containers (see below).

Steps:

1. Record `start` as the current time.
2. `POST` the provider `/_control`: `{"mode": "ok", "delay_ms": 0}`, or `{"mode": "timeout", "delay_ms": 0}` with `--outage`.
3. As `member_u` / `ws_unverified`, post `--videos` videos (default 200). Each has `--frames` frames (default 10) of `{"explicit": 0.1}`, except the last frame of every video is `{"explicit": 0.95}`. In the unverified workspace every one of them must end `blocked`. A published one is a missed last frame.
4. Right after the first video is posted, as `member_v` / `ws_verified`, post one image every 2 seconds, 5 in total, of `{"explicit": 0.1}`.
5. Poll the five images with `GET /media/{id}` every second until none is `pending`, or 120 seconds pass. Record how long each one took.
6. Each second, also count the burst's `pending` media with one SQL `count(*)`, not 200 GETs.
7. Print one line per image: its final status, how long it took, and how many videos were still pending at that moment.
8. Print the metrics JSON for `since=start`. With `--outage`, this is the during-outage sample.
9. With `--outage` only: set the provider back to `ok`, wait until no media since `start` is `pending` or `held` / `no_decision`, or 180 seconds pass, then print the metrics JSON again. This is the after-recovery sample.

The images leaving `pending` while dozens of videos are still waiting is the fairness evidence. In an outage they end `held`, not stuck behind the burst. After recovery they end `published` without an admin.

Before an outage run, set `PROVIDER_HTTP_TIMEOUT_SECONDS=1` for the worker. Otherwise each timeout takes 10 seconds and the run takes a very long time.

Switching modes, from the repo root in PowerShell:

```powershell
$env:SCREENING_MODE = "broken"
$env:PROVIDER_HTTP_TIMEOUT_SECONDS = "1"
docker compose up -d --force-recreate api worker scheduler
```

Use `"fixed"` for the second run. Compose reads both variables through `${SCREENING_MODE:-fixed}` and `${PROVIDER_HTTP_TIMEOUT_SECONDS:-10}`. Add the second one to the compose file in this phase.

Add `tests\test_metrics.py`: insert one `published` media with no provider decision and one with a decision, both after `since`, and one unchecked row before `since`. `published_unchecked` is `1`. Mock `/_stats` with respx.

Phase 9 runs the script by hand four times: broken and fixed, each with and without `--outage`. This phase only has to make the script run and the unit tests pass.

## Logs to check

Run one item through a timeout and then a success. The log contains one correlation id for the API request and another for the worker attempt. The worker lines include `workspace_id`, `media_id`, `job_id`, and `attempt`. A grep for the media id shows the failure and the later success. No line contains `test-secret`.

## Done when

- The fairness test and the crash tests pass.
- `python -m app.scripts.metrics` prints the JSON object.
- The full pytest suite passes.

## Report, then stop

```text
Phase 8 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
