"""Form submit testing on a visited menu page: discovery, sample values, empty/sample submit, classification."""
import random
import re
import time
from datetime import datetime

from app.services.executor.checks import Collector, pace, redact, sanitize_url

SKIP_LABEL = re.compile(r"delete|remove|destroy|log\s*-?out|sign\s*-?out|unsubscribe|deactivate|purge|clear\s+all", re.I)
ERROR_TEXT = re.compile(r"error|fail|exception|invalid", re.I)
MODAL_NOTE = "Forms in modals/wizards are not tested"
NO_VALIDATION = "No validation feedback on empty submit"
BLOCKED_OK = "Submit button was disabled, the UI blocked this value"
BLOCKED_WARN = ("Submit stayed disabled or could not be clicked; the form may need data this tool cannot fill "
                "(for example choosing a product)")
PERMISSION = "The test user is not allowed to do this (HTTP {code}). Check its role"
DUPLICATE = "HTTP 409 Conflict: the value may already exist (duplicate)"
CODE_LIKE = re.compile(r"code|sku|barcode|invoice|reference|username|slug|ref", re.I)

_VISIBLE = ("(e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); "
            "return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; }")

FORMS_JS = """() => { const vis = VIS;
  return [...document.forms].map((f, idx) => {
  const inputs = [...f.querySelectorAll('input,select,textarea')]
    .filter(e => !['hidden', 'submit', 'button', 'reset', 'image'].includes(e.type));
  const buttons = [...f.querySelectorAll('button,input[type=submit],input[type=button],input[type=image],[role=button]')]
    .map(b => (b.innerText || b.value || b.getAttribute('aria-label') || b.title || '').trim().replace(/\\s+/g, ' '));
  const sub = f.querySelector('button[type=submit],input[type=submit],button:not([type])');
  const submit = sub ? (sub.innerText || sub.value || sub.getAttribute('aria-label') || '').trim() : '';
  const pw = inputs.filter(e => e.type === 'password');
  return {idx, visible: vis(f), modal: !!f.closest('dialog,[role=dialog],[role=alertdialog],[aria-modal=true],.modal'),
    captcha: !!f.querySelector('.g-recaptcha,.h-captcha,[data-sitekey],iframe[src*=captcha]'),
    buttons, submit, action: f.getAttribute('action') || '',
    name: (f.getAttribute('aria-label') || f.getAttribute('name') || f.id || '').trim(),
    required: inputs.some(e => e.required || e.getAttribute('aria-required') === 'true'),
    passwords: pw.length, newpw: pw.some(e => (e.autocomplete || '').includes('new')),
    textish: inputs.filter(e => !['password', 'checkbox', 'radio', 'file', 'select-one'].includes(e.type)).length};
}); }""".replace("VIS", _VISIBLE)

FIELDS_JS = """(form) => { const vis = VIS;
  return [...form.querySelectorAll('input,select,textarea')].map((e, i) => ({
    i, tag: e.tagName.toLowerCase(), type: e.type, name: e.name || e.id || '',
    label: ((e.labels && e.labels[0] ? e.labels[0].innerText : '') || e.getAttribute('aria-label') || e.placeholder
            || e.name || e.id || 'value').trim().replace(/\\s+/g, ' '),
    required: e.required || e.getAttribute('aria-required') === 'true',
    placeholder: e.placeholder || '', pattern: e.getAttribute('pattern'), step: e.getAttribute('step'),
    min: e.min || null, max: e.max || null, maxlength: e.maxLength > 0 ? e.maxLength : null,
    disabled: e.disabled, readonly: e.readOnly, visible: vis(e),
    first_option: e.tagName === 'SELECT' ? (([...e.options].find(o => o.value !== '' && !o.disabled) || {}).value ?? null) : null}));
}""".replace("VIS", _VISIBLE)

SNAP_JS = """(idx) => { const vis = VIS;
  const banners = [...document.querySelectorAll('[role=alert],.alert-danger,.alert-error,.error,[class*=error],.invalid-feedback,.text-danger')]
    .filter(vis).map(e => (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200)).filter(Boolean);
  const f = document.forms[idx];
  return {marker: window.__nin === 1, banners, aria: document.querySelectorAll('[aria-invalid=true],.is-invalid').length,
          invalid: !!(f && f.matches(':invalid')), text: document.body ? document.body.innerText.trim() : ''};
}""".replace("VIS", _VISIBLE)

