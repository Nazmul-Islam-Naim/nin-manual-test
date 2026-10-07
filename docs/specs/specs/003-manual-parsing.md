---
id: "003"
title: Manual parsing
status: built
date: 2026-10-07
instruction: docs/specs/instructions/003-manual-parsing.md
---

## Summary
Convert a stored manual's text into an ordered list of structured test cases and steps using an LLM, so the executor (R-004) can run them.

## Problem & Goal
Manuals are free-form prose. The executor needs discrete, ordered, machine-readable steps. Goal: a faithful, schema-valid extraction that never invents steps.

## Scope
- Parse manual text (spec 001) for a test run (spec 002).
- Persist test cases and steps.
- Update run status; read endpoint for parsed steps.

Out of scope: selector generation, editing, execution.

## Analysis
- Depends on 001 (manual text) and 002 (`test_run`, status `parsing`).
- Risks: hallucinated steps; very long manuals exceeding the context window; malformed LLM output; Bangla/English mixed text; non-deterministic results between runs; API cost and latency.

## Design
- **Trigger:** automatically after a run is created (spec 002), asynchronously; status `parsing`.
- **Prompt:** instruct the model to extract only what the manual states, keep original language for text, use the English action vocabulary, and mark anything ambiguous `unclear: true`. Temperature 0.
- **Output schema (JSON):** `{ test_cases: [{ title, steps: [{ order, action, target, value?, expected?, unclear }] }] }`. Validate against the schema; on failure retry once, then fail the run.
- **Long manuals:** if text exceeds a configured size, split at headings/paragraph boundaries, parse chunks, and merge in order.
- **Actions (initial set):** open, click, type, select, check, assert_text, assert_visible, wait.
- **API:** `GET /test-runs/{id}/steps` -> test cases with steps. Run status moves `parsing` -> `parsed`, or `failed` with `error`.
- **Data:** `test_case { id, run_id, title, order }`, `step { id, test_case_id, order, action, target, value?, expected?, unclear }`.

- **LLM provider:** a small provider interface with four implementations: Anthropic (Claude API), OpenRouter, Gemini, and `claude_cli`. `LLM_PROVIDER` selects one; each has its own API key and model setting. The prompt and the JSON output schema are identical for all providers; a schema mismatch retries once, then fails the run.
- **`claude_cli` provider:** runs `claude -p --output-format json` as a subprocess, prompt via stdin, answer read from the JSON `result` field. It runs from an empty temp directory with tools disabled and without plugins/hooks to keep context small (exact flags confirmed from `claude --help` at build time). Config: `CLAUDE_CLI_MODEL` (default `sonnet`), `CLAUDE_CLI_TIMEOUT_S` (default 120). `claude` missing, not logged in, or timeout -> run `failed` with a clear reason.
- **Stack:** parsing runs as a FastAPI background job.

- **Field rules (instruction 013):** the parse output also contains `field_rules`: `[{ field, rule?, valid: [<=5 strings], invalid: [<=5 strings] }]` taken only from what the manual states (e.g. "Phone must be 11 digits"). Optional in the schema (absent = []). Stored per run and returned by `GET /test-runs/{id}/steps` as `field_rules`.

## Acceptance & Test criteria
- A manual with 3 numbered scenarios yields 3 test cases with steps in the original order.
- A step missing from the manual is not generated; vague text is flagged `unclear`.
- Bangla manual -> Bangla target/expected text, English action names.
- Output failing the schema is retried once, then the run becomes `failed` with a reason.
- A manual line "Phone must be 11 digits, starting with 01" yields a field rule for "Phone" with a valid and an invalid example; manuals without rules yield `field_rules: []`.
- Re-parsing the same manual yields the same structure (within temperature-0 variation).

## Deploy notes
`claude_cli` needs the `claude` CLI installed and logged in on the same machine and is for local personal use only (not for server deployment or other users; check Anthropic's current terms). Other providers need `LLM_PROVIDER` and the matching key (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` or `GEMINI_API_KEY`); model names and chunk size configurable. Parsing runs in a background job, not in the request.

## Open questions
- Which model per provider gives the best cost/accuracy for parsing?
- Allow step editing before execution in a later spec?

## Change log
- 2026-10-07: Parse output gains `field_rules` (instruction 013).
- 2026-10-06: Added `claude_cli` provider (instruction 009).
- 2026-10-05: LLM provider abstraction (Claude, OpenRouter, Gemini) and FastAPI stack (instruction 008). Deploy note: replaces single `ANTHROPIC_API_KEY` with `LLM_PROVIDER` plus a key per provider. See docs/specs/instructions/008-stack-and-decisions.md.
