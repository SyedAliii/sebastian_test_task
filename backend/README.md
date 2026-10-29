# Moderation API

Python 3.12. The API listens on port 8000.

The worker scores accepted media. The scheduler starts and logs that it started. It does not move jobs yet.

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

`http://127.0.0.1:8000/health` and `http://127.0.0.1:8001/health` both return `{"status":"ok"}`.
