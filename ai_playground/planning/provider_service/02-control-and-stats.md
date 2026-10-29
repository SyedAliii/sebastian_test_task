# Phase 2 — Mode and invoice

Phase 1 must already pass. Do this phase only. Stop at the end.

## Goal

`POST /_control` saves the provider mode in memory. `GET /_stats` returns the call map. Scoring is still not implemented, so the map stays empty. Control calls must not create media ids.

## Do not

- Do not add `POST /score`.
- Do not add a database.
- Do not count `/_control` or `/_stats` as scoring calls.

## Behavior

`POST /_control` accepts:

```json
{"mode": "ok", "delay_ms": 0}
```

- `mode` must be `ok`, `slow`, `timeout`, or `error`. Anything else is `422`. Use a pydantic `Literal` and let FastAPI return its normal `422` validation body. Do not write a custom error handler.
- `delay_ms` is an integer `>= 0`. If it is missing, save `0`. If it is negative or not an integer, return `422`.
- Optional `error_kind`: `http_500`, `http_429`, or `malformed`. If it is missing, store `http_500`. If it is present and not one of those three, return `422`. Store it even when mode is not `error`. It is only used later, in phase 5.
- Success is `200` and the saved values:

```json
{"mode": "ok", "delay_ms": 0, "error_kind": "http_500"}
```

Their grader may send only `mode` and `delay_ms`. That must work.

`GET /_stats` always returns `200`:

```json
{"calls": {}}
```

The keys are media ids and the values are integers. This phase has no way to add a call, so the object stays `{}`. Do not add a fake id.

## Repo

Create `app\repo\store.py`. This is the only file that holds the dicts.

Class `MemoryProviderStore`:

- Starts at mode `ok`, `delay_ms` `0`, `error_kind` `http_500`, calls `{}`.
- Uses one `asyncio.Lock` for every read and write.
- `async def set_control(mode, delay_ms, error_kind) -> dict` saves and returns the three values.
- `async def get_control() -> dict` returns the three values.
- `async def get_calls() -> dict[str, int]` returns a copy of the map.
- `async def increment_call(media_id: str) -> int` adds 1 for that id and returns the new count. No route calls this until phase 3. Add it now so the lock and the map exist in one place.

No method loops over frames. No SQL.

`create_app()` creates one `MemoryProviderStore` and puts it on `app.state.store`. Never make the store a module-level global: tests rely on each `create_app()` getting an empty one.

Put the control request model in `app\domain\schemas.py` as `ControlRequest`.

`app\api\deps.py` has `get_store(request) -> MemoryProviderStore` reading `request.app.state.store`.

## Routes

- `app\api\routes\control.py` — `POST /_control`.
- `app\api\routes\stats.py` — `GET /_stats`.

The route calls the repo method and returns the dict. It does not touch a dict itself. Include both routers from `main.py`.

## Tests

Add `tests\test_control_and_stats.py`. Use the client from `conftest.py`. Each test gets a new app and an empty store. Reset by creating the app in the fixture, not by a public reset route.

| Test | Assert |
| --- | --- |
| `test_stats_starts_empty` | `GET /_stats` is `200` and `{"calls": {}}` |
| `test_control_ok` | POST `{"mode": "ok", "delay_ms": 0}` returns that mode and `error_kind` `http_500` |
| `test_control_defaults_delay` | POST `{"mode": "slow"}` returns `delay_ms` `0` |
| `test_control_rejects_bad_mode` | POST `{"mode": "ok", "delay_ms": 1}`, then POST `{"mode": "nope", "delay_ms": 0}`. The second response is `422`. Then POST `{"mode": "ok", "delay_ms": 1}` again and the response is still `ok` and `1`. Validate the body before calling `set_control`, so a bad mode never writes. |
| `test_control_rejects_negative_delay` | POST `{"mode": "ok", "delay_ms": -1}` is `422` |
| `test_control_saves_error_kind` | POST mode `error`, `delay_ms` `0`, `error_kind` `http_429`. GET is not required. The next POST response body shows `http_429`. |
| `test_control_does_not_count_as_a_call` | After two control calls, `GET /_stats` is still `{"calls": {}}` |

## How to run

From `provider_service` with the venv active:

```powershell
python -m pytest
```

Expected: phase 1 and phase 2 tests pass.

## Done when

- The seven tests pass.
- A bad `mode` returns `422` and does not replace the mode saved before it.
- No `POST /score` yet.

## Report, then stop

```text
Phase 2 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
