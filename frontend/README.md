# Travel Planner — Frontend

Next.js 16 frontend for the travel planning agent.

## Setup

**Requirements:** Node 18+

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Base URL of the FastAPI backend |

## Routes

| Path | Description |
|---|---|
| `/` | Trip list |
| `/trips/new` | Create a new AI-planned trip |
| `/trips/[tripId]` | Trip detail and replanning |

## Scripts

```bash
npm run dev      # development server
npm run build    # production build
npm run start    # serve production build
npm run lint     # ESLint
```

## Backend

Start the FastAPI backend first — see `../backend/README.md`.
