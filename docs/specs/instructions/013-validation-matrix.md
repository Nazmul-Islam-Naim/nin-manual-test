---
id: "013"
title: Validation matrix
date: 2026-10-07
status: frozen
---

## Original request
"ekhane validaiton, valid and invalid data esara jato dhoroner test kora possible manual ta sob thakbe. like phone number email etc.." Clarified: test data comes from the tool itself and from the manual; invalid categories wanted: wrong format, boundary, blank and special characters, security-style (XSS/SQL), "and anything else".

## Assumptions & corrections
- Method: keep every other field valid and replace one field's value per case, then submit.
- Field kind is inferred from `type`, `name`, label, placeholder and `maxlength`/`min`/`max`/`pattern` (phone, email, number, date, password, url, text/textarea).
- Invalid categories: format (email without @, phone with letters or too short/long, bad date), boundary (just outside min/max, negative, over maxlength), blank and special (spaces only, symbols, Bangla, emoji, very long), security-style (`<script>` XSS payloads, `' OR '1'='1' --` SQL payload). No destructive SQL payloads (no DROP).
- Valid data: Bangladesh-style phone (`01712345678`), `test+<timestamp>@example.com`, etc. The real valid submit stays at one per form to limit created data.
- Outcome rules: invalid data accepted -> failed (`invalid_accepted`); valid data rejected -> failed (`valid_rejected`); XSS payload executed or rendered as live markup -> failed, merely accepted -> warning (`xss_risk`); SQL error text or 5xx on the SQL payload -> failed (`sql_error`); special/unicode/long inputs fail only on 5xx or a crash.
- Manual-derived rules: the manual parse also extracts `field_rules` (field name, rule, valid and invalid examples). The executor matches them to fields by label and adds them as cases marked source "manual". If parsing has not finished when execution starts, only tool-generated data runs and the note says so.
- Depth option `validation_depth`: basic (today's behavior: empty + sample), standard (+ format, boundary, blank), thorough (+ special, unicode, long, XSS, SQL). Default thorough. Caps: `MAX_CASES_PER_FORM` 25, `MAX_CASES` 200.
- New error types: `invalid_accepted`, `valid_rejected`, `xss_risk`, `sql_error`.
- UI: Validation depth selector in the setup panel; form cases grouped by form then field with counts; "Rules found in the manual" shown in the Manual steps area.
- Same limits as before: forms in modals, CAPTCHA, file uploads, wizards are not covered.

## Agreed scope
Field-level valid/invalid validation testing with tool-generated and manual-derived data, end to end.

## Out of scope
Destructive payloads, fuzzing beyond the listed catalog, auth/permission testing, API-level testing.
