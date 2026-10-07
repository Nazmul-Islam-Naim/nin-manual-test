# Contract 004 — Visible menu sweep

Spec: docs/specs/specs/004-test-execution.md (+ instruction 010) · Builds on contracts 001–003 (same base URL, CORS, error shape, no auth).

## Run status
`test_run.status` adds real use of `running` and `done`: `created|parsed|done|failed -> running -> done | failed`. `error` (string|null) set when `failed`.

## POST /test-runs/{id}/execute
Request `application/json` (body optional): `{ "credentials": { "username": "<string>", "password": "<string>" } | null }`.
Allowed when status is `created`, `parsing`, `parsed`, `done` or `failed` (re-run replaces the previous "Menu sweep" test case). Sets status `running`, spawns the executor subprocess, returns immediately.
Success `202`: `{ "id": "<uuid>", "status": "running" }`.
Errors: `404 test_run_not_found`; `409 run_busy` (status is already `running`); `422 invalid_request` (bad body).
Credentials go to the subprocess via stdin (never argv/env of the visible command line), are never stored, logged or returned.

## GET /test-runs/{id}/steps  (extended)
Same shape as contract 003, plus:
- each step gets `"result": null | { "status": "running"|"passed"|"failed"|"warning", "error": string|null, "http_status": int|null, "console_errors": int, "failed_requests": int, "duration_ms": int|null }` (`null` = not visited yet; `running` = being visited now).
- top level gets `"summary": { "total": int, "passed": int, "failed": int, "warning": int, "pending": int }` computed from the "Menu sweep" steps (all zeros when none).
- For a menu sweep: one test case titled `"Menu sweep"`; steps `{ action: "visit_menu", target: "<menu label>", value: "<href or null>", expected: null, unclear: false }`. `action` enum gains `visit_menu`. Steps are created as soon as discovery finishes (all `result: null`), then results fill in one by one, so polling shows live progress.
- `test_cases` may be non-empty while `status = running`. While the run is `running` before discovery finishes, `test_cases` may be `[]`.
- The response `status` field mirrors the run status.

## GET /test-runs/{id}  (unchanged shape)
`status` may now be `running` or `done`.

## Result semantics
- `failed`: navigation HTTP >= 400, error-page marker (404, 500, "Not Found", "Internal Server Error"), blank page, or 15 s timeout. `error` explains.
- `warning`: loaded fine but console errors and/or failed XHR/fetch (4xx/5xx) recorded; counts in `console_errors`, `failed_requests`.
- `passed`: otherwise.
- If more than `MAX_MENUS` (default 30) menus are found, the extra ones are not visited and the truncation is noted in the run's `error` is NOT used; instead add top-level `"note": string|null` to the steps response (e.g. "Found 45 menus, visited the first 30"). Else null.

## Executor behavior (backend)
- Subprocess: `python -m app.services.executor <run_id>` with the same venv Python; credentials JSON on stdin. Headed Chromium by default (`EXEC_HEADED=true`), `EXEC_SLOW_MO_MS=400`, maximized window, 15 s per-page timeout, 15 min overall limit. `MAX_MENUS` configurable.
- Discovery: `nav`, `header`, `aside`/sidebar, `[role=navigation]`, `[role=menubar]`, `[role=menuitem]`; same-origin visible clickable items; expand one dropdown level; dedupe by label+href; denylist (logout, sign out, log out, delete, remove, external domains, `mailto:`, `tel:`, downloads). Click-target gets a temporary outline. Screenshot taken after each menu (stored under `STORAGE_DIR/runs/<run_id>/`, path kept in the result row; serving files is spec 005).
- Playwright or Chromium missing, base URL unreachable, or crash -> run `failed` with a clear `error` (for missing Chromium: "Chromium is not installed. Run: python -m playwright install chromium").
- Result rows live in a new table `step_results` (one per step, unique `step_id`), shaped so spec 005 can adopt it.
- If the API process restarts while a run is `running`, startup marks stale `running` runs `failed` ("Interrupted").

