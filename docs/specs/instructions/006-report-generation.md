---
id: "006"
title: Report generation
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-006: Report generation — Summary ও step-wise details screenshot সহ; screen-এ দেখা ও PDF/HTML download.

## Assumptions & corrections
- Report contents: title, URL, run time, totals (total/passed/failed/skipped), total duration, per-test-case status, per-step status, error, expected vs actual, screenshot.
- The on-screen report and the exports come from one template so they never differ.
- HTML export is a single self-contained file (screenshots embedded as base64) so it can be emailed or shared.
- PDF is produced from that HTML with Playwright (Chromium); no new library.
- Failed test cases and steps are expanded and highlighted at the top; passed ones are collapsed.
- Reports exist for `done` or `failed` runs; a running run shows an "in progress" state.
- Report language follows the manual; UI labels (e.g. "Passed") stay English.
- Credentials never appear in a report (already masked in R-005).

## Agreed scope
Render a run's results as a viewable report and export it as HTML and PDF.

## Out of scope
Run history list (R-007), emailing reports, custom branding, charts beyond simple counts, report editing.
