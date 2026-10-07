"""Validation matrix (instruction 013): per-field valid/invalid/security cases for one form.
Each case keeps every other field valid, replaces ONE field's value, reloads the page first, submits, classifies.
Payloads are never destructive (no DROP/DELETE/UPDATE)."""
import re
import time
from itertools import zip_longest
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.services.executor.checks import Collector, redact, sanitize_url
from app.services.executor.forms import (BLOCKED_OK, BLOCKED_WARN, FIELDS_JS, SNAP_JS, SubmitBlocked, _fill, _num, _snap,
                                         click_submit, code_outcome, open_context)

STANDARD = {"format", "boundary", "blank"}
KIND_OF = {"format": "invalid", "boundary": "invalid", "blank": "invalid", "special": "tolerant",
           "unicode": "tolerant", "long": "tolerant", "xss": "security", "sqli": "security"}
LABELS = {"format": "Invalid format", "boundary": "Boundary", "blank": "Blank", "special": "Special characters",
          "unicode": "Unicode", "long": "Very long", "xss": "XSS payload", "sqli": "SQL payload",
          "manual_valid": "Manual valid", "manual_invalid": "Manual invalid"}
XSS = ("<script>window.__xss=1</script>", '"><img src=x onerror=window.__xss=1>')
SQLI = ("' OR '1'='1' --", "admin'--")
SQL_ERROR = re.compile(r"SQL syntax|SQLSTATE|ORA-\d|unclosed quotation|sqlite3\.|PG::", re.I)
XSS_INERT = ("Accepted but not executed; output is escaped or not shown here "
             "(stored output on other pages is not checked)")
SUCCESS_TEXT = re.compile(r"success|saved|thank|created|submitted|welcome|done", re.I)

XSS_JS = """() => ({xss: window.__xss === 1,
  markup: [...document.querySelectorAll('script,img[onerror],[onerror]')].some(e => e.outerHTML.includes('__xss'))})"""


@dataclass
class Case:
    kind: str          # valid | invalid | security | tolerant
    category: str
    field_i: int       # index in FIELDS_JS output
    field: str         # label
    value: str
    source: str = "auto"

    @property
    def expected(self) -> str:
        if self.kind == "valid":
            return "accepted"
        if self.kind in ("invalid",) or self.category == "xss":
            return "rejected"
        return "no server error"

    @property
    def shown(self) -> str:
        v = f"{LABELS[self.category]}: {self.value}"
        return v if len(v) <= 80 else v[:79] + "…"

    def meta(self, form_label: str) -> dict:
        return {"kind": self.kind, "category": self.category, "field": self.field, "form": form_label,
                "source": self.source}


# ---- field kind inference ------------------------------------------------------------------

_HINTS = (("email", r"e-?mail|ইমেইল"), ("phone", r"phone|mobile|tel\b|cell|contact\s*no|ফোন|মোবাইল"),
          ("url", r"\burl\b|website|web\s*site|link"), ("date", r"\bdate\b|\bdob\b|birth"),
          ("password", r"pass(word|code)"), ("number", r"\bage\b|qty|quantity|amount|price|\bcount\b"))


def infer_kind(f: dict) -> str | None:
    """email|phone|number|date|password|url|text, or None for fields the matrix skips."""
    t = f["type"]
    if f["tag"] == "select" or f["disabled"] or f["readonly"] or not f["visible"]:
        return None
    direct = {"email": "email", "tel": "phone", "number": "number", "date": "date", "password": "password",
              "url": "url"}
    if t in direct:
        return direct[t]
    if t not in ("text", "search", "textarea", ""):
        return None
    hay = f"{f['name']} {f['label']} {f.get('placeholder') or ''}".lower()
    for kind, rx in _HINTS:
        if re.search(rx, hay):
            return kind
    return "text"


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)


