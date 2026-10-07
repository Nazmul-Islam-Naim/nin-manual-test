---
id: "008"
title: Stack and decisions
date: 2026-10-05
status: frozen
---

## Original request
"fastapi + nextjs, claude and open router and giminie, ss file add hobe seta dowload kora jabe then 2days pro remove login pore lagbe"

## Assumptions & corrections
- Stack: Next.js frontend, FastAPI backend.
- LLM provider is selectable by config (`LLM_PROVIDER` = anthropic | openrouter | gemini), with one API key per provider; no per-run switch in the UI.
- The parsing JSON schema is identical across providers; a schema mismatch retries once, then fails the run.
- Each step's screenshot has a Download button; all screenshots of a run can be downloaded as one ZIP.
- Screenshot files are deleted 48 hours after creation by an hourly background job (configurable). Only files are deleted; run and step results (text) stay.
- After deletion, reports and the history list show "Screenshot expired". Previously exported HTML/PDF keep their images.
- Login stays out of scope for now; the single-user ownership assumption holds.

## Agreed scope
Apply these decisions to specs 001, 002, 003, 004, 005, 006, 007 (each updated in place with a Change log entry).

## Out of scope
Login and multi-user, per-run provider switching in the UI, OCR.
