---
id: "011"
title: Form submit testing
date: 2026-10-07
status: frozen
---

## Original request
"ekta jinis dekhlam ta hosse form submit ekhane kaj kore nah et check dite hobe" (the menu sweep does not check that form submit works; this must be checked).

## Assumptions & corrections
- On every visited menu page, each form gets two checks: an empty submit and a submit with generated sample data (real submit; the user confirmed this is a test site and sample data may be created).
- Empty submit: if the form has required fields, expect validation feedback (native invalid state, aria-invalid, role=alert, .error/.invalid-feedback, or a 4xx/422 response) -> passed; if it succeeds anyway -> warning; no required fields -> skipped.
- Sample submit: values by field type (email, tel, number within min/max, date, password, text/textarea, first non-empty select option, required checkbox, first radio; file inputs skipped with a warning). Outcome: failed on HTTP >= 400, a new error banner, or a crash; passed on HTTP < 400 with a success sign or no error; warning when there is no visible reaction or only console errors.
- Safety: forms whose submit label contains delete, remove, destroy, logout, unsubscribe, deactivate, purge or clear all are skipped; confirm()/alert() dialogs are dismissed; the login form still uses the supplied credentials, not sample data.
- Limits: max 5 forms per page, 50 total. Forms inside modals or opened by Add/New buttons, multi-step wizards and CAPTCHA are not covered; the report must say so.
- Results reuse step/step_result: action `submit_form`, target "<menu label> > <form name or submit label>", value `empty` or `sample`. Each menu's form steps follow that menu step.
- `POST /test-runs/{id}/execute` gains optional `submit_forms` (default true); env `EXEC_SUBMIT_FORMS`.
- Fix two blockers found while testing: execute is allowed while the run is `parsing` (parse then saves steps and only changes status if it is still `parsing`), and the default `CLAUDE_CLI_TIMEOUT_S` becomes 600.

## Agreed scope
Add form submit checks to the menu sweep and remove the two blockers above.

## Out of scope
Modal/wizard forms, CAPTCHA, file uploads, custom per-form data, manual-driven form data.