## Frontend behavior
- After the run exists (any of created/parsed/done/failed), show a "Run menu test" button (disabled while `running` or `parsing`). Optional collapsible "Login (optional)" with username/password inputs (type=password for password; not persisted).
- Click -> `POST /test-runs/{id}/execute`; then poll `GET /test-runs/{id}` and `GET /test-runs/{id}/steps` every 2 s until `done`/`failed` (cleanup on unmount; ~20 min cap).
- Show live list of menus with status chips (pending, running, passed, failed, warning), error text, counts for console errors/failed requests, plus summary bar and the `note`. Say clearly "A Chromium window opens on this computer". Handle 409/404/422/network errors inline.
- Manual-parse steps view from spec 003 stays; the menu sweep is a separate section.

## Layout
Backend: `api/app/services/executor/{__init__,__main__,runner,menu_discovery,checks}.py`, router/service/repository extensions, model `StepResult`, startup stale-run cleanup; tests in `api/tests` (headless against a local `http.server` fixture site). Frontend: `web/src/features/manual/MenuSweep.tsx`, `web/src/lib/api.ts`, wiring in `ManualForm.tsx`/`RunProgress.tsx`.

## Notes (added at reconcile)
- `summary.pending` counts `running` steps too, so total = passed+failed+warning+pending.
- `note` is stored in `test_runs.sweep_note` (column added at startup via ALTER).
- Every step now carries a `result` key (null for manual-parse steps).
- Dropdown items that are non-link `[role=menuitem]` fail if the dropdown is closed at visit time; link items are visited via goto.
- If the executor interpreter dies, the run stays `running` until the next API restart marks it `failed` ("Interrupted"). Over 15 min -> `failed` "Overall time limit exceeded".
- Error-page markers are looked for in title/headings, or in the body only when it is under 300 characters.

## Addendum 2026-10-07 — form submit testing (instruction 011)

### POST /test-runs/{id}/execute (extended)
Body: `{ "credentials": {...} | null, "submit_forms": true | false }` (`submit_forms` optional, default `true`, also env `EXEC_SUBMIT_FORMS`). `409 run_busy` now ONLY when status is already `running`; `parsing` is allowed. While parsing runs concurrently, the parse job must save its test cases/steps without touching the "Menu sweep" test case, and must set its final status (`parsed`/`failed`) ONLY if the run status is still `parsing` (compare-and-set); it must never overwrite `running`.

### Steps: new action `submit_form`
`action` enum gains `submit_form`. Each form on a visited menu page gets up to two steps right after that menu's `visit_menu` step: `{ action: "submit_form", target: "<menu label> > <form name or submit button label>", value: "empty" | "sample", expected: null, unclear: false }`. Same `result` shape as menus. Order in `test_cases[].steps` is menu, its forms (empty then sample), next menu... All steps are created as soon as discovery of that page's forms is done, so a menu's form steps may appear after the menu step finishes (live list grows); menu steps still exist from the start. `summary` counts all steps (`total` includes forms).

### Form rules (backend)
- Limits: `MAX_FORMS_PER_PAGE` (5), `MAX_FORMS` (50); beyond that skipped and noted in `note`.
- Empty submit: no required fields -> no `empty` step. With required fields: validation feedback (native invalid, aria-invalid, role=alert, .error/.invalid-feedback, or 4xx/422) -> `passed`; submit succeeds anyway -> `warning` ("No validation feedback on empty submit"); otherwise `failed` only for HTTP >= 500.
- Sample submit: values by type (email `test+<timestamp>@example.com`, tel `01700000000`, number within min/max, date today, password `Test@12345`, text/textarea `Test <label>`, select first non-empty option, required checkbox ticked, first radio; file inputs skipped and result at least `warning` "File input skipped"). `failed`: HTTP >= 400, new error banner (alert/error elements with error/failed/exception text), or crash; `passed`: HTTP < 400 with a success sign or no error; `warning`: nothing visible happened or only console errors/failed requests.
- Skip (no step created, no request sent) forms whose submit label contains: delete, remove, destroy, logout, sign out, unsubscribe, deactivate, purge, clear all. Dismiss `confirm()`/`alert()` dialogs. The login form uses the supplied credentials, never sample data. Forms inside modals/wizards, CAPTCHA and file uploads are not covered; `note` must mention "Forms in modals/wizards are not tested" when `submit_forms` is true.
- Env: `EXEC_SUBMIT_FORMS` (default true). `CLAUDE_CLI_TIMEOUT_S` default becomes 600 (`config.py`, `.env.example`, README).

