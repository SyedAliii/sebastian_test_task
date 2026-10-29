# Phase 6 — Postman and manual check

Phase 5 must already pass. This phase adds the Postman files and a callback catcher. Do not change score behavior unless a manual check shows a bug. If you fix a bug, add or adjust a test for it, then run pytest again.

## Goal

A person can run the provider, send the grader routes, and see a signed callback without the backend existing.

## Files to add

```text
d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\postman\provider.postman_collection.json
d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\postman\local.postman_environment.json
d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\scripts\callback_catcher.py
```

Update `README.md` with the manual steps below. Do not remove the pytest steps.

## Postman environment

Name: `provider local`.

| Variable | Value |
| --- | --- |
| `base_url` | `http://127.0.0.1:8001` |
| `media_id` | `demo-1` |
| `long_media_id` | `demo-long` |

## Postman requests

Collection name: `fake provider`. Every URL starts with `{{base_url}}`.

| Folder | Request | Method and body |
| --- | --- | --- |
| Health | health | `GET /health` |
| Control | set ok | `POST /_control` `{"mode": "ok", "delay_ms": 0}` |
| Control | set slow | `POST /_control` `{"mode": "slow", "delay_ms": 2000}` |
| Control | set timeout | `POST /_control` `{"mode": "timeout", "delay_ms": 0}` |
| Control | set error 500 | `POST /_control` `{"mode": "error", "delay_ms": 0}` |
| Control | set error 429 | `POST /_control` `{"mode": "error", "delay_ms": 0, "error_kind": "http_429"}` |
| Control | set malformed | `POST /_control` `{"mode": "error", "delay_ms": 0, "error_kind": "malformed"}` |
| Stats | stats | `GET /_stats` |
| Score | one frame | `POST /score` with `media_id` `{{media_id}}` and one frame `{"explicit": 0.02}` |
| Score | nine frames | `POST /score` with `media_id` `demo-nine` and nine frames. Frame 9, the last one, has `explicit` `0.95`. The first eight have `explicit` `0.01`. |
| Score | thirty one frames | `POST /score` with `media_id` `{{long_media_id}}` and 31 frames of `{"explicit": 0.1}` |

Write the 31-frame body as JSON in the collection. Do not tell the user to generate it by hand during the click-through. A small saved body is fine.

## Callback catcher

`scripts\callback_catcher.py` is a tiny FastAPI app, run as a script.

- Listens on `127.0.0.1:9000`.
- `POST /provider/callback` reads the raw body with `await request.body()`.
- Prints the raw body and the `X-Signature` header.
- Recomputes HMAC-SHA256 over those raw bytes with the secret from env `PROVIDER_HMAC_SECRET`, default `test-secret`, and compares with `hmac.compare_digest`. Prints `signature_ok=true` or `signature_ok=false`.
- Do not import `sign_body` from `app.services.signature`. Recompute with `hmac` directly, so the catcher checks the provider instead of trusting its own code.
- Returns `200` `{"status": "ok"}`.

Run it with:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
.\.venv\Scripts\Activate.ps1
python scripts\callback_catcher.py
```

Use uvicorn inside that file on port 9000. Do not use the provider's port.

## Manual steps

Do these in order. Check each expected result before the next step.

1. Copy env if you have not:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
copy .env.example .env
```

2. Confirm `.env` has `PROVIDER_PORT=8001`, `PROVIDER_HMAC_SECRET=test-secret`, `CALLBACK_BASE_URL=http://127.0.0.1:9000`, and `CALLBACK_PATH=/provider/callback`.

3. Start the catcher in PowerShell window A. Leave it open.

4. Start the provider in PowerShell window B:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

5. Import the collection and the environment into Postman. Select the environment.

6. Send **health**. Expect `200` and `{"status": "ok"}`.

7. Send **stats**. Expect `200` and `{"calls": {}}`.

8. Send **set ok**, then **one frame**. Expect `200`. The frame has all six labels. `explicit` is `0.02`. The other labels are `0`. The catcher prints nothing.

9. Send **stats**. Expect `demo-1` equal to `1`.

10. Send **one frame** again. Send **stats**. Expect `demo-1` equal to `2`.

11. Send **nine frames**. Expect `200` and 9 frames. The last frame has `explicit` `0.95`.

12. Send **thirty one frames**. Expect `202`, `status` `accepted`, and no `frames` in that response. Within a second, window A prints the body, 31 frames, and `signature_ok=true`.

13. Send **stats**. Expect `demo-long` equal to `1`.

14. Send **set slow** (`delay_ms` 2000), then **one frame**. Expect `200` after about 2 seconds, with scores.

15. Send **stats** and write down the number for `demo-1`. Send **set timeout**, then **one frame**. The request hangs for `TIMEOUT_HOLD_SECONDS`, 120 seconds by default, then returns `504` with no `frames`. You may cancel it in Postman instead of waiting. Either way, send **stats** again: `demo-1` is 1 higher than the number you wrote down.

16. Send **set error 500**, then **one frame**. Expect `500` and no `frames`.

17. Send **set error 429**, then **one frame**. Expect `429` and header `Retry-After: 2`.

18. Send **set malformed**, then **one frame**. Expect `200` and a body whose only label is `explicit`.

19. Send **set ok** again so the next person does not inherit timeout mode. The process forgets this when it stops anyway.

20. Stop both windows with Ctrl+C.

Optional, Docker. Docker Desktop must be running. Keep the catcher running in window A. In `.env`, set `CALLBACK_BASE_URL=http://host.docker.internal:9000`, because inside the container `127.0.0.1` is the container itself. Run `docker compose up --build` in window B, then repeat steps 6, 8, and 12. Window A must again print `signature_ok=true`. Set `CALLBACK_BASE_URL` back to `http://127.0.0.1:9000` afterwards.

21. Run:

```powershell
python -m pytest
```

Expect every test to pass.

## Done when

- The checklist above has been run, or the blocker is written down in the phase report.
- Postman files exist.
- Pytest still passes.
- No backend, Postgres, or Redis was added.

## Report, then stop

```text
Phase 6 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
Manual checklist: <which step failed, or all passed>
```
