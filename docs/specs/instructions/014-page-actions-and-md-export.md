---
id: "014"
title: Page actions and Markdown export
date: 2026-10-07
status: frozen
---

## Original request
"ekhane faild and warning er exportable md fiel dite hobe. esara o kisu jini missing dekha jasse like ekta menu ekta list ace seta abar kisu action contain kore sei action gulo test hoitece nah. jemon ekta jini dekhal pos saled test hoi nai ei rakom case gulo mis hoitece"
Clarified: test one action per type; also test the forms that an action opens (modal, drawer or new page) including valid/invalid/security cases.

## Assumptions & corrections
- Export: a "Export .md" button (and "Copy as Markdown") in the report header produces a Markdown file with run info, counts, the sweep note and limits, an "Issues to fix" summary, and ONLY failed and warning items grouped by menu, each with error type, explanation, what to check and the evidence. Passed items are only counted. File name `test-report-<run id first 8>-<date>.md`. Frontend only, built from data already loaded.
- Why things were missed: menu discovery covers only nav/header/aside/navigation containers, so buttons and links in the page body (list row actions, tabs, cards, "Add New", pagination) were never touched, and forms inside modals were deliberately skipped.
- New page action sweep, after each menu page check and its form tests: discover clickable elements in the page body (same-origin links, buttons, role=button, role=tab, data-bs-toggle, icon buttons with aria-label/title, row actions, pagination), dedupe by signature (label + kind + href with numeric/uuid parts replaced by `:id`) so one per type is tested, caps `MAX_ACTIONS_PER_PAGE` 15 and `MAX_ACTIONS` 150.
- Denylist: delete, remove, destroy, purge, clear all, logout, sign out, unsubscribe, deactivate, void, refund, external domains, mailto:, tel:, downloads; extendable with `ACTION_DENY_EXTRA`.
- Per action: reload the page, highlight, click, then classify: navigated (check like a menu; run form tests on the new page), modal/drawer opened (test its forms with the same form tests and validation matrix, re-opening the modal for every case, then close it), new tab/popup/download (passed, popup closed), in-place content change (passed), nothing happened (warning `action_no_effect`).
- Steps: action `click_action`, target "<menu> > <action label>", value kind + href, `meta.category` one of action_link, action_button, action_tab, action_row, action_pagination; modal/page form steps follow their action step.
- Control: `test_actions` flag in the execute body (default true, env `EXEC_TEST_ACTIONS`). Depth is one level: actions inside pages reached by an action are not followed (noted).
- New error type: `action_no_effect`.
- Spec 006 (report) later adds HTML/PDF; the Markdown export lands earlier through this instruction.

## Agreed scope
Markdown export of failed/warning results, and the page action sweep with modal/page form testing.

## Out of scope
Following actions two levels deep, testing every row's action, wizards, CAPTCHA, file uploads, HTML/PDF export.
