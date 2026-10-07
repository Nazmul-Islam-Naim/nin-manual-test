---
id: "002"
title: URL input
date: 2026-10-05
status: frozen
---

## Original request
"dhoro ami keta project make korte cai jar kaj hobe manula test automation korar jekhane project er user manula and url dea hobe ebong se seta test korbe ebong ekta report dibe"
PRD row R-002: URL ইনপুট — যে website/app test হবে তার URL দেওয়া ও validate করা.

## Assumptions & corrections
- Only http/https URLs; a missing scheme defaults to https://.
- Validation checks format and reachability (server-side request, 10 s timeout).
- localhost and private IPs are allowed by default (users test their own dev sites); configurable to block.
- One base URL per test run; relative paths in manual steps resolve against it.
- Login credentials are out of this step (part of R-004).
- A new test run starts with status `created`.

## Agreed scope
Accept and validate a URL, then create a test run linking manual (001) and URL.

## Out of scope
Credentials, crawling, multiple base URLs per run, executing the test.
