# Fake provider

Python 3.12. This process listens on port 8001.

Call counts stay in memory and are lost when the process restarts.

## Local

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Tests

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
.\.venv\Scripts\Activate.ps1
python -m pytest
```

## Docker

```powershell
docker compose up --build
```

Inside Docker, `127.0.0.1` is the container. To reach a catcher on your machine, set `CALLBACK_BASE_URL=http://host.docker.internal:9000` in `.env`, then set it back to `http://127.0.0.1:9000` when you stop using Docker.

## Manual check

1. Copy the env file if it is not there yet: `copy .env.example .env`.
2. Confirm `.env` has `PROVIDER_PORT=8001`, `PROVIDER_HMAC_SECRET=test-secret`, `CALLBACK_BASE_URL=http://127.0.0.1:9000`, and `CALLBACK_PATH=/provider/callback`.
3. In window A, from `provider_service`, run `python scripts\callback_catcher.py`. Leave it open. It listens on `127.0.0.1:9000`.
4. In window B, from `provider_service`, run `uvicorn app.main:app --host 0.0.0.0 --port 8001`.
5. Import `postman\provider.postman_collection.json` and `postman\local.postman_environment.json` into Postman. Select the environment named `provider local`.
6. Send **health**. Expect `200` and `{"status": "ok"}`.
7. Send **stats**. Expect `200` and `{"calls": {}}`.
8. Send **set ok**, then **one frame**. Expect `200`. The frame has all six labels. `explicit` is `0.02`. The other labels are `0`. The catcher prints nothing.
9. Send **stats**. Expect `demo-1` equal to `1`.
10. Send **one frame** again. Send **stats**. Expect `demo-1` equal to `2`.
11. Send **nine frames**. Expect `200` and 9 frames. The last frame has `explicit` `0.95`.
12. Send **thirty one frames**. Expect `202`, `status` `accepted`, and no `frames` in that response. Within a second, window A prints the body, 31 frames, and `signature_ok=true`.
13. Send **stats**. Expect `demo-long` equal to `1`.
14. Send **set slow**, then **one frame**. Expect `200` after about 2 seconds, with scores.
15. Write down the `demo-1` count. Send **set timeout**, then **one frame**. The request waits `TIMEOUT_HOLD_SECONDS` (120 seconds) and then returns `504` with no `frames`. You can cancel it in Postman instead of waiting. Either way, `demo-1` is 1 higher than the number you wrote down.
16. Send **set error 500**, then **one frame**. Expect `500` and no `frames`.
17. Send **set error 429**, then **one frame**. Expect `429` and header `Retry-After: 2`.
18. Send **set malformed**, then **one frame**. Expect `200` and a body whose only label is `explicit`.
19. Send **set ok** so the next request is not left in timeout or error mode.
20. Stop both windows with Ctrl+C.
21. Run `python -m pytest`. Every test should pass.