### Frontend
- Checkbox next to Run menu test: "Also test forms (fills sample data and submits)", default checked, sent as `submit_forms`.
- Render `submit_form` steps nested under their menu with a form icon plus "empty"/"sample" label and the same status chips; keep text, not colour only. Button is enabled while status is `parsing` (disabled only while `running` or request in flight). Show the existing `note`.

## Notes (added at reconcile, form testing)
- Login form = a form with exactly one password field (not autocomplete=new-password) and at most one other text field. With credentials it is used; without them no `sample` step is created (an `empty` step still appears if required fields exist).
- Skip rule checks every button label and the form `action` path, not only the default submit; modals, role=dialog, CAPTCHA and invisible forms are skipped.
- `MAX_FORMS_PER_PAGE`/`MAX_FORMS` count forms, not steps.
- Empty submit does not clear prefilled fields. A sample submit with no request, navigation, banner or text change is `warning` ("No visible reaction after submit"); browser validation blocking sample data is a separate `warning`.
- Form steps have no screenshot (`screenshot_path` null). Parse-job test cases are appended after existing cases (order offset).

## Addendum 2026-10-07 (b) — error details (instruction 012)

### result (extended, all new fields optional/nullable)
`result` gains:
- `"error_type": null | "server_error" | "client_error" | "error_page" | "blank_page" | "timeout" | "navigation_failed" | "console_error" | "failed_request" | "validation_missing" | "no_reaction" | "form_error_banner" | "browser_validation_blocked" | "file_input_skipped" | "crash" | "interrupted"` (null when status is passed/pending/running).
- `"page_url": string | null` — final URL at the time of the check (fragment removed; query string kept but values of keys named token, key, secret, password, auth, session replaced with `***`).
- `"details": null | { "console_messages": [ { "type": "error" | "pageerror", "text": string(<=300), "location": string | null } ] (max 5), "failed_requests": [ { "method": string, "url": string, "status": int } ] (max 5, status 0 for network failure), "excerpt": string | null (<=300 chars: page title/heading of an error page, or the text of the error banner/validation message) }`.
Mapping: HTTP 5xx -> `server_error`; HTTP 4xx -> `client_error`; error-page markers -> `error_page`; blank body -> `blank_page`; 15 s timeout -> `timeout`; goto failure -> `navigation_failed`; console errors only -> `console_error`; failed XHR/fetch only -> `failed_request` (if both, choose `failed_request` and still list both in details); form: empty submit succeeded despite required fields -> `validation_missing`; sample submit with no visible reaction -> `no_reaction`; new error banner or 4xx/5xx on submit -> `form_error_banner` (5xx still sets `http_status`); browser validation blocked sample data -> `browser_validation_blocked`; file input skipped -> `file_input_skipped`; executor exception -> `crash`; stale run -> `interrupted`.
Existing fields (`status`, `error`, `http_status`, `console_errors`, `failed_requests`, `duration_ms`) are unchanged; `console_errors`/`failed_requests` remain integer counts. Storage: nullable columns/JSON on `step_results`; existing databases get ALTER TABLE at startup. Never put credentials or typed passwords in `details`.

