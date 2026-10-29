# Prompt: Build a categorized application logger (inspired by Uranus backend)

You are implementing logging for a backend service. Follow this design closely.
Prefer a single shared logger facade over ad-hoc `print` / raw `logging.getLogger(__name__)` calls in business code.

---

## Goals

1. **Human-scannable terminal logs** during local/dev (colored, labeled categories, optional emojis).
2. **Priority filtering** so the same code can run quiet (prod-ish) or very verbose (debug) via env.
3. **Correlation IDs** that tie request → outbound HTTP → webhooks → jobs → errors → API error JSON.
4. **Sensitive data redaction** for headers/tokens in logged payloads.
5. **Category methods** (not free-form levels only) so grepping is consistent: `BUSINESS`, `PIPELINE`, `WEBHOOK_IN`, `ERROR`, etc.

Do **not** invent a second logging style. All app code should call the shared facade.

---

## Architecture

### Single facade + stdlib underneath

- One module exports:
  - `logger` — the categorized facade instance
  - `correlation_manager` — generates 8-char IDs and tracks elapsed time per ID
  - `apply_log_settings(...)` — apply settings from config/env at startup
  - `format_json(...)` — safe JSON dump with truncation + redaction
- Internally use Python `logging.Logger` with a **single StreamHandler to stdout**.
- Formatter: `%(asctime)s.%(msecs)03d - %(message)s` with datefmt `%Y-%m-%d %H:%M:%S`
- `propagate = False` on the app logger
- Silence noisy third-party loggers to WARNING: access logs, HTTP clients, SQL engine/pool, vector DB clients, etc.
- On Windows, reconfigure stdout to UTF-8 (errors=replace) so emoji category markers don’t crash the process.

### Config (env / settings)

| Setting | Values | Default | Meaning |
|---------|--------|---------|---------|
| `LOG_DETAIL_LEVEL` | `none` \| `high` \| `mid` \| `low` | `mid` | Verbosity gate |
| `LOG_ENABLE_EMOJIS` | bool | `true` | Prefix icons |
| `LOG_JSON_MAX_SIZE` | int | `50000` | Truncate JSON payloads |
| `LOG_JSON_MAX_DEPTH` | int | `10` | Nested object depth cap |

At startup: call `apply_log_settings` from loaded Settings, then print a **banner that always shows** active detail level (not gated by the level itself).

### Priority model (most important)

