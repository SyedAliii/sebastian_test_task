# Phase 5 — Slow, timeout, and error

Phase 4 must already pass. Do this phase only. Stop at the end.

## Goal

The mode saved by `POST /_control` changes `POST /score`. Timeouts, HTTP `500`, HTTP `429`, and a bad body are different. Every one of them still counts the call. None of them returns usable scores, except `slow` and `ok`, which do.

## Do not

- Do not turn a timeout into scores. That bug belongs to the backend, on purpose, later.
- Do not count `/_control`.
- Do not send a callback after timeout or error, even if the video has more than 30 frames.
- Do not use `time.sleep`. Use `asyncio.sleep`, so one slow call does not freeze the process.

## Read the mode once

After the body is valid, take one store call that both increments the media id and returns a snapshot of `mode`, `delay_ms`, and `error_kind`. Add `begin_score(media_id)` on the repo if `increment_call` cannot return the snapshot. One lock. One media id. Not once per frame.

Use that snapshot for the rest of the request. A later `/_control` must not change this in-flight request.

## Modes

| Snapshot | What `/score` does |
| --- | --- |
| `timeout` | `asyncio.sleep(TIMEOUT_HOLD_SECONDS)`, then `504` `{"detail": "provider timeout"}`. No `frames`. No callback. |
| `error` and `error_kind` `http_500` or missing | `500` `{"detail": "provider error"}`. No callback. |
| `error` and `error_kind` `http_429` | `429` `{"detail": "provider busy"}` and header `Retry-After` set to `RETRY_AFTER_SECONDS`. No callback. |
| `error` and `error_kind` `malformed` | `200` with a bad body: `{"media_id": "<the id>", "frames": [{"explicit": 0.0}]}`. One frame, one label. No callback. |
| `ok` or `slow`, 1 to 30 frames | `asyncio.sleep(delay_ms / 1000)`, then the normal `200` score body. |
| `ok` or `slow`, 31 or more frames | Return `202` immediately. The background task sleeps `delay_ms / 1000`, then posts the signed callback. |

`ok` and `slow` use the same wait. The wait is `delay_ms`. `0` means no wait. Their grader makes a call slow by sending `{"mode": "slow", "delay_ms": 10000}` or any other millisecond value.

Timeout and error ignore `delay_ms`.

## Tests

Add `tests\test_failure_modes.py`. Build the app with `timeout_hold_seconds` of `0.2` so the suite stays fast. The real `.env` stays at `120`.

| Test | Assert |
| --- | --- |
| `test_slow_waits_then_scores` | Mode `slow`, `delay_ms` `200`, one frame. Status `200`. Elapsed time at least `0.15` seconds. All six labels present. Stats is `1`. |
| `test_ok_with_zero_delay_does_not_wait` | Mode `ok`, `delay_ms` `0`. Status `200`. Elapsed under `0.5` seconds. |
| `test_timeout_returns_504_after_hold` | Mode `timeout`, hold `0.2` seconds from `test_settings`. Status `504`. Elapsed at least `0.15` seconds. Body has no `frames`. Stats is `1`. |
| `test_timeout_counts_while_still_open` | Start the score POST with `asyncio.create_task`. Wait until it is in flight by polling `GET /_stats` every `0.01` seconds, up to `1` second, until the id shows `1`. Assert the score task is not done yet. Then await it and assert `504`. This proves the count happens before the hold. |
| `test_timeout_does_not_callback` | 31 frames, mode `timeout`. Status `504`. After `drain()`, the callback route has zero calls. |
| `test_error_defaults_to_500` | Mode `error`, no `error_kind`. Status `500`. Stats is `1`. No callback. |
| `test_error_429_sets_retry_after` | `error_kind` `http_429`. Status `429`. Header `Retry-After` is `2`. Stats is `1`. |
| `test_error_malformed_omits_labels` | `error_kind` `malformed`. Status `200`. `frames` has length 1 and the only label is `explicit`. Stats is `1`. No callback. |
| `test_error_on_long_video_does_not_callback` | 31 frames, mode `error`. Status `500`. Callback mock received nothing. Stats is `1`. |
| `test_slow_long_video_delays_callback` | 31 frames, `slow`, `delay_ms` `200`. The `202` arrives in under `0.15` seconds and the callback route still has zero calls. After `drain()`, the route has one call, total elapsed time is at least `0.15` seconds, and the signature matches. |
| `test_mode_change_does_not_affect_in_flight_call` | Mode `slow`, `delay_ms` `200`, one frame. Start the score POST as a task. Once `/_stats` shows `1`, POST `/_control` `{"mode": "error", "delay_ms": 0}`. Await the score task. It is still `200` with scores, because it uses the snapshot taken at the start. |

Mark the callback route with `respx.mock` exactly as in phase 4, and `await app.state.dispatcher.drain()` before checking callback calls. Wall-clock limits use `time.perf_counter()`. Keep them loose, as written, so a slow laptop does not fail the suite.

`delay_ms` for the long video is passed to `dispatcher.dispatch(..., delay_seconds=delay_ms / 1000)`. The dispatcher's task sleeps first, then sends.

Keep the phase 3 and 4 tests on the default mode `ok` and `delay_ms` `0`. They must still pass without posting to `/_control`.

## How to run

```powershell
python -m pytest
```

## Done when

- Timeout never returns a `frames` list.
- `429`, `500`, and malformed are three different responses, and each increases `calls`.
- A slow direct score waits. A slow long video returns `202` first and waits only inside the callback task.
- Existing sync and async tests still pass.

## Report, then stop

```text
Phase 5 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
