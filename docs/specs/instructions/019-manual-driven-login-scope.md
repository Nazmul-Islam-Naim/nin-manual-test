---
id: "019"
title: Manual-driven login scope
date: 2026-10-15
status: frozen
---

## Original request
The user supplied a cashier user manual (demo login `cashier@rahim.demo` / `demo1234`, steps on the dashboard and POS) and expected the run to log in and test the logged-in pages first; the run tested only public pages (SmartPOS, Features, Pricing, FAQ, Log in). "user manual er upor base kore tomar bujhte hobe test ta ki after login na ki before login." Also: update the Google sheet.

## Assumptions & corrections
- Cause: the engine does not read login data from the manual, and `_login` silently does nothing when the start page has no password field (the start URL was the public home page).
- The parse step decides a scope in the same LLM call: `before_login`, `after_login` or `both`, plus `login_user` and the order, taken only from what the manual states. Unclear: `after_login` if login credentials are found, else `before_login`. `both`: manual order, public first if the order is unclear.
- Credential precedence: values typed in "Login (optional)" win; otherwise the credentials in the manual.
- No new credential storage: the run stores only `access_scope` and `login_user`. The password is read from the stored manual text when the run starts, and is masked in logs and responses (existing `Collector.secrets`).
- If the start page has no login form and credentials exist, the engine finds a "Log in / Sign in / লগইন" link and clicks it. If login still fails, the run does not fail: it adds a clear note and continues with the public menus.
- `after_login`: menus after login are tested first; public pages are skipped, or run last for `both`.
- Several users in the manual (rahim, mita): the first one is used.
- The setup panel shows "Detected: <scope>, user <login_user>" and lets the user change the scope (`access_scope` on execute).

## Agreed scope
`access` in the parse output, run fields `access_scope` and `login_user`, login-link discovery and ordering in the executor, setup-panel display and override, contract and spec updates.

## Out of scope
Step-by-step replay of the manual, role switching, storing credentials.
