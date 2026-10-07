---
id: "001"
title: Manual input
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-001: Manual ইনপুট — User test manual দেবে (text paste বা PDF/DOCX/MD upload).

## Assumptions & corrections
- Input is either pasted text or an uploaded file (.pdf, .docx, .md, .txt).
- Max upload size 10 MB.
- Plain text is extracted server-side; the original file is kept too.
- Each manual gets an id and is attached to a test run together with the URL (R-002).
- Scanned/image-only PDFs are not supported in this step; show a clear error when no text is found.
- Stack is undecided; the spec describes behavior only.

## Agreed scope
Accept a manual, extract its text, store it, and expose it for parsing (R-003).

## Out of scope
Parsing into test steps (R-003), URL input (R-002), OCR, editing the manual after submit.