```text
NONE (0) < HIGH (1) < MID (2) < LOW (3)

--

Gate rule: emit if LOG_DETAIL_LEVEL >= method_priority.

Interpretation:

none — almost silent (except always-on banners / rare critical ops alerts)
high — errors, warnings, auth failures, webhook failures only (prod-friendly)
mid — normal ops: HTTP req/res, outbound API, job start/end, system lifecycle, pipeline steps
low — verbose: payloads, cache hit/miss, business step trails, WS progress ticks, webhook detail
Map methods to priorities deliberately (see category table below). Do not make every line MID.

Line format
Every categorized line should look like:


2026-09-28 12:34:56.789 - 📥 [AB12CD34] REQ GET /api/v1/videos from 127.0.0.1
Structure:

Timestamp (handler formatter)
Optional emoji (if enabled)
Optional ANSI color around [cid] LABEL
Message body (plain, grep-friendly key=value pairs)
Emitted shape inside the logger:


{emoji}{color}[{correlation_id}] {LABEL}{reset} {message}
If no correlation id: omit [cid].

Colors (ANSI):

BLUE — outbound / job start
CYAN — inbound server / system / auth attempt / WS connect / pipeline
GREEN — success / 2xx–3xx / auth ok / cache hit
YELLOW — warn / 4xx / auth fail / webhook fail
RED — errors / 5xx / job failed
MAGENTA — business / webhook in
GREY — payload / detail / progress ticks
BOLD+RED — critical / rare operational alerts
Correlation IDs
Generation
8 chars from [A-Z0-9] (easy to spot in terminals and support tickets).
Thread-safe timer map: start(cid), elapsed(cid), clear_correlation(cid).
Lifecycle
HTTP middleware generates cid on request start → store on request.state.correlation_id.
Log REQ with method/path/client.
Downstream code may reuse the same cid (outbound calls, errors).
On response: log RES with elapsed + status; set response header X-Correlation-ID: {cid}; clear timer.
On unhandled exception: log with same cid; include correlation_id in JSON error body.
Outbound HTTP / webhooks / jobs may mint their own cid when not inside a request, and pass it through request/response pair methods.
API error JSON (always include when available)

{
  "error_code": "...",
  "message": "...",
  "extra": {},
  "correlation_id": "AB12CD34"
}
Also return X-Correlation-ID on successful responses.

Category methods (implement these)
Use named methods, not only info/warning/error. Business code should call the semantic method.

Method	Label	Priority	When to use
api_request_out(url, method=, payload=, correlation_id=)
API_REQUEST_OUT
MID (+ payload at LOW)
Outbound HTTP starting; returns cid
api_response_in(url, status=, correlation_id=)
API_RESPONSE_IN
MID
Outbound HTTP finished; show elapsed
webhook_in(name, payload=, source=)
WEBHOOK_IN
HIGH
Inbound webhook accepted; returns cid
webhook_out(name, payload=, source=, correlation_id=)
WEBHOOK_OUT
MID
Fan-out / outbound webhook
webhook_fail(name, source=, error=, correlation_id=)
WEBHOOK_FAIL
HIGH
Signature fail / processing fail
webhook_detail(msg, correlation_id=)
WEBHOOK
LOW
High-frequency webhook ticks
ws_connect(path=, client=)
WS_CONNECT
MID
WebSocket accept; returns cid
ws_progress(msg, correlation_id=)
WS_PROGRESS
LOW
WS lifecycle / progress chatter
server_request_in(method=, path=, client=)
REQ
MID
Inbound HTTP; returns cid
server_response_out(status=, path=, correlation_id=)
RES
MID
Inbound HTTP done; elapsed + status color
auth_attempt(msg, correlation_id=)
AUTH_ATTEMPT
MID
Auth in progress
auth_success(msg, correlation_id=)
AUTH_OK
MID
Auth succeeded
auth_fail(msg, correlation_id=)
AUTH_FAIL
HIGH
Auth rejected
business_flow(msg, step=, correlation_id=)
BUSINESS
LOW
Domain milestones (billing, grants, chat turns)
job_start(msg)
JOB_START
MID
Background job start; returns cid
job_end(msg, status=, correlation_id=)
JOB_END
MID
Background job end; elapsed
cache_hit / cache_miss / cache_set / cache_invalidate
CACHE_*
LOW
Cache diagnostics
log_level_banner(service, detail_level=, extra=)
LOG_CONFIG
always
Startup config line
system_info(msg, correlation_id=)
SYSTEM
MID
Lifecycle, recovery, workers started
pipeline(msg, correlation_id=)
PIPELINE
MID
Long multi-step flows; grep-friendly
critical_info(msg)
CRITICAL
always-ish (WARNING)
Must-see operational alerts
error_trace(msg, exc_info=True, correlation_id=)
ERROR
HIGH
Exceptions with traceback
error_detail(msg, correlation_id=, **extra)
ERROR_DETAIL
HIGH
Structured error fields without forcing TB
warning(msg, correlation_id=)
WARN
HIGH
Recoverable problems
Optional domain-specific always-on alert (example pattern):

Rare bandwidth/cost alert methods that bypass normal quietness and print a visual separator (====...====).
Pairing rules
Always pair:

server_request_in ↔ server_response_out (same cid)
api_request_out ↔ api_response_in (same cid)
job_start ↔ job_end (same cid)
webhook_in → later business_flow / webhook_fail with same cid
Message style conventions
Write messages for grep, not prose paragraphs.

Good:


broadcast enqueued id=... audience=all recipient_count=42 actor=admin@example.com
job=... video=... step=gpu_submit account=local status=409
resend send failed (429): rate_limited
signup_bonus granted user=... amount=150
Rules:

Prefer key=value tokens separated by spaces.
Include stable IDs early: user=, job=, video=, broadcast=, session=.
Include a step= when logging multi-step domain flows.
Never log secrets: API keys, JWTs, webhook signatures, cookies, raw Authorization headers.
When logging outbound request payloads, pass a sanitized subset (e.g. to/subject/id), not full credential headers.
Truncate large bodies; redact known sensitive header/key names to <redacted>.
For high-frequency events (stage progress ticks), use LOW detail helpers so mid stays readable.
Errors: short human reason + ids; let error_trace attach traceback.
Sensitive keys to redact in JSON helpers (case-insensitive match): authorization, x-api-key, cookie, paddle-signature, svix-signature, and any project-specific signature headers.

JSON dump rules:

Cap list length (e.g. first 50 items)
Cap depth
Cap string size with …<truncated>
default=str for non-JSON types
HTTP middleware pattern

cid = logger.server_request_in(method, path, client)
request.state.correlation_id = cid
try:
    response = await call_next(request)
except Exception:
    clear cid timer
    raise
logger.server_response_out(status, path, correlation_id=cid)
clear cid timer
response.headers["X-Correlation-ID"] = cid
return response
Skip or keep quiet for health checks if access noise becomes a problem (optional).

Exception handler pattern
Known domain exceptions → JSON with error_code, message, extra, correlation_id from request.state
Unexpected exceptions → logger.error_trace(..., correlation_id=cid) + optional Sentry capture tagged with cid/path → generic 500 JSON including correlation_id
Domain helper pattern (recommended for long pipelines)
For multi-stage flows (ingest, billing fulfillment, media processing), add a thin helper — do not sprinkle inconsistent strings.

Example shape:


STEP_VIDEO_CREATE = "video_create"
STEP_GPU_SUBMIT = "gpu_submit"
STEP_JOB_SUCCEEDED = "job_succeeded"
STEP_JOB_FAILED = "job_failed"
def pipeline_log(step, *, job_id=None, video_id=None, correlation_id=None, **fields) -> str:
    msg = f"job={job_id or '-'} video={video_id or '-'} step={step} " + " ".join(
        f"{k}={v}" for k, v in fields.items() if v is not None
    )
    if step in (STEP_JOB_SUCCEEDED, STEP_JOB_FAILED):
        cid = correlation_id or logger.pipeline(msg, correlation_id=correlation_id)
        logger.job_end(msg, status="ok" if step == STEP_JOB_SUCCEEDED else "failed", correlation_id=cid)
        return cid
    return logger.pipeline(msg, correlation_id=correlation_id)
Webhook ingress helper:

Important events → webhook_in (HIGH) + pipeline_log
High-frequency progress ticks → webhook_detail (LOW) only
Where each category belongs in code
Layer	Typical methods
Middleware
server_request_in / server_response_out
Auth deps
auth_attempt / auth_success / auth_fail
Routes
almost never log (keep thin); exceptions carry cid
Services (domain)
business_flow, system_info, pipeline_log, warning
Outbound HTTP clients
api_request_out / api_response_in + error_trace on failure
Webhook handlers
webhook_in / webhook_fail / business_flow
Background workers
system_info on start; error_trace on loop failures; job_start/job_end
Cache wrappers
cache_* at LOW
Startup/shutdown
log_level_banner, system_info, recovery error_trace
Anti-patterns (do not do)
print(...) in services/routes
Creating per-module stdlib loggers with inconsistent formats
Logging full Authorization / signature headers
Logging entire request/response bodies at MID (payloads are LOW only, truncated)
Prose novels: "User successfully completed the process of..." — use key=value
Emitting every cache hit at MID (will drown signal)
Generating a new correlation id on every log line of the same request
Forgetting to clear correlation timers (memory leak of timer map)
Relying on uvicorn access logs as the primary request log (use REQ/RES instead; silence access if redundant)
Minimal acceptance checklist for the other AI
One shared categorized logger module + exported singleton
Priority filter none|high|mid|low wired from settings
Correlation id on request state, response header, and error JSON
Outbound HTTP request/response pairing with elapsed time
Webhook in/fail categories
Business / pipeline / system / error methods used by services
JSON payload helper with redaction + truncation
Noisy libraries silenced
Startup banner always prints active log level
Example usage in at least: middleware, one outbound client, one webhook, one domain service, one worker
Example expected log sequence (happy path)

... LOG_CONFIG my-api log_detail_level=mid
... SYSTEM my-api started env=dev
... [A1B2C3D4] REQ POST /api/v1/videos from 10.0.0.2
... [A1B2C3D4] PIPELINE job=... video=... step=video_create source=youtube
... [A1B2C3D4] PIPELINE job=... video=... step=gpu_enqueue account=local
... [ZX98Y7W6] API_REQUEST_OUT POST https://gpu.example/submit
... [ZX98Y7W6] API_RESPONSE_IN [0.42s] 200 https://gpu.example/submit
... [A1B2C3D4] RES [1.10s] 202 /api/v1/videos
... [QWERTY12] WEBHOOK_IN gpu/progress
... [QWERTY12] PIPELINE job=... step=webhook_progress stage=transcribe
... [QWERTY12] PIPELINE job=... step=job_succeeded
... [QWERTY12] JOB_END [84.20s] job=... step=job_succeeded status=ok
When implementing, match this philosophy first; adapt label names only if the new domain truly needs new categories — do not collapse everything into generic info().


---
### How to use it
Paste that block as system/user instructions for the other AI, then add one line for their stack, e.g.:
> Target stack: FastAPI + Python 3.11. Put the logger under `app/core/logging/`. Wire middleware in `create_app()`. Keep Uranus-style categories and correlation behavior.
If you want, I can also drop this into a file under `overview/` or `docs/` in this repo.