### Frontend
- Show, for every failed/warning result: a title and plain-English explanation per `error_type`, a "What to check" list (frontend-owned text), and an evidence block (page URL, HTTP status, console messages, failed requests as method+URL+status, excerpt). Handle old/missing fields gracefully (fall back to `error` text and counts).
- Issues summary grouped by `error_type` with counts; filters All/Failed/Warning/Passed; ring score chart; report-style header with run meta; Run again.

## Notes (added at reconcile, error details + redesign)
- Passed steps also carry `page_url`; `details` exists only for failed/warning steps.
- Network failures appear in `details.failed_requests` with status 0 but are not counted in the integer `failed_requests`.
- `crash` is used only for form-step exceptions; menu-step exceptions map to `navigation_failed` or `timeout`.
- `excerpt` is filled only for server_error, client_error, error_page (menu) and form_error_banner (form); validation_missing, browser_validation_blocked and no_reaction have no excerpt yet.
- Stale running steps become failed with `error_type=interrupted`.

## Addendum 2026-10-07 (c) — validation matrix (instruction 013)

### POST /test-runs/{id}/execute (extended)
Body gains optional `"validation_depth": "basic" | "standard" | "thorough"` (default `"thorough"`, env `EXEC_VALIDATION_DEPTH`; `422 invalid_request` for other values). `basic` = today's behavior (empty + sample). Caps: `MAX_CASES_PER_FORM` (25), `MAX_CASES` (200); beyond them cases are skipped and a note says so. Only runs when `submit_forms` is true.

### Steps: case steps and `meta`
Each case is a `submit_form` step placed after the form's `empty`/`sample` steps. Fields: `target` = `"<menu label> > <form> > <field label>"`, `value` = human-readable data, e.g. `"Invalid format: abc@"` (long values truncated to 80 chars with an ellipsis), `expected` = `"accepted"` | `"rejected"` | `"no server error"`. Every step in the response gains `"meta": null | { "kind": "valid" | "invalid" | "security" | "tolerant", "category": "valid_sample" | "empty" | "format" | "boundary" | "blank" | "special" | "unicode" | "long" | "xss" | "sqli" | "manual_valid" | "manual_invalid", "field": string | null, "form": string | null, "source": "auto" | "manual" }` (null for menu steps; existing `empty`/`sample` steps get kind invalid/valid with category `empty`/`valid_sample`).

Outcome rules: kind `invalid` -> rejected = passed, accepted = failed (`invalid_accepted`); kind `valid` -> accepted = passed, rejected = failed (`valid_rejected`); kind `security` with `xss` -> executed/rendered as markup = failed (`xss_risk`), accepted but inert = warning (`xss_risk`), rejected = passed; `sqli` -> SQL error text (SQL syntax, SQLSTATE, ORA-, unclosed quotation, sqlite3., PG::) or 5xx = failed (`sql_error`), otherwise passed; kind `tolerant` (special, unicode, long) -> failed only on 5xx (`server_error`) or crash. Rejection detection: native invalid state, validation messages (role=alert, aria-invalid, .error/.invalid-feedback), 4xx/422, no success sign/navigation, or maxlength truncation. New `error_type` values: `invalid_accepted`, `valid_rejected`, `xss_risk`, `sql_error`. `details.excerpt` carries the validation message or the matched SQL error text (<=300 chars).

Manual-derived cases: `field_rules` (contract 003 addendum) are read from the database at execution start; match a form field by normalized label/name/placeholder (case-insensitive, contains either way); each `valid` example -> kind valid, category `manual_valid`, source `manual`; each `invalid` example -> kind invalid, category `manual_invalid`, source `manual`. If no rules exist yet and the run's manual parsing is still running, only auto cases run and the sweep `note` includes "Manual rules were not available yet". Reload the page before each case. Payloads must never include destructive SQL (no DROP/DELETE/UPDATE).

