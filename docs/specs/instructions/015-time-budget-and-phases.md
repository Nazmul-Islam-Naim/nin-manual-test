---
id: "015"
title: Time budget and phases
date: 2026-10-07
status: frozen
---

## Original request
"Run failed: Overall time limit exceeded — eta kokhon dey" (when does this happen). Answer found in the code and the last run: the executor fails the run once elapsed time passes `EXEC_OVERALL_TIMEOUT_S` (default 900 s). The last run used 14.6 minutes: only 8 of 14 menus were visited because 132 validation-case steps (average 5.9 s) took about 12.5 minutes, and work was depth-first.

## Assumptions & corrections
- Two phases (breadth first). Phase 1: every menu visit, each form's empty/sample, and page actions. Phase 2: validation cases across all forms in round-robin order (one case per form per round) for as long as the time budget allows. Phase 1 collects "case jobs" (form, opener context, anchor step id); steps are still inserted after their anchor with `add_form_steps`, so the order seen in `/steps` is unchanged.
- Reaching the time limit is not a failure: the run ends `done`, the remaining steps stay pending (counted as "left"), and the sweep `note` says "Stopped at the time limit (<N> min); <X> checks were not run". `failed` is only for real errors (site not reachable, login failure, crash).
- Time limit: default 60 minutes. Execute body gains `max_minutes` (integer 1-240, other values 422 `invalid_request`); env `EXEC_OVERALL_TIMEOUT_S` default becomes 3600 and is used when the body omits `max_minutes`. UI select: 15 / 30 / 60 / 120 minutes, default 60.
- `test_runs` gains nullable `started_at`, `finished_at`, `max_minutes` (safe ALTER TABLE at startup); `GET /test-runs/{id}` and `GET /test-runs/{id}/steps` return them. UI shows "Elapsed mm:ss / limit"; the Markdown export uses `started_at` as "Started" (until now it showed `created_at`).
- Speed: the browser-level `slow_mo` is removed; a small `pace(page)` wait (`EXEC_SLOW_MO_MS`, default 300) is applied only to the watchable steps of phase 1 (highlight, click, sample fill). Phase 2 has no artificial delay. In case runs the networkidle wait drops from 3 s to 1.5 s. "Fast mode" (`fast_mode` in the execute body, default false) disables the pace and highlight delays entirely. Measure per-case time before and after; do not claim a number that was not measured.
- The deadline check stays between steps and cases; a single page operation may overrun slightly.

## Agreed scope
Two-phase scheduling, graceful stop at the time limit, selectable time budget with elapsed display and real start/finish times, and faster case execution.

## Out of scope
Resuming a stopped run, parallel browsers, estimating the total time before a run, sampling rows beyond one-per-type.
