# web — Manual input (spec 001)

Next.js App Router + TypeScript + Tailwind.

    cp .env.example .env.local   # set NEXT_PUBLIC_API_URL (default http://localhost:8000)
    npm install
    npm run dev                  # http://localhost:3000
    npm run build && npm run lint && npm run typecheck

API client: `src/lib/api.ts` (single place to change the backend URL / calls).
Backend must allow CORS for http://localhost:3000.
Page `/` submits pasted text (JSON) or a file (multipart) to `POST /manuals`, then shows the result and loads `GET /manuals/{id}` for a preview.
