---
id: "004"
title: Test execution engine
status: built
date: 2026-10-07
instruction: docs/specs/instructions/004-test-execution.md
---

## Summary
Open the target site in a visible Chromium window, discover its menus automatically, and visit them one by one, checking each and recording a passed/failed/warning outcome. Superseded design: see Change log.

## Problem & Goal
Users want to watch the system load and each menu being exercised. Goal: a visible, reliable menu sweep that finds menus without a script and reports what is broken.

## Scope
- Headed Chromium (Playwright for Python), slow-motion, window maximized.
- Load base URL (spec 002), optional login.
- Menu discovery, denylist, limit.
- Per-menu visit and checks.
- Results saved as test case "Menu sweep" with `visit_menu` and `submit_form` steps.
- Form checks on every visited page (instruction 011).
- Trigger endpoint and run status `running` -> `done`/`failed`.

Out of scope: manual-step execution (later requirement), forms in modals/wizards, CAPTCHA, file uploads, other browsers, headless/server deployment, result screenshots storage details (spec 005).

## Analysis
- Depends on 002 (`base_url`, run) and reuses the `TestCase`/`Step` tables from 003.
- Risks: menus rendered by JavaScript after load; mega-menus and hover menus; SPAs that change content without navigation; session expiry; heuristics missing menus; clicking destructive items (denylist); Playwright on Windows needs its own process outside uvicorn's event loop; Chromium download size.

## Design
- **Trigger:** `POST /test-runs/{id}/execute` with optional `{ credentials: { username, password } }`. Allowed when status is `created`, `parsed` or `done`/`failed` (re-run). Sets `running`, spawns the executor as a separate subprocess (`python -m app.services.executor <run_id>`) so the window opens on the user's desktop; subprocess exits when done; status becomes `done` (or `failed` with `error`).
- **Browser:** `EXEC_HEADED=true` (default), `EXEC_SLOW_MO_MS=400`, viewport from maximized window, default timeout 15 s, overall limit 15 min.
- **Flow:** open base URL, wait for load; optional login (fill the first visible username/password inputs and submit, only when credentials given); discover menus; create/replace test case "Menu sweep"; for each menu in order: highlight it (temporary outline), click or navigate, wait for load, run checks, record the step result, take a screenshot, return to the start page when needed.
- **Discovery:** collect candidates from `nav`, `header`, `aside`/sidebar, `[role=navigation]`, `[role=menubar]`, and `[role=menuitem]`; keep same-origin links and visible clickable items; expand one dropdown level (hover/click items with `aria-haspopup` or `aria-expanded`); dedupe by label + href; cap at `MAX_MENUS` (default 30); denylist labels/hrefs: logout, sign out, log out, delete, remove, external domains, `mailto:`, `tel:`, downloads.
- **Checks per menu:** navigation HTTP status < 400; error-page markers (404, 500, "Not Found", "Internal Server Error"); body text not blank; collect console errors and failed XHR/fetch (4xx/5xx). Result: `failed` for HTTP >= 400, error page, blank page or timeout; `warning` for console errors or failed requests only; otherwise `passed`.
- **Result storage:** test case "Menu sweep" with steps `{ action: "visit_menu", target: <label>, value: <href>, expected: null }`; per-step outcome fields follow spec 005 (status, error, duration, screenshot). Until spec 005 is built, outcome (status/error/duration) is stored on the step row via a lightweight result table that spec 005 later adopts.
- **Credentials:** held in memory for the run, passed to the subprocess through stdin or environment (not command line), never written to logs, results or reports.

- **Form checks (instruction 011):** after a menu page is checked, each form (max 5 per page, 50 total) gets an empty submit and a sample-data submit. Empty: with required fields expect validation feedback (native invalid state, aria-invalid, role=alert, .error/.invalid-feedback, or 4xx/422) -> passed, success anyway -> warning, no required fields -> skipped. Sample: fill by type (email, tel, number within min/max, date, password, text/textarea, first non-empty select option, required checkbox, first radio; file inputs skipped with a warning), submit, and classify: failed on HTTP >= 400, a new error banner or crash; passed on HTTP < 400 with a success sign or no error; warning when nothing visibly happens or only console errors. Skip forms whose submit label contains delete, remove, destroy, logout, unsubscribe, deactivate, purge or clear all; dismiss confirm()/alert(); login form uses supplied credentials. Steps: action `submit_form`, target "<menu label> > <form name or submit label>", value `empty`|`sample`, placed right after their menu step. Env `EXEC_SUBMIT_FORMS`, `MAX_FORMS_PER_PAGE`, `MAX_FORMS`.
- **Parsing overlap:** execute is allowed while `parsing`; the parse job saves its steps and changes status only if it is still `parsing` (compare-and-set), so it never overwrites `running`. Default `CLAUDE_CLI_TIMEOUT_S` is 600.

