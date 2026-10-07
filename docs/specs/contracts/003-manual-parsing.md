# Contract 003 — Manual parsing

Spec: docs/specs/specs/003-manual-parsing.md (+ instruction 009) · Builds on contracts 001 and 002 (same base URL, CORS, error shape, no auth).

## Run lifecycle change
Creating a run (`POST /test-runs`, contract 002) still returns `201` with `status: "created"`, then immediately schedules a background parse job. Status moves `created -> parsing -> parsed`, or `-> failed` with `error`. `parsing`/`parsed` are the only new transitions in this spec (`running`/`done` belong to spec 004).

`test_run` gains: `error: string | null` (human-readable reason when `status = "failed"`, else null). It is returned by `POST /test-runs` (null) and `GET /test-runs/{id}`.

## GET /test-runs/{id}  (extended)
`200`: `{ "id", "manual_id", "base_url", "status", "error", "created_at" }` · `404 test_run_not_found`.

## GET /test-runs/{id}/steps
`200`:
```json
{
  "run_id": "<uuid>",
  "status": "parsed",
  "test_cases": [
    { "id": "<uuid>", "title": "Login", "order": 1,
      "steps": [
        { "id": "<uuid>", "order": 1, "action": "open", "target": "login page",
          "value": null, "expected": null, "unclear": false }
      ] }
  ]
}
```
- `action` is one of: `open, click, type, select, check, assert_text, assert_visible, wait`.
- `value`, `expected`: string or null. `unclear`: boolean.
- While `status` is `created`/`parsing`/`failed`, `test_cases` is `[]` (and `GET` still returns 200 so the UI can poll one endpoint).
- `404 test_run_not_found` for unknown id.

## Parse output schema (LLM -> backend, validated)
`{ "test_cases": [ { "title": str, "steps": [ { "order": int>=1, "action": <enum above>, "target": str, "value": str|null, "expected": str|null, "unclear": bool } ] } ] }`
Rules: extract only what the manual states; keep the manual's language for text, English for `action`; flag vague parts `unclear: true`; schema mismatch -> retry once -> run `failed`. Long manuals are chunked at paragraph/heading boundaries and merged in order.

## Providers
`LLM_PROVIDER` = `claude_cli` (default) | `anthropic` | `openrouter` | `gemini`. Keys: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`; models: `ANTHROPIC_MODEL`, `OPENROUTER_MODEL`, `GEMINI_MODEL`, `CLAUDE_CLI_MODEL` (default `sonnet`), `CLAUDE_CLI_TIMEOUT_S` (default 120). `claude_cli` runs `claude -p --output-format json` as a subprocess from an empty temp dir, prompt on stdin, answer in JSON `result`; confirm minimal-context flags from `claude --help`. `PARSE_CHUNK_CHARS` configurable. Missing key/CLI, not logged in, timeout -> run `failed` with a clear `error`.

## Errors
No new endpoint-level error codes; failures surface through `status = "failed"` + `error`.

## Data
`test_case { id, run_id, title, order }`, `step { id, test_case_id, order, action, target, value?, expected?, unclear }`; `test_runs.error` column added (create_all will not alter an existing table: backend must add the column safely, e.g. check/ALTER on startup, since `app.db` already exists).

## Frontend behavior
- After Start succeeds, show run id/status as in 002 and poll `GET /test-runs/{id}` every 2 s until status is `parsed` or `failed` (stop polling on unmount/new submit; give up politely after ~5 min).
- `parsing`/`created`: "Parsing manual…". `failed`: show `error`. `parsed`: fetch `GET /test-runs/{id}/steps` and render test cases with ordered steps (action, target, value, expected); `unclear` steps visibly marked with a note that they will be skipped. No editing.
- Execution UI is out of scope (spec 004).

## Layout
Backend: extend `api/app` (providers under `app/services/llm/`, parsing service, repositories, models, routers, background task); tests in `api/tests` mocking all providers; no real LLM calls in tests. Frontend: extend `web/src` (API client in `src/lib/api.ts`, steps view in `src/features/manual`).

## Notes (added at reconcile)
- Retry-once applies only to malformed JSON / schema mismatch; provider errors (CLI missing, not logged in, timeout, no key) fail the run immediately.
- Step and test case `order` are renumbered from 1 on save; zero test cases extracted -> run `failed`.
- Extra env `LLM_HTTP_TIMEOUT_S` (default 120). Default model names for anthropic/openrouter/gemini are unverified guesses.
- `claude_cli` flags: `-p --output-format json --tools "" --strict-mcp-config --disable-slash-commands --no-session-persistence --setting-sources ""`; `--bare` is NOT used because it ignores the logged-in OAuth account.

## Addendum 2026-10-07 — field rules (instruction 013)
Parse output schema gains optional `field_rules`: `[ { "field": str, "rule": str|null, "valid": [str] (max 5), "invalid": [str] (max 5) } ]`; take only what the manual states; absent/invalid -> `[]` (a bad `field_rules` must not fail the whole parse). Persist per run (new table `field_rules`: id, run_id, field, rule, valid JSON, invalid JSON; replaced on re-parse). `GET /test-runs/{id}/steps` response gains top-level `"field_rules": [ { "field", "rule", "valid", "invalid" } ]` (default `[]`). Update the LLM prompt: extract field-level rules and example values (e.g. "Phone must be 11 digits starting with 01"); do not invent rules.
