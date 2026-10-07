---
id: "007"
title: Run history
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-007: Run history — আগের test run ও report-এর তালিকা, আবার খোলা বা আবার চালানো.

## Assumptions & corrections
- The list shows per run: date/time, URL, manual name or first line, status, passed/failed/skipped counts, total duration; newest first.
- Pagination (20 per page) and a status filter (all / passed / failed / running).
- Clicking a row opens the report (R-006); a running run shows "In progress".
- "Run again" creates a new test run from the same manual and URL; the old run is untouched and parsing happens again.
- Credentials are not copied on re-run (they are never stored); the user supplies them again if needed.
- Deleting a run also deletes its results and screenshot files, after a confirmation.
- No login yet, so the single user owns all runs; multi-user needs a separate spec.
- No search or run-to-run comparison in this step.

## Agreed scope
List past runs, open their reports, re-run, and delete.

## Out of scope
Search, comparison between runs, scheduling, multi-user ownership, retention policies.
