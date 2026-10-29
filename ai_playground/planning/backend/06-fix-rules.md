# Phase 6 — Fix the rules

Phase 5 is committed and its incident tests fail. Do this phase only. Stop at the end.

## Goal

Make every rule in the task hold for upload and generation. Change the default `SCREENING_MODE` to `fixed`. The incident tests pass. The broken path stays behind `SCREENING_MODE=broken` so the before-and-after numbers can be run again later. Do not delete the broken branch.

## The five fixes

| Bug | Fix |
| --- | --- |
| Timeout publishes | `timeout_publishes` returns false when mode is `fixed`. A timeout leaves the job for retry. Do not set `published`. Do not insert a decision. |
| Only 8 frames | `frames_for_provider` returns every frame when mode is `fixed`. |
| Prompts ignored | `POST /media` calls `prompt_refusal` before insert when mode is `fixed`. |
| Second caller scores again | `process_one` claims the job with one update. No row back means return true and do not call the provider. Log `warning` with the job id. |
| Review error looks empty | In fixed mode, the service catches `SQLAlchemyError`, logs `error_trace`, and raises `ReviewUnavailable`. The route turns that into `503` `{"detail": "review queue unavailable"}`. Never `200` with `[]`. |

## Prompt list

`app\domain\prompts.py`. Normalize the text: lowercase, turn hyphens into spaces, collapse repeated spaces.

Return the first matching category name in a list. Empty list means allowed.

| Category | Match |
| --- | --- |
| `minor` | `minor`, `underage`, `child`, `teen`, `schoolgirl`, a number from 1 to 17 followed by `year old`, or a number from 1 to 17 followed by `yo` |
| `sexual_violence` | `rape`, `sexual violence`, `non consensual` |
| `bestiality` | `bestiality` |
| `self_harm` | `self harm`, `suicide` |
| `real_person` | `celebrity`, `real person` |
| `incest` | `incest` |
| `trafficking` | `trafficking` |

`a 16-year-old at the beach` matches `minor`. `two adults on a beach at sunset` matches nothing.

Match whole words with regex word boundaries, so `child` does not match inside an unrelated longer word. A list like this has false positives (`a minor detail`) and misses paraphrases. That is acceptable for the exercise. Write both limits in the README, next to the part 3 answer about production prompt checks.

Add `tests\test_prompts.py`, with no database: `16-year-old`, `16 year old`, `16yo`, `Teen`, `incest`, and `human trafficking` are refused. `two adults on a beach at sunset` and `a 30 year old couple` are allowed.

`422` body is only `{"reasons": ["minor"]}` or more than one category if you find more than one. Do not insert media. Do not push Redis. Do not call the provider.

`SCREENING_MODE=broken` still skips this function, so the old incident can be reproduced.

## Claim

Use the update from `db-design.md`, including the parentheses around the two `or` branches. Set `lease_owner` to `WORKER_ID`, `lease_until` to now plus `LEASE_SECONDS`, add 1 to `attempts_used`, and set `needs_enqueue` false.

While the provider HTTP call is running, a background task every `LEASE_SECONDS / 3` runs:

```sql
update jobs
set lease_until = now() + make_interval(secs => :lease_seconds)
where id = :job_id and lease_owner = :worker and state = 'running'
```

Cancel that task in a `finally` after the call returns. One update per refresh, not one per frame.

The save transaction also requires `lease_owner = :worker`. If a late worker lost the lease, it does not write.

## Callback and scores

Unchanged from phase 4, except `decide` now sees every frame the provider returned. The provider returns every label. If the reply is `malformed`, do not call `decide`. Leave that to phase 7's retry. In this phase a malformed reply must not publish. Set nothing to `published`. Leaving it `pending` is enough until phase 7.

A usable reply still saves the decision, the media status, and `jobs.state = 'succeeded'` in one transaction.

`explicit` below 0.8 does not hold and does not block by itself. `0.8` on a prohibited label blocks. `0.5` holds. `0.79` holds. `0.8` does not hold.

## Review

`GET /review` returns only `hold_reason = review`. A database error is `503`. A member is `403`. An empty admin list is `200` and `[]`, and that is the only empty success.

Approve and reject stay as in phase 4.

## Tests

The phase 5 file passes with `screening_mode="fixed"`. Change the fixture in `test_incident.py` to `fixed`.

Add `tests\test_rules.py`:

| Test | Assert |
| --- | --- |
| `test_explicit_verified_publishes` | `explicit` 0.9, `ws_verified`, status `published` |
| `test_explicit_unverified_blocks` | `explicit` 0.9, `ws_unverified`, status `blocked` |
| `test_explicit_0_6_does_not_hold` | `explicit` 0.6, either workspace, `published` |
| `test_minor_0_8_blocks_verified` | `minor` 0.8 in `ws_verified` is `blocked` |
| `test_incest_prompt_is_422` | Prompt `incest`, no row |
| `test_upload_has_no_prompt_check` | An upload with no prompt and a safe frame is `202` |
| `test_callback_with_good_signature_blocks` | Build the raw bytes the same way as the provider (`sort_keys`, compact separators). Sign them. A 9th-frame `explicit` 0.95 on an unverified item ends `blocked`. |
| `test_second_callback_does_not_change_status` | A second valid callback returns `200` and does not add a second provider decision. |
| `test_broken_mode_still_publishes_on_timeout` | One test with `screening_mode="broken"` still sees a timeout become `published`. This keeps the incident reproducible. |

## How to run

```powershell
python -m pytest | Out-File -Encoding ascii evidence\fixed-pytest.txt
```

The exit code must be 0. If `test_incident.py` still fails, the fix is incomplete. Do not weaken the assertion.

## Commit

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
git add backend
git commit -m "Fail closed when screening has no decision and score every frame."
```

## Done when

- `evidence\fixed-pytest.txt` shows the tests passed.
- Default `SCREENING_MODE` in `.env.example` is `fixed`.
- `git log -2 --oneline` shows the failing-test commit and then this fix.

## Report, then stop

```text
Phase 6 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
Commit: <git log -1 --oneline>
```
