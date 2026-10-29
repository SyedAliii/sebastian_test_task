# Phase 3 — Direct score

Phase 2 must already pass. Do this phase only. Stop at the end.

## Goal

`POST /score` accepts 1 to 30 frames, fills every label, echoes the scores, and counts the call. Mode is still treated as `ok` for the response in this phase. Timeout and error come in phase 5. If the saved mode is not `ok`, still return the normal `200` for 1 to 30 frames for now. Do not read `delay_ms` yet.

## Do not

- Do not drop frames after the 8th. Return every frame that was sent.
- Do not refuse prompts. Ignore a `prompt` field if it is present.
- Do not call the callback URL. 30 frames or fewer never start a callback.
- Do not dedupe. Two valid posts for the same `media_id` make `calls` equal `2`.
- Do not call the repo once per frame.

## Request

```json
{"media_id": "demo-1", "frames": [{"explicit": 0.02}]}
```

Rules:

- `media_id` is a non-empty string. Do not require it to be a UUID.
- `frames` has at least 1 object.
- This phase only defines the success path up to 30 frames. If `frames` has 31 or more, return `422` with `{"detail": "long videos are added in the next phase"}`. Do not count that request. Phase 4 replaces this branch.
- Each score is a number from 0 to 1 inclusive. A string, a missing frame object, or a number outside that range is `422`. Do not count it.
- Unknown label names are ignored.
- A missing known label means `0`.

Known labels, in this order:

1. `minor`
2. `sexual_violence`
3. `bestiality`
4. `self_harm`
5. `real_person`
6. `explicit`

Put the tuple in `app\domain\labels.py` as `LABELS`. Services import it from there. Routes do not copy the list.

## Success body

`200`:

```json
{
  "media_id": "demo-1",
  "frames": [
    {
      "minor": 0.0,
      "sexual_violence": 0.0,
      "bestiality": 0.0,
      "self_harm": 0.0,
      "real_person": 0.0,
      "explicit": 0.02
    }
  ]
}
```

Keep the caller's numbers. `0.1` stays `0.1`. Fill only the labels they left out.

## Order inside the request

1. FastAPI validates the body with `ScoreRequest` in `app\domain\schemas.py`. A bad body is `422` before any code of ours runs, so the store is not touched.
2. The route calls `ScoreService.score(request)` once.
3. The service checks the frame count. More than 30 returns a result that the route turns into the temporary `422`. The store is not touched.
4. The service calls `store.increment_call(media_id)` once.
5. The service calls the pure function `normalize_frames(frames) -> list[dict]` in `app\services\scoring.py`. It loops in memory over frames already loaded. It does not call the repo.
6. The service returns a small result object, for example a dataclass with `status_code` and `body`. The route returns it as JSON.

Files:

- `app\services\score_service.py` — class `ScoreService(store, settings)`. This is the only place `/score` logic lives. Phases 4 and 5 extend this class.
- `app\api\deps.py` — add `get_score_service(request)`. Build it from `app.state`. Do not create a new store per request.
- `app\api\routes\score.py` — the route. No `if` on modes, no loops, no dict updates.

Schema details for `ScoreRequest`:

- `media_id: str` with `min_length=1`.
- `frames: list[dict[str, float]]` with `min_length=1`.
- A validator that refuses any value below 0 or above 1. Integers such as `0` and `1` are fine. Refuse `true` and `false`: pydantic turns them into `1.0` and `0.0`. Use a `field_validator("frames", mode="before")` so the check sees the raw values before that conversion.
- Ignore extra top-level fields such as `prompt`, `type`, or `source`.

## Log

After a counted call, log one line at info with `media_id`, `frame_count`, and outcome `scored`. Use the standard library logger named `provider`. Do not log the whole frame list at info.

## Tests

Add `tests\test_sync_score.py`.

| Test | Assert |
| --- | --- |
| `test_score_fills_missing_labels` | Input one frame `{"explicit": 0.02}`. Status `200`. That frame has all six labels. `explicit` is `0.02`. The other five are `0`. |
| `test_score_keeps_every_frame` | Input 9 frames. Only frame index 8 has `explicit` `0.95`. Response has 9 frames. Frame 8 still has `0.95`. |
| `test_score_counts_each_call` | Two posts with media id `demo-1`. `GET /_stats` is `{"calls": {"demo-1": 2}}`. |
| `test_score_counts_separate_ids` | One post for `a` and one for `b`. Stats has `a: 1` and `b: 1`. |
| `test_invalid_body_does_not_count` | POST `{"media_id": "demo-1", "frames": []}`. Status `422`. Stats stay `{}`. |
| `test_score_out_of_range_does_not_count` | A frame with `explicit` `1.2` is `422`. Stats stay `{}`. |
| `test_score_bool_does_not_count` | A frame with `explicit` `true` is `422`. Stats stay `{}`. |
| `test_unknown_label_is_dropped` | Input `{"explicit": 0.2, "extra": 0.9}`. Response frame has the six labels only. `explicit` is `0.2`. |
| `test_thirty_frames_is_sync` | 30 frames returns `200` and 30 filled frames. Stats count is `1`. |
| `test_thirty_one_frames_not_yet` | 31 frames returns `422` and does not count. Phase 4 changes this test. |
| `test_prompt_field_is_ignored` | Body includes `"prompt": "a 16-year-old"`. Status `200`. This service does not refuse prompts. |
| `test_normalize_frames_is_pure` | Unit test, no HTTP: `normalize_frames([{"minor": 0.6}])` returns one dict with six labels and `minor` `0.6`. The input list is unchanged. |

Compare scores as numbers, not as JSON text.

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
.\.venv\Scripts\Activate.ps1
python -m pytest
```

## Done when

- The new tests pass, and phase 1 and 2 still pass.
- A 9-frame video is not cut to 8.
- A second call increases the same media id to `2`.

## Report, then stop

```text
Phase 3 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
