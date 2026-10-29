# Phase 9 — Postman and manual check

Phase 8 must already pass. This phase adds Postman and the manual checks. Do not change a rule unless a check shows a bug. If you fix a bug, add a test and run pytest.

## Files to add

```text
d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\postman\backend.postman_collection.json
d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\postman\local.postman_environment.json
```

Update `backend\README.md` with the steps below. Keep the earlier run steps.

## Postman environment

Name: `backend local`.

| Variable | Value |
| --- | --- |
| `base_url` | `http://127.0.0.1:8000` |
| `provider_url` | `http://127.0.0.1:8001` |
| `media_id` | leave empty; the tests below copy it from the response |

Collection name: `moderation api`. Every API URL starts with `{{base_url}}`.

Headers on every API request except health and the callback: `X-User-Id` and `X-Workspace-Id`.

| Folder | Request | What it sends |
| --- | --- | --- |
| Health | health | `GET /health` |
| Media | upload safe image | `POST /media` as `member_v` / `ws_verified`. One frame `explicit` 0.1 |
| Media | read own | `GET /media/{{media_id}}` with the same headers |
| Media | read other workspace | `GET /media/{{media_id}}` as `member_u` / `ws_unverified` |
| Media | bad prompt | `POST /media` source `generation`, prompt `a 16-year-old at the beach`, one safe frame, `member_v` |
| Media | gray score | `POST /media` one frame `self_harm` 0.66, `member_v` |
| Review | list as admin | `GET /review` as `admin_v` / `ws_verified` |
| Review | list as member | `GET /review` as `member_v` / `ws_verified` |
| Review | approve | `POST /review/{{media_id}}/approve` as `admin_v` |
| Review | reject | `POST /review/{{media_id}}/reject` as `admin_v` |
| Callback | unsigned | `POST /provider/callback` body `{"media_id":"x","frames":[]}` and no `X-Signature` |
| Provider | set ok | `POST {{provider_url}}/_control` `{"mode":"ok","delay_ms":0}` |
| Provider | stats | `GET {{provider_url}}/_stats` |

The collection does not set a signature. The unsigned request must get `401`.

## Manual steps

Compose is running from the repo root. `SCREENING_MODE=fixed` in the API container. Provider is `ok`.

1. Import the collection and environment. Select the environment.

2. **health**. Expect `200` `{"status":"ok"}`.

3. **upload safe image**. Expect `202` (accepted) and `pending`. Copy `id` into the `media_id` variable.

4. Wait two seconds. **read own**. Expect `200` and `published`. Reasons `[]`.

5. **read other workspace**. Expect `404`.

6. **bad prompt**. Expect `422` (refused) and `reasons` containing `minor`.

7. **gray score**. Copy this new id over `media_id`. Wait two seconds. **read own** as `member_v`. Expect `held`.

8. **list as member**. Expect `403`.

9. **list as admin**. Expect `200` and a list that includes that id. It is not an error and it is not empty.

10. **approve**. Expect `200` and `published`. **list as admin** again. That id is gone. If no other holds exist, the list is `[]`. That empty list is a real empty list, because the status was `200`.

11. **unsigned**. Expect `401`.

12. **stats**. Note the number for the safe image. It should be `1`.

13. DBeaver. Open the `moderation` connection from phase 2. View Data on `media`. The safe image is `published`. View Data on `screening_decisions`. That media id has `source` `provider`. Do not edit cells.

14. Redis Insight. Open the `local` database from phase 3. The lists `queue:ws_verified` and `queue:ws_unverified` are empty or short, because the worker popped them. If a key is missing, that means the list was emptied. That is fine. Do not delete other keys.

15. Before-and-after numbers. These are required by the task, not optional. Allow about 20 minutes. Run every command from the repo root in one PowerShell window, so the variables stay set.

Broken run:

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
```

Fixed run:

```powershell
$env:SCREENING_MODE = "fixed"
docker compose up -d --force-recreate api worker scheduler
cd backend
python -m app.scripts.workload --videos 200 --outage | Out-File -Encoding ascii evidence\workload-fixed-outage.txt
python -m app.scripts.workload --videos 200 | Out-File -Encoding ascii evidence\workload-fixed-normal.txt
cd ..
```

What to check in the files:

- Broken outage: `published_unchecked` is above 0.
- Fixed outage: `published_unchecked` is 0 in both samples. Images end `held` during the outage and `published` after it.
- Broken normal: some of the 200 videos end `published` in an unverified workspace, because their last frame was never sent.
- Fixed normal: every video ends `blocked`.
- Fixed: provider calls per upload is close to 1 when there is no outage. Retries during an outage raise it, and that is expected.
- The images finish while many videos are still pending.

The workload runs against the Compose database, not the test database, so its rows remain visible in DBeaver afterwards. That is expected.

Finish with `$env:PROVIDER_HTTP_TIMEOUT_SECONDS = "10"` and recreate the three containers again.

16. Crash, by hand. This is a second look at what the phase 8 test proves.

```powershell
$env:SCREENING_MODE = "fixed"
docker compose up -d --force-recreate api worker scheduler
```

Make the provider slow, so the worker is still waiting when you kill it:

```powershell
curl -X POST http://127.0.0.1:8001/_control -H "Content-Type: application/json" -d "{\"mode\":\"slow\",\"delay_ms\":8000}"
```

Post one image as `member_u`. Within 8 seconds run `docker compose kill worker`. That stops both worker containers.

This kill happens before the provider answers, not after. That is the closest a manual step can get. The phase 8 test is the one that crashes after the score arrives and before it is saved. In DBeaver, the media is `pending`, the job is `running`, and the last `attempts` row has `finished_at` empty. Set the provider back to `ok`, then `docker compose up -d worker`. After about 30 seconds, the lease has expired, and the media is decided. `GET /_stats` shows `2` for that id. Write that `2` in the README: the item was not published unchecked, and the provider was billed twice.

17. `python -m pytest` still passes.

## Done when

- The checklist above has been run, or the step that blocked you is in the phase report.
- Postman files exist.
- Pytest passes.
- No React page was added.

## Report, then stop

```text
Phase 9 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest
Result: <pass or fail>
Manual checklist: <which step failed, or all passed>
```
