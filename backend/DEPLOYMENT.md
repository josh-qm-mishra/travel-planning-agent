# Backend — Deployment Guide

## Required environment variables

| Variable | Description | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key for the planning agent | Yes (production) |
| `GOOGLE_API_KEY` | Google Maps API key (Places + Routes) | Yes (production) |
| `DATABASE_URL` | SQLAlchemy async connection string | Yes (production) |
| `CORS_ORIGINS` | JSON array of allowed frontend origins | Recommended |
| `OPENAI_MODEL` | OpenAI model name (default: `gpt-4o`) | No |
| `LOG_LEVEL` | Python logging level (default: `INFO`) | No |
| `APP_DEBUG` | Enable FastAPI debug mode (default: `false`) | No |

Set these via your hosting platform's secret manager or a `.env` file at the repository root.  
**Never commit real credentials.**

### Example DATABASE_URL formats

```
# PostgreSQL (production)
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/travel_planning

# SQLite (local development only)
DATABASE_URL=sqlite+aiosqlite:///./travel_planning.db
```

### Example CORS_ORIGINS

```
CORS_ORIGINS=["https://your-frontend.example.com"]
```

---

## Database migrations (Alembic)

All schema changes are managed by Alembic.  Commands must be run from the `backend/` directory.

### Fresh database (new production deployment)

```bash
cd backend
alembic upgrade head
```

This creates the `trips` table and all subsequent schema additions in one step.

### Existing database that was created before Alembic was introduced

The pre-Alembic schema already has the `trips` table.  
**Do not** run `alembic upgrade head` directly — it would try to create an already-existing table.

Instead:

```bash
cd backend
# 1. Mark the initial migration as already applied (no DDL executed).
alembic stamp a1b2c3d4e5f6

# 2. Apply all subsequent migrations (e.g. adds the version column).
alembic upgrade head
```

### Applying future migrations

```bash
cd backend
alembic upgrade head
```

### Checking current state

```bash
alembic current          # which revision the database is at
alembic history          # full migration chain
alembic check            # verify models match the database (no pending changes)
```

### Rolling back one step

```bash
alembic downgrade -1
```

---

## Starting the server

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The server runs `create_all` on startup as an idempotent fallback for development; this has no effect on a properly migrated PostgreSQL database since the tables already exist.  In production, always run `alembic upgrade head` **before** starting the server.

---

## Health and readiness endpoints

| Endpoint | Purpose | External calls |
|---|---|---|
| `GET /health` | Liveness probe — always fast | None |
| `GET /ready` | Readiness probe — checks DB connectivity | None |

Use `/ready` as the Kubernetes/load-balancer readiness check.  
Use `/health` as the liveness check.

---

## Optimistic concurrency / replan conflicts

Every trip record has a `version` integer (starts at 1, increments on each replan).

The `POST /trips/{id}/replan` endpoint accepts an optional `expected_version` field.  
When provided:

- The update is executed as `WHERE id = ? AND version = expected_version`.
- If the trip was modified concurrently the statement matches zero rows and the server returns **HTTP 409**.
- The frontend displays an amber notice telling the user to refresh and retry.

This prevents silent data loss when two browser tabs or users replan the same trip simultaneously.

---

## Logging

The application logs structured key=value pairs to stdout at `INFO` level by default.

Key log events:

| Event | Level | When |
|---|---|---|
| `startup` | INFO | Application starting |
| `startup_complete` | INFO | Database ready |
| `trip_planning_started` | INFO | POST /trips received |
| `trip_planning_succeeded` | INFO | Agent returned a valid itinerary |
| `trip_planning_failed` | ERROR | Agent raised PlanningError |
| `trip_planning_validation_failed` | WARNING | Validation exceeded attempts |
| `trip_replan_started` | INFO | POST /trips/{id}/replan received |
| `trip_replan_succeeded` | INFO | Replan stored successfully |
| `trip_replan_failed` | ERROR | Replan raised PlanningError |
| `trip_replan_conflict` | WARNING | Optimistic concurrency conflict (409) |
| `readiness_check_failed` | ERROR | /ready — DB unreachable |
| `shutdown` | INFO | Application shutting down |