### Frontend
- Setup panel: "Validation depth" select (Basic / Standard / Thorough, default Thorough) with a one-line hint about time and sample data; sent as `validation_depth` (only when forms are enabled).
- Results: group form case steps by form, then field (use `meta`), collapsible group headers with counts per status; each case row shows data used (`value`), expected (`expected`), source badge ("manual" vs "auto"), and the same chip/detail UI. Add titles, explanations and "What to check" text for `invalid_accepted`, `valid_rejected`, `xss_risk`, `sql_error`. Issues summary and filters include them. Show "Rules found in the manual" (from `field_rules`) inside the Manual steps section. Handle missing `meta`/`field_rules` gracefully.

## Notes (added at reconcile, validation matrix)
- "Parsing not finished" is detected as: no field rules AND no manual test cases saved yet (run status is already `running`), so the note "Manual rules were not available yet" also appears when parsing failed or the manual has no rules. It is added only when depth is not basic.
- A 5xx on ANY case kind is `failed` (`server_error`, or `sql_error` for the SQL payload), not only for tolerant cases.
- maxlength truncation (or the browser refusing the value) means the form is not submitted and counts as rejected; for kind valid this is `valid_rejected`.
- Rejection heuristic: no request, no navigation and no page text change together = rejected; new banners count as validation messages unless they look like success text.
- Rule matching: contains either way, but a matched fragment must be >= 3 characters; underscores are word separators.
- Case `value` format: "<Label>: <data>", max 80 chars. Login forms (single password field) get no cases. Auto cases only for text-like, email, tel, number, date (min/max boundary only), password, url; XSS/SQL payloads only on text/textarea (url gets javascript:alert(1)); select/checkbox/radio/file are skipped.
- Case steps follow each form own empty/sample steps (not all forms at the end of the menu).

## Addendum 2026-10-07 (d) — page actions (instruction 014)

### POST /test-runs/{id}/execute (extended)
Body gains optional `"test_actions": true | false` (default `true`, env `EXEC_TEST_ACTIONS`; non-boolean -> `422 invalid_request`). Caps `MAX_ACTIONS_PER_PAGE` (15), `MAX_ACTIONS` (150); beyond them actions are skipped and noted. Env `ACTION_DENY_EXTRA` (comma-separated words) extends the denylist.

### Steps
After a menu step and its form steps, each tested page action is a step: `action: "click_action"`, `target: "<menu label> > <action label>"`, `value: "<kind>: <href or ->"` (e.g. `"row_action: /sales/:id"`), `expected: "reacts"`, `meta: { kind: "action", category: "action_link" | "action_button" | "action_tab" | "action_row" | "action_pagination", field: null, form: null, source: "auto" }`. `meta.kind` gains the value `"action"`. Forms found after the action (modal/drawer or the page it navigated to) are tested like menu forms; their steps (empty/sample/cases, with `target` prefix `"<menu label> > <action label> > <form> ..."`) are inserted right after that action step. All existing result fields apply; `error_type` gains `action_no_effect`.

### Discovery and denylist (backend)
Candidates are visible, enabled elements in the page body: same-origin `a[href]`, `button`, `[role=button]`, `[role=tab]`, `[data-bs-toggle]`, `[data-toggle]`, icon-only buttons with aria-label or title, row actions inside `tr`/list items, pagination links. Exclude anything inside `nav`, `header`, `aside`, `[role=navigation]`, `[role=menubar]` (already covered as menus) and anything inside a form's own submit controls (covered by form tests). Label = innerText, aria-label or title (trimmed, collapsed). Signature = lowercase label + kind + href with numeric and uuid path segments replaced by `:id`; keep the first of each signature. Denylist (label, href path, aria-label): delete, remove, destroy, purge, clear all, logout, sign out, unsubscribe, deactivate, void, refund, plus `ACTION_DENY_EXTRA`, external domains, `mailto:`, `tel:`, `javascript:`, downloads, bare `#`. Never click a submit button of a form that forms.py would skip.

