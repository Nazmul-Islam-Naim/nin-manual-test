---
id: "012"
title: Error details and UI redesign
date: 2026-10-07
status: frozen
---

## Original request
"2+3 etar combination valo hobe. ebong error er dhoron o ekhane show korte hobe jeno seta solve kora jay" (first need to improve the design, make it professional; combine the dark console layout with the warm report style; also show the kind of error so it can be fixed).

## Assumptions & corrections
- UI direction: layout of "Dark Console" (left setup panel, right live results) plus the "Warm Report" features (report-style header, ring score chart, serif display headings). Dark is the default theme, a warm light theme (paper background, teal accent) follows `prefers-color-scheme` and has a manual toggle. Fonts: Inter, JetBrains Mono for technical text, Fraunces for display headings.
- The UI shows, for every failed or warning result, the error type with a plain-English explanation and a short "what to check" list, plus the evidence: page URL, HTTP status, the actual console messages, the failed requests (method, URL, status) and a short response/banner excerpt.
- An "Issues" summary groups problems by error type with counts so the tester sees what to fix first; list filters: All, Failed, Warning, Passed.
- Backend gains structured error info on each step result: `error_type`, `page_url` and `details` (console messages, failed requests, response excerpt), all bounded in size. Existing fields stay unchanged; new fields are optional for old clients.
- Manual parsing result ("0 test cases found") moves into a collapsible "Manual steps" section instead of a prominent card.
- No behavior change to execution, polling or endpoints; UI only plus the new optional result fields.

## Agreed scope
Redesign the whole web UI and add the error-detail fields end to end.

## Out of scope
Report export (spec 006), run history page (spec 007), fixing the target site's bugs, storing screenshots.
