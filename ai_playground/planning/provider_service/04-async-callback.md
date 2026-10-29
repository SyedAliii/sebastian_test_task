# Phase 4 — Long video callback

Phase 3 must already pass. Do this phase only. Stop at the end.

## Goal

A valid score with more than 30 frames returns `202` (accepted) and later posts the filled scores to the callback URL. The raw body is signed. 30 frames or fewer stay on the phase 3 path: `200` and no callback.

## Do not

- Do not wait for the callback before returning `202`.
- Do not sign with a hash of a new JSON dump. Sign the bytes you actually send.
- Do not retry a failed callback inside the provider. Log the error and stop. The count stays increased.
- Do not drop frames after the 8th.
- Do not look at prompts.

## Replace the phase 3 branch

Delete the temporary `422` for 31 frames. Update `test_thirty_one_frames_not_yet` so it no longer expects `422`.

If the body is valid and has more than 30 frames, `ScoreService.score` does this:

1. `increment_call(media_id)` once.
2. `normalize_frames` on the full list.
3. Hand the payload to the callback dispatcher. This only schedules the work. It does not wait for it.
4. Return `202` with:

```json
{"media_id": "demo-long", "status": "accepted"}
```

Do not sleep on `delay_ms` in this phase. Phase 5 adds the wait.

## Callback dispatcher

`app\services\callback_dispatcher.py` — class `CallbackDispatcher(settings, sender)`.

- `dispatch(media_id, payload, delay_seconds=0.0)` builds the raw bytes and the signature, then starts `asyncio.create_task(...)` for the send. It is a normal method, not `async`, and it returns immediately.
- It keeps every task in a `set` and removes it in a `done` callback. Without that set Python can garbage-collect a running task.
- `async def drain()` awaits every task still in the set. Tests call this to wait for callbacks. Production code does not call it.

`create_app()` builds one dispatcher and puts it on `app.state.dispatcher`. `get_score_service` passes it to `ScoreService`.

Do not use FastAPI `BackgroundTasks`. The httpx test client runs those before it returns the response, so a test could not tell whether `202` came back first.

## Callback

URL: `settings.callback_url`, which is `CALLBACK_BASE_URL` plus `CALLBACK_PATH`.

Default local values:

- `CALLBACK_BASE_URL=http://127.0.0.1:9000`
- `CALLBACK_PATH=/provider/callback`

Body, same shape as the sync `200`:

```json
{"media_id": "demo-long", "frames": [{"minor": 0.0, "sexual_violence": 0.0, "bestiality": 0.0, "self_harm": 0.0, "real_person": 0.0, "explicit": 0.02}]}
```

Build the bytes once:

```python
raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
```

Send `content=raw` and header `Content-Type: application/json`. Do not pass a dict to the HTTP client, or the signed bytes will not match the sent bytes.

Header:

```text
X-Signature: <lowercase hex>
```

`app\services\signature.py`:

```python
def sign_body(raw: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
```

No `sha256=` prefix. Hex is lowercase, which is what `hexdigest()` already returns.

`app\services\callback_client.py` has `async def send_callback(url, raw, signature, media_id)`. It creates an `httpx.AsyncClient` with a 5 second timeout inside the function, posts once, and closes the client. On any HTTP error or a non-200 response, log `media_id` and the error. Never raise out of the task. Log success too: `media_id`, outcome `callback_sent`, and the status code.

Log one info line when the `202` is returned: `media_id`, `frame_count`, outcome `accepted_async`.

## Tests

Add `tests\test_async_callback.py`.

Use `respx` to catch the outbound POST. The `test_settings` fixture from phase 1 already points at `http://callback.test` and `/provider/callback`. Do not call the real network.

Use `respx.mock` as a context manager or decorator, with a route for `POST http://callback.test/provider/callback`. respx only patches real network transports, so the test client's `ASGITransport` still reaches the app.

Each test follows the same order:

1. POST `/score` and check the `202`.
2. `await app.state.dispatcher.drain()`.
3. Check the respx route: `route.call_count`, and `route.calls[0].request.content` for the raw bytes and `.headers["X-Signature"]` for the signature.

Never use `asyncio.sleep` to wait for a callback.

| Test | Assert |
| --- | --- |
| `test_long_video_returns_202` | 31 frames. Status `202`. Body is `media_id` and `status` `accepted`. No `frames` in that body. |
| `test_long_video_posts_signed_callback` | The mocked callback received one POST. `json.loads` of the raw body has 31 frames. Every frame has all six labels. `X-Signature` equals `sign_body(raw_bytes, "test-secret")`. |
| `test_callback_uses_sent_bytes` | Change one byte of the captured body and sign it. That hex is different from the header. |
| `test_thirty_frames_does_not_callback` | 30 frames returns `200`. The mock received zero calls. |
| `test_long_video_is_counted` | One 31-frame post. Stats for that id is `1`. |
| `test_second_long_call_counts_again` | Two 31-frame posts, same id. Stats is `2`. Two callbacks were sent. |
| `test_callback_failure_still_counts` | Mock the callback to return `500`. The score request is still `202`. After `drain()`, stats is `1`. Nothing raises. |
| `test_callback_network_error_does_not_raise` | Mock the callback route with `side_effect=httpx.ConnectError`. Score is `202`. `drain()` finishes without raising. |
| `test_returns_202_before_callback_finishes` | Mock the callback with a side effect that awaits an `asyncio.Event` the test controls. The `202` arrives while the event is still unset, which proves the response did not wait. Then set the event and `drain()`. |
| `test_sign_body_known_value` | Unit test, no HTTP: `sign_body(b'{"a":1}', "test-secret")` equals the hex from `hmac.new(b"test-secret", b'{"a":1}', hashlib.sha256).hexdigest()`, and it is 64 lowercase hex characters. |

## How to run

```powershell
python -m pytest tests\test_async_callback.py tests\test_sync_score.py
```

Then the full file:

```powershell
python -m pytest
```

## Done when

- 31 frames is `202` plus one signed callback.
- 30 frames is `200` and no callback.
- A wrong body would not match the signature. The test proves that.
- A failed callback does not reduce the call count.

## Report, then stop

```text
Phase 4 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