### Execution and outcome rules
Reload the page (open context), highlight, click, wait for load/networkidle (<= 3 s), then classify in this order:
1. New page (URL changed or navigation response): check like a menu (HTTP status, error-page markers, blank page, console errors, failed requests) -> passed/warning/failed with the existing error types; then run form tests (and validation matrix) on that page.
2. Modal/drawer appeared (`dialog[open]`, `[role=dialog]`, `[role=alertdialog]`, `.modal.show`, `[aria-modal=true]` newly visible): passed if it shows content; run form tests on its forms with an opener so each case reloads the page and clicks the action again to re-open it; close afterwards (Escape, then a close button).
3. Popup/new tab/download: passed ("Opened a new tab" / "Started a download"); close popups.
4. In-place change (visible text or ARIA state such as aria-selected/aria-expanded changed): passed.
5. None of the above (no navigation, no modal, no text/ARIA change, no request): warning with `error_type: "action_no_effect"`, `error: "Nothing happened after clicking"`.
Errors during click (element not clickable, detached) -> failed with `error_type: "crash"`... except obstructed/not visible -> warning "Could not click". Dialogs are always dismissed. One level only: actions on pages reached by an action are not followed; the sweep `note` says "Actions inside pages opened by an action were not followed" when `test_actions` is true.

### Modal forms and the opener
`forms.discover_forms` accepts forms inside a visible modal ONLY when an opener context is given; without an opener modal forms stay skipped. The opener context `{ url, action: { signature, label, kind, nth } }` is applied by one helper (e.g. `open_context(page, ctx)`) wherever the executor previously did `page.goto(page_url)` for a form step or case: goto url, then re-click the action found by label/kind/nth, wait for the modal.

### Frontend
- `StepAction` gains `click_action`; `meta.kind` gains `action`; `ErrorType` gains `action_no_effect`; `executeRun(id, creds, submit_forms, validation_depth, test_actions)`.
- Setup panel: checkbox "Also test buttons, tabs and links inside pages" (default on, sent as `test_actions`).
- Results: under each menu show "Page actions" (icon by category, label, result chip, detail); forms opened by an action stay grouped by the existing form/field grouping, labelled with their action path. `errorInfo` entry for `action_no_effect` (title, explanation, what to check).
- Markdown export (instruction 014): "Export .md" and "Copy as Markdown" in the report header. `buildMarkdown(run, steps, summary, note)` returns: `# Test report`, run info (URL, run id, started, status), counts table (total/passed/warning/failed/left), note and limits, "Issues to fix" (error type, title, count), then `## Failed` and `## Warning`, each grouped by menu (`### <menu>`), each item with path (menu > action/form > field), status, error type + title, explanation, "What to check" bullets, evidence (page URL, HTTP status, duration, data used, expected, source, console messages, failed requests as `METHOD url -> status`, excerpt, error message). No passed items except as a count. Escape pipes/backticks in tables and code spans; truncate over-long text to 500 chars. File name `test-report-<first 8 chars of run id>-<YYYY-MM-DD>.md`, saved via Blob + anchor; copy uses the clipboard inside try/catch. Disabled with a hint when there are no failed or warning items.

## Notes (added at reconcile, page actions)
- Messages for passed outcomes ("Opened a new tab", "Started a download") are stored in `result.error` with status passed and `error_type` null.
- "Could not click" (obstructed/not visible) is a warning with `error_type: action_no_effect`.
- Modal / in-place / popup / download outcomes become warning (`console_error` / `failed_request`) when console errors or failed XHR occur; a modal that opens empty is warning `action_no_effect` ("Dialog opened with no content").
- In-place reaction = text or ARIA change, or any XHR/fetch request. Download is checked before navigation (Playwright reports a download as a navigation response too).
- Clicking an already-selected tab counts as "nothing happened" (warning); this can be a false positive.
- Pagination signatures normalise numbers in labels to `#` (page 2 and 3 share one).
- `kind` values: link, button, tab, row_action, pagination.
- `test_actions=true` with `submit_forms=false`: actions run, but forms opened by actions are not tested.
- Sweep note gets "Actions inside pages opened by an action were not followed" (after the modal note, before the manual-rules note).
- Frontend report shows run `created_at` as the start time (the API has no start/end timestamps).

