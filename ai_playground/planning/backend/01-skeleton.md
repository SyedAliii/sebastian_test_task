# Phase 1 — Skeleton

Read `00-overview.md` first. Do this phase only. Stop at the end.

If `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\provider_service\app\main.py` does not exist, stop. Finish the provider plan first. Do not copy the provider into this folder.

## Goal

The backend starts on port 8000 and answers `GET /health`. Compose starts Postgres, Redis, the provider, the API, a worker process, and a scheduler process. The worker and scheduler only log that they started. They do not read jobs yet.

## Do not

- Do not add `/media`, `/review`, or `/provider/callback`.
- Do not create tables by hand in DBeaver.
- Do not add the React page.

## Manual steps before coding

1. Open PowerShell and check Python:

```powershell
py -3.12 --version
```

You need `Python 3.12.x`. If it fails, install Python 3.12 and tick "Add python.exe to PATH". Do not continue on another version.

2. Docker Desktop must be running. `docker info` should print server info, not an error.

## Files to create

Root of the service: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\`

```text
app\__init__.py
app\main.py
app\config.py
app\worker_main.py
app\scheduler_main.py
app\api\__init__.py
app\api\deps.py
app\api\routes\__init__.py
app\api\routes\health.py
app\api\middleware.py
app\core\__init__.py
app\core\logging\__init__.py
app\core\logging\logger.py
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
Dockerfile
docker-compose.yml
README.md
```

The compose file for the whole submission lives at the repo root, not inside `backend`:

`d:\MyWorkspace\MainProjects\Other\sebastian_test_task\docker-compose.yml`

Empty `__init__.py` files stay empty.

## Settings

`app\config.py` uses pydantic-settings. `create_app(settings=None)` uses the passed object, or `Settings()` when it is `None`. Tests pass `Settings(_env_file=None, ...)`.

Fields and env names are the table in `00-overview.md`. `timeout` style numbers that tests set below 1 must be `float`. `LOG_ENABLE_EMOJIS` is a bool.

Also add:

| Field | Env | Default |
| --- | --- | --- |
Every name in the overview env table is a field. Two need code:

- `worker_id`: when `WORKER_ID` is empty, use `socket.gethostname()`.
- `screening_mode`: a `Literal["broken", "fixed"]`. Default `broken` until phase 6 changes `.env.example` to `fixed`.

`.env.example` lists every name from the overview table with its local value.

`app = create_app()` at the bottom of `main.py` so uvicorn can load `app.main:app`.

## Logger

Build `app\core\logging\logger.py` from the ideas in `ai_playground\logger_prompt.md`. Implement only these methods: `apply_log_settings`, `log_level_banner`, `server_request_in`, `server_response_out`, `api_request_out`, `api_response_in`, `webhook_in`, `webhook_fail`, `job_start`, `job_end`, `pipeline`, `business_flow`, `warning`, `error_trace`, `system_info`, `format_json`.

Rules from that prompt that you must keep:

- One facade. Business code does not call `logging.getLogger` or `print`.
- Stdlib logger underneath, one stdout handler, `propagate = False`.
- Format `%(asctime)s.%(msecs)03d - %(message)s`.
- Gate: `none < high < mid < low`. A line prints when the env level is at least the method's priority. Banner always prints.
- Priorities: banner always; warning, error_trace, webhook_fail are high; request, response, provider call, job, pipeline, system are mid; payloads inside `format_json` are low.
- Correlation id is 8 characters from `A-Z` and `0-9`. `server_request_in` returns it. The middleware stores it on `request.state.correlation_id`, logs the response, sets header `X-Correlation-ID`, and clears the timer.
- Skip `/health` in the middleware so it does not flood the log.
- On Windows, reconfigure stdout to UTF-8 with `errors="replace"`.
- `format_json` redacts keys that contain `authorization`, `signature`, `secret`, `cookie`, or `x-signature`. It truncates past the max size and depth.
- Silence `uvicorn.access`, `httpx`, and `sqlalchemy.engine` to WARNING.

`create_app` calls `apply_log_settings` and `log_level_banner("moderation-api")`.

## Health

`GET /health` returns `200` and `{"status": "ok"}`. The route file only returns that dict. `main.py` includes the router.

## Dependencies

`requirements.txt` lists, unpinned:

```text
fastapi
uvicorn
pydantic-settings
httpx
sqlalchemy
asyncpg
psycopg
alembic
redis
pytest
pytest-asyncio
respx
```

Install, then write the lock with ASCII so Docker can read it on Windows:

```powershell
python -m pip freeze | Out-File -Encoding ascii requirements.lock
```

## Docker

`backend\Dockerfile`:

- `python:3.12-slim`
- Install `requirements.lock`
- Copy `app` only in this phase. Phase 2 adds `COPY alembic` and `COPY alembic.ini`.
- Command is not fixed in the image. Compose sets the command.

Repo-root `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `node_modules/`. Commit `.env.example`, not `.env`.

