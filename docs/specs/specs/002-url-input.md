---
id: "002"
title: URL input
status: built
date: 2026-10-05
instruction: docs/specs/instructions/002-url-input.md
---

## Summary
Let a user provide the URL of the site to test, validate it, and create a test run that ties it to a submitted manual (spec 001).

## Problem & Goal
The executor needs a known, reachable target. Goal: reject bad URLs early and produce a `test_run` record that downstream steps (parsing, execution, report) share.

## Scope
- URL field alongside the manual input.
- Normalize and validate the URL.
- Create `test_run { manual_id, base_url, status: created }`.

Out of scope: credentials, crawling, multi-URL runs, running the test.

## Analysis
- Builds on spec 001 (`manual_id`).
- Risks: SSRF when the server fetches user URLs (mitigated by config to block private ranges); sites that block HEAD requests or bots; slow hosts; redirects to another domain.

## Design
- **Normalize:** trim; if no scheme, prepend `https://`; reject schemes other than http/https; strip fragment.
- **Validate:** parse URL (host required); reachability via HEAD, fall back to GET on 405/403; follow up to 5 redirects; 10 s timeout. Any HTTP response counts as reachable (even 4xx/5xx is reported as a warning, not a block); DNS failure, connection refused or timeout is a failure.
- **Config:** `ALLOW_PRIVATE_URLS` (default true). When false, resolve host and reject private/loopback ranges.
- **API:** `POST /test-runs` body `{ manual_id, url }` -> `{ id, manual_id, base_url, status: "created", warning? }`. `GET /test-runs/{id}`. Errors: 422 invalid URL, 400 unreachable, 404 unknown manual_id.
- **UI:** one form: manual input + URL + "Start" button; inline errors; warning shown if reachable but non-2xx.
- **Data:** `test_run { id, manual_id, base_url, status: created|parsing|running|done|failed, created_at }`.

- **Stack:** Next.js form posts to FastAPI `POST /test-runs`; reachability check done in FastAPI (httpx).

## Acceptance & Test criteria
- `example.com` is normalized to `https://example.com`.
- `ftp://x`, empty, or host-less input -> 422.
- Unresolvable or timed-out host -> 400 with a clear message.
- Reachable URL returns a run with status `created`; a 404 page returns the run with a warning.
- With `ALLOW_PRIVATE_URLS=false`, `http://127.0.0.1` is rejected.
- Unknown `manual_id` -> 404.

## Deploy notes
`ALLOW_PRIVATE_URLS` and timeout must be configurable. Outbound network access is required from the server.

## Open questions
- Should private URLs be blocked by default in a hosted deployment?

## Change log
- 2026-10-05: Stack fixed to Next.js + FastAPI (instruction 008). See docs/specs/instructions/008-stack-and-decisions.md.
