# Contract 001 — Manual input

Spec: docs/specs/specs/001-manual-input.md · Base URL: `http://localhost:8000` (env `NEXT_PUBLIC_API_URL` in web) · Auth: none (login out of scope) · CORS: allow `http://localhost:3000` (configurable `CORS_ORIGINS`).

## Data: `manual`
| field | type | note |
|---|---|---|
| id | string (uuid4) | |
| source_type | `"text"\|"pdf"\|"docx"\|"md"\|"txt"` | |
| original_filename | string \| null | null for pasted text |
| char_count | integer | length of extracted `text` |
| text | string | only returned by GET |
| created_at | string (ISO 8601 UTC) | |

DB also keeps `file_path` (original file under `STORAGE_DIR/manuals/<id>/`); never returned.

## POST /manuals
Two request forms, same route.
1. Paste: `Content-Type: application/json`, body `{ "text": "<string>" }`.
2. Upload: `Content-Type: multipart/form-data`, field `file` (.pdf .docx .md .txt, max 10 MB, `MAX_UPLOAD_MB` configurable).

Success `201`: `{ "id": "...", "source_type": "pdf", "original_filename": "a.pdf", "char_count": 1234, "created_at": "..." }`

Extraction: .md/.txt UTF-8 (reject invalid UTF-8 with 422); .docx via python-docx (paragraphs + table cell text); .pdf via pypdf text layer. Normalize `\r\n`/`\r` to `\n`, trim. If both `text` and `file` are sent, `file` wins.

## GET /manuals/{id}
`200`: `{ "id", "source_type", "original_filename", "char_count", "text", "created_at" }` · `404` unknown id.

## Errors (all)
`{ "error": { "code": "<snake_case>", "message": "<human readable English>" } }`

| status | code | when |
|---|---|---|
| 413 | file_too_large | file > 10 MB |
| 415 | unsupported_file_type | extension not in list |
| 422 | empty_text | pasted/extracted text empty or whitespace |
| 422 | no_readable_text | file parsed but yields no text (e.g. scanned PDF) |
| 422 | invalid_encoding | .md/.txt not UTF-8 |
| 422 | invalid_request | neither `text` nor `file` provided, or file unreadable/corrupt |
| 404 | manual_not_found | GET unknown id |

Backend must convert FastAPI/Pydantic validation errors into this same shape.

## Frontend behavior
- Page `/`: toggle "Paste text" / "Upload file"; submit; on 201 show the returned id and char count (and a link/preview that calls GET); on error show `error.message` inline.
- Client-side pre-check (UX only, server is authority): extension list and 10 MB.
- URL field and Start button belong to spec 002, not here.

## Layout
Backend root `api/` (FastAPI, `app/` package: routers, services, schemas, repositories; tests under `api/tests`). Frontend root `web/` (Next.js App Router + Tailwind, TypeScript).

## Additional framework errors (added at reconcile)
404 `not_found` and 405 `method_not_allowed` for unknown routes/methods, same error shape.

## Notes
- Empty pasted text -> `empty_text`; empty/whitespace-only file -> `no_readable_text`.
- Frontend hard-codes the 10 MB limit; keep in sync with `MAX_UPLOAD_MB`.
