---
id: "009"
title: Claude CLI provider
date: 2026-10-06
status: frozen
---

## Original request
"claude api er key use nah kore je account ami ekhon use korchi eta ki kono vabe use kora jabe" -> "option 2 use koro amar jonno eta ami use kore dekhte cai" (run `claude -p` as a subprocess using the user's logged-in Claude Code account).

## Assumptions & corrections
- New provider value `claude_cli` joins anthropic, openrouter, gemini in spec 003.
- Backend runs a subprocess `claude -p --output-format json`; the prompt goes to stdin; the answer is the `result` field of the JSON.
- The subprocess runs from an empty temp directory with tools disabled and without plugins/hooks to keep context small; exact flags are confirmed from `claude --help` at build time.
- Config: `CLAUDE_CLI_MODEL` (default `sonnet`), `CLAUDE_CLI_TIMEOUT_S` (default 120). If `claude` is missing, not logged in, or times out, the run becomes `failed` with a reason.
- The JSON output schema is the same as other providers; mismatch retries once, then fails.
- Local, personal use only. Not for server deployment or other users; the user must check Anthropic's current terms themselves.

## Agreed scope
Add the `claude_cli` provider to the spec 003 provider interface.

## Out of scope
Using subscription tokens directly against the API, per-run provider switching, other CLIs.