`.dockerignore`: `.venv`, `__pycache__`, `.pytest_cache`, `.env`, `evidence`.

Repo-root `docker-compose.yml` services:

| Service | Image or build | Ports | Command |
| --- | --- | --- | --- |
| `postgres` | `postgres:16` | `5432:5432` | default |
| `redis` | `redis:7` | `6379:6379` | default |
| `provider` | build `./provider_service` | `8001:8001` | the provider's own command |
| `api` | build `./backend` | `8000:8000` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `worker` | build `./backend` | none | `python -m app.worker_main` |
| `scheduler` | build `./backend` | none | `python -m app.scheduler_main` |

Postgres env: `POSTGRES_USER=moderation`, `POSTGRES_PASSWORD=moderation`, `POSTGRES_DB=moderation`.

Postgres healthcheck with `pg_isready -U moderation`. Redis healthcheck with `redis-cli ping`. The API waits until postgres and redis are healthy.

The API gets a healthcheck too, with Python because the slim image has no `curl`:

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
  interval: 5s
  retries: 20
```

Worker and scheduler use `depends_on: api: condition: service_healthy`. The API runs migrations before it starts (phase 2), so the worker never reads a table that does not exist yet.

The worker service sets `deploy: replicas: 2`. Two workers are what make the duplicate-call bug possible, and what the fix has to survive. Leave `WORKER_ID` empty so each container uses its own host name.

Provider env override inside this compose file:

- `CALLBACK_BASE_URL=http://api:8000`
- `CALLBACK_PATH=/provider/callback`
- `PROVIDER_HMAC_SECRET=test-secret`

API, worker, and scheduler env:

- `DATABASE_URL=postgresql+asyncpg://moderation:moderation@postgres:5432/moderation`
- `ALEMBIC_DATABASE_URL=postgresql+psycopg://moderation:moderation@postgres:5432/moderation`
- `REDIS_URL=redis://redis:6379/0`
- `PROVIDER_BASE_URL=http://provider:8001`
- `PROVIDER_HMAC_SECRET=test-secret`
- `SCREENING_MODE=${SCREENING_MODE:-fixed}`. Until phase 6, set `SCREENING_MODE=broken` in your shell before `docker compose up`, or the stack will run the fixed path that does not exist yet.

Do not use `env_file` for these three services. Compose would load `backend\.env`, whose hosts are `127.0.0.1`, and inside a container that is the container itself.

Mount an init SQL file so the test database exists the first time the volume is created:

`d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\docker\init-test-db.sql`

```sql
CREATE DATABASE moderation_test;
```

Mount it to `/docker-entrypoint-initdb.d/01-test-db.sql`. This file runs only on a brand-new volume.

`worker_main.py` and `scheduler_main.py` configure logging, log `system_info` with `process=worker` or `process=scheduler`, and sleep in a loop. No job code.

## Tests

`pytest.ini`: `asyncio_mode = auto` and `testpaths = tests`.

`tests\conftest.py` builds the app with `Settings(_env_file=None)` and an `httpx.AsyncClient` on `httpx.ASGITransport(app=app, raise_app_exceptions=False)`. Without that flag, an unhandled error is raised inside the test instead of coming back as a `500` response, and a test cannot check the status. No database in this phase.

Also register one exception handler in `create_app` for `Exception`: log `error_trace` with the request's correlation id, and return `500` `{"detail": "internal error", "correlation_id": "<id>"}`.

`test_health_returns_ok`: `GET /health` is `200` and `{"status": "ok"}`.

`test_health_has_no_correlation_header`: `/health` does not set `X-Correlation-ID`.

`test_banner_function_exists`: call `log_level_banner("moderation-api")` and assert it does not raise.

## README

Short. Python 3.12. How to copy `.env.example` to `.env`. How to run `docker compose up --build` from the repo root. Port 8000. Say the worker does not score yet.

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip freeze | Out-File -Encoding ascii requirements.lock
copy .env.example .env
python -m pytest
```

Then from the repo root, with Docker Desktop running:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
docker compose up --build
```

In another window:

```powershell
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8000/health
```

Both return `{"status":"ok"}`. Worker and scheduler logs show a startup line. Stop with Ctrl+C.

## Done when

- Pytest passes.
- Both health URLs return `200`.
- No media route exists.

## Report, then stop

```text
Phase 1 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
