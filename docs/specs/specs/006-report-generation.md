---
id: "006"
title: Report generation
status: draft
date: 2026-10-05
instruction: docs/specs/instructions/006-report-generation.md
---

## Summary
Turn a finished run's stored results (spec 005) into a readable report: on screen, and downloadable as a self-contained HTML file or a PDF.

## Problem & Goal
Raw step results are hard to read and share. Goal: one clear report that shows what passed, what failed and why, with evidence, in a form users can keep and send.

## Scope
- Report data assembly from results.
- Report page in the UI.
- HTML and PDF export.
- In-progress and empty states.

Out of scope: history list, emailing, branding, editing.

## Analysis
- Depends on 005 (results, summary, screenshots), 002 (URL, run times), 003 (test case titles).
- Risks: HTML size from embedded screenshots on long runs; PDF page breaks cutting steps or images; Bangla fonts missing in PDF; very long error text; sensitive data visible in screenshots.

## Design
- **Data:** `GET /test-runs/{id}/report` returns `{ run, summary, test_cases: [{ title, status, steps: [{ order, action, target, status, error?, expected?, actual?, screenshot_url? }] }] }` built from stored results.
- **Template:** one HTML template renders the report. The UI page uses it directly; exports reuse it.
- **Layout:** header (title, URL, started/finished, duration); summary block with counts and an overall status (passed / failed); list of test cases; failed ones first and expanded, passed ones collapsed; each step shows status, text, error, expected vs actual, thumbnail that opens the full screenshot.
- **HTML export:** `GET /test-runs/{id}/report.html` returns one file with CSS inline and screenshots embedded as base64.
- **PDF export:** `GET /test-runs/{id}/report.pdf` renders the same HTML with Playwright `page.pdf()` (A4, print CSS: avoid breaking inside a step, images scaled to page width). Bundle a Bangla-capable font so text renders correctly.
- **States:** `running`/`parsing` -> "In progress"; `failed` with engine error -> report shows the error and any partial results; no results -> empty message.
- **Access:** only the run's owner can view or export.

- **Stack:** report page in Next.js; HTML/PDF export endpoints in FastAPI.
- **Expired screenshots:** if a screenshot was removed (spec 005), the report shows a "Screenshot expired" placeholder in its place. HTML/PDF files exported earlier keep their embedded images.
- **Download:** each screenshot in the on-screen report has a Download button.

## Acceptance & Test criteria
- A finished run shows correct totals and per-step statuses matching stored results.
- Failed test cases appear first, expanded, with error and screenshot.
- The HTML file opens offline with all images visible.
- The PDF contains the same content, steps are not split across pages, and Bangla text renders correctly.
- A running run shows "In progress", not an empty report.
- Another user's run returns 403/404.
- After a screenshot expires, the report shows "Screenshot expired" and everything else is intact.

## Deploy notes
PDF export needs Chromium on the server (shared with the executor) and a Bangla font installed or bundled. Large reports may need a size warning.

## Open questions
- Add a cap or lower resolution for screenshots in HTML export?
- Share via public link later?

## Change log
- 2026-10-07: A Markdown export of failed/warning results was delivered early in the UI (instruction 014); HTML/PDF export is still this spec.
- 2026-10-05: Stack, expired-screenshot placeholder and per-screenshot download (instruction 008). See docs/specs/instructions/008-stack-and-decisions.md.
