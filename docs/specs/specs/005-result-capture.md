---
id: "005"
title: Result capture
status: draft
date: 2026-10-05
instruction: docs/specs/instructions/005-result-capture.md
---

## Summary
Persist what the executor (spec 004) reports for each step, including a screenshot, and expose per-step results and a computed run summary for the report (R-006).

## Problem & Goal
The executor emits outcomes but stores nothing. Goal: a durable, complete record of every step so reports and history can be built from it without re-running tests.

## Scope
- `step_result` data model and storage.
- Screenshot capture and file storage.
- Computed summary for a run and each test case.
- Secret masking.

Out of scope: rendering/exporting reports, run list, retention, video.

## Analysis
- Depends on 004 (outcome per step) and 003 (steps, test cases).
- Risks: large disk usage from per-step screenshots; secrets leaking via screenshots, error text or typed values; partial results if a run crashes midway; screenshot timing on slow or animated pages.

## Design
- **Capture hook:** the executor calls `record_result(step, outcome)` after each step; the result is written immediately so a crashed run still keeps what completed.
- **Screenshots:** after every step take a viewport PNG; on failure also a full-page PNG. Saved at `<storage>/runs/<run_id>/<step_id>[-full].png`. Skipped steps get no screenshot.
- **Data:** `step_result { id, run_id, step_id, status: passed|failed|skipped, error?, expected?, actual?, duration_ms, started_at, finished_at, screenshot_path?, fullpage_path? }`.
- **Masking:** values of `type` steps that target password fields, and any configured credentials, are replaced with `••••` in stored value, error and actual text.
- **Summary:** computed query/helper per run and per test case: `{ total, passed, failed, skipped, duration_ms, status }`; a test case is `failed` if any step failed, else `passed` (or `skipped` if all skipped).
- **API:** `GET /test-runs/{id}/results` -> test cases, steps with results, and summaries; `GET /test-runs/{id}/screenshots/{name}` serves a file, only for the run's owner.

- **Download:** each screenshot is served with a download header; `GET /test-runs/{id}/screenshots.zip` returns all of a run's screenshots as one ZIP.
- **Retention:** screenshot files are deleted 48 hours after creation (`SCREENSHOT_TTL_HOURS`, default 48) by an hourly background job. Only files are deleted; `step_result` rows stay with `screenshot_path` kept and a derived `screenshot_expired` flag (file missing or past TTL).
- **Expired state:** screenshot endpoints return 410 Gone with "Screenshot expired" after deletion.

## Acceptance & Test criteria
- After a run, every step has exactly one result with the right status.
- A failed step has an error message, expected vs actual for assertions, and both screenshots.
- A run that crashes midway still returns results for the steps that finished.
- Summary counts equal the number of step results by status.
- A password typed in a step appears only as `••••` in results and errors.
- A screenshot URL for another user's run returns 403/404.
- A screenshot older than 48 h is removed by the cleanup job; its endpoint returns 410 and the step result text remains.
- The ZIP contains every non-expired screenshot of the run.

## Deploy notes
Needs writable storage with enough space; storage path configurable. Consider cleanup in a later spec.

## Open questions
- Blur or redact sensitive regions in screenshots?

## Change log
- 2026-10-05: Added screenshot download (single and ZIP) and 48 h retention with hourly cleanup (instruction 008). Replaces "No retention policy". See docs/specs/instructions/008-stack-and-decisions.md.
