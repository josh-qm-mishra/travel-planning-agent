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

## Public deployment considerations

Before exposing this service to public internet traffic:

### Rate limiting

The planning and replan endpoints make paid OpenAI API calls.  The current implementation has **no rate limiting**.

Options for rate limiting before public launch:
- Use your hosting platform's gateway/edge layer (e.g. Cloudflare Workers, AWS API Gateway, Vercel middleware) to rate-limit by IP.
- Add an authentication layer so only authorized users can plan trips.
- Deploy behind a reverse proxy (nginx, Caddy) configured with request rate limits.

An in-memory Python rate limiter is **not** safe for production because it resets on restart and does not work across multiple worker processes.

### Authentication

Currently there is no user authentication.  Every caller can read and modify every trip.  Add authentication before exposing the API publicly.

### CORS

Set `CORS_ORIGINS` to the exact URL(s) of your deployed frontend.  The default allows only `localhost:3000` and `localhost:3001`.

### HTTPS

Terminate TLS at the load balancer / reverse proxy level.  Do not run uvicorn directly on port 443 in production.

### Secrets management

Do not pass secrets via command-line arguments (they appear in process lists).  Use environment variables set via your platform's secret store.
