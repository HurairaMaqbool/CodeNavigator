# CodeNavigator — Next.js Frontend

Professional UI replacing Streamlit. Calls the existing FastAPI backend only — no pipeline changes.

## Run

1. Start backend: `uvicorn app.main:app --port 8000` (from repo root)
2. Copy env: `cp .env.local.example .env.local` and set `NEXT_PUBLIC_API_KEY` to match backend `API_KEY`
3. Dev server:

```bash
cd frontend-next
npm install
npm run dev
```

Open http://localhost:3000

## Routes

| Route | Feature |
|-------|---------|
| `/workspace` | Ingest, status stepper, chat, call graph |
| `/evaluation` | RAGAS eval, Golden CI, compare versions |
| `/platform` | Usage, subscription, audit log |

## Stack

Next.js 16 · TypeScript · Tailwind v4 · shadcn/ui · TanStack Query · Framer Motion · mermaid · Recharts

## Production build

```bash
npm run build
npm run start
```
