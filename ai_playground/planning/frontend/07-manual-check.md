# Phase 7 — Manual check

Phase 6 must already pass. This phase checks the page in a browser. Do not change a rule unless a click shows a bug. If you fix a bug, add a test and run `npm test`.

## Do not

- Do not open DBeaver.
- Do not open Redis Insight.
- Do not add a Postman collection.
- Do not edit a table or a Redis key to make the page look right.

The page only talks to the API. If a status looks wrong, the backend plans already have the DBeaver and Redis Insight steps.

## Before you click

1. Docker Desktop is running.
2. From the repo root:

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task
$env:SCREENING_MODE = "fixed"
docker compose up -d --build
```

3. Wait until both of these succeed:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:3000/
```

The second one is the HTML page. It will not be JSON.

4. Open Chrome or Edge at `http://127.0.0.1:3000`. You should see the heading `Moderation`.

## Clicks

Do these in order. Stop if a step does not match, and write which step failed.

1. Workspace `ws_verified`, user `admin_v`. The signed-in line includes both ids.

2. The review box shows either `Loading review queue` briefly, then `Nothing to review`, or a list. It must not stay on the loading text.

3. Click `Needs review`, then `Submit`. The page shows `Accepted` and an id, then `pending`, then `held`. This can take a few seconds. Reasons include `self_harm`.

4. The review box now lists that id. It does not say `Nothing to review`.

5. Click `Approve` on that row. The row disappears. If it was the only one, the box says `Nothing to review`. The status of that word is a real empty list, because the request succeeded.

6. Change the user to `member_v`. The review box says `Review is for workspace admins`. Click `Explicit image`, then `Submit`. The status becomes `published`, because this workspace is verified.

7. Change the workspace to `ws_unverified`. The user changes to `admin_u`. Click `Explicit image`, then `Submit`. The status becomes `blocked`.

8. Set How to `generation`. Leave the prompt as `two adults on a beach at sunset`. Click `Safe image`, then `Submit`. The status becomes `published`. The source was sent as generation.

9. Change the prompt to `a 16-year-old at the beach`. Submit again. The page shows `Refused` and `minor`. It does not show `Accepted`.

10. Click `Video, last frame explicit`, set How back to `upload`, and submit as `member_u` in `ws_unverified`. The status becomes `blocked`.

11. Show the bug on purpose. Stop only the API:

```powershell
docker compose stop api
```

Open `http://127.0.0.1:3000/?reviewBug=1` and refresh. This URL is the old bug, so the box says `Nothing to review` even though the API is down. There is no `Try again` button on this URL. That is the incident.

12. Open `http://127.0.0.1:3000` without the query string, as `admin_v`. Refresh. The review box says `Review queue failed`. It does not say `Nothing to review`. The status is `502`, because nginx is still up and the API behind it is not. On the Vite dev server at port 5173, the proxy also answers with an error status. The button `Try again` is visible.

13. Start the API again:

```powershell
docker compose start api
```

Wait until `curl http://127.0.0.1:8000/health` works. Click `Try again`. The box becomes `Nothing to review` or a list. It leaves the failed text. If it still shows `502` after the API is healthy, the nginx `resolver` line from phase 1 is missing.

14. In the browser devtools console, confirm the log lines are short `step=submit` and `step=review` lines. They do not contain a full `frames` array.

15. From `frontend`:

```powershell
npm test
```

Expect a pass.

## Done when

- Step 12 shows `Review queue failed` and not `Nothing to review`.
- Step 11 still shows the old bug when `reviewBug=1` is in the URL.
- Step 9 refuses the prompt.
- `npm test` passes.

## Report, then stop

```text
Phase 7 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: <pass or fail>
Manual checklist: <which step failed, or all passed>
```