- **Error details (instruction 012):** every non-passed step result carries `error_type` (one of server_error, client_error, error_page, blank_page, timeout, navigation_failed, console_error, failed_request, validation_missing, no_reaction, form_error_banner, browser_validation_blocked, file_input_skipped, crash, interrupted), `page_url` (final URL), and `details`: up to 5 console messages (type, text <= 300 chars, location), up to 5 failed requests (method, URL, status), and a short response/banner excerpt (<= 300 chars). Secrets (credentials, passwords typed) never appear in details; URLs have query strings trimmed of obvious tokens. Passed steps have `error_type: null`.

- **Validation matrix (instruction 013):** per form, keep all fields valid and replace one field's value per case, then submit. Kinds are inferred from type/name/label/placeholder and maxlength/min/max/pattern. Catalog: email (valid `test+<ts>@example.com`; invalid: no @, missing local/domain part, space inside, 256-char local part), phone (valid `01712345678`; invalid: letters, too short, too long, `++` prefix, symbols), number (below min, above max, negative, decimal on integer step, huge), date (before min, after max, impossible dates on text inputs), password (too short, spaces only, over-long), url (valid `https://example.com`; invalid `htp:/bad`; `javascript:alert(1)` as security), text/textarea (spaces only when required, symbols, Bangla and emoji, over maxlength or 1000-5000 chars, XSS `<script>window.__xss=1</script>` and `"><img src=x onerror=window.__xss=1>`, SQL `' OR '1'='1' --` and `admin'--`; no destructive payloads). Depth `validation_depth`: basic = empty + sample; standard = + format, boundary, blank; thorough = + special, unicode, long, XSS, SQL (default thorough, env `EXEC_VALIDATION_DEPTH`). Caps `MAX_CASES_PER_FORM` 25, `MAX_CASES` 200. Reload the page before each case. Manual-derived `field_rules` (spec 003) matching a field by normalized label add valid/invalid cases marked source manual; if parsing has not finished, only auto cases run and the note says so.
- **Outcome rules:** invalid accepted -> failed `invalid_accepted`; valid rejected -> failed `valid_rejected`; XSS payload executed (dialog or `window.__xss`) or rendered as live markup -> failed `xss_risk`, accepted but inert -> warning `xss_risk`; SQL error text or 5xx on the SQL payload -> failed `sql_error`; special/unicode/long inputs fail only on 5xx or crash. Rejection = native invalid state, validation messages, 4xx/422, or no success/navigation; maxlength truncation counts as rejected.

- **Page actions (instruction 014):** after each menu page and its forms, the page body (outside nav/header/aside) is searched for clickable actions (same-origin links, buttons, role=button, role=tab, data-bs-toggle, icon buttons, row actions, pagination). One action per signature (label + kind + href with numeric/uuid parts as `:id`) is clicked (caps `MAX_ACTIONS_PER_PAGE` 15, `MAX_ACTIONS` 150; denylist delete, remove, destroy, purge, clear all, logout, sign out, unsubscribe, deactivate, void, refund, external, mailto, tel, downloads; `ACTION_DENY_EXTRA`). Outcomes: navigated -> checked like a menu and its forms tested; modal/drawer opened -> its forms tested with the validation matrix, re-opening the modal for each case, then closed; popup/download -> passed; in-place change -> passed; nothing happened -> warning `action_no_effect`. Steps: `click_action` with `meta.category` action_link/action_button/action_tab/action_row/action_pagination. Env `EXEC_TEST_ACTIONS`; one level deep only.

- **Time budget and phases (instruction 015):** phase 1 visits every menu and runs forms' empty/sample and page actions; phase 2 runs validation cases across all forms round-robin until the budget is spent. Reaching the limit ends the run `done` with a note ("Stopped at the time limit (N min); X checks were not run"), never `failed`. Body `max_minutes` (1-240, default from `EXEC_OVERALL_TIMEOUT_S`, now 3600) and `fast_mode`; `started_at`, `finished_at`, `max_minutes` returned. The browser-level slow motion is replaced by a short pace in phase 1 only (`EXEC_SLOW_MO_MS` 300); case runs have no artificial delay and a 1.5 s networkidle wait.

