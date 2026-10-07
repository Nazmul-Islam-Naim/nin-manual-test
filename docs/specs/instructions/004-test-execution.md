---
id: "004"
title: Test execution engine
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-004: Test execution engine — step অনুযায়ী URL-এ browser automation চালানো (Playwright, headless).

## Assumptions & corrections
- Playwright with headless Chromium; one fresh browser context per run.
- Target descriptions are resolved with Playwright accessible locators (role, label, text); if none match, an LLM picks the best element from a simplified DOM.
- Steps run sequentially. A failed step skips the remaining steps of that test case; the next test case still runs.
- Steps flagged `unclear` are not executed and are marked `skipped`.
- Per-step timeout 15 s; per-run limit 10 min.
- Optional login credentials supplied at run creation; used only during the run and never logged or shown in reports.
- Status `running` on start, `done` at the end; execution is a background job.
- Web only, Chromium only.

## Agreed scope
Execute parsed steps in a browser against the run's base URL and produce a per-step outcome.

## Out of scope
Persisting results and screenshots (R-005), reports (R-006), mobile or other browsers, parallel runs of one test case.
