"""Fewer false alarms (instruction 016): headless Playwright against a local http.server fixture."""
import re
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

from app.services.executor import cases, forms, runner
from tests.test_execution import Handler, _reset_hits, make_run, steps  # noqa: F401
from tests.test_validation_matrix import F, by_cat, case_steps, sweep, vpage  # noqa: F401

PHONES, CODES, CONFLICTS = [], [], []

FORMS = {
    "dis": '<form method=post action=/dis-post name=Buy><label>Note <input name=note required></label>'
           '<button disabled>Create</button></form>',
    "cond": '<form method=post action=/cond-post name=Buy><label>Note <input name=note required oninput="'
            "document.getElementById('b').disabled = this.value !== 'magic'\"></label>"
            '<button id=b disabled>Create</button></form>',
    "uniq": '<form method=post action=/uniq-post name=Reg><label>Phone <input type=tel name=phone></label>'
            '<label>Product code <input name=code></label><button>Save</button></form>',
    "dup": '<form method=post action=/dup-post name=Item><label>Title <input name=title></label><button>Save</button></form>',
    "forbid": '<form method=post action=/forbid-post name=Stock><label>Title <input name=title></label>'
              '<button>Save</button></form>',
    "act": '<div><button role=tab aria-selected=true>Grocery</button> <button role=tab aria-selected=false>Other</button>'
           '<button aria-pressed=true>Cash</button><button class="btn active">All</button>'
           '<a href="#demo">Jump</a><button>Noop</button></div><div style="height:3000px"></div><div id=demo>Demo</div>',
}
PAGES = {f"/{k}": vpage(v) for k, v in FORMS.items()}
PAGES.update({f"/start-{k}": f'<html><head><title>S</title></head><body><nav><a href="/{k}">Page {k}</a></nav>'
                             '<h1>Start</h1><p>some real content here</p></body></html>' for k in FORMS})


class FHandler(Handler):
    def do_GET(self):
        Handler.hits.append(self.path)
        self._send(200, PAGES[self.path]) if self.path in PAGES else self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        Handler.hits.append("POST " + self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        Handler.posts.append(raw)
        d = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        if self.path == "/uniq-post":
            if d.get("phone") in PHONES or d.get("code") in CODES:
                CONFLICTS.append(raw)
                return self._send(409, vpage("<div class=error>Duplicate</div>"))
            PHONES.append(d.get("phone")), CODES.append(d.get("code"))
        if self.path == "/dup-post":
            return self._send(409, vpage("<div class=error>Conflict</div>"))
        if self.path == "/forbid-post":
            return self._send(403, vpage("<h1>Forbidden</h1>"))
        self._send(200, vpage("<p>Saved successfully</p>"))


@pytest.fixture(scope="module")
def fsite():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def forms_by_value(b):
    return {s["value"]: s["result"] for s in b["test_cases"][0]["steps"] if s["action"] == "submit_form"}


# ---- submit state -----------------------------------------------------------------------------

@pytest.mark.parametrize("page", ["dis", "cond"])
def test_disabled_submit_is_not_a_crash(client, fsite, page):
    _, b = sweep(client, fsite, page, "thorough")
    r = forms_by_value(b)
    assert r["empty"]["status"] == "passed" and r["empty"]["error"] == forms.BLOCKED_OK and r["empty"]["error_type"] is None
    assert r["sample"]["status"] == "warning" and r["sample"]["error_type"] == "submit_blocked"
    assert r["sample"]["error"] == forms.BLOCKED_WARN
    cs = {s["meta"]["category"]: s["result"] for s in case_steps(b)}
    assert cs["blank"]["status"] == "passed" and cs["blank"]["error"] == forms.BLOCKED_OK  # invalid
    assert cs["xss"]["status"] == "passed" and cs["sqli"]["status"] == "passed"  # security
    for cat in ("special", "unicode", "long"):  # tolerant
        assert cs[cat]["status"] == "warning" and cs[cat]["error_type"] == "submit_blocked"
    assert not any(s["result"]["error_type"] == "crash" for s in b["test_cases"][0]["steps"])
    assert b["status"] == "done" and not [h for h in Handler.hits if h.startswith("POST")]  # never forced


# ---- page actions -----------------------------------------------------------------------------

def test_already_active_controls_and_hash_link_pass(client, fsite):
    rid = make_run(f"{fsite}/start-act")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=True)
    acts = {s["target"]: s["result"] for s in steps(client, rid)["test_cases"][0]["steps"] if s["action"] == "click_action"}
    for label in ("Grocery", "Cash", "All"):
        r = acts[f"Page act > {label}"]
        assert r["status"] == "passed" and r["error"] == "Already active, nothing to switch", label
    assert acts["Page act > Jump"]["status"] == "passed" and acts["Page act > Jump"]["error_type"] is None
    assert acts["Page act > Noop"]["error_type"] == "action_no_effect"  # real no-ops still warn


