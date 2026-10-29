# Phase 1 — Skeleton

Read `00-overview.md` first. Do this phase only. Stop at the end.

## Goal

The provider starts on port 8001 and answers `GET /health`. Settings come from the env file. Pytest can import the app. Nothing is scored in this phase.

## Do not

- Do not add `/score`, `/_control`, or `/_stats`.
- Do not add Postgres, Redis, or the backend.
- Do not decide published, held, or blocked.

## Manual steps before coding

1. Open PowerShell.
2. Check Python:

```powershell
py -3.12 --version
```

You need `Python 3.12.x`. If the command fails, install Python 3.12 from python.org and tick "Add python.exe to PATH". Close PowerShell, open it again, and run the command again. Do not continue on 3.11 or 3.13.

3. From the repo root, the later commands use this folder:

`d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service`

## Files to create

All paths below are under `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\`.

```text
app\__init__.py
app\main.py
app\config.py
app\api\__init__.py
app\api\deps.py
app\api\routes\__init__.py
app\api\routes\health.py
app\domain\__init__.py
app\repo\__init__.py
app\services\__init__.py
tests\__init__.py
tests\conftest.py
tests\test_health.py
requirements.txt
requirements.lock
pytest.ini
.env.example
.dockerignore
Dockerfile
docker-compose.yml
README.md
```

Empty `__init__.py` files stay empty.

## Settings

`app\config.py` reads the env with pydantic-settings.

| Field | Env name | Default |
| --- | --- | --- |
| `provider_host` | `PROVIDER_HOST` | `0.0.0.0` |
| `provider_port` | `PROVIDER_PORT` | `8001` |
| `provider_hmac_secret` | `PROVIDER_HMAC_SECRET` | `test-secret` |
| `callback_base_url` | `CALLBACK_BASE_URL` | `http://127.0.0.1:9000` |
| `callback_path` | `CALLBACK_PATH` | `/provider/callback` |
| `timeout_hold_seconds` | `TIMEOUT_HOLD_SECONDS` | `120`. Type `float` |
| `retry_after_seconds` | `RETRY_AFTER_SECONDS` | `2` |
| `log_level` | `LOG_LEVEL` | `INFO` |

Add a method `callback_url` that joins the base and the path with one slash between them.

Load `.env` from the current working directory. Ignore unknown env keys.

`.env.example` contains every name and the default value, one `NAME=value` per line. No quotes.

## App

`app\main.py` exposes `create_app(settings: Settings | None = None) -> FastAPI`.

- If `settings` is `None`, build `Settings()` from the env.
- Save the settings on `app.state.settings`.
- Configure the standard logging level from `settings.log_level`.
- Title: `fake-provider`.
- Include the health router.
- At the bottom of the file, add `app = create_app()`. That is what `uvicorn app.main:app` loads.
- Do not create global mutable score state in this phase. Later state goes on `app.state`, so every `create_app()` call gets fresh state.

`app\api\deps.py` has `get_settings(request) -> Settings`, which reads `request.app.state.settings`. Routes get settings from here, not by importing a global.

`GET /health` returns `200` and `{"status": "ok"}`. Put the route in `app\api\routes\health.py`. `main.py` only includes the router.

## Dependencies

`requirements.txt` lists:

```text
fastapi
uvicorn
pydantic-settings
httpx
pytest
pytest-asyncio
respx
```

Do not pin ranges by guessing. Install them, then write `requirements.lock` with `pip freeze`.

## Docker

`Dockerfile`:

- Base image `python:3.12-slim`.
- Workdir `/app`.
- Copy `requirements.lock` and install it with `pip install --no-cache-dir -r requirements.lock`. The lockfile, not `requirements.txt`, so the image gets the versions you tested.
- Copy `app`.
- Expose `8001`.
- Command: `uvicorn app.main:app --host 0.0.0.0 --port 8001`.

Add `.dockerignore` with `.venv`, `__pycache__`, `.pytest_cache`, and `.env`.

`docker-compose.yml` in this folder runs only the provider:

- Service name: `provider`.
- Build: this folder.
- Ports: `"8001:8001"`.
- Env file: `.env`.
- Healthcheck. The slim image has no `curl`, so use Python:

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health')"]
  interval: 5s
  timeout: 3s
  retries: 5
```

This file is not the full project compose. The full compose comes in a later plan. Do not add Postgres here.

## Tests

`pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

`tests\conftest.py` has three fixtures:

- `test_settings` returns `Settings(_env_file=None, provider_hmac_secret="test-secret", callback_base_url="http://callback.test", callback_path="/provider/callback", timeout_hold_seconds=0.2, retry_after_seconds=2)`. `_env_file=None` keeps a local `.env` out of the tests. For `timeout_hold_seconds=0.2` to work, the field type must be `float`, not `int`.
- `app` calls `create_app(test_settings)`.
- `client` yields `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`.

Every test gets a new app, so in-memory state never leaks between tests.

`tests\test_health.py`:

- `test_health_returns_ok`: `GET /health`. Assert status `200` and body `{"status": "ok"}`.
- `test_callback_url_joins_one_slash`: `Settings(_env_file=None, callback_base_url="http://x:9000/", callback_path="/provider/callback").callback_url` equals `http://x:9000/provider/callback`. Also check a base with no trailing slash.

## README

`README.md` in this folder only explains how to run the provider. Keep it short:

- Python 3.12.
- Create the venv, install, copy env, run uvicorn.
- Or `docker compose up --build`.
- Say port `8001`.
- Say this process keeps call counts in memory and loses them on restart.

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip freeze | Out-File -Encoding ascii requirements.lock
copy .env.example .env
python -m pytest
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Do not use `pip freeze > requirements.lock` in Windows PowerShell 5. That writes UTF-16, and the Docker build cannot read it reliably. The `Out-File -Encoding ascii` line above writes plain text.

If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

To check Docker as well, Docker Desktop must be running:

```powershell
docker compose up --build
```

Then `curl http://127.0.0.1:8001/health` from another window. Stop with Ctrl+C.

In a second PowerShell:

```powershell
curl http://127.0.0.1:8001/health
```

Expected body: `{"status":"ok"}`.

Leave the server running only for this check, then stop it with Ctrl+C. Tests must pass before you call the phase done.

## Done when

- `python -m pytest` passes.
- `GET /health` returns `200` and `{"status": "ok"}`.
- `.env.example` has every env name from the table.
- No score route exists.

## Report, then stop

```text
Phase 1 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
