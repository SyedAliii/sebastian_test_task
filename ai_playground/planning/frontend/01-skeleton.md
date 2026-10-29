# Phase 1 — Skeleton

Read `00-overview.md` first. Do this phase only. Stop at the end.

## Goal

A React and TypeScript page builds, and Docker serves it at `http://127.0.0.1:3000`. The page does not call the API yet.

## Do not

- Do not add a backend, a database, or Postman.
- Do not call `fetch`.
- Do not install a component library or Tailwind.

## Manual steps before coding

1. Open PowerShell.

```powershell
node -v
npm -v
```

You need Node 20 or newer. If `node` is missing, install the Node 20 LTS from nodejs.org and open a new PowerShell. Do not continue on Node 18.

2. The API from the backend plan should already be running:

```powershell
curl http://127.0.0.1:8000/health
```

Expect `{"status":"ok"}`. If it fails, start Compose from the repo root before phase 2. Phase 1 can still build the page without it.

## Files to create

Root: `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend\`

```text
package.json
package-lock.json
tsconfig.json
vite.config.ts
src\test\setup.ts
index.html
nginx.conf
Dockerfile
.dockerignore
.env.example
src\main.tsx
src\App.tsx
src\index.css
src\vite-env.d.ts
```

Write the files by hand. Do not run `npm create vite`, because that prompt is interactive and easy to mis-answer.

`package.json` scripts:

- `dev` — `vite`
- `build` — `tsc --noEmit && vite build`
- `test` — `vitest run`
- `preview` — `vite preview --host 127.0.0.1 --port 4173`

Dependencies: `react`, `react-dom`.
Dev dependencies: `typescript`, `vite`, `@vitejs/plugin-react`, `@types/react`, `@types/react-dom`, `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`.

Install the current stable versions. Do not invent version numbers. Commit `package-lock.json`.

One `tsconfig.json` only. No project references, so a plain `tsc --noEmit` works:

- `target` `ES2022`, `module` `ESNext`, `moduleResolution` `Bundler`, `jsx` `react-jsx`.
- `strict` true, `noUnusedLocals` true, `noEmit` true.
- `types`: `["vite/client", "@testing-library/jest-dom"]`.
- `include`: `["src", "vite.config.ts"]`.

`vite.config.ts` imports `defineConfig` from `vitest/config`, not from `vite`. Otherwise the `test` block is a type error.

- React plugin.
- `test.environment` `"jsdom"`, `test.globals` false, `test.setupFiles` `["./src/test/setup.ts"]`.
- Dev server port `5173`.
- Proxy `/media`, `/review`, and `/health` to `http://127.0.0.1:8000`. `changeOrigin: true`. Do not rewrite the path.

`src\test\setup.ts`:

```ts
import "@testing-library/jest-dom/vitest"
import { afterEach } from "vitest"
import { cleanup } from "@testing-library/react"

afterEach(() => cleanup())
```

With `globals` off, Testing Library cannot find `afterEach` on its own, so without this file every rendered component stays on the page for the next test.

`main.tsx` wraps `App` in `React.StrictMode`. In dev, StrictMode runs effects twice, so you will see two `GET /review` calls in the browser network tab. That is expected. Tests render without StrictMode.

`index.html` title: `Moderation`. Mount `<div id="root">`.

`App.tsx` renders an `h1` with the exact text `Moderation`. Nothing else yet.

## Docker

`Dockerfile` has two stages.

1. `node:20-alpine`. Copy package files, `npm ci`, copy the rest, `npm run build`.
2. `nginx:1.27-alpine`. Copy `dist` to `/usr/share/nginx/html`. Copy `nginx.conf` over `/etc/nginx/conf.d/default.conf`.

`nginx.conf`:

```nginx
server {
  listen 80;
  resolver 127.0.0.11 valid=10s;
  set $api http://api:8000;

  location ~ ^/(media|review|health) {
    proxy_pass $api;
    proxy_set_header Host $host;
  }

  location / {
    root /usr/share/nginx/html;
    try_files $uri $uri/ /index.html;
  }
}
```

The `resolver` line and the `$api` variable matter. A plain `proxy_pass http://api:8000;` looks up the API's address only once, when nginx starts. Two things go wrong with that:

- nginx refuses to start if the API is not up yet.
- After `docker compose stop api` and `start api`, the API can come back on a new address, and the page keeps getting `502`.

`127.0.0.11` is Docker's internal DNS. With a variable and no path after the host, nginx passes the request path through unchanged.

Do not add `proxy_intercept_errors`. A `503` from the API must stay `503`.

`.dockerignore`: `node_modules`, `dist`, `.env`, `evidence`.

Add `dist/` to the repo-root `.gitignore`. `node_modules/` is already there from the backend plan. Add it if it is not.

`.env.example` contains one line: `VITE_API_BASE_URL=`

Add a `web` service to `d:\MyWorkspace\MainProjects\Other\sebastian_test_task\docker-compose.yml`:

- Build `./frontend`.
- Ports `3000:80`.
- `depends_on` api with `condition: service_healthy`.

Do not give the web service `DATABASE_URL`, `REDIS_URL`, or the HMAC secret.

## Tests

`src\App.test.tsx`:

- `test_page_shows_title`. Render `App`. The heading is `Moderation`.

## How to run

```powershell
cd d:\MyWorkspace\MainProjects\Other\sebastian_test_task\frontend
npm install
npm test
npm run dev
```

Open `http://127.0.0.1:5173`. You should see `Moderation`. Stop the dev server with Ctrl+C.

From the repo root, with Docker Desktop running:

```powershell
docker compose up -d --build web
```

Open `http://127.0.0.1:3000`. Same heading. Leave Compose up for the later phases.

## Done when

- `npm test` passes.
- Both URLs show `Moderation`.
- No `fetch` exists under `src`.

## Report, then stop

```text
Phase 1 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: <pass or fail>
```
