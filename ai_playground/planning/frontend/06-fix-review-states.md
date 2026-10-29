# Phase 6 — Fix the three states

Phase 5 is committed and the new tests fail. Do this phase only. Stop at the end.

## Goal

Loading, failed, and empty are three different views. The incident stays available behind a query string so you can show it on the call.

## The function

Change `reviewView`:

- `loading` stays loading.
- `error` returns `{ kind: "failed", text: "Review queue failed", status }`.
- `ready` with no items stays empty.
- `ready` with items stays a list.

Rename the old function to `reviewViewBroken` and keep it in the same file. It still maps `error` to empty.

`ReviewQueue` uses `reviewView`, unless the page URL contains `reviewBug=1`. Then it uses `reviewViewBroken`. Read that flag once with `new URLSearchParams(window.location.search)`.

## The box

When the view is `failed`:

- Text `Review queue failed`.
- The status number, including `0` for a network error.
- A button `Try again`. Clicking it sets loading and calls `getReview` once.

When the view is `empty`, the text is only `Nothing to review`. No Try again button.

When the view is `loading`, the text is only `Loading review queue`.

Do not render the empty text inside the failed branch.

## Tests

Point `test_broken_error_looks_empty` at `reviewViewBroken`. It should pass again.

The phase 5 tests call `reviewView` and must pass without any change to their expectations.

Add one test:

| Test | Assert |
| --- | --- |
| `test_try_again_loads_once_more` | First `getReview` returns status `503`. Click `Try again`. The fake's second call returns `[]`. The page ends on `Nothing to review`. `getReview` was called twice. |

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend
npm test | Out-File -Encoding ascii evidence\fixed-review-tests.txt
```

The exit code must be 0. If a phase 5 test still fails, the view function is still mapping errors to empty. Do not weaken the test.

## Commit

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
git add frontend
git commit -m "Keep a failed review request distinct from an empty queue."
```

## Done when

- `evidence\fixed-review-tests.txt` shows a pass.
- `reviewView({ kind: "error", status: 503 })` is `failed`.
- `http://127.0.0.1:5173/?reviewBug=1` still shows the old bug. You can check that in phase 7.
- `git log -2 --oneline` shows the failing-test commit and then this fix.

## Report, then stop

```text
Phase 6 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: <pass or fail>
Commit: <git log -1 --oneline>
```
