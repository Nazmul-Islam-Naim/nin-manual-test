---
id: "007"
title: Run history
status: draft
date: 2026-10-05
instruction: docs/specs/instructions/007-run-history.md
---

## Summary
Give users a list of past test runs with quick access to each report, the ability to run the same manual and URL again, and to delete runs.

## Problem & Goal
Runs are stored but invisible. Goal: let users find earlier results, repeat a test without re-entering anything, and clean up.

## Scope
- Paginated, filterable run list (API and UI).
- Link to the report for each run.
- Re-run action.
- Delete action with confirmation.

Out of scope: search, comparison, scheduling, multi-user, retention.

## Analysis
- Depends on 002 (`test_run`, `manual_id`, `base_url`), 005 (results and screenshots, summary), 006 (report), 001 (manual, for display name).
- Risks: slow list queries as runs grow (summaries computed per row); deleting a run that is still executing; orphaned screenshot files if deletion fails midway; re-run without credentials producing a run that fails at login.

## Design
- **List API:** `GET /test-runs?page=1&page_size=20&status=` returns `{ items: [{ id, created_at, base_url, manual_title, status, summary: { total, passed, failed, skipped }, duration_ms }], total }`, newest first. Status filter values: all, passed, failed, running. Summary counts come from one grouped query over `step_result`, not a query per row. `manual_title` is the filename or the first line of the text, truncated.
- **UI:** a "History" page with a table, status filter, pagination; row click opens the report; each row has "Run again" and "Delete".
- **Re-run:** `POST /test-runs/{id}/rerun` creates a new run with the same `manual_id` and `base_url`, status `created`, and starts parsing. Returns the new run. Optional body `{ credentials? }` for login.
- **Delete:** `DELETE /test-runs/{id}` removes the run, its test cases, steps, results and the screenshot folder `runs/<id>/`. Refused with 409 while the run is `parsing` or `running`. The UI asks for confirmation first.
- **Display status:** `passed` if finished with no failed steps, `failed` if any step failed or the run failed, `running` while `parsing`/`running`.

- **Stack:** History page in Next.js; list/re-run/delete endpoints in FastAPI.
- **Expired screenshots:** the list is unaffected by cleanup; opening a report shows "Screenshot expired" where files are gone. Deleting a run still removes any remaining files.

## Acceptance & Test criteria
- The list shows the newest run first with correct counts and durations.
- Filtering by `failed` returns only runs with a failed step or a failed run.
- Pagination returns 20 per page and a correct total.
- Clicking a row opens that run's report.
- Re-run creates a new run with the same manual and URL and leaves the old run unchanged.
- Deleting a finished run removes its DB rows and screenshot files; deleting a running run returns 409.
- The list does not run one query per row (checked with a query count in a test).

## Deploy notes
Index `test_run.created_at` and `step_result.run_id` for list performance. Deletion needs write access to the screenshot storage.

## Open questions
- Add search by URL or manual name later?
- Auto-delete whole runs (not just screenshots) after N days?

## Change log
- 2026-10-05: Stack and screenshot-expiry behavior (instruction 008). See docs/specs/instructions/008-stack-and-decisions.md.
