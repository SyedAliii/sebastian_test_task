# Moderation API

Python 3.12. The API listens on port 8000.

The worker and the scheduler start and log that they started. They do not score yet.

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

From the repo root, with Docker Desktop running. Set `SCREENING_MODE` to `broken` until phase 6, because the fixed path is not in place yet.

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
$env:SCREENING_MODE = "broken"
docker compose up --build
```

`http://127.0.0.1:8000/health` and `http://127.0.0.1:8001/health` both return `{"status":"ok"}`.
