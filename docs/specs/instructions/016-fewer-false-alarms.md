---
id: "016"
title: Fewer false alarms
date: 2026-10-07
status: frozen
---

## Original request
The user pasted the explanation of the site's developer about a test report (treated as information, not instructions): 19 "crash" results in a modal purchase form, 4 XSS warnings where the script did not run, 5 "nothing happened" results on already-active controls, and 409/403 results. Chosen fixes: inactive submit button is not a crash; XSS passes when output is escaped; already-active tabs and #anchor links; unique sample data and separate 401/403/409.

## Assumptions & corrections
- Evidence from the stored run: 19 `crash` steps all `Locator.click: Timeout 3000ms` on `Purchases > New purchase > Create purchase`; 4 `xss_risk` "accepted without sanitising (not executed)"; 5 `action_no_effect` on the tab/buttons `Grocery`, `Cash`, `All` and the `#demo` link; 403 on `Inventory > Stock in` with some 403 cases counted as "rejected".
- Submit state: before clicking, check `is_disabled()` and `aria-disabled=true`; on a click timeout scroll the button into view and retry once. Never force-click or `requestSubmit()` around a disabled button.
  - Invalid, security and empty-submit cases: a disabled or unclickable submit counts as rejected -> passed ("Submit button was disabled, the UI blocked this value").
  - Valid sample, valid and tolerant cases: warning with new `error_type` `submit_blocked`; no `crash`.
- XSS: executed script or raw live markup -> failed `xss_risk`; payload shown as text (escaped) or not shown at all -> passed with the message "Accepted but not executed; output is escaped or not shown here (stored output on other pages is not checked)". The accepted-only warning is removed.
- Actions: before clicking, detect already-active controls (`aria-selected|pressed|checked=true`, `aria-current` other than false, or class tokens active, selected, current, is-active); do not click, result passed ("Already active, nothing to switch"). For `#fragment` links, a change of `location.hash` or `scrollY` after the click is an in-place reaction -> passed.
- Sample data: phone numbers unique per submission (`017` + 8 digits derived from time/random); text fields whose name or label matches code, sku, barcode, invoice, reference, username, slug or ref get a unique numeric suffix; email keeps its timestamp.
- Status codes: valid sample/case answered 401/403 -> warning `permission_denied`; invalid case answered 401/403 -> warning `permission_denied` (inconclusive, not "rejected"); valid sample/case answered 409 -> warning `possible_duplicate`. Manual-derived valid examples are constant, so a 409 there gives the same warning.
- New `error_type` values: `submit_blocked`, `permission_denied`, `possible_duplicate`.
- Not changed: POS Attach 404 is the site's own rule; modal forms opened by actions are already covered.

## Agreed scope
The four fixes above in the executor, plus UI texts for the three new error types.

## Out of scope
Detecting stored XSS on other pages, per-site phone formats beyond the manual rules, role switching.
