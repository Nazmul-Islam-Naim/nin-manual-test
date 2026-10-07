---
id: "010"
title: Visible menu sweep
date: 2026-10-06
status: frozen
---

## Original request
"ami ektu batikrome cinta kortecilam. ar ta holo ekhane ekta window thakbe je puro system ta load korbe then one by one menu test korbe jete visible hobe."
Clarified: the tool discovers menus itself; the window is a real Chromium window on the user's screen.

## Assumptions & corrections
- Execution is a visible (headed) Chromium window with a small slow-motion delay; the window loads the whole system first.
- The tool discovers menus itself (nav, header, sidebar, role=navigation/menubar; same-origin links and menu items; one dropdown level) and visits them one by one.
- Denylist: logout/sign out, delete/remove, external domains, mailto:, tel:, downloads. Max menus configurable (default 30).
- A "test" per menu: navigation succeeds (HTTP < 400), no error-page markers, page not blank, console errors and failed XHR/fetch recorded; result passed, failed or warning. No form submits and no data changes.
- Optional login credentials supplied at execution time, never stored or logged.
- Running manual steps from spec 003 is not part of this step; it becomes a later requirement. Parsing (003) stays as is.
- Results are stored as a test case "Menu sweep" whose steps are `visit_menu` (target = menu label), so specs 005 and 006 apply unchanged.
- The executor runs in a separate subprocess so the window opens in the user's desktop session. Local use only.

## Agreed scope
Replace the headless, manual-driven execution design of spec 004 with a visible, self-discovering menu sweep, triggered by `POST /test-runs/{id}/execute`.

## Out of scope
Manual-step execution, form filling, other browsers, server/headless deployment, parallel runs.