SKIP_TYPES = ("hidden", "submit", "button", "reset", "image")


class DeadlineExceeded(Exception):
    pass


class SubmitBlocked(Exception):
    """The submit control is disabled or cannot be clicked (never worked around)."""


_USED: set[int] = set()


def unique_digits(n: int) -> str:
    """n digits derived from time + a random number, never repeated inside this process."""
    mod = 10 ** n
    while True:
        v = (int(time.time() * 1000) * 7919 + random.randrange(10 ** 4)) % mod
        if v not in _USED or len(_USED) >= mod:
            _USED.add(v)
            return f"{v:0{n}d}"


def click_submit(loc) -> None:
    """Click the form's submit control. Disabled / aria-disabled -> SubmitBlocked; a click timeout is retried
    once after scrolling into view, then SubmitBlocked. No force-click, no requestSubmit around a button."""
    btn = loc.locator("button:not([type=button]):not([type=reset]), input[type=submit], input[type=image]").first
    if not btn.count():
        loc.evaluate("f => f.requestSubmit()")
        return

    def blocked():
        return btn.is_disabled() or btn.get_attribute("aria-disabled") == "true"

    if blocked():
        raise SubmitBlocked()
    for attempt in (1, 2):
        try:
            if attempt == 2:
                btn.scroll_into_view_if_needed(timeout=1000)
            btn.click(timeout=3000 if attempt == 1 else 2000)
            return
        except Exception as e:
            if type(e).__name__ != "TimeoutError":
                raise
            if attempt == 2 or blocked():
                raise SubmitBlocked() from e


def code_outcome(statuses: list[int], valid: bool) -> tuple[str, str, int] | None:
    """401/403 (and 409 for valid data) -> (message, error_type, code) warning outcome, else None."""
    code = next((x for x in statuses if x in (401, 403)), None)
    if code:
        return PERMISSION.format(code=code), "permission_denied", code
    if valid and 409 in statuses:
        return DUPLICATE, "possible_duplicate", 409
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sample_value(f: dict, now: datetime) -> str:
    """Sample text for one field dict (as returned by FIELDS_JS)."""
    t = f["type"]
    if t == "email":
        return f"test+{int(now.timestamp())}@example.com"
    if t == "tel":
        return "017" + unique_digits(8)
    if t in ("number", "range"):
        lo, hi = _num(f.get("min")), _num(f.get("max"))
        v = lo if lo is not None else (min(1.0, hi) if hi is not None else 1.0)
        if hi is not None:
            v = min(v, hi)
        return str(int(v)) if v == int(v) else str(v)
    if t == "date":
        return now.strftime("%Y-%m-%d")
    if t == "time":
        return "12:00"
    if t == "datetime-local":
        return now.strftime("%Y-%m-%dT%H:%M")
    if t == "month":
        return now.strftime("%Y-%m")
    if t == "url":
        return "https://example.com"
    if t == "password":
        return "Test@12345"
    v = f"Test {f['label']}"
    if CODE_LIKE.search(f"{f.get('name') or ''} {f['label']}"):  # unique numeric suffix (kept inside maxlength)
        suf, ml = unique_digits(6), f.get("maxlength")
        return (v[: max(ml - len(suf), 0)] + suf)[-ml:] if ml else f"{v} {suf}"
    return v[: f["maxlength"]] if f.get("maxlength") else v


def open_context(page, ctx: dict) -> None:
    """Put the page into the state a form step starts from: ctx = {url, action}; action (an action opener)
    is re-clicked after the reload so a modal form is open again."""
    page.goto(ctx["url"], wait_until="load")
    if ctx.get("action"):
        from app.services.executor import actions  # lazy: actions imports this module
        actions.reopen(page, ctx["action"])


def discover_forms(page, opener: dict | None = None) -> list[dict]:
    """Visible, non-captcha forms that are safe to submit, in page order. Without an opener modal forms are
    skipped; with one (the page is in the state the opener produces) ONLY the modal forms are taken."""
    out = []
    for f in page.evaluate(FORMS_JS):
        if not f["visible"] or f["modal"] != bool(opener) or f["captcha"]:
            continue
        if any(SKIP_LABEL.search(b) for b in f["buttons"]) or SKIP_LABEL.search(f["action"]):
            continue  # destructive: no step, no request
        f["login"] = f["passwords"] == 1 and not f["newpw"] and f["textish"] <= 1
        f["label"] = f["name"] or f["submit"] or f"form {f['idx'] + 1}"
        out.append(f)
    return out


