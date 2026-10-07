import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ERROR_MARKER = re.compile(r"\b(404|500)\b|not found|internal server error", re.I)

# title + first heading + (only for short pages) body, so "404" deep in normal text is not a false alarm
PAGE_JS = """() => ({title: document.title || '',
  h1: (document.querySelector('h1,h2')||{}).innerText || '',
  body: (document.body ? document.body.innerText : '').trim()})"""


class UI:
    """Per-run look-and-feel switches (one executor process = one run; runner sets them at start)."""
    pace_ms = 0
    highlight = True


def pace(page) -> None:
    """Small pause so a human can follow phase 1 (never used in case runs)."""
    if UI.pace_ms:
        page.wait_for_timeout(UI.pace_ms)


SENSITIVE_KEYS = {"token", "key", "secret", "password", "auth", "session"}
MAX_ITEMS, MAX_TEXT = 5, 300


def sanitize_url(url: str | None) -> str | None:
    """Drop fragment; mask values of sensitive query keys."""
    if not url:
        return None
    u = urlsplit(url)
    q = [(k, "***" if k.lower() in SENSITIVE_KEYS else v) for k, v in parse_qsl(u.query, keep_blank_values=True)]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q, safe="*"), ""))


def redact(text: str | None, secrets) -> str | None:
    """Cap length and mask any known secret (login/sample passwords) so none reach the DB."""
    if text is None:
        return None
    for sec in secrets:
        if sec:
            text = text.replace(sec, "***")
    return text[:MAX_TEXT]


class Collector:
    """Counts console errors and failed XHR/fetch for the current menu, and keeps the first few as evidence."""

    def __init__(self, page):
        self.console_errors = self.failed_requests = 0
        self.secrets: list[str] = ["Test@12345"]  # sample password; runner adds the login password
        self.console_messages: list[dict] = []
        self.failed_request_list: list[dict] = []
        self.submit_statuses: list[int] = []  # non-GET + navigation responses (form submit outcome)
        self.dialogs: list[str] = []  # alert/confirm/prompt messages seen (XSS evidence; runner dismisses them)
        page.on("dialog", lambda d: self.dialogs.append(d.message))
        page.on("console", self._console)
        page.on("pageerror", self._pageerror)
        page.on("response", self._response)
        page.on("requestfailed", self._requestfailed)

    def _add(self, name):
        setattr(self, name, getattr(self, name) + 1)

    def _console(self, m):
        if m.type == "error" and "Failed to load resource" not in m.text:  # those are counted via responses
            self._add("console_errors")
            try:
                loc = m.location or {}
                where = f"{loc.get('url')}:{loc.get('lineNumber')}" if loc.get("url") else None
            except Exception:
                where = None
            self._msg("error", m.text, where)

    def _pageerror(self, e):
        self._add("console_errors")
        self._msg("pageerror", str(e), None)

    def _msg(self, kind, text, where):
        if len(self.console_messages) < MAX_ITEMS:
            self.console_messages.append({"type": kind, "text": redact(text, self.secrets),
                                          "location": sanitize_url(where) if where else None})

    def _req(self, method, url, status):
        if len(self.failed_request_list) < MAX_ITEMS:
            self.failed_request_list.append({"method": method, "url": redact(sanitize_url(url), self.secrets),
                                             "status": status})

    def _requestfailed(self, r):  # network failure: listed as status 0, not counted (counts stay as before)
        if r.resource_type in ("xhr", "fetch") and "ERR_ABORTED" not in (r.failure or ""):
            self._req(r.method, r.url, 0)

    def _response(self, r):
        if r.request.method != "GET" or r.request.is_navigation_request():
            self.submit_statuses.append(r.status)
        if r.request.resource_type in ("xhr", "fetch") and r.status >= 400:
            self._add("failed_requests")
            self._req(r.request.method, r.url, r.status)

    def details(self, excerpt: str | None = None) -> dict | None:
        excerpt = redact(excerpt.strip(), self.secrets) if excerpt and excerpt.strip() else None
        if not (self.console_messages or self.failed_request_list or excerpt):
            return None
        return {"console_messages": list(self.console_messages), "failed_requests": list(self.failed_request_list),
                "excerpt": excerpt}

    def reset(self):
        self.console_errors = self.failed_requests = 0
        self.console_messages, self.failed_request_list = [], []
        self.submit_statuses = []
        self.dialogs = []


def classify(http_status, page_info, console_errors, failed_requests):
    """-> (status, error). page_info = dict(title, h1, body) from PAGE_JS."""
    if http_status is not None and http_status >= 400:
        return "failed", f"HTTP {http_status}"
    if not page_info["body"]:
        return "failed", "Page is blank"
    head = f'{page_info["title"]} {page_info["h1"]}'
    if ERROR_MARKER.search(head) or (len(page_info["body"]) < 300 and ERROR_MARKER.search(page_info["body"])):
        return "failed", "Error page detected"
    if console_errors or failed_requests:
        return "warning", f"{console_errors} console error(s), {failed_requests} failed request(s)"
    return "passed", None


def menu_error_type(status: str, http_status, error: str | None, failed_requests: int) -> str | None:
    """Contract mapping for a menu result (status/error as produced by _visit + classify)."""
    if status == "passed":
        return None
    if http_status is not None and http_status >= 500:
        return "server_error"
    if http_status is not None and http_status >= 400:
        return "client_error"
    if error == "Page is blank":
        return "blank_page"
    if error == "Error page detected":
        return "error_page"
    if status == "failed":
        return "timeout" if (error or "").startswith("Timed out") else "navigation_failed"
    return "failed_request" if failed_requests else "console_error"


def menu_excerpt(page_info: dict | None) -> str | None:
    """Title/heading of an error page."""
    if not page_info:
        return None
    return (page_info.get("h1") or page_info.get("title") or "").strip() or None
