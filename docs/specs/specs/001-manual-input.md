---
id: "001"
title: Manual input
status: built
date: 2026-10-05
instruction: docs/specs/instructions/001-manual-input.md
---

## Summary
Let a user submit a test manual as pasted text or an uploaded file. The system extracts plain text, stores it, and hands it to the parser (R-003).

## Problem & Goal
Test steps live in human-written manuals. The tool needs them as clean text before it can parse and run them. Goal: one reliable entry point for manual content.

## Scope
- Paste text into a textarea.
- Upload .pdf, .docx, .md, .txt (max 10 MB).
- Server-side text extraction; store original file and extracted text.
- Create a `manual` record and return its id.

Out of scope: OCR, parsing steps, editing after submit.

## Analysis
- Greenfield: no existing code or specs.
- Risks: PDFs with no text layer; DOCX with tables/images; very long manuals; non-UTF-8 files. Bangla and English text must both survive extraction.

## Design
- **UI:** a form with a tab/toggle "Paste text" / "Upload file", a submit button, inline errors.
- **API:** `POST /manuals` accepts either `text` (JSON) or a multipart `file`. Returns `{ id, source_type, char_count }`. `GET /manuals/{id}` returns the record with extracted text.
- **Extraction:** by extension — .md/.txt read as UTF-8; .docx via a docx reader; .pdf via a text-layer PDF reader. Normalize line endings and trim.
- **Validation:** reject unsupported type (415), file over 10 MB (413), empty or whitespace-only extracted text (422, "no readable text found").
- **Data:** `manual { id, source_type: text|pdf|docx|md|txt, original_filename?, file_path?, text, created_at }`.
- **Flow:** submit -> validate -> extract -> store -> return id; the test run later references `manual_id`.

- **Stack:** Next.js frontend (form), FastAPI backend (`POST /manuals`); extraction in FastAPI with Python libraries (e.g. pypdf, python-docx).

## Acceptance & Test criteria
- Pasted text is stored and returned unchanged (apart from line-ending normalization).
- Each supported file type yields its text; Bangla and English both preserved.
- File over 10 MB -> 413; unsupported type -> 415; image-only PDF or empty input -> 422 with a clear message.
- Response contains a usable manual id; `GET /manuals/{id}` returns the stored text.

## Deploy notes
File storage location and size limit must be configurable. Stack and storage backend to be decided with the project scaffold.

## Open questions
- Should OCR for scanned PDFs be added later?

## Change log
- 2026-10-05: Stack fixed to Next.js + FastAPI (instruction 008). See docs/specs/instructions/008-stack-and-decisions.md.
