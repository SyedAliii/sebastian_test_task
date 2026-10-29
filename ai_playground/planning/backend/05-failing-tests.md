# Phase 5 — Failing tests

Phase 4 must already pass, including its bugs. Do this phase only. Stop at the end.

## Goal

Add tests that describe the safe behavior. Run them against `SCREENING_MODE=broken`. They fail. Save the output. Commit the broken code and these tests together.

This failure is the result you want. Do not change `policy.py`, the worker, the review route, or the prompt path to make the new tests pass. Phase 6 does that.

## Tests to add

File: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend\tests\test_incident.py`

Settings: `screening_mode="broken"`. Provider is respx, not the real process, except where a test says otherwise.

| Test | What the safe behavior is | Why it fails today |
| --- | --- | --- |
| `test_timeout_does_not_publish` | After a timeout, status is `pending` or `held`, never `published`. No provider decision is required yet. | The broken worker sets `published`. |
| `test_frame_nine_blocks_unverified` | `member_u` uploads a 9-frame video. Frames 1–8 are `explicit` 0.01. Frame 9 is `explicit` 0.95. After the worker runs, status is `blocked`. | Only 8 frames are sent, so the provider never sees 0.95. |
| `test_sixteen_year_old_is_refused` | `POST /media` source `generation`, prompt `a 16-year-old at the beach`, one harmless frame. Status `422`. Body `reasons` contains `minor`. No media row. Provider mock received zero calls. | The route does not check the prompt. |
| `test_second_worker_does_not_call_again` | Push the same job id twice. Start two `process_one` calls. Hold the first provider call open with an `asyncio.Event` inside respx. The safe result is one `POST /score`. | Nothing claims the job, so both copies call the provider. |
| `test_review_error_is_not_an_empty_list` | Monkeypatch `media_repo.list_review` to raise `sqlalchemy.exc.OperationalError("select", {}, Exception("db down"))`. `GET /review` as `admin_v` is `503` with `{"detail": "review queue unavailable"}`, not `200` with `[]`. | The service returns `[]`. |
| `test_review_empty_is_200` | No held items. `GET /review` as `admin_v` is `200` and `[]`. This passes in both modes. It is the real empty state the page must tell apart from a failure. |
| `test_cross_workspace_media_is_404` | Already true from phase 3. Repeat it here so the incident file lists it. This one may pass. That is fine. |
| `test_unsigned_callback_is_401` | Already true from phase 4. May pass. |
| `test_member_approve_is_403` | Already true from phase 4. May pass. |
| `test_gray_score_is_held` | One frame, `self_harm` 0.66, verified workspace. After the worker, status is `held` and `hold_reason` is `review`. | This one should pass if `decide` is correct and the single frame was sent. If it fails, do not change `decide`. Write the failure down. |

A test that already passes stays in the file. The phase is done when these five fail: `test_timeout_does_not_publish`, `test_frame_nine_blocks_unverified`, `test_sixteen_year_old_is_refused`, `test_second_worker_does_not_call_again`, and `test_review_error_is_not_an_empty_list`.

A test that runs the worker calls `process_one` directly. It does not start `worker_main`. Pop order and Redis keys come from `redis_client` (database `1`).

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\backend
.\.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force evidence | Out-Null
python -m pytest tests\test_incident.py -rA --tb=line | Out-File -Encoding ascii evidence\broken-pytest.txt
```

Compose Postgres and Redis must be running. A non-zero exit code is expected. Do not rerun with a "fix".

`evidence` is in `.dockerignore` but not in `.gitignore`. The test output is part of the submission.

Open `evidence\broken-pytest.txt` and check that the five names above are in the failure summary.

## Commit

The task asks for the git history. From the repo root:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
git add backend provider_service docker-compose.yml
git commit -m "Reproduce the screening incident with a broken handler and failing tests."
```

Do not commit `.env`, `.venv`, or `__pycache__`. If `provider_service` is already committed, that is fine.

If git is not initialized, run `git init` once, then the add and commit.

## Done when

- `evidence\broken-pytest.txt` exists and shows the five failures.
- The broken behavior is unchanged.
- The commit exists. `git log -1 --oneline` shows the message above.

## Report, then stop

```text
Phase 5 done.
Files affected:
- <full path of every file created or edited>
Tests: python -m pytest tests\test_incident.py
Result: fail, as required
Failed names: <list>
Commit: <git log -1 --oneline>
```