def plan(form: dict, creds: dict | None) -> list[str]:
    kinds = ["empty"] if form["required"] else []
    if not form["login"] or creds:  # a login form is never filled with sample data
        kinds.append("sample")
    return kinds


def _fill(form, fields: list[dict], creds: dict | None, login: bool, now: datetime) -> bool:
    """Fill the form; -> True when a file input was skipped."""
    file_skipped, radios, user_done = False, set(), False
    for f in fields:
        t = f["type"]
        if t in SKIP_TYPES or f["disabled"] or f["readonly"]:
            continue
        if t == "file":
            file_skipped = True
            continue
        if not f["visible"]:
            continue
        loc = form.locator("input,select,textarea").nth(f["i"])
        try:
            if t == "checkbox":
                if f["required"]:
                    loc.check(timeout=2000)
            elif t == "radio":
                if (f["name"] or f["i"]) not in radios:
                    radios.add(f["name"] or f["i"])
                    loc.check(timeout=2000)
            elif f["tag"] == "select":
                if f["first_option"] is not None:
                    loc.select_option(f["first_option"], timeout=2000)
            elif login and t == "password":
                loc.fill(creds["password"], timeout=2000)
            elif login and not user_done:
                user_done = True
                loc.fill(creds["username"], timeout=2000)
            else:
                loc.fill(sample_value(f, now), timeout=2000)
        except Exception:  # ponytail: a field that can't be filled is skipped; the submit outcome tells the rest
            continue
    return file_skipped


def classify_empty(statuses: list[int], feedback: bool) -> tuple[str, str | None, int | None]:
    http = max(statuses) if statuses else None
    if any(400 <= s < 500 for s in statuses) or feedback:
        return "passed", None, http
    if http is not None and http >= 500:
        return "failed", f"HTTP {http}", http
    return "warning", NO_VALIDATION, http


def classify_sample(statuses, new_banners, console_errors, failed_requests, reacted, file_skipped, rejected):
    http = max(statuses) if statuses else None
    if http is not None and 400 <= http < 500 and (o := code_outcome(statuses, True)):
        return "warning", o[0], o[2]
    if http is not None and http >= 400:
        return "failed", f"HTTP {http}", http
    errs = [b for b in new_banners if ERROR_TEXT.search(b)]
    if errs:
        return "failed", f"Error shown: {errs[0][:150]}", http
    if file_skipped:
        return "warning", "File input skipped", http
    if console_errors or failed_requests:
        return "warning", f"{console_errors} console error(s), {failed_requests} failed request(s)", http
    if rejected:
        return "warning", "Sample data was rejected by browser validation", http
    if not reacted:
        return "warning", "No visible reaction after submit", http
    return "passed", None, http


def form_error_type(status: str, error: str | None, failed_requests: int = 0) -> str | None:
    """Contract mapping from a form result's status/error message."""
    if status == "passed":
        return None
    e = error or ""
    if e == BLOCKED_WARN:
        return "submit_blocked"
    if e.startswith("The test user is not allowed"):
        return "permission_denied"
    if e == DUPLICATE:
        return "possible_duplicate"
    if e == NO_VALIDATION:
        return "validation_missing"
    if e.startswith("HTTP ") or e.startswith("Error shown"):
        return "form_error_banner"
    if e == "File input skipped":
        return "file_input_skipped"
    if e.startswith("Sample data was rejected"):
        return "browser_validation_blocked"
    if e == "No visible reaction after submit":
        return "no_reaction"
    if status == "warning":
        return "failed_request" if failed_requests else "console_error"
    return "crash"


def _banner(after: dict, before: dict) -> str | None:
    """Text of the (new, else any) visible error/validation banner after submit."""
    new = [b for b in after["banners"] if b not in before["banners"]]
    return (new or after["banners"] or [None])[0]


def _snap(page, idx) -> dict:
    try:
        page.wait_for_load_state("load")
        return page.evaluate(SNAP_JS, idx)
    except Exception:
        return {"marker": False, "banners": [], "aria": 0, "invalid": False, "text": ""}


