# AI

I built this with Cursor Pro ($20). Cursor's agent wrote most of the services, tests, and page. Tools I used:

- Cursor Pro ($20), including the agent
- Warp, for the terminal
- Docker and Docker Compose
- Git
- Postgres, viewed in DBeaver
- Redis, viewed in Redis Insight
- pytest and the frontend test runner

## What I checked

The broken incident tests fail, and the fixed run passes. The review page shows loading, a failed request, and a real empty queue as three different states. A timeout in `broken` mode publishes the item with no provider decision. In `fixed` mode the same timeout parks it, and a recovered provider screens it without an admin. I checked the three numbers and a worker killed during a provider call by hand. The 200-video before-and-after numbers are the saved evidence files. The death of worker after a score is also verified.

## Incorrect suggestions I caught

- Images are not scored ahead of videos in the same workspace. Each workspace has one queue. Workers alternate between the two workspaces.
- Setting the provider back to `ok` does not push parked jobs. The scheduler does, on its probe.
- A `succeeded` job is not proof the media was screened. The broken timeout path marks the job `succeeded` and still publishes with no decision.
- Docker does not read `backend/.env`. The mode and the provider timeout have to be set in the shell before the containers are recreated.
- `GET /_stats` keeps old ids after a database truncate. Restarting the provider clears them.
- Killing the worker during the slow call happens before the provider answers. The after-score gap is the crash test, not that kill.
