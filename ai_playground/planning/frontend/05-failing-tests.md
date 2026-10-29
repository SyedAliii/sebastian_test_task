# Phase 5 — Failing tests

Phase 4 is in place and the bug is still there. Do this phase only. Stop at the end.

## Goal

Add tests for the three states the task requires. Run them. They fail. Save the output. Commit.

Do not change `reviewView`, `ReviewQueue`, or the API client to make the new tests pass. Phase 6 does that.

## Tests to add

File: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend\src\domain\reviewStates.test.ts`

These call `reviewView` and expect the safe behavior.

| Test | Input | Expected |
| --- | --- | --- |
| `test_loading_is_its_own_state` | `{ kind: "loading" }` | kind `loading`, text `Loading review queue` |
| `test_error_is_not_empty` | `{ kind: "error", status: 503 }` | kind `failed`, text `Review queue failed`, status `503`. The text does not contain `Nothing to review`. |
| `test_network_error_is_not_empty` | `{ kind: "error", status: 0 }` | kind `failed`. Not `empty`. |
| `test_forbidden_is_not_empty` | `{ kind: "error", status: 403 }` | kind `failed`, status `403`. |
| `test_real_empty_stays_empty` | `{ kind: "ready", items: [] }` | kind `empty`, text `Nothing to review` |
| `test_rows_stay_a_list` | one media item | kind `list`, that id |

`test_loading_is_its_own_state`, `test_real_empty_stays_empty`, and `test_rows_stay_a_list` can pass today. That is fine.

These three must fail today: `test_error_is_not_empty`, `test_network_error_is_not_empty`, `test_forbidden_is_not_empty`.

Add to `src\components\ReviewQueue.test.tsx` (the file from phase 4):

| Test | Assert |
| --- | --- |
| `test_failed_request_shows_failure_not_empty` | Fake client `getReview` returns `{ ok: false, status: 503, message: "response status 503" }`. The page shows `Review queue failed` and `503`. It does not show `Nothing to review`. A button named `Try again` is present. |

This component test must fail today.

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend
New-Item -ItemType Directory -Force evidence | Out-Null
npm test | Out-File -Encoding ascii evidence\broken-review-tests.txt
```

`npm test` is `vitest run`, so it exits. A non-zero exit is expected. Do not "fix" the page and rerun.

Open the evidence file and check that the four names above are in the failure list.

`frontend\evidence` is part of the submission. Do not add it to `.gitignore`. Check that `git status` does not list `node_modules` or `dist`. The repo-root `.gitignore` covers both.

## Commit

From the repo root:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
git add frontend docker-compose.yml
git commit -m "Show a failed review request as an empty list, with tests that catch it."
```

Do not commit `node_modules` or `dist`.

## Done when

- The evidence file shows the four failures.
- `reviewView` still maps an error to the empty view.
- `git log -1 --oneline` shows the message above.

## Report, then stop

```text
Phase 5 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: fail, as required
Failed names: <list>
Commit: <git log -1 --oneline>
```