def _day(v: str | None, delta: int) -> str | None:
    try:
        return (date.fromisoformat(v) + timedelta(days=delta)).isoformat()
    except (TypeError, ValueError):
        return None


def _catalog(f: dict, k: str) -> list[tuple[str, str]]:
    """-> [(category, value)] for one field in priority order."""
    out: list[tuple[str, str]] = []
    ml = f.get("maxlength")
    if k == "email":
        out += [("format", v) for v in ("plainaddress", "@example.com", "user@", "us er@example.com",
                                         "a" * 256 + "@example.com")]
    elif k == "phone":
        out += [("format", v) for v in ("01712abcde8", "0171234", "017123456789012345", "++8801712345678",
                                         "0171-234#5678")]
    elif k == "number":
        lo, hi = _num(f.get("min")), _num(f.get("max"))
        if lo is not None:
            out.append(("boundary", _fmt(lo - 1)))
        else:
            out.append(("boundary", "-1"))
        if hi is not None:
            out.append(("boundary", _fmt(hi + 1)))
        if f.get("step") in (None, "", "1"):
            out.append(("format", "1.5"))
        out.append(("boundary", "99999999999999999999"))
    elif k == "date":
        if f["type"] == "date":
            below, above = _day(f.get("min"), -1), _day(f.get("max"), 1)
            out += [("boundary", v) for v in (below, above) if v]
        else:
            out += [("format", v) for v in ("2026-02-30", "31/02/2026", "not a date")]
    elif k == "password":
        out += [("boundary", "abc"), ("blank", "   "), ("long", "A1!" * 100)]
    elif k == "url":
        out += [("format", "htp:/bad"), ("format", "not a url"), ("xss", "javascript:alert(1)")]
    else:  # text
        if f["required"]:
            out.append(("blank", "   "))
        out += [("special", "!@#$%^&*()_+-=[]{}|;:,.?/~`"), ("unicode", "বাংলা টেস্ট ডাটা"), ("unicode", "😀🎉 emoji")]
        if not ml:
            out.append(("long", "x" * 1000))
        out += [("xss", v) for v in XSS] + [("sqli", v) for v in SQLI]
    if ml:
        out.insert(0, ("boundary", ("1" if k in ("phone", "number") else "x") * (ml + 1)))
    return out


def auto_cases(f: dict, depth: str) -> list[Case]:
    k = infer_kind(f)
    if k is None or depth == "basic":
        return []
    return [Case(KIND_OF[c], c, f["i"], f["label"], v) for c, v in _catalog(f, k)
            if depth == "thorough" or c in STANDARD]


# ---- manual rules --------------------------------------------------------------------------

def _norm(s: str | None) -> str:
    return " ".join(re.findall(r"[^\W_]+", (s or "").lower()))


def matches(f: dict, rule_field: str) -> bool:
    """Case-insensitive, contains either way, on label/name/placeholder.
    ponytail: containment needs >=3 chars so a field named 'e' does not match every rule."""
    r = _norm(rule_field)
    for cand in (_norm(f["label"]), _norm(f["name"]), _norm(f.get("placeholder"))):
        if r and cand and (r == cand or (len(min(r, cand, key=len)) >= 3 and (r in cand or cand in r))):
            return True
    return False


def manual_cases(f: dict, rules) -> list[Case]:
    if infer_kind(f) is None:
        return []
    out = []
    for r in rules:
        if matches(f, r["field"]):
            out += [Case("valid", "manual_valid", f["i"], f["label"], v, "manual") for v in r["valid"]]
            out += [Case("invalid", "manual_invalid", f["i"], f["label"], v, "manual") for v in r["invalid"]]
    return out


def build_cases(fields: list[dict], rules, depth: str) -> list[Case]:
    """Manual cases first, then auto cases round-robin across fields so a cap still covers every field."""
    if depth == "basic":
        return []
    manual = [c for f in fields for c in manual_cases(f, rules)]
    per_field = [auto_cases(f, depth) for f in fields]
    return manual + [c for tier in zip_longest(*per_field) for c in tier if c]


