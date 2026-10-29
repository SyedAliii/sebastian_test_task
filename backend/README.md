# Moderation API

Python 3.12. The API listens on port 8000.

The worker scores accepted media. The scheduler puts due jobs back on the queue.

A broken outage can make `oldest_waiting_seconds` look small, because a timeout is published and the job is marked succeeded. That low number means the wait was hidden, not that the queue is healthy.

## Setup

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
python -m pytest
```

## Docker

From the repo root, with Docker Desktop running. The default `SCREENING_MODE` is `fixed`. Set it to `broken` only when you want to reproduce the incident.

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
docker compose up --build
```

## Prompt check

In fixed mode, a generation prompt is refused before it is saved when it matches a word list: minor, sexual violence, bestiality, self-harm, a real person, incest, or trafficking. The text is lowercased and hyphens become spaces. `a 16-year-old at the beach` is refused. `two adults on a beach at sunset` is allowed.

This list has false positives, such as `a minor detail`, and it misses paraphrases. A production check would keep a list like this and also use a model that looks for disguised requests.

`GET /review` returns only `review` holds. A `no_decision` hold is not in that list, and approve or reject on it returns `409`. An outage hold cannot be approved onto the site. It is screened again when the provider answers.

`http://127.0.0.1:8000/health` and `http://127.0.0.1:8001/health` both return `{"status":"ok"}`.

## Postman

Import `postman/backend.postman_collection.json` and `postman/local.postman_environment.json`. Select the environment named `backend local`.

`upload safe image` and `gray score` copy the new id into `media_id`. The callback request sends no signature, so it returns `401`.

## Manual check

Compose is running from the repo root. The API container uses `SCREENING_MODE=fixed`, and the provider mode is `ok`.

1. **health**. `200` `{"status":"ok"}`.
2. **upload safe image**. `202` and `pending`.
3. Wait two seconds. **read own**. `200` and `published`. Reasons `[]`.
4. **read other workspace**. `404`.
5. **bad prompt**. `422` and `reasons` containing `minor`.
6. **gray score**. Copy that id into `media_id`. Wait two seconds. **read own** as `member_v`. `held`.
7. **list as member**. `403`.
8. **list as admin**. `200` and the list includes that id.
9. **approve**. `200` and `published`. **list as admin** again. That id is gone.
10. **unsigned**. `401`.
11. **stats**. The safe image was called once.

In DBeaver, on the `moderation` database, the safe image row in `media` is `published`, and `screening_decisions` has `source` `provider` for that id. Do not edit cells.

In Redis Insight, database `local`, the lists `queue:ws_verified` and `queue:ws_unverified` are empty or short. A missing key means the worker emptied that list.

Before-and-after numbers, from the repo root in one PowerShell window:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
$env:SCREENING_MODE = "broken"
$env:PROVIDER_HTTP_TIMEOUT_SECONDS = "1"
docker compose up -d --force-recreate api worker scheduler
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.scripts.workload --videos 200 --outage | Out-File -Encoding ascii evidence\workload-broken-outage.txt
python -m app.scripts.workload --videos 200 | Out-File -Encoding ascii evidence\workload-broken-normal.txt
cd ..
$env:SCREENING_MODE = "fixed"
docker compose up -d --force-recreate api worker scheduler
cd backend
python -m app.scripts.workload --videos 200 --outage | Out-File -Encoding ascii evidence\workload-fixed-outage.txt
python -m app.scripts.workload --videos 200 | Out-File -Encoding ascii evidence\workload-fixed-normal.txt
cd ..
$env:PROVIDER_HTTP_TIMEOUT_SECONDS = "10"
docker compose up -d --force-recreate api worker scheduler
```

A broken outage can show `published_unchecked` above 0. A fixed outage keeps that number at 0. During the outage the images are `held`. After the provider recovers they are `published` without an admin. In a broken normal run, some unverified videos are `published` because the last frame was never sent. In a fixed normal run, every one of those videos is `blocked`. With no outage, provider calls per upload stay close to 1. The images leave `pending` while many videos are still waiting.

Killing a worker while the provider is slow leaves the media `pending` and the job `running`, with `finished_at` empty on the attempt. After the worker starts again and the 30 second lease expires, the item is decided. `GET /_stats` showed `2` for that id: the item was not published unchecked, and the provider was billed twice.
