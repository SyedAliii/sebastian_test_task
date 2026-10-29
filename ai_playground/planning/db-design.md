# Database design

Postgres stores workspaces, users, media, and the proof that an item was screened. It is also the source of truth for who owns a job right now. Redis holds the queue of job ids. The fake provider stores its own mode and call counts. A refused prompt is not stored: the API returns `422` and nothing is inserted.

A finished job is not proof of screening. `jobs.state = succeeded` only means the worker finished. `media.status = published` is allowed only when a provider decision row exists, or when an admin approves a gray-zone hold that already has one.

## What is not in Postgres

| Data | Where it lives |
| --- | --- |
| Ready job ids, one list per workspace | Redis |
| Provider mode (`ok`, `slow`, `timeout`, `error`) and `delay_ms` | Provider process |
| Call count per media id (`GET /_stats`) | Provider process |

Workers take from the workspace lists in turn. That keeps 200 videos in one workspace from stopping the other workspace's images.

Redis only says “this job may be ready.” A Redis entry can be delivered twice, so a worker must claim the job in Postgres before it calls the provider. See `jobs`.

## Tables

### `workspaces`

Seeded on startup. The API never creates these.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text, primary key | `ws_verified`, `ws_unverified` |
| `verified` | boolean, not null | Decides whether `explicit` ≥ 0.8 may be published |

### `users`

Seeded on startup. The request headers must match a row: `X-User-Id` plus `X-Workspace-Id`. A user belongs to one workspace.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text, primary key | `admin_v`, `member_v`, `admin_u`, `member_u` |
| `workspace_id` | text, not null, foreign key | |
| `role` | text, not null | `admin` or `member` |

Missing headers, or a user who does not belong to the given workspace, get `401`. Document that choice in the README.

### `media`

One row per accepted upload or generation. This is the row `GET /media/{id}` and `GET /review` read.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid, primary key | Returned as `id` |
| `workspace_id` | text, not null, foreign key | Isolation: every read filters on this |
| `submitted_by` | text, not null, foreign key | The user in the headers |
| `type` | text, not null | `image` or `video` |
| `source` | text, not null | `upload` or `generation` |
| `prompt` | text, null | Required for `generation`, null for `upload`. Checked before insert |
| `frames` | jsonb, not null | The submitted frames. Exactly one object for an image, one per second for a video. This is the answer key sent to the provider, not the decision |
| `frame_count` | int, not null | Copied from `frames`. Longer than 30 means the provider answers through the callback |
| `status` | text, not null | `pending`, `published`, `held`, or `blocked` |
| `hold_reason` | text, null | Only when `status = held`: `review` or `no_decision` |
| `reasons` | jsonb, not null, default `[]` | Returned by `GET /media/{id}` |
| `created_at` | timestamptz, not null | |
| `updated_at` | timestamptz, not null | |

`hold_reason` splits the two meanings of `held`:

- `review` — a prohibited score from 0.5 up to 0.8. `GET /review` returns these. The workspace admin approves or rejects them.
- `no_decision` — the provider timed out, returned an error, or returned a body we could not use, and the retry limit ran out. Not in the review list. An admin cannot approve it. Once the provider works again it is screened automatically.

Indexes: `(workspace_id, status)`, and `(workspace_id) where status = 'held' and hold_reason = 'review'` for `GET /review`.

### `screening_decisions`

The proof that something actually judged the item. Publishing checks this table, not the job.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid, primary key | |
| `media_id` | uuid, not null, foreign key | |
| `source` | text, not null | `provider` or `admin` |
| `scores` | jsonb, null | The provider's scores: one object per frame, every label present. Null for an admin action |
| `outcome` | text, not null | `published`, `held`, or `blocked` |
| `reasons` | jsonb, not null | |
| `decided_by` | text, null | The admin's user id. Null for the provider |
| `created_at` | timestamptz, not null | |

At most one provider decision and one admin decision per item:

```sql
create unique index one_provider_decision
  on screening_decisions (media_id)
  where source = 'provider';

create unique index one_admin_decision
  on screening_decisions (media_id)
  where source = 'admin';
```

An admin approve or reject is allowed only when a provider row exists and `media.hold_reason = review`. That keeps an outage hold from being approved unchecked.

The decision row, the `media.status` update, and the job's `succeeded` state are one transaction. If the worker dies after the provider responds and before that transaction commits, none of it is saved. The media stays `pending` and is not published. The next attempt may call the provider again. The local kill proves we do not publish and that the job is picked up again. It does not prove the provider was billed once.

### `jobs`

One screening job per media item. Job state and media status are different facts.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid, primary key | |
| `media_id` | uuid, not null, unique, foreign key | One job per item |
| `workspace_id` | text, not null | Copied so the scheduler and log lines do not need a join |
| `state` | text, not null | See below |
| `attempts_used` | int, not null, default 0 | Provider tries in the current round. Stops retries |
| `available_at` | timestamptz, not null | Earliest time the job may run again. For `awaiting_callback`, the callback deadline |
| `lease_owner` | text, null | The worker id that holds the job |
| `lease_until` | timestamptz, null | When the claim expires if that worker stops refreshing it |
| `needs_enqueue` | boolean, not null, default true | The scheduler pushes the job id to Redis only when this is true, then sets it false. A retry sets it true again. This stops the same id being appended on every scheduler tick. |
| `created_at` | timestamptz, not null | |
| `updated_at` | timestamptz, not null | |

