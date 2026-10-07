# Contract 002 — URL input

Spec: docs/specs/specs/002-url-input.md · Builds on contract 001 (same base URL, CORS, error shape, no auth).

## Data: `test_run`
| field | type | note |
|---|---|---|
| id | string (uuid4) | |
| manual_id | string | FK to manual (001) |
| base_url | string | normalized |
| status | `"created"\|"parsing"\|"running"\|"done"\|"failed"` | this spec only creates `created` |
| created_at | string (ISO 8601 UTC) | |

## POST /test-runs
Request `application/json`: `{ "manual_id": "<uuid>", "url": "<string>" }`

Normalize `url`: trim; if no scheme prepend `https://`; only `http`/`https` allowed; host required; strip fragment.
Reachability (server-side, httpx): HEAD, fall back to GET on 403/405; follow max 5 redirects; 10 s timeout (`URL_CHECK_TIMEOUT_S`). Any HTTP response = reachable. DNS failure, connection refused, timeout = unreachable.
Private/loopback hosts: allowed when `ALLOW_PRIVATE_URLS=true` (default); when false, resolve the host and reject private, loopback and link-local ranges with `private_url_blocked`.

Success `201`: `{ "id", "manual_id", "base_url", "status": "created", "created_at", "warning": null | "<string>" }`
`warning` is set (e.g. "Site responded with HTTP 404") when the final response is 4xx/5xx; the run is still created.

## GET /test-runs/{id}
`200`: same shape as POST success (without `warning`; field omitted or null) · `404 test_run_not_found`.

## Errors (same shape as 001: `{ "error": { "code", "message" } }`)
| status | code | when |
|---|---|---|
| 404 | manual_not_found | `manual_id` unknown |
| 404 | test_run_not_found | GET unknown id |
| 422 | invalid_url | empty, bad scheme, no host, malformed |
| 422 | invalid_request | missing/non-string `manual_id` or `url`, bad JSON |
| 400 | url_unreachable | DNS failure, refused, timeout |
| 400 | private_url_blocked | blocked by `ALLOW_PRIVATE_URLS=false` |

## Frontend behavior
- Same page `/`: below the manual input add a URL field (label "Website URL", placeholder `https://example.com`) and a "Start" button.
- Start flow: submit manual (`POST /manuals`, reuse the id if already submitted and unchanged) then `POST /test-runs`; show run id, normalized `base_url`, status, and the `warning` if present.
- Map each error code to an inline message using `error.message`; disable Start while submitting.
- Parsing/execution UI is out of scope (specs 003/004).

## Layout
Backend: extend `api/app` (routers, services, schemas, repositories, models); tests in `api/tests`. Frontend: extend `web/src` (API client in `src/lib/api.ts`, form in `src/features/manual`).

## Notes (added at reconcile)
- Check order: manual_id lookup (404) -> URL normalize (422) -> network check (400).
- With `ALLOW_PRIVATE_URLS=false`, DNS is resolved at every redirect hop (SSRF guard).
- More than 5 redirects ending in 3xx counts as reachable, not an error.
- Private mode + DNS failure -> `url_unreachable`.
