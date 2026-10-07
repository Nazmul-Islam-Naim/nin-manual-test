---
id: "005"
title: Result capture
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-005: Result capture — প্রতি step-এর pass/fail, error message ও screenshot রাখা.

## Assumptions & corrections
- A viewport screenshot is taken after every step; failed steps additionally get a full-page screenshot.
- Screenshots are PNG files in storage; the DB keeps only the path.
- Results are stored for every step (passed, failed, skipped), not just failures.
- Per step store: status, error message, expected vs actual (for assertions), duration, start/end time, screenshot path.
- Run summary (total, passed, failed, skipped, total time) is computed from step results, not stored separately.
- Credentials never appear in results or errors; password values typed in `type` steps are masked (`••••`).
- Screenshots may show sensitive data, so they are accessible only to the run's owner.
- No retention policy in this step.

## Agreed scope
Persist per-step outcomes and screenshots from the executor and expose them with a computed summary.

## Out of scope
Report rendering/export (R-006), run history list (R-007), retention/cleanup, video recording.
