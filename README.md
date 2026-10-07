# nin-manual-test

Upload a user manual (or paste a URL) and a login, and the tool turns the manual into test steps, then runs them in a visible browser against your web app. It reports what passed, what failed and why, with screenshots.

## What it does
- Takes a manual (file upload) and the target app URL.
- Parses the manual into test cases and steps with an LLM.
- Drives Chromium (Playwright): sweeps menus, submits forms with a validation matrix (empty, sample, boundary, special characters, XSS and SQL probes), and clicks page actions.
- Never clicks delete, remove or logout-like actions.
- Shows results with a score, issues summary, error details, run history and Markdown export.

## Structure
| Folder | What |
|--------|------|
| `api/` | FastAPI + SQLAlchemy (SQLite) backend and the Playwright executor |
| `web/` | Next.js 16 + React 19 + Tailwind 4 frontend |
| `docs/specs/` | Instructions, contracts and specs for each feature |

## Quick start

### 1. API (port 8000)
```
cd api
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env          # optional
uvicorn app.main:app --reload --port 8000
```
By default the LLM provider is the local `claude` CLI (must be installed and logged in). To use an API instead, set `LLM_PROVIDER` to `anthropic`, `openrouter` or `gemini` plus its key. All settings are listed in [api/README.md](api/README.md).

### 2. Web (port 3000)
```
cd web
npm install
copy .env.example .env.local    # point it at the API
npm run dev
```
Open http://localhost:3000.

## Tests
```
cd api && pytest
cd web && npm run typecheck && npm run lint
```

## Notes
- Local use only: the browser window opens on the desktop of the user running the API.
- The `claude_cli` provider is for personal local use, not server deployment.