def _run_step(page, form: dict, kind: str, ctx: dict, col: Collector, creds, now: datetime):
    """-> (status, error, http_status, excerpt, final page url)"""
    try:
        open_context(page, ctx)
        loc = page.locator("form").nth(form["idx"])
        if loc.count() == 0:
            return "failed", "Form not found on reload", None, None, page.url
        file_skipped = False
        if kind == "sample":
            file_skipped = _fill(loc, loc.evaluate(FIELDS_JS), creds, form["login"], now)
        pace(page)  # watchable: filled form, about to click
        page.evaluate("window.__nin = 1")
        before = page.evaluate(SNAP_JS, form["idx"])
        col.reset()
        try:
            click_submit(loc)
        except SubmitBlocked:
            if kind == "empty":
                return "passed", BLOCKED_OK, None, None, page.url
            return "warning", BLOCKED_WARN, None, None, page.url
        page.wait_for_timeout(300)
        after = _snap(page, form["idx"])
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        st = col.submit_statuses
        stayed = after["marker"]
        if kind == "empty":
            feedback = (stayed and not st and after["invalid"]) or bool(set(after["banners"]) - set(before["banners"])) \
                or after["aria"] > before["aria"]
            return (*classify_empty(st, feedback), _banner(after, before), page.url)
        new = [b for b in after["banners"] if b not in before["banners"]]
        reacted = bool(st) or not stayed or bool(new) or after["text"] != before["text"] or after["aria"] != before["aria"]
        return (*classify_sample(st, new, col.console_errors, col.failed_requests, reacted, file_skipped,
                                 stayed and not st and after["invalid"]), _banner(after, before), page.url)
    except Exception as e:
        return "failed", (str(e).strip().splitlines() or [type(e).__name__])[0][:300], None, None, page.url


def _meta(kind: str, category: str, form_label: str) -> dict:
    return {"kind": kind, "category": category, "field": None, "form": form_label, "source": "auto"}


def test_page_forms(page, repo, menu_step_id: str, menu_label: str, ctx: dict, col: Collector, creds,
                    s, state: dict, notes: list[str], deadline: float, depth: str = "basic", rules=()) -> None:
    """Discover forms on the current menu page (or action-opened modal/page), add their steps after the anchor
    step (menu or action), run them. ctx = {"url", "action"} (see open_context); menu_label is the target prefix.
    state = {"tested": int, "cases": int} shared across pages for the MAX_FORMS / MAX_CASES caps.
    depth != basic queues a case job per (non-login) form in state["jobs"]; phase 2 runs them (cases.Job)."""
    from app.services.executor import cases  # lazy: cases imports this module

    state.setdefault("cases", 0)
    found = discover_forms(page, ctx.get("action"))
    chosen = found[: s.max_forms_per_page]
    if len(found) > len(chosen):
        notes.append(f"'{menu_label}' has {len(found)} forms, tested the first {len(chosen)}")
    chosen = [f for f in chosen if plan(f, creds)]
    room = max(s.max_forms - state["tested"], 0)
    if len(chosen) > room:
        note = f"Reached MAX_FORMS ({s.max_forms}), remaining forms skipped"
        if note not in notes:
            notes.append(note)
        chosen = chosen[:room]
    state["tested"] += len(chosen)
    rows = [(f"{menu_label} > {f['label']}", k, None,
             _meta("invalid", "empty", f["label"]) if k == "empty" else _meta("valid", "valid_sample", f["label"]))
            for f in chosen for k in plan(f, creds)]
    if not rows:
        return
    ids = iter(repo.add_form_steps(menu_step_id, rows))
    for f in chosen:
        last = None
        for k in plan(f, creds):
            sid = last = next(ids)
            if time.monotonic() > deadline:
                raise DeadlineExceeded()
            repo.save_result(sid, status="running")
            t0 = time.monotonic()
            status, err, http, excerpt, url = _run_step(page, f, k, ctx, col, creds, datetime.now())
            etype = form_error_type(status, err, col.failed_requests)
            repo.save_result(sid, status=status, error=redact(err, col.secrets), http_status=http, console_errors=col.console_errors,
                             failed_requests=col.failed_requests, duration_ms=int((time.monotonic() - t0) * 1000),
                             error_type=etype, page_url=sanitize_url(url),
                             details=col.details(excerpt if etype == "form_error_banner" else None) if etype else None)
        if depth != "basic" and not f["login"]:
            state.setdefault("jobs", []).append(cases.Job(f, ctx, last, menu_label))
