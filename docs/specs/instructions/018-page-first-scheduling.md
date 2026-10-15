---
id: "018"
title: Page-first scheduling
date: 2026-10-15
status: frozen
---

## Original request
"random page test calay ami cassi page wise complete korbe. ekta page sesh hole arekta page jabe. kintu loop hosse ek page theke onno page abar ager page. eta bad" - a run should finish one page completely, then go to the next; today it hops between pages and returns to earlier ones.

## Assumptions & corrections
- Cause (traced in code): phase 2 of instruction 015 runs validation cases round-robin across all forms, and each case reloads its form's page, so the browser goes A, B, C, A, B, C. A second cause: an action that navigates to a page that is also a menu item gets that page's forms tested inside the action and again under its own menu.
- Default becomes page-first: after a menu's phase 1 (forms empty/sample, page actions), that menu's validation cases run to completion before the next menu. Breadth-first (old round-robin) stays as an option `schedule=round_robin`, because it covers every form when the time limit is short. Env `EXEC_SCHEDULE` (`page` default | `round_robin`), per-run override.
- With page-first and a short time limit, later pages may stay untested; the existing "Stopped at the time limit" note and pending steps already cover this.
- An action that navigates to a URL already in the menu set does not form-test that page again (it is tested under its own menu); the step says so.

## Agreed scope
Scheduling change in the runner, `schedule` setting and run field, setup-panel select, action-navigation dedupe.

## Out of scope
Changing menu order, discovery or dedupe by final URL, per-field ordering inside a form.
