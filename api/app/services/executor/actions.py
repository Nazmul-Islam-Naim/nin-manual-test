"""Page action sweep (instruction 014): click one action per signature in a page body, classify the outcome,
and test the forms of the modal/page the action opens (one level only)."""
import re
import time
from urllib.parse import urlparse

from app.services.executor import forms
from app.services.executor.checks import (PAGE_JS, UI, classify, menu_error_type, menu_excerpt, pace, redact,
                                          sanitize_url)
from app.services.executor.forms import DeadlineExceeded, open_context
from app.services.executor.menu_discovery import DENY_WORDS, DOWNLOAD_EXT

DENY_MORE = re.compile(r"\bvoid\b|\brefund", re.I)
UNSAFE_HREF = re.compile(r"^(mailto|tel|javascript|data|blob):", re.I)
CATEGORY = {"link": "action_link", "button": "action_button", "tab": "action_tab", "row_action": "action_row",
            "pagination": "action_pagination"}
ID_SEG = re.compile(r"^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)
MODAL_SEL = "dialog[open],[role=dialog],[role=alertdialog],.modal.show,[aria-modal=true]"
CLOSE_SEL = "[data-bs-dismiss=modal],[data-dismiss=modal],.modal-close,.close,[aria-label=Close],[aria-label=close]"
NO_EFFECT = "Nothing happened after clicking"
ALREADY_ACTIVE = "Already active, nothing to switch"
ACTIVE_JS = """(e) => ['aria-selected', 'aria-pressed', 'aria-checked'].some(n => e.getAttribute(n) === 'true')
  || (e.hasAttribute('aria-current') && e.getAttribute('aria-current') !== 'false')
  || ['active', 'selected', 'current', 'is-active'].some(c => e.classList.contains(c))"""

# One function for both jobs so discovery and re-finding agree: no arg -> list candidates; arg {label, kind, nth}
# -> mark the nth match with data-nin-act and return true.
ACT_JS = """(arg) => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const label = (e) => (e.innerText || e.getAttribute('aria-label') || e.title || '').trim().replace(/\\s+/g, ' ');
  const kind = (e) => e.matches('[rel=next],[rel=prev]') || e.closest('.pagination,[class*=pagination],[class*=pager]') ? 'pagination'
    : e.matches('[role=tab],[data-bs-toggle=tab],[data-bs-toggle=pill],[data-toggle=tab],[data-toggle=pill]') ? 'tab'
    : e.closest('tr,li') ? 'row_action' : e.tagName === 'A' ? 'link' : 'button';
  const els = [...document.querySelectorAll('a[href],button,[role=button],[role=tab],[data-bs-toggle],[data-toggle]')]
    .filter(e => !e.closest('nav,header,aside,[role=navigation],[role=menubar],[role=menuitem],dialog,[role=dialog],[role=alertdialog],[aria-modal=true],.modal')
      && vis(e) && !e.disabled && e.getAttribute('aria-disabled') !== 'true'
      && !(e.closest('form') && e.matches('input[type=submit],input[type=image],input[type=reset],button:not([type]),button[type=submit],button[type=reset]')));
  const seen = {};
  const list = els.map(e => { const l = label(e), k = kind(e), key = l + '|' + k, f = e.closest('form');
    const nth = seen[key] = (seen[key] === undefined ? 0 : seen[key] + 1);
    const a = e.tagName === 'A';
    return {e, label: l, kind: k, nth, aria: e.getAttribute('aria-label') || '', title: e.title || '',
      href: a ? e.getAttribute('href') : null, abs: a ? e.href : null, download: e.hasAttribute('download'),
      target: e.getAttribute('target') || '',
      formtext: f ? [f.getAttribute('action') || '', ...[...f.querySelectorAll('button,input[type=submit]')]
        .map(b => b.innerText || b.value || '')].join(' ') : ''};
  });
  if (arg) { const m = list.find(x => x.label === arg.label && x.kind === arg.kind && x.nth === arg.nth);
    if (!m) return false; m.e.setAttribute('data-nin-act', '1'); return true; }
  return list.map(({e, ...rest}) => rest);
}"""

STATE_JS = """(sel) => { const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const modals = [...document.querySelectorAll(sel)].filter(vis);
  return {url: location.href.split('#')[0], hash: location.hash, scroll: Math.round(window.scrollY), modals: modals.length, modal_text: modals.map(m => m.innerText).join(' ').trim(),
    text: document.body ? document.body.innerText.trim() : '',
    aria: [...document.querySelectorAll('[aria-selected],[aria-expanded],[aria-pressed],[aria-checked]')]
      .map(e => ['selected', 'expanded', 'pressed', 'checked'].map(n => e.getAttribute('aria-' + n)).join('')).join(',')}; }"""


def normalize_href(href: str | None) -> str:
    """Path with numeric/uuid segments replaced by :id ('-' for no href)."""
    if not href:
        return "-"
    path = urlparse(href).path or href
    return "/".join(":id" if ID_SEG.match(seg) else seg for seg in path.split("/"))


def signature(c: dict) -> tuple:
    label = re.sub(r"\d+", "#", c["label"].lower()) if c["kind"] == "pagination" else c["label"].lower()
    return label, c["kind"], normalize_href(c["href"])


def deny_regex(s) -> re.Pattern | None:
    words = [re.escape(w) for w in s.action_deny_extra]
    return re.compile("|".join(words), re.I) if words else None


def is_denied(c: dict, origin: str, extra: re.Pattern | None = None) -> bool:
    """Label, aria-label, title, href path and the surrounding form's buttons/action are checked."""
    texts = [c["label"], c["aria"], c["title"], c["formtext"]]
    if c["download"] or any(forms.SKIP_LABEL.search(t) or DENY_WORDS.search(t) or DENY_MORE.search(t)
                            or (extra and extra.search(t)) for t in texts):
        return True
    href = c["href"]
    if href is None:
        return False
    if href.strip() in ("", "#") or UNSAFE_HREF.match(href.strip()):
        return True
    u = urlparse(c["abs"])
    path = u.path
    return (f"{u.scheme}://{u.netloc}" != origin or u.path.lower().endswith(DOWNLOAD_EXT)
            or any(r.search(path) for r in (forms.SKIP_LABEL, DENY_WORDS, DENY_MORE) + ((extra,) if extra else ())))


def discover(page, origin: str, s) -> list[dict]:
    """Safe, visible body actions, first of each signature, in page order."""
    extra, seen, out = deny_regex(s), set(), []
    for c in page.evaluate(ACT_JS):
        if not (c["label"] or c["aria"] or c["title"]) or is_denied(c, origin, extra):
            continue
        sig = signature(c)
        if sig not in seen:
            seen.add(sig)
            out.append(c)
    return out


def reopen(page, act: dict) -> None:
    """Click the action again (found by label/kind/nth) and wait for its modal. Used by open_context."""
    if not page.evaluate(ACT_JS, act):
        raise RuntimeError("Action not found after reload")
    page.locator("[data-nin-act]").first.click(timeout=3000)
    try:
        page.wait_for_selector(MODAL_SEL, state="visible", timeout=3000)
    except Exception:  # a drawer that is already in the DOM is picked up by the form lookup below
        pass


def _close_modal(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        close = page.locator(CLOSE_SEL).locator("visible=true").first
        if page.locator(MODAL_SEL).locator("visible=true").count() and close.count():
            close.click(timeout=1000)
    except Exception:  # cosmetic: the next action reloads the page anyway
        pass


class _Watch:
    """Popups, downloads, main-frame navigation responses and XHR/fetch requests seen since the last clear."""

    def __init__(self, page):
        self.page, self.popups, self.downloads, self.nav, self.requests = page, [], [], [], 0
        self._on = [("popup", lambda p: self.popups.append(p)), ("download", lambda d: self.downloads.append(d)),
                    ("response", self._response), ("request", self._request)]
        for ev, fn in self._on:
            page.on(ev, fn)

    def _response(self, r):
        try:
            if r.request.is_navigation_request() and r.request.frame == self.page.main_frame:
                self.nav.append(r.status)
        except Exception:
            pass

    def _request(self, r):
        if r.resource_type in ("xhr", "fetch"):
            self.requests += 1

    def clear(self):
        self.popups.clear(), self.downloads.clear(), self.nav.clear()
        self.requests = 0

    def close(self):
        for ev, fn in self._on:
            self.page.remove_listener(ev, fn)


def _settle(page) -> None:
    try:
        page.wait_for_load_state("load", timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(300)
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass


def run_action(page, act: dict, page_url: str, col, watch: _Watch) -> dict:
    """Reload, highlight, click, classify. -> {status, error, http, error_type, excerpt, outcome}"""
    out = {"status": "passed", "error": None, "http": None, "error_type": None, "excerpt": None, "outcome": "inplace"}
    phase = "open"
    try:
        open_context(page, {"url": page_url, "action": None})
        if not page.evaluate(ACT_JS, act):
            raise RuntimeError("Action not found after reload")
        loc = page.locator("[data-nin-act]").first
        if UI.highlight:
            try:
                loc.evaluate("e => { e.style.outline = '3px solid #f59e0b'; e.style.outlineOffset = '2px'; }")
                loc.scroll_into_view_if_needed(timeout=1000)
            except Exception:  # cosmetic only
                pass
            pace(page)
        if loc.evaluate(ACTIVE_JS):  # already the current tab/toggle: clicking proves nothing
            return {**out, "error": ALREADY_ACTIVE}
        before = page.evaluate(STATE_JS, MODAL_SEL)
        col.reset()
        watch.clear()
        phase = "click"
        loc.click(timeout=3000)
        phase = "after"
        pace(page)
        _settle(page)
        after = page.evaluate(STATE_JS, MODAL_SEL)
    except Exception as e:
        if phase == "click" and type(e).__name__ == "TimeoutError":
            return {**out, "status": "warning", "error": "Could not click", "error_type": "action_no_effect",
                    "outcome": "error"}
        msg = (str(e).strip().splitlines() or [type(e).__name__])[0][:300]
        return {**out, "status": "failed", "error": msg, "error_type": "crash", "outcome": "error"}

    def noisy(o):  # console errors / failed XHR make an otherwise fine reaction a warning
        if col.console_errors or col.failed_requests:
            msg = f"{col.console_errors} console error(s), {col.failed_requests} failed request(s)"
            o.update(status="warning", error=msg, error_type="failed_request" if col.failed_requests else "console_error")
        return o

    if watch.downloads:
        return noisy({**out, "outcome": "download", "error": "Started a download"})
    if after["url"] != before["url"] or watch.nav:
        http = watch.nav[-1] if watch.nav else None
        try:
            info = page.evaluate(PAGE_JS)
        except Exception:
            info = {"title": "", "h1": "", "body": ""}
        status, msg = classify(http, info, col.console_errors, col.failed_requests)
        etype = menu_error_type(status, http, msg, col.failed_requests)
        return {**out, "status": status, "error": msg, "http": http, "error_type": etype, "outcome": "navigated",
                "excerpt": menu_excerpt(info) if etype in ("server_error", "client_error", "error_page") else None}
    if after["modals"] > before["modals"]:
        if not after["modal_text"]:
            return {**out, "status": "warning", "error": "Dialog opened with no content",
                    "error_type": "action_no_effect", "outcome": "modal"}
        return noisy({**out, "outcome": "modal"})
    if watch.popups:
        return noisy({**out, "outcome": "popup", "error": "Opened a new tab"})
    anchor = (act["href"] or "").startswith("#") and (after["hash"] != before["hash"] or after["scroll"] != before["scroll"])
    if after["text"] != before["text"] or after["aria"] != before["aria"] or watch.requests or anchor:
        return noisy(out)
    return {**out, "status": "warning", "error": NO_EFFECT, "error_type": "action_no_effect", "outcome": "none"}


def test_page_actions(page, repo, menu_step_id: str, menu_label: str, page_url: str, col, creds, s, state: dict,
                      notes: list[str], deadline: float, depth: str, rules, submit_forms: bool) -> None:
    """Actions of the menu page at page_url: steps go after the menu's form steps; each action's own form
    steps go right after that action step. state also holds {"actions": int} for the MAX_ACTIONS cap."""
    state.setdefault("actions", 0)
    try:
        open_context(page, {"url": page_url, "action": None})
        u = urlparse(page.url)
        found = discover(page, f"{u.scheme}://{u.netloc}", s)
    except Exception:
        return
    chosen = found[: s.max_actions_per_page]
    if len(found) > len(chosen):
        notes.append(f"'{menu_label}' has {len(found)} actions, tested the first {len(chosen)}")
    room = max(s.max_actions - state["actions"], 0)
    if len(chosen) > room:
        note = f"Reached MAX_ACTIONS ({s.max_actions}), remaining actions skipped"
        if note not in notes:
            notes.append(note)
        chosen = chosen[:room]
    if not chosen:
        return
    state["actions"] += len(chosen)
    meta = [{"kind": "action", "category": CATEGORY[c["kind"]], "field": None, "form": None, "source": "auto"}
            for c in chosen]
    rows = [(f"{menu_label} > {c['label'] or c['aria'] or c['title']}", f"{c['kind']}: {normalize_href(c['href'])}",
             "reacts", m) for c, m in zip(chosen, meta)]
    ids = repo.add_form_steps(repo.group_end(menu_step_id), rows, action="click_action")
    watch = _Watch(page)
    try:
        for c, sid, row in zip(chosen, ids, rows):
            if time.monotonic() > deadline:
                raise DeadlineExceeded()
            repo.save_result(sid, status="running")
            t0 = time.monotonic()
            r = run_action(page, c, page_url, col, watch)
            etype = r["error_type"]
            repo.save_result(sid, status=r["status"], error=redact(r["error"], col.secrets), http_status=r["http"],
                             console_errors=col.console_errors, failed_requests=col.failed_requests,
                             duration_ms=int((time.monotonic() - t0) * 1000), error_type=etype,
                             page_url=sanitize_url(page.url),
                             details=col.details(r["excerpt"]) if etype else None)
            if submit_forms and r["status"] != "failed" and r["outcome"] in ("navigated", "modal"):
                ctx = ({"url": page.url, "action": None} if r["outcome"] == "navigated"
                       else {"url": page_url, "action": {"label": c["label"], "kind": c["kind"], "nth": c["nth"]}})
                forms.test_page_forms(page, repo, sid, row[0], ctx, col, creds, s, state, notes, deadline, depth, rules)
            if r["outcome"] == "modal":
                _close_modal(page)
            for p in watch.popups:  # new tabs are closed right away
                try:
                    p.close()
                except Exception:
                    pass
    finally:
        watch.close()