## Addendum 2026-10-07 (e) — time budget and phases (instruction 015)

### POST /test-runs/{id}/execute (extended)
Body gains `"max_minutes": integer 1..240` (optional; default from env `EXEC_OVERALL_TIMEOUT_S`, which now defaults to 3600) and `"fast_mode": boolean` (default false). Invalid values -> `422 invalid_request`. The effective limit is stored on the run (`max_minutes`).

### Run fields
`GET /test-runs/{id}` and the top level of `GET /test-runs/{id}/steps` gain `"started_at": string (ISO 8601 UTC) | null`, `"finished_at": string | null`, `"max_minutes": integer | null`. `started_at` is set when execution begins, `finished_at` when the run reaches `done` or `failed` (both null for runs created before this change). Storage: nullable columns on `test_runs` with safe startup ALTER TABLE.

### Scheduling (backend)
Phase 1 (breadth): visit every menu (subject to MAX_MENUS), then for each page its forms' empty/sample steps and its page actions (including forms opened by actions: empty/sample only). While doing so, collect case jobs (form, opener context, anchor step id, page label) instead of running them. Phase 2 (depth): run the collected case jobs in round-robin order, one case per form per round, until jobs are exhausted or the time budget is spent. Case steps are inserted with `add_form_steps(anchor_id, ...)` so `/steps` order is menu, its forms, form cases after their form, actions, action forms (unchanged from before). Case steps are created only when their job is first run (a stopped run therefore has fewer case steps rather than many pending ones); the note reports how many cases were skipped, e.g. "Stopped at the time limit (15 min); validation cases for 4 forms were not run".
Time limit: checked before each step/case. When exceeded, finish gracefully: set the run `done`, `finished_at`, and add the note "Stopped at the time limit (<N> min); <X> checks were not run" (X = pending steps + skipped case jobs; when phase 1 itself is cut short, the unvisited menus remain pending). `failed` only for real errors. The old behavior of marking the run `failed` with "Overall time limit exceeded" is removed.
Speed: remove browser-level `slow_mo`; add `pace(page)` (waits `EXEC_SLOW_MO_MS`, default 300, only in phase 1 watchable steps: before/after a click, after highlight, after sample fill; skipped when `fast_mode`, and never used by tests unless enabled). In case runs, networkidle waits are 1.5 s. Highlighting is skipped in fast mode.

### Frontend
- Setup panel: "Max duration" select (15 / 30 / 60 / 120 minutes, default 60) sent as `max_minutes`; "Fast mode" checkbox (hint: no pauses between actions) sent as `fast_mode`.
- Report header: elapsed time "Elapsed mm:ss / <limit>:00" while running (computed from `started_at`, `finished_at` when present, falling back gracefully); when the sweep `note` contains "Stopped at the time limit" show an amber banner "Stopped at the time limit — <X> checks were not run" (use the note text), keep the run status `done` (not an error state). `buildMarkdown` uses `started_at` for "Started" (fallback `created_at`), adds "Finished" and "Duration" when available, and includes the banner text in "Note and limits".

## Notes (added at reconcile, time budget and phases)
- The stop note shows N as `max(1, round(limit_s / 60))`. X counts pending steps plus each case job not yet started as 1 (their cases do not exist yet); a job that already started contributes its remaining cases as pending steps. When jobs never started the note adds " (validation cases for K forms were not started)".
- Phase 2 cap notes ("ran the first N", MAX_CASES) are appended to the note only when the run ends, so they appear late; phase 1 notes are no longer updated live per menu.
- `started_at` is set twice (at the execute call and when the executor subprocess starts, the second one shares the deadline clock).
- The deadline is checked between steps and cases; one phase-1 action or form may overrun it slightly.
- `max_minutes` omitted -> `round(EXEC_OVERALL_TIMEOUT_S / 60)` is stored on the run.
- Measured on a local fixture form (headless, standard depth, 20 format cases): 2.47 s per case with launch-level slow_mo 400, 0.59 s per case after (about 4.2x). The fixture is fast to go idle, so the networkidle change shows little there; real sites should gain more. The "before" figure is the new code with slow_mo injected, not the old code verbatim.

