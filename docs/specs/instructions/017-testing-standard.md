---
id: "017"
title: Testing standard
date: 2026-10-15
status: frozen
---

## Original request
"ami ekta standard use korte cai" - the user wants the project to use a testing standard; "settings theke eta select korar option thakbe. default OWASP"; for how to use it: "jeta tomar kase best practice mone hoy". Agreed draft: a "Testing standard" select (OWASP default, ISTQB, ISO/IEC/IEEE 29119); the standard changes case order and adds a reference tag to each case; reports and run history show the standard.

## Assumptions & corrections
- "Settings" means the existing run setup panel (there is no separate Settings page). Default comes from `.env` (`EXEC_TESTING_STANDARD=owasp`) and can be overridden per run, like `validation_depth`.
- The standard changes only case order and tags, never the case set. Existing caps (25 per form, 200 total) are unchanged, so a lower-priority case may be cut by a cap, as today.
- Priority: OWASP puts xss, sqli, special, unicode, long first; ISTQB and ISO 29119 put boundary, blank, format first.
- Tags (`standard_ref`): OWASP - xss/sqli "OWASP A03: Injection", special/unicode/long "OWASP ASVS V5: Validation", format/boundary/blank "OWASP ASVS V5: Validation"; ISTQB - boundary "ISTQB: Boundary Value Analysis", format/blank "ISTQB: Equivalence Partitioning", others "ISTQB: Error Guessing"; ISO 29119 - same techniques named "ISO/IEC/IEEE 29119-4: <technique>".
- `validation_depth` stays independent. Old runs have no `standard_ref` (null).
- Wording is "mapped to", never "certified" or "compliant".

## Agreed scope
`testing_standard` setting and run field, standard-aware ordering in the case builder, `standard_ref` in case meta and step results, setup-panel select, display in report and run history.

## Out of scope
New test techniques, compliance certification claims, changing the case set per standard.
