# Content moderation

Screen uploaded and generated images and videos. Postgres, Redis, the API, two workers, the scheduler, a fake provider, and the page all start together.

From this folder, with Docker Desktop running:

```powershell
docker compose up --build
```

The page is http://127.0.0.1:3000. The API is http://127.0.0.1:8000. The fake provider is http://127.0.0.1:8001.

## Where to read more

- [backend/README.md](backend/README.md) — install, tests, and the API setup.
- [provider_service/README.md](provider_service/README.md) — the fake provider.
- [ai_playground/other/README.md](ai_playground/other/README.md) — the failure, evidence, fix, before-and-after numbers, limits, part 3, and the production plan.
- [ai_playground/other/AI.md](ai_playground/other/AI.md) — which tools were used and what was checked.