# ---- unique data ------------------------------------------------------------------------------

def test_sample_data_is_unique_per_submission(client, fsite):
    PHONES.clear(), CODES.clear(), CONFLICTS.clear()
    for _ in range(2):
        _, b = sweep(client, fsite, "uniq", "basic")
        assert forms_by_value(b)["sample"]["status"] == "passed"
    assert len(PHONES) == 2 and PHONES[0] != PHONES[1] and all(re.fullmatch(r"017\d{8}", p) for p in PHONES)
    assert all(re.fullmatch(r"Test Product code \d{6}", c) for c in CODES) and CODES[0] != CODES[1]
    assert not CONFLICTS  # the server that answers 409 on a repeat never saw one


# ---- status codes ------------------------------------------------------------------------------

def test_409_is_possible_duplicate_for_valid_not_for_invalid(client, fsite):
    _, b = sweep(client, fsite, "dup", "standard", [("title", ["Real title"], ["x"])])
    assert forms_by_value(b)["sample"]["error_type"] == "possible_duplicate"
    assert forms_by_value(b)["sample"]["status"] == "warning" and "HTTP 409 Conflict" in forms_by_value(b)["sample"]["error"]
    valid, invalid = case_steps(b)
    assert valid["result"]["status"] == "warning" and valid["result"]["error_type"] == "possible_duplicate"
    assert invalid["result"]["status"] == "passed"  # 409 still counts as rejected


def test_403_is_permission_denied_not_rejected(client, fsite):
    _, b = sweep(client, fsite, "forbid", "standard", [("title", ["Real title"], ["x"])])
    s = forms_by_value(b)["sample"]
    assert s["status"] == "warning" and s["error_type"] == "permission_denied" and s["http_status"] == 403
    assert s["error"] == "The test user is not allowed to do this (HTTP 403). Check its role"
    valid, invalid = case_steps(b)
    for r in (valid["result"], invalid["result"]):
        assert r["status"] == "warning" and r["error_type"] == "permission_denied"


# ---- units -------------------------------------------------------------------------------------

def test_classification_units():
    def c(kind, cat):
        return cases.Case(kind, cat, 0, "X", "v")

    def o(*st, **k):
        return {"statuses": list(st), "rejected": True, "message": None, "xss": None, "sql": None, **k}

    cl = cases.classify_case
    assert cl(c("valid", "manual_valid"), o(401))[0:3:2] == ("warning", "permission_denied")
    assert cl(c("invalid", "format"), o(403))[0:3:2] == ("warning", "permission_denied")
    assert cl(c("security", "sqli"), o(403))[2] == "permission_denied"
    assert cl(c("valid", "valid_sample"), o(409))[2] == "possible_duplicate"
    assert cl(c("invalid", "format"), o(409))[0] == "passed"
    assert cl(c("valid", "valid_sample"), o(500))[2] == "server_error"
    assert cl(c("security", "xss"), o(200, xss="was rendered as live markup"))[0:3:2] == ("failed", "xss_risk")
    assert forms.classify_sample([403], [], 0, 0, True, False, False) == ("warning", forms.PERMISSION.format(code=403), 403)
    assert forms.classify_sample([409], [], 0, 0, True, False, False)[1] == forms.DUPLICATE
    assert forms.classify_sample([404], [], 0, 0, True, False, False)[0] == "failed"
    assert forms.form_error_type("warning", forms.DUPLICATE) == "possible_duplicate"