Set `LOG_LEVEL=DEBUG` only during development — it is noisy.

---

## Input limits

These limits are enforced by Pydantic at the API boundary (returns HTTP 422):

| Field | Limit |
|---|---|
| `destination` | max 200 characters |
| `start_date` / `end_date` | trip duration < 30 days |
| `interests` | max 20 tags, each ≤ 60 characters |
| `food_preferences` | max 20 tags, each ≤ 60 characters |
| `total_budget` | max $1,000,000 |
| `change_request` | 1 – 2000 characters |

---

## Anonymous ownership model

Each trip is associated with an anonymous browser session rather than a user account.

### How it works

1. The frontend generates a random 32-byte hex token (`tpa_client_id`) on first visit and persists it in `localStorage`.
2. Every API request includes an `X-Client-ID: <token>` header.
3. The server hashes the token with SHA-256 (`owner_hash`) and stores the hash in the `trips.owner_hash` column.  The raw token is **never stored or logged**.
4. All trip endpoints — list, get, replan — filter by `owner_hash`, so a visitor can only see and modify their own trips.
5. Requests without an `X-Client-ID` header are rejected with HTTP 401.
6. Requests for a trip that belongs to another owner return HTTP 404 (not 403), avoiding information disclosure.

### Security limitations

| Limitation | Notes |
|---|---|
| **No true authentication** | Possession of the raw token is the only credential.  Anyone who obtains a visitor's `localStorage` value can impersonate them. |
| **Client-side secret** | The token lives in browser `localStorage` — visible to JavaScript running on the same origin.  XSS on the frontend would expose it. |
| **Single-device** | The token is not shared across browsers or devices; a visitor using a different browser sees no trips. |
| **Clearing storage** | If a visitor clears `localStorage` (or uses private browsing), a new token is generated and their previous trips are no longer accessible. |
| **Orphaned rows** | Trips created before this migration have `owner_hash=''`, which no valid browser request can match; they are effectively abandoned. |

This model is appropriate for a public portfolio / demo deployment.  Add proper authentication (e.g. OAuth, magic links) before storing sensitive user data.

---

## Rate limiting

`POST /trips` and `POST /trips/{id}/replan` are subject to a per-owner sliding-window rate limit to protect paid OpenAI API costs.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | `5` | Maximum AI planning requests per owner per minute |
| `RATE_LIMIT_PER_HOUR` | `20` | Maximum AI planning requests per owner per hour |

Set these in `.env` or your platform's environment variables.

### Response when limited

```
HTTP 429 Too Many Requests
Retry-After: <seconds>

{"detail": "Too many planning requests. Please wait and try again."}
```

The frontend surfaces a user-friendly amber message and the user can retry after the indicated delay.

### Single-instance limitation

The rate limiter is **in-process and in-memory**.  It resets on server restart and does not coordinate across multiple uvicorn workers or replicas.

For a single-process demo deployment this is acceptable.  For multi-worker or multi-replica deployments, replace the in-memory limiter with a shared store (Redis, database counters, or your platform's API gateway rate limiting).

---

## Public deployment considerations

Before exposing this service to public internet traffic:

### Additional rate limiting

Consider adding edge-level rate limiting in front of the application layer:
- Cloudflare Workers, AWS API Gateway, or Vercel middleware can rate-limit by IP address.
- A reverse proxy (nginx, Caddy) can add request rate limits per source IP.

This complements the per-owner in-process limiter above.

### Authentication

The current ownership model is anonymous (browser token only).  Every visitor can read and modify their own trips but not others'.  There is no concept of user accounts, passwords, or sessions.  Add proper authentication before storing sensitive user data.

### CORS

Set `CORS_ORIGINS` to the exact URL(s) of your deployed frontend.  The default allows only `localhost:3000` and `localhost:3001`.

### HTTPS

Terminate TLS at the load balancer / reverse proxy level.  Do not run uvicorn directly on port 443 in production.

### Secrets management

Do not pass secrets via command-line arguments (they appear in process lists).  Use environment variables set via your platform's secret store.
