import type { ErrorType } from "@/lib/api";

export type ErrorInfo = { title: string; explain: string; check: string[] };

// Frontend-owned wording for every error_type in contract 004 (addendum b).
export const ERROR_INFO: Record<ErrorType, ErrorInfo> = {
  server_error: {
    title: "Server error (5xx)",
    explain:
      "The server answered with an error status, so it failed while handling this request. This is usually a bug or an outage on the server side.",
    check: [
      "Open the server logs around the time of this run.",
      "Open the page yourself and see if the error repeats.",
      "Check the database and any service the page depends on.",
    ],
  },
  client_error: {
    title: "Client error (4xx)",
    explain: "The server rejected the request, for example the page was not found or access was denied.",
    check: [
      "Check the menu link: is the path correct?",
      "If the page needs a login, run again with the Login option filled in.",
      "Check the permission of the test user for this page.",
    ],
  },
  error_page: {
    title: "Error page shown",
    explain:
      "The page loaded, but its title or heading looks like an error page such as 404 or Internal Server Error.",
    check: [
      "Open the page in a browser and read the message.",
      "Check whether the route exists in the app.",
      "Look at the excerpt below to see what the page said.",
    ],
  },
  blank_page: {
    title: "Blank page",
    explain: "The page loaded but nothing is visible. The app may have crashed while rendering.",
    check: [
      "Open the page and the browser console and look for a JavaScript error.",
      "Check that the data the page needs is returned by the API.",
      "Try again: the page may be slow to render.",
    ],
  },
  timeout: {
    title: "Timed out",
    explain: "The page did not finish loading within 15 seconds.",
    check: [
      "Check if the page or one of its API calls is very slow.",
      "Check server load and network speed.",
      "Look for a request that never completes.",
    ],
  },
  navigation_failed: {
    title: "Navigation failed",
    explain:
      "The browser could not open this address at all (for example a connection error or a bad certificate).",
    check: [
      "Check that the site is running and reachable from this computer.",
      "Check the link address and its HTTPS certificate.",
      "Check for a redirect loop.",
    ],
  },
  console_error: {
    title: "Console errors",
    explain: "The page loaded, but the browser console logged JavaScript errors. Parts of the page may not work.",
    check: [
      "Read the console messages below and find the failing script.",
      "Open the page with DevTools open to reproduce it.",
      "Fix the undefined values or missing resources named in the message.",
    ],
  },
  failed_request: {
    title: "Failed requests",
    explain:
      "The page loaded, but some of its background (XHR/fetch) requests returned an error or never finished. Data on the page may be missing.",
    check: [
      "Look at the failed URLs and their status codes below.",
      "Check the API endpoint and its logs.",
      "Check authentication: a 401 or 403 often means the login is missing.",
    ],
  },
  validation_missing: {
    title: "No validation on empty submit",
    explain: "The form has required fields, but submitting it empty was accepted without any validation message.",
    check: [
      "Check that required fields are validated in the browser and on the server.",
      "Make sure an error message is shown next to the empty field.",
      "Check that empty data was not saved by mistake.",
    ],
  },
  no_reaction: {
    title: "No visible reaction",
    explain: "The form was submitted with sample data, but nothing visible changed: no message, no navigation and no request.",
    check: [
      "Submit the form by hand and see if anything happens.",
      "Check the submit handler and that the button is wired up.",
      "Add a success or error message so users get feedback.",
    ],
  },
  form_error_banner: {
    title: "Form showed an error",
    explain: "After the submit, the page showed an error message or the server answered with 4xx/5xx.",
    check: [
      "Read the message in the excerpt below.",
      "Check what the server returned for this form request.",
      "The sample data may not fit your rules: try real values by hand.",
    ],
  },
  browser_validation_blocked: {
    title: "Browser validation blocked the sample",
    explain:
      "The browser refused to submit the sample data because a field rule (pattern, min/max, format) was not met.",
    check: [
      "Find the field with a strict pattern or limit.",
      "Try the form by hand with a valid value.",
      "Check that the rules are not stricter than needed.",
    ],
  },
  file_input_skipped: {
    title: "File upload skipped",
    explain: "The form has a file input. The test does not upload files, so this part was not tested.",
    check: ["Test the file upload by hand.", "Nothing is broken if the rest of the form works."],
  },
  crash: {
    title: "Test crashed",
    explain: "The test runner hit an unexpected error while checking this item. It may not be a problem in your site.",
    check: ["Read the message below.", "Run the test again.", "Check the API logs for the executor error."],
  },
  interrupted: {
    title: "Run interrupted",
    explain: "The run was stopped before it finished, for example because the API server restarted.",
    check: ["Start the run again.", "Keep the API server running until the run finishes."],
  },
  invalid_accepted: {
    title: "Invalid data accepted",
    explain: "The form accepted a value that should have been rejected, such as a wrong format, out-of-range or blank value.",
    check: [
      "Check the rule for this field in the manual and compare it with the form.",
      "Add or fix validation in the browser and, more importantly, on the server.",
      "Check whether the invalid value was saved.",
    ],
  },
  valid_rejected: {
    title: "Valid data rejected",
    explain: "The form refused a value that the manual or normal use says is valid, so real users may be blocked.",
    check: [
      "Read the validation message in the excerpt below.",
      "Check the pattern, min/max and length rules on this field.",
      "Try the same value by hand.",
    ],
  },
  xss_risk: {
    title: "Possible XSS risk",
    explain:
      "A script-like payload was accepted. If it was shown back as live markup or executed, attackers could run code in other users' browsers.",
    check: [
      "Check where this field's value is displayed again and that it is HTML-escaped.",
      "Reject or sanitize markup on the server.",
      "Open the saved record and see if the payload renders as text.",
    ],
  },
  sql_error: {
    title: "SQL error exposed",
    explain:
      "A quote-style SQL payload caused a database error or a server crash. The input may be placed into a query unsafely.",
    check: [
      "Use parameterized queries instead of building SQL from input.",
      "Read the matched error text in the excerpt below.",
      "Hide raw database errors from users.",
    ],
  },
  action_no_effect: {
    title: "Button or link did nothing",
    explain:
      "The test clicked this button, tab or link, but nothing happened: no new page, no dialog and no visible change.",
    check: [
      "Click it by hand and see if it reacts.",
      "Check that the click handler or link address is wired up.",
      "Check whether it is disabled until something else is filled in (then this may be fine).",
    ],
  },
  submit_blocked: {
    title: "The submit button did not allow a test",
    explain:
      "The submit button stayed disabled or blocked, so the form could not be sent. The test could not check what happens on submit.",
    check: [
      "Find out when the button becomes enabled (for example after choosing a product or filling a required field).",
      "Describe that step in the manual so the test can follow it.",
      "Try the form by hand and see if the button ever turns on.",
    ],
  },
  permission_denied: {
    title: "The test user lacks permission",
    explain:
      "The server answered 401 or 403, so the test user is not allowed to do this. The result is inconclusive, not a pass or a bug.",
    check: [
      "Check the role and permissions of the test user.",
      "Run again with a login for a role that is allowed to do this.",
      "Check that the session did not expire during the run.",
    ],
  },
  possible_duplicate: {
    title: "A conflict, possibly a duplicate",
    explain:
      "The server answered 409 Conflict for a valid value. The same value may already be stored, so this may not be a bug.",
    check: [
      "Check whether the same value is already saved.",
      "Check whether this field has a uniqueness rule (code, email, username).",
      "Run again with a different value or clean up old test records.",
    ],
  },
};

export const FALLBACK_INFO: Record<"failed" | "warning", ErrorInfo> = {
  failed: {
    title: "Check failed",
    explain: "This check failed. No detailed error type was recorded for it (older result), so only the message is shown.",
    check: ["Open the page by hand and compare it with the message.", "Run the test again to get more details."],
  },
  warning: {
    title: "Check finished with warnings",
    explain: "This check finished but something looked wrong. No detailed error type was recorded (older result).",
    check: ["Open the page with the browser console open.", "Run the test again to get more details."],
  },
};

export const infoFor = (type: string | null | undefined, status: "failed" | "warning"): ErrorInfo =>
  (type ? (ERROR_INFO as Record<string, ErrorInfo | undefined>)[type] : undefined) ?? FALLBACK_INFO[status];