| `state` | Meaning |
| --- | --- |
| `queued` | Ready to run |
| `running` | A worker holds the lease and is calling the provider |
| `awaiting_callback` | Video longer than 30 frames. The provider returned `202` and will post the result |
| `retry_wait` | A try failed. Waiting for its backoff |
| `parked` | Retry limit reached. Media is `held` / `no_decision` |
| `succeeded` | A provider decision was saved |

A worker claims a job with one conditional update:

```sql
update jobs
set state = 'running',
    lease_owner = :worker,
    lease_until = now() + interval '30 seconds',
    attempts_used = attempts_used + 1,
    needs_enqueue = false
where id = :job_id
  and (
    (state in ('queued', 'retry_wait') and available_at <= now())
    or (state = 'running' and lease_until < now())
  )
returning *;
```

The parentheses matter. `and` binds tighter than `or`, so without them a claim for one id could update a different job whose lease had expired.

No row back means another worker owns the job, or it is finished. The second worker does not call the provider. While the provider call is in flight, the worker extends `lease_until`. A redelivered Redis entry therefore cannot start a second call while the first is still running.

A worker whose lease expired can still come back and try to save. The final transaction checks `lease_owner = :worker`, and the unique provider-decision index refuses a second decision.

A scheduler loop moves due jobs back onto their workspace's Redis list. That covers jobs waiting for `available_at`, `running` jobs with an expired lease (a dead worker), and `awaiting_callback` jobs whose deadline passed without a callback.

Recovering an outage: the scheduler puts one `parked` job back on the queue as a probe. When that call succeeds, the same database transaction sets every remaining `parked` job to `queued` with `attempts_used = 0` and `needs_enqueue = true`. No admin step. Nothing reads `POST /_control`. A successful score is how the app learns the provider is back.

Age of the oldest waiting job:

```sql
select now() - min(created_at)
from jobs
where state <> 'succeeded';
```

### `attempts`

One row each time a worker calls the provider. This is the trail for a workspace, media item, job, and attempt through failure and recovery.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid, primary key | |
| `job_id` | uuid, not null, foreign key | |
| `media_id` | uuid, not null | |
| `workspace_id` | text, not null | |
| `n` | int, not null | 1, 2, 3, … across the whole life of the job |
| `worker_id` | text, not null | |
| `started_at` | timestamptz, not null | |
| `finished_at` | timestamptz, null | Null if the worker died mid-attempt |
| `result` | text, null | `success`, `accepted_async`, `timeout`, `http_429`, `http_500`, `malformed` |
| `detail` | text, null | Short error text for the log |

Unique `(job_id, n)`.

A worker that loses the claim does not write an attempt. It did not call the provider. It writes a log line with the same ids instead.

Each failure gets its own backoff, and all of them share a retry limit:

| `result` | Retry |
| --- | --- |
| `timeout` | Backoff, then retry |
| `http_429` | Longer backoff, or the provider's `Retry-After` |
| `http_500` | Backoff, fewer tries |
| `malformed` | One short retry, then park |

After the limit, the job is `parked` and the media is `held` / `no_decision`.

## How a row moves

**Accepted upload or allowed prompt.** Insert `media` as `pending` and a `queued` job in one transaction, then push the job id to Redis. Return `202`. If the push fails, the scheduler finds the job by `available_at`.

**Provider reply.** A body is usable only if it has the same number of frames as `media.frame_count` and every label in every frame. The provider always returns every label. A missing label or a short list is `malformed`, not a score of 0. The 0 rule applies to labels left out of the submitted JSON, before it is sent.

A usable reply is saved, with the new media status and the job's `succeeded` state, in one transaction.

| Worst score | Verified workspace | Unverified workspace |
| --- | --- | --- |
| Prohibited label ≥ 0.8 | `blocked` | `blocked` |
| Prohibited label from 0.5 up to 0.8, and nothing blocked | `held` / `review` | `held` / `review` |
| `explicit` ≥ 0.8, and nothing above applies | `published` | `blocked` |
| Otherwise | `published` | `published` |

`blocked` beats `held`, and `held` beats `published`. One frame at 0.8 or above blocks the whole video.

**Video longer than 30 frames.** The provider returns `202`. The worker writes an `accepted_async` attempt, sets the job to `awaiting_callback`, sets `available_at` to the callback deadline, and releases the lease.

**Callback.** A bad signature returns `401` and writes nothing. A valid callback is checked the same way as a direct reply, then saved in the same transaction. A callback that arrives after its deadline is still used if the item has no provider decision yet. A second valid callback for an item that already has one returns `200` and writes nothing.

**No decision.** While retries remain, the media stays `pending`. After the limit, it becomes `held` / `no_decision` and the job is `parked`. When the provider recovers, it goes back to `queued` and the media is decided normally.

**Admin.** Approve sets `published`. Reject sets `blocked`. Both insert an `admin` decision. A member's call returns `403` and writes nothing. Another workspace's id returns `404`. An item that is not `held` / `review` returns `409` and writes nothing.

## Counts the README needs

| Number | Query |
| --- | --- |
| Published unchecked | `media.status = published` and no `screening_decisions` row with `source = provider` |
| Provider calls per upload | `GET /_stats` on the provider, divided by uploads. `attempts` is our record of a try, not the bill |
| Oldest waiting job | The query in the `jobs` section |

Run the same workload once on the broken handler and once on the fix. Capture the three numbers during the outage and again after recovery. After recovery the oldest wait falls, which hides the bug if that is the only sample.

The broken handler publishes a timed-out item without writing a provider decision. That is what makes “published unchecked” countable.

## Seed

| `workspaces.id` | `verified` | Users |
| --- | --- | --- |
| `ws_verified` | true | `admin_v` admin, `member_v` member |
| `ws_unverified` | false | `admin_u` admin, `member_u` member |