# ---- outcome -------------------------------------------------------------------------------

def sql_excerpt(text: str) -> str | None:
    m = SQL_ERROR.search(text or "")
    if not m:
        return None
    a = text.rfind("\n", 0, m.start()) + 1
    b = text.find("\n", m.end())
    return text[a: b if b != -1 else len(text)].strip()[:300]


def classify_case(case: Case, obs: dict) -> tuple[str, str | None, str | None, str | None]:
    """obs: statuses, rejected, message, xss (executed|rendered text or None), sql (matched text or None).
    -> (status, error, error_type, excerpt)"""
    http = max(obs["statuses"]) if obs["statuses"] else None
    if obs.get("blocked"):  # disabled / unclickable submit: the UI blocked it (invalid, security) or we could not test
        if case.kind in ("invalid", "security"):
            return "passed", BLOCKED_OK, None, None
        return "warning", BLOCKED_WARN, "submit_blocked", None
    if case.category == "sqli" and obs["sql"]:
        return "failed", "SQL error text shown after the SQL payload", "sql_error", obs["sql"]
    if http is not None and http >= 500:
        if case.category == "sqli":
            return "failed", f"HTTP {http} on the SQL payload", "sql_error", None
        return "failed", f"HTTP {http}", "server_error", None
    if case.category == "xss" and obs["xss"]:
        return "failed", f"XSS payload {obs['xss']}", "xss_risk", None
    rejected = obs["rejected"]
    if case.kind in ("valid", "invalid", "security") and (o := code_outcome(obs["statuses"], case.kind == "valid")):
        return "warning", o[0], o[1], None  # inconclusive, never counted as rejected/accepted
    if case.kind == "invalid" and not rejected:
        return "failed", "Invalid data was accepted", "invalid_accepted", None
    if case.kind == "valid" and rejected:
        return "failed", "Valid data was rejected", "valid_rejected", obs["message"]
    if case.category == "xss" and not rejected:
        return "passed", XSS_INERT, None, None
    return "passed", None, None, None


# ---- browser -------------------------------------------------------------------------------

def _observe(page, loc, form: dict, col: Collector, case: Case, before: dict, pre: dict) -> dict:
    page.wait_for_timeout(300)
    after = _snap(page, form["idx"])
    try:
        page.wait_for_load_state("networkidle", timeout=1500)
    except Exception:
        pass
    st = list(col.submit_statuses)
    stayed = after["marker"]
    new = [b for b in after["banners"] if b not in before["banners"] and not SUCCESS_TEXT.search(b)]
    native = stayed and not st and after["invalid"]
    rejected = (any(400 <= x < 500 for x in st) or native or bool(new) or after["aria"] > before["aria"])
    reacted = bool(st) or not stayed or after["text"] != before["text"]
    message = new[0] if new else None
    if native and not message:
        try:
            message = loc.evaluate("f => (f.querySelector(':invalid') || {}).validationMessage || ''") or None
        except Exception:
            pass
    x = {}
    try:
        x = page.evaluate(XSS_JS)
    except Exception:
        pass
    xss = None
    if col.dialogs or (x.get("xss") and not pre.get("xss")):
        xss = "was executed"
    elif x.get("markup") and not pre.get("markup"):
        xss = "was rendered as live markup"
    sql = sql_excerpt(after["text"]) if not sql_excerpt(before["text"]) else None
    return {"statuses": st, "rejected": rejected or not reacted, "message": message, "xss": xss, "sql": sql}