## Addendum 2026-10-07 (f) — fewer false alarms (instruction 016)

### New `error_type` values
`submit_blocked`, `permission_denied`, `possible_duplicate` (all appear with status `warning`). Existing fields are unchanged.

### Rules (backend)
- **Submit state.** Before clicking a form's submit control (empty, sample and case steps), check `is_disabled()` and `aria-disabled=true`; if the click times out, scroll into view and retry once. Never force-click or call `requestSubmit()` to get around a disabled button. A disabled or unclickable submit: for `empty` and for kinds `invalid`/`security` -> `passed`, `error` = "Submit button was disabled, the UI blocked this value"; for sample, kind `valid` and kind `tolerant` -> `warning`, `error_type: "submit_blocked"`, `error` = "Submit stayed disabled or could not be clicked; the form may need data this tool cannot fill (for example choosing a product)". These situations are never `crash`.
- **XSS.** Payload executed (dialog or `window.__xss`) or rendered as live markup -> `failed`, `xss_risk`. Payload visible as text (escaped) or not visible at all -> `passed`, `error` = "Accepted but not executed; output is escaped or not shown here (stored output on other pages is not checked)". The old accepted-but-inert `warning` is removed.
- **Page actions.** Before clicking, if the element is already active (`aria-selected`, `aria-pressed` or `aria-checked` equal to true; `aria-current` present and not false; or a class token among active, selected, current, is-active), do not click: `passed`, `error` = "Already active, nothing to switch". For links whose href is a `#fragment`, a change of `location.hash` or of `window.scrollY` after the click counts as an in-place reaction -> `passed`.
- **Unique sample data.** In sample and case fills: phone values are unique per submission (`017` followed by 8 digits derived from time and a random number); text fields whose name, id or label matches (case-insensitive) code, sku, barcode, invoice, reference, username, slug or ref get a unique numeric suffix; emails keep the `test+<timestamp>@example.com` form. Manual-derived valid examples are used as written.
- **Status codes on submit.** Valid sample or valid case answered HTTP 401 or 403 -> `warning`, `permission_denied`, `error` = "The test user is not allowed to do this (HTTP <code>). Check its role". Invalid/security case answered 401/403 -> `warning`, `permission_denied` (inconclusive; NOT rejected/passed), same text. Valid sample or valid case answered HTTP 409 -> `warning`, `possible_duplicate`, `error` = "HTTP 409 Conflict: the value may already exist (duplicate)". For kind `invalid` a 409 still counts as rejected.

### Frontend
`ErrorType` gains the three values; `errorInfo.ts` gets title, explanation and "What to check" for each: `submit_blocked` ("The submit button did not allow a test"; check when the button becomes enabled and describe that in the manual, for example which product to choose), `permission_denied` ("The test user lacks permission"; check the role and permissions of the test user, or log in as a role allowed to do this), `possible_duplicate` ("A conflict, possibly a duplicate"; check whether the same value is already stored or the rule is a uniqueness rule). Issues summary, filters and the Markdown export need no further change.

## Notes (added at reconcile, fewer false alarms)
- SUPERSEDES the earlier page-action note "Clicking an already-selected tab counts as nothing happened (warning)": an already-active control is now passed ("Already active, nothing to switch") without a click.
- Empty submit answered 401/403 stays passed (4xx = validation feedback); it is not treated as inconclusive.
- Tolerant cases (special, unicode, long) answered 401/403 stay passed; only valid, invalid and security cases become `permission_denied`.
- 5xx still wins over 401/403/409 when both appear.
- The code-like field rule is a plain substring match (for example "ref" also matches "prefix"); harmless, it only adds a unique suffix.
- Unique digits never repeat inside one process; phones are `017` + 8 digits.
