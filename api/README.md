# Manual input + URL input + manual parsing API (specs 001, 002, 003)

FastAPI + SQLAlchemy (SQLite). Contract: `docs/specs/contracts/001-manual-input.md`.

## Run
```
cd api
python -m venv .venv && .venv\Scripts\activate     # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m playwright install chromium             # one-time, ~150 MB (spec 004)
copy .env.example .env                              # optional; env vars are read from the process environment
uvicorn app.main:app --reload --port 8000
```
Tables (`manuals`, `test_runs`) are created on startup. No migration tool (SQLite).

Note: `.env` is not loaded automatically; export the variables or pass them to the shell.

## Config (env)
`DATABASE_URL`, `STORAGE_DIR`, `MAX_UPLOAD_MB`, `CORS_ORIGINS` (comma separated).
Spec 002: `ALLOW_PRIVATE_URLS` (default `true`; when `false`, hosts resolving to private/loopback/link-local IPs are rejected, also on redirects), `URL_CHECK_TIMEOUT_S` (default `10`). The server needs outbound network access for `POST /test-runs`.

Spec 003 (parsing runs as a background task after `POST /test-runs`; `GET /test-runs/{id}/steps` returns the result):
- `LLM_PROVIDER`: `claude_cli` (default) | `anthropic` | `openrouter` | `gemini`.
- Keys/models: `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`, `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`, `GEMINI_API_KEY`/`GEMINI_MODEL`.
- `claude_cli`: `CLAUDE_CLI_MODEL` (default `sonnet`), `CLAUDE_CLI_TIMEOUT_S` (default `600`). Runs `claude -p --output-format json` from an empty temp dir with no tools, MCP, skills, settings/hooks/plugins or session files; prompt on stdin, answer in JSON `result`. Needs the `claude` CLI installed and logged in on the same machine. Local personal use only, not for server deployment or other users (check Anthropic's current terms). On Windows the npm shim is resolved to the native `claude.exe`.
- `PARSE_CHUNK_CHARS` (default `12000`): longer manuals are split at paragraph boundaries and merged in order. `LLM_HTTP_TIMEOUT_S` (default `120`) for the HTTP providers.
- Missing key/CLI, not logged in, timeout, or invalid output after one retry -> run `failed` with `error`.
- Tables `test_cases`, `steps` are created on startup; `test_runs.error` is added with ALTER TABLE if an older DB lacks it.

Spec 004 (`POST /test-runs/{id}/execute` spawns `python -m app.services.executor <run_id>` as a separate process; credentials go via stdin only; the Chromium window opens on the desktop of the user running the API, so local use only):
- `EXEC_HEADED` (default `true`; tests set `false`), `EXEC_SLOW_MO_MS` (default `300`; pause used only in phase 1, skipped in `fast_mode`), `MAX_MENUS` (default `30`), `EXEC_PAGE_TIMEOUT_S` (default `15`), `EXEC_OVERALL_TIMEOUT_S` (default `3600`; used when the execute body has no `max_minutes`; hitting it ends the run `done` with a "Stopped at the time limit" note).
- Form submit testing (instruction 011): `EXEC_SUBMIT_FORMS` (default `true`; per-request override `submit_forms` in the execute body), `MAX_FORMS_PER_PAGE` (default `5`), `MAX_FORMS` (default `50`). Each form on a visited menu page gets an `empty` and a `sample` submit step (`submit_form`); forms with delete/remove/logout-like buttons are never submitted. Execute is allowed while parsing; parsing only sets its final status if the run is still `parsing` and never touches the "Menu sweep" case.
- Validation matrix (instruction 013): `EXEC_VALIDATION_DEPTH` (`basic` = empty + sample only, `standard` = + format/boundary/blank, `thorough` = + special/unicode/long/XSS/SQL; default `thorough`; per-request `validation_depth` in the execute body, `422` for other values), `MAX_CASES_PER_FORM` (default `25`), `MAX_CASES` (default `200`). Per form, one field's value is replaced per case (other fields stay valid), the page is reloaded before each case, and the case is a `submit_form` step with `meta` (kind, category, field, form, source). New `error_type`s: `invalid_accepted`, `valid_rejected`, `xss_risk`, `sql_error`. Payloads are never destructive. The manual parse also extracts optional `field_rules` (table `field_rules`, returned as top-level `field_rules` of `GET /test-runs/{id}/steps`); they are matched to form fields by label/name/placeholder and added as `manual` cases. If the manual has not been parsed yet when execution starts, only tool-generated data runs and the note says so. `steps.meta` is added to existing databases at startup.
- Page actions (instruction 014): `EXEC_TEST_ACTIONS` (default `true`; per-request `test_actions` in the execute body, non-boolean -> `422`), `MAX_ACTIONS_PER_PAGE` (default `15`), `MAX_ACTIONS` (default `150`), `ACTION_DENY_EXTRA` (comma-separated words added to the denylist). After each menu page and its forms, visible buttons/links/tabs/row actions/pagination in the page body are deduplicated by signature (label + kind + href with ids as `:id`), the page is reloaded before each one, and each is a `click_action` step (`meta.kind = action`). Outcomes: new page (checked like a menu, then its forms), modal/drawer (its forms are tested; the page is reloaded and the action clicked again before every case), new tab/download, in-place change = passed; nothing happened = warning `action_no_effect`. Delete/remove/logout-like actions, external, `mailto:`/`tel:` links and downloads are never clicked. Actions inside pages reached by an action are not followed.
- Needs `python -m playwright install chromium`; if missing the run fails with that hint.
- New table `step_results` (create_all); `test_runs.sweep_note` is added with ALTER TABLE on older DBs. Screenshots go to `STORAGE_DIR/runs/<run_id>/`. Runs still `running` at API startup are marked `failed` ("Interrupted").
- Tests run headless against a local `http.server` fixture site.

## Test
```
pytest
```

## Layout
`app/routers` (HTTP) -> `app/services` (validation, extraction, orchestration) -> `app/repositories` (DB). `app/schemas.py`, `app/models.py`, `app/errors.py`, `app/config.py`, `app/db.py`.