def run_case(page, form: dict, case: Case, ctx: dict, col: Collector, now: datetime):
    """-> (status, error, http, excerpt, error_type, url)"""
    try:
        open_context(page, ctx)
        loc = page.locator("form").nth(form["idx"])
        if loc.count() == 0:
            return "failed", "Form not found on reload", None, None, "crash", page.url
        fields = loc.evaluate(FIELDS_JS)
        _fill(loc, fields, None, False, now)  # every field valid ...
        f = fields[case.field_i]
        el = loc.locator("input,select,textarea").nth(f["i"])
        problem = None
        try:  # ... except this one
            if f["maxlength"]:  # real typing so the browser's maxlength applies
                el.fill("", timeout=2000)
                el.press_sequentially(case.value, timeout=5000)
                if el.input_value() != case.value:
                    problem = "Value was cut off by maxlength"
            else:
                el.fill(case.value, timeout=2000)
        except Exception:
            problem = "Browser refused the value"
        if problem and (case.kind in ("valid", "invalid") or problem.startswith("Browser")):
            obs = {"statuses": [], "rejected": True, "message": problem, "xss": None, "sql": None}
        else:
            page.evaluate("window.__nin = 1")
            before = page.evaluate(SNAP_JS, form["idx"])
            pre = page.evaluate(XSS_JS)
            col.reset()
            try:
                click_submit(loc)
                obs = _observe(page, loc, form, col, case, before, pre)
            except SubmitBlocked:
                obs = {"statuses": [], "rejected": True, "message": None, "xss": None, "sql": None, "blocked": True}
        status, err, etype, excerpt = classify_case(case, obs)
        http = max(obs["statuses"]) if obs["statuses"] else None
        return status, err, http, excerpt, etype, page.url
    except Exception as e:
        return "failed", (str(e).strip().splitlines() or [type(e).__name__])[0][:300], None, None, "crash", page.url


@dataclass
class Job:
    """One form's validation cases, collected in phase 1 and run round-robin in phase 2.
    Case steps are created on the first turn (prepare), anchored after the form's last step."""
    form: dict
    ctx: dict
    anchor: str
    menu_label: str
    cases: list | None = None  # None = not started
    ids: list = field(default_factory=list)
    done: int = 0

    @property
    def finished(self) -> bool:
        return self.cases is not None and self.done >= len(self.cases)


def prepare(page, repo, job: Job, s, state: dict, notes: list[str], depth: str, rules) -> None:
    """Generate the form's cases, apply caps, add their steps after the job's anchor step."""
    job.cases = []
    try:
        open_context(page, job.ctx)
        fields = page.locator("form").nth(job.form["idx"]).evaluate(FIELDS_JS)
    except Exception:
        return
    cs = build_cases(fields, rules, depth)
    label = f"{job.menu_label} > {job.form['label']}"
    if len(cs) > s.max_cases_per_form:
        notes.append(f"'{label}' had {len(cs)} cases, ran the first {s.max_cases_per_form}")
        cs = cs[: s.max_cases_per_form]
    room = max(s.max_cases - state["cases"], 0)
    if len(cs) > room:
        note = f"Reached MAX_CASES ({s.max_cases}), remaining cases skipped"
        if note not in notes:
            notes.append(note)
        cs = cs[:room]
    if not cs:
        return
    state["cases"] += len(cs)
    job.ids = repo.add_form_steps(job.anchor, [(f"{label} > {c.field}", c.shown, c.expected, c.meta(job.form["label"]))
                                               for c in cs])
    job.cases = cs


def run_next(page, repo, job: Job, col: Collector) -> None:
    """Run the job's next case and save its result."""
    c, sid = job.cases[job.done], job.ids[job.done]
    job.done += 1
    repo.save_result(sid, status="running")
    t0 = time.monotonic()
    status, err, http, excerpt, etype, url = run_case(page, job.form, c, job.ctx, col, datetime.now())
    repo.save_result(sid, status=status, error=redact(err, col.secrets), http_status=http,
                     console_errors=col.console_errors, failed_requests=col.failed_requests,
                     duration_ms=int((time.monotonic() - t0) * 1000), error_type=etype,
                     page_url=sanitize_url(url), details=col.details(excerpt) if etype else None)