- **Fewer false alarms (instruction 016):** a disabled or unclickable submit is never a crash (rejected -> passed for empty/invalid/security; warning `submit_blocked` for valid/sample/tolerant); an XSS payload that is escaped or not shown passes, only executed or live-markup payloads fail; already-active tabs/buttons pass without a click and `#fragment` links count a hash or scroll change as a reaction; sample phones and code-like fields are unique per submission; 401/403 -> warning `permission_denied` (also for invalid cases, which are inconclusive) and 409 on valid data -> warning `possible_duplicate`.

## Acceptance & Test criteria
- Against a local test site with a nav of 4 links (one broken, one "Logout"), the sweep visits the 3 safe links, marks the broken one `failed`, and skips Logout.
- Menus are visited in page order, one by one, in a visible window (manual check with `EXEC_HEADED=true`).
- A console error alone gives `warning`; HTTP 500 gives `failed`.
- More menus than `MAX_MENUS` are truncated and the truncation is recorded.
- A required form submitted empty gives validation feedback (passed); a valid form with sample data gives 200 (passed); a form that returns 500 is `failed`; a form without validation is `warning`; a form with a Delete button is not submitted (server sees no request).
- `submit_forms=false` produces no `submit_form` steps; the 50-form cap is enforced.
- Execute during `parsing` returns 202 and the later parse completion does not overwrite `running`.
- A page with a console error and a failing XHR returns `error_type`, the console text and the request (method, URL, status) in `details`; a 500 page returns `server_error` with an excerpt; a passed step has `error_type: null`.
- On a fixture form: invalid email/phone accepted -> failed `invalid_accepted`; properly validated form -> passed; valid data rejected -> `valid_rejected`; XSS echoed as markup -> `xss_risk`; SQL error text -> `sql_error`; `validation_depth=basic` produces no case steps; caps respected; manual-derived rules appear as source manual.
- On a fixture list page with 3 rows (each View, Edit, Delete): View and Edit are each tested once, Delete never gets a request; a 500 action is `failed`; a do-nothing button is `action_no_effect`; an "Add New" modal form gets empty/sample/validation cases with the modal re-opened each time; a tab switch passes; a card link to a failing page (such as a POS sale page) is `failed`; `test_actions=false` produces no action steps; caps and notes work.
- With a tiny time budget the run ends `done` with the "Stopped at the time limit" note, every menu is visited at least once, remaining work stays pending; real errors still end `failed`. Cases of two forms are interleaved round-robin. `max_minutes` outside 1-240 -> 422. `started_at`/`finished_at` are returned.
- A form whose submit is disabled gives passed for invalid cases and `submit_blocked` for valid sample, never `crash`; escaped XSS echo passes and raw-HTML echo fails; an already-active tab and a `#demo` link pass; a repeated sample phone does not collide; 403 and 409 fixtures give `permission_denied` / `possible_duplicate` warnings.
- Credentials never appear in logs or stored data.
- Run status goes `running` -> `done`; engine failure -> `failed` with a reason.

## Deploy notes
Needs Playwright and Chromium (`playwright install chromium`). The visible window works only when the API runs in the user's desktop session (local use). Timeouts, `EXEC_HEADED`, `EXEC_SLOW_MO_MS` and `MAX_MENUS` configurable.

## Open questions
- Add manual-step execution (from spec 003) as a follow-up requirement?
- Add Firefox/WebKit later?

## Change log
- 2026-10-07: Fewer false alarms: submit_blocked, escaped XSS passes, already-active controls, unique sample data, permission_denied/possible_duplicate (instruction 016).
- 2026-10-07: Two-phase scheduling, graceful stop at the time limit, selectable budget, faster cases (instruction 015).
- 2026-10-07: Page action sweep with modal/page form testing (instruction 014).
- 2026-10-07: Validation matrix: per-field valid/invalid/security cases from tool and manual (instruction 013).
- 2026-10-07: Added structured error details to step results (instruction 012).
- 2026-10-07: Added form submit checks (empty and sample data), execute allowed during parsing, CLAUDE_CLI_TIMEOUT_S default 600 (instruction 011).
- 2026-10-06: Redesigned as a visible, self-discovering menu sweep; manual-step execution deferred (instruction 010). Replaces the earlier headless, manual-driven design.
- 2026-10-05: Element-picking LLM uses the shared provider abstraction; Playwright for Python in FastAPI (instruction 008) — superseded by the above.
