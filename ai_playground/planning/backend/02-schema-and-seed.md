# Phase 2 — Tables and seed

Phase 1 must already pass. Do this phase only. Stop at the end.

## Goal

Postgres has the tables from `ai_playground\planning\db-design.md`. Startup inserts the two workspaces and four users. You can see them in DBeaver. Tests use a second database, `moderation_test`, and wipe it between tests.

## Do not

- Do not click SQL in DBeaver to create or alter tables.
- Do not add columns that are not in this file.
- Do not start calling the provider.

## Migration

Add Alembic under `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\alembic\`.

`alembic.ini` reads `ALEMBIC_DATABASE_URL`. Do not point Alembic at the async URL.

Write the migration by hand. Do not use autogenerate. One file: `alembic\versions\001_schema.py`.

Tables, in this order: `workspaces`, `users`, `media`, `screening_decisions`, `jobs`, `attempts`.

`workspaces`: `id text` primary key, `verified boolean not null`.

`users`: `id text` primary key, `workspace_id text not null` references workspaces, `role text not null` check `admin` or `member`.

`media`:

- `id uuid` primary key
- `workspace_id` references workspaces
- `submitted_by` references users
- `type` check `image` or `video`
- `source` check `upload` or `generation`
- `prompt text` null
- `frames jsonb not null`
- `frame_count int not null` check `>= 1`
- `status` check `pending`, `published`, `held`, `blocked`
- `hold_reason` check null or `review` or `no_decision`
- `reasons jsonb not null default '[]'`
- `created_at`, `updated_at` timestamptz not null
- check: `held` requires `hold_reason`; any other status requires `hold_reason` null
- check: `generation` requires `prompt`; `upload` requires `prompt` null
- check: `image` requires `frame_count = 1`

Indexes: `(workspace_id, status)`, and a partial index on `(workspace_id)` where `status = 'held' and hold_reason = 'review'`.

`screening_decisions`:

- `id uuid` primary key
- `media_id` references media
- `source` check `provider` or `admin`
- `scores jsonb` null
- `outcome` check `published`, `held`, `blocked`
- `reasons jsonb not null`
- `decided_by text` null references users
- `created_at timestamptz not null`
- unique partial index on `media_id` where `source = 'provider'`
- unique partial index on `media_id` where `source = 'admin'`

`jobs`:

- `id uuid` primary key
- `media_id uuid not null unique` references media
- `workspace_id` references workspaces
- `state` check `queued`, `running`, `awaiting_callback`, `retry_wait`, `parked`, `succeeded`
- `attempts_used int not null default 0`
- `available_at timestamptz not null`
- `lease_owner text` null
- `lease_until timestamptz` null
- `needs_enqueue boolean not null default true`
- `created_at`, `updated_at` timestamptz not null

Index `(state, available_at)`. Partial index on `needs_enqueue` where it is true.

`attempts`:

- `id uuid` primary key
- `job_id` references jobs
- `media_id` references media
- `workspace_id` references workspaces
- `n int not null`
- `worker_id text not null`
- `started_at timestamptz not null`
- `finished_at timestamptz` null
- `result text` null
- `detail text` null
- unique `(job_id, n)`

`result` stays free text so a new outcome does not need a migration. The allowed values are `success`, `accepted_async`, `timeout`, `http_429`, `http_500`, `malformed`.

Downgrade drops the tables in reverse order.

## Models and repos

SQLAlchemy 2.0 models in `app\db\models.py`. One class per table. Column names match the migration exactly.

`app\db\session.py` builds one async engine and a session factory from `DATABASE_URL`.

Every repo function takes the session as its first argument. No repo opens its own engine or commits. The service that started the transaction commits.

| File | Methods |
| --- | --- |
| `app\repo\seed_repo.py` | `insert_seed(session)` using `INSERT ... ON CONFLICT DO NOTHING` |
| `app\db\seed.py` | `seed(session)` calls that one method |

`seed.py` is the only code that writes seed rows. It is data, not schema, so it is allowed outside Alembic.

Seed rows, exactly:

| workspace | verified | users |
| --- | --- | --- |
| `ws_verified` | true | `admin_v` role `admin`, `member_v` role `member` |
| `ws_unverified` | false | `admin_u` role `admin`, `member_u` role `member` |

One statement for workspaces and one for users. Not one query per user inside a loop of extra selects.

`create_app` lifespan: open a session, `seed`, commit. A second startup does not duplicate rows.

API startup does not run Alembic itself. The compose command for `api` is:

```text
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker and scheduler do not run migrations.

Update `backend\Dockerfile` now: add `COPY alembic alembic` and `COPY alembic.ini .`.

`alembic\env.py` reads the URL from an `ALEMBIC_URL` override first, then `ALEMBIC_DATABASE_URL`. The test fixture sets the override to `ALEMBIC_DATABASE_URL_TEST`, so tests migrate `moderation_test` and never the main database. Run that upgrade once per pytest session, not once per test.

## Tests

Tests need Compose Postgres up. Document that at the top of `tests\conftest.py`.

Fixture `db_session`:

- URL is `DATABASE_URL_TEST`.
- Truncate `attempts`, `screening_decisions`, `jobs`, `media`, `users`, `workspaces` with `CASCADE`, in one statement.
- Call `seed` and commit.
- Yield a session factory for `moderation_test`.

The app under test uses that same factory through a dependency override. Services commit as they would in production. Tests open their own session from the factory to read what was saved. Do not share one open session between the app and the test: a commit inside the app would end the test's transaction.

Also add `redis_client`: connect to `REDIS_URL_TEST` (database `1`) and run `FLUSHDB` before each test. Never flush database `0`. That is where the running Compose worker reads.

| Test | Assert |
| --- | --- |
| `test_seed_inserts_four_users` | After seed, one query returns the four user ids. |
| `test_seed_is_safe_twice` | Calling `seed` again does not raise and still returns four users. |
| `test_image_frame_count_check` | Inserting an image with `frame_count` 2 raises an integrity error. Roll back. |

Do not add a route that returns the users.

## DBeaver — look, do not edit

1. Start Compose from the repo root if it is not running: `docker compose up`.
2. Open DBeaver.
3. Database, New Database Connection, PostgreSQL.
4. Host `127.0.0.1`, port `5432`, database `moderation`, username `moderation`, password `moderation`.
5. Test Connection. If the driver download prompt appears, allow it.
6. Finish. Open the connection.
7. Expand `moderation`, Schemas, `public`, Tables.
8. You should see `workspaces`, `users`, `media`, `screening_decisions`, `jobs`, `attempts`.
9. Right-click `users`, View Data. You should see `admin_v`, `member_v`, `admin_u`, `member_u`.
10. Do not use the SQL editor to insert or alter. If a column is missing, fix the migration and run `alembic upgrade head` again.

If Test Connection fails, the postgres container is not up, or the port is not `5432`.

The test database is a second connection: same host and user, database name `moderation_test`. It can be empty of users until pytest runs. That is fine.

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python -m pytest
```

`alembic upgrade head` uses `.env`. If the test database has no tables, the fixture runs upgrade against `DATABASE_URL_TEST` as well. Write that into the fixture with Alembic's `command.upgrade`.

## Done when

- DBeaver shows `workspaces`, `users`, `media`, `screening_decisions`, `jobs`, and `attempts`.
- Four users are visible.
- Pytest passes.
- No application code outside `seed` and the migration inserts those users.

## Report, then stop

```text
Phase 2 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
```
