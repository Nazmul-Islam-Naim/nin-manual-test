---
id: "003"
title: Manual parsing
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-003: Manual parsing — manual পড়ে ক্রমানুসারে test case ও step বের করা (AI).

## Assumptions & corrections
- Parsing uses an LLM (Claude API) with a fixed JSON output schema.
- Each step has: order, action (open, click, type, select, assert text, etc.), target description, optional value, expected result.
- No selectors are generated here; targets stay human-readable and the executor (R-004) resolves them.
- Manuals may be Bangla or English; step text keeps the manual's language, action names are English.
- Nothing is invented: ambiguous parts are flagged `unclear` and skipped at execution.
- On success the run moves `parsing` -> `parsed`; on failure `failed` with a reason.
- Users can view parsed steps but cannot edit them in this step.

## Agreed scope
Turn stored manual text into structured test cases and steps, persist them, update run status.

## Out of scope
Selector generation, step editing UI, executing steps, OCR.
