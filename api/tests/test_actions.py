"""Page action sweep (instruction 014): headless Playwright against a local http.server fixture site."""
import dataclasses
import re
import threading
from http.server import ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.executor import actions, runner
from tests.test_execution import Handler, _reset_hits, fake_execution, make_run, steps  # noqa: F401

NAV = '<nav><a href="/sales">Sales</a> <a href="/tabs">Tabs</a> <a href="/cards">Cards</a> <a href="/misc">Misc</a></nav>'
MANY_NAV = '<nav><a href="/many">Many</a> <a href="/many2">Many2</a></nav>'
NOTE = "Actions inside pages opened by an action were not followed"


def pg(body, nav=NAV):
    return f"<html><head><title>T</title></head><body>{nav}<h1>Page</h1><p>some real content here</p>{body}</body></html>"


def rows():
    return "".join(f'<tr><td>Sale {i}</td><td><a href="/sales/{i}">View</a> <a href="/sales/{i}/edit">Edit</a> '
                   f'<a href="/sales/{i}/delete">Delete</a></td></tr>' for i in (1, 2, 3))


def many(prefix):
    return pg("".join(f"<button onclick=\"document.getElementById('o').innerText='{prefix}{i}'\">{prefix}{i}</button>"
                      for i in (1, 2, 3)) + "<p id=o>original</p>", MANY_NAV)


PAGES = {
    "/": pg(""),
    "/start-many": pg("", MANY_NAV),
    "/sales": pg(f"<table>{rows()}</table>"
                 "<button onclick=\"document.getElementById('m').style.display='block'\">Add New</button>"
                 "<button>Noop</button>"
                 "<div id=m role=dialog style='display:none'><p>New sale</p><form method=post action=/add-post "
                 "name=AddSale><label>Title <input name=title required></label><button>Save</button></form></div>"),
    "/tabs": pg("<div><button role=tab aria-selected=true onclick='sel(0)'>Summary</button>"
                "<button role=tab aria-selected=false onclick='sel(1)'>Overview</button>"
                "<button role=tab aria-selected=false onclick='sel(2)'>History</button></div>"
                "<div class=pn>Summary panel</div><div class=pn style='display:none'>Overview panel</div>"
                "<div class=pn style='display:none'>History panel</div>"
                "<script>function sel(n){document.querySelectorAll('[role=tab]').forEach((t,i)=>"
                "t.setAttribute('aria-selected',i==n));document.querySelectorAll('.pn').forEach((p,i)=>"
                "p.style.display=i==n?'block':'none');}</script>"),
    "/cards": pg('<div><a href="/pos-sale">POS Sale</a></div><div><a href="/about">About card</a></div>'
                 '<div><a href="https://example.org/x">Partner</a> <a href="mailto:a@b.c">Mail us</a> '
                 '<a href="tel:123">Call</a> <a href="/files/r.pdf">Brochure</a> <a href="#">Top</a></div>'),
    "/misc": pg('<a href="/popup" target="_blank">Open report</a>'
                "<button onclick=\"document.getElementById('o').innerText='changed'\">Change text</button>"
                "<p id=o>original</p>"),
    "/about": pg("<p>about</p>"), "/popup": pg("<p>popup</p>"),
    "/many": many("A"), "/many2": many("B"),
}


class ActionHandler(Handler):
    def do_GET(self):
        Handler.hits.append(self.path)
        if self.path == "/pos-sale":
            return self._send(500, "<h1>Internal Server Error</h1>")
        if re.fullmatch(r"/sales/\d+", self.path):
            return self._send(200, pg("<p>Sale detail</p>"))
        if re.fullmatch(r"/sales/\d+/edit", self.path):
            return self._send(200, pg("<form method=post action=/edit-post name=EditSale>"
                                      "<label>Name <input name=name required></label><button>Save</button></form>"))
        if self.path in PAGES:
            return self._send(200, PAGES[self.path])
        self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        Handler.hits.append("POST " + self.path)
        Handler.posts.append(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        self._send(200, pg("<p>Saved successfully</p>"))


@pytest.fixture(scope="module")
def asite():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ActionHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(scope="module")
def full(asite):
    """One full sweep shared by the scenario tests: (steps body, GET/POST hits, POST bodies)."""
    Handler.hits.clear(), Handler.posts.clear()
    with TestClient(app) as c:
        rid = make_run(asite + "/")
        runner.run_sweep(rid, None, submit_forms=True, validation_depth="standard", test_actions=True)
        yield steps(c, rid), list(Handler.hits), list(Handler.posts)


def group(body, menu):
    """Steps of one menu group: from its visit_menu step up to (excluding) the next visit_menu."""
    st, out, on = body["test_cases"][0]["steps"], [], False
    for s in st:
        if s["action"] == "visit_menu":
            on = s["target"] == menu
        if on:
            out.append(s)
    return out


def act(body, target):
    hit = [s for s in body["test_cases"][0]["steps"] if s["action"] == "click_action" and s["target"] == target]
    assert len(hit) == 1, target
    return hit[0]


def test_row_actions_once_each_and_delete_never_requested(full):
    body, hits, _ = full
    assert body["status"] == "done"
    view, edit = act(body, "Sales > View"), act(body, "Sales > Edit")
    assert view["value"] == "row_action: /sales/:id" and view["expected"] == "reacts" and edit["value"].startswith("row_action")
    assert view["meta"] == {"kind": "action", "category": "action_row", "field": None, "form": None, "source": "auto"}
    assert view["result"]["status"] == "passed" and edit["result"]["status"] == "passed"
    assert not [s for s in body["test_cases"][0]["steps"] if s["target"] == "Sales > Delete"]
    assert "/sales/1" in hits and "/sales/2" not in hits and "/sales/3" not in hits
    assert not [h for h in hits if h.endswith("/delete")]
    assert body["summary"]["pending"] == 0


def test_step_order_menu_forms_actions_and_action_forms_after_their_action(full):
    body, _, _ = full
    g = group(body, "Sales")
    t = [s["target"] for s in g]
    assert t[:3] == ["Sales", "Sales > View", "Sales > Edit"]
    add = t.index("Sales > Add New")
    assert add > 3 and all(x.startswith("Sales > Edit > EditSale") for x in t[3:add])  # edit page form steps
    assert all(x.startswith("Sales > Add New > AddSale") for x in t[add + 1:-1]) and add < len(t) - 2
    assert t[-1] == "Sales > Noop"
    assert [s["order"] for s in body["test_cases"][0]["steps"]] == list(range(1, len(body["test_cases"][0]["steps"]) + 1))
    assert {s["value"] for s in g if s["target"] == "Sales > Edit > EditSale"} == {"empty", "sample"}


def test_modal_form_reopened_for_every_case(full):
    body, hits, posts = full
    ms = [s for s in group(body, "Sales") if s["target"].startswith("Sales > Add New > ")]
    assert len(ms) >= 3  # empty, sample, at least one validation case
    assert all(s["result"]["error_type"] not in ("crash",) and s["result"]["error"] != "Form not found on reload" for s in ms)
    assert any(s["meta"]["category"] == "blank" for s in ms)
    assert ms[0]["result"]["status"] == "passed"  # empty submit blocked by the browser = validation feedback
    add = [p for p in posts if "title=" in p]
    assert any("title=Test+Title" in p for p in add) and any("title=+++" in p for p in add)  # server got the submissions
    assert hits.count("POST /add-post") == len(add) >= 2


def test_no_effect_tab_card_popup_and_external(full):
    body, hits, _ = full
    noop = act(body, "Sales > Noop")["result"]
    assert noop["status"] == "warning" and noop["error_type"] == "action_no_effect" and noop["error"] == "Nothing happened after clicking"
    assert act(body, "Sales > Add New")["result"]["status"] == "passed"
    for tab in ("Overview", "History"):
        s = act(body, f"Tabs > {tab}")
        assert s["result"]["status"] == "passed" and s["meta"]["category"] == "action_tab" and s["value"] == "tab: -"
    pos = act(body, "Cards > POS Sale")["result"]
    assert pos["status"] == "failed" and pos["error_type"] == "server_error" and pos["http_status"] == 500
    assert act(body, "Cards > About card")["result"]["status"] == "passed"
    assert act(body, "Misc > Open report")["result"]["status"] == "passed"
    assert act(body, "Misc > Change text")["result"]["status"] == "passed"
    targets = {s["target"] for s in body["test_cases"][0]["steps"]}
    assert not {"Cards > Partner", "Cards > Mail us", "Cards > Call", "Cards > Brochure", "Cards > Top"} & targets
    assert not {"/x", "/files/r.pdf"} & set(hits)
    assert NOTE in body["note"] and "Forms in modals/wizards are not tested" in body["note"]


def test_edit_page_form_tests_run(full):
    body, hits, posts = full
    assert "POST /edit-post" in hits and any("name=Test+Name" in p for p in posts)
    edit = [s for s in body["test_cases"][0]["steps"] if s["target"].startswith("Sales > Edit > EditSale")]
    assert edit and all(s["result"]["status"] in ("passed", "failed", "warning") for s in edit)


def test_test_actions_false_has_no_action_steps(client, asite):
    rid = make_run(asite + "/")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    b = steps(client, rid)
    assert b["status"] == "done" and not [s for s in b["test_cases"][0]["steps"] if s["action"] == "click_action"]
    assert b["note"] is None and b["summary"]["total"] == 4


def test_caps_and_notes(client, asite):
    rid = make_run(asite + "/start-many")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), max_actions_per_page=2, max_actions=3),
                     submit_forms=False, test_actions=True)
    b = steps(client, rid)
    acts = [s["target"] for s in b["test_cases"][0]["steps"] if s["action"] == "click_action"]
    assert acts == ["Many > A1", "Many > A2", "Many2 > B1"]
    assert "'Many' has 3 actions, tested the first 2" in b["note"]
    assert "Reached MAX_ACTIONS (3), remaining actions skipped" in b["note"] and NOTE in b["note"]
    assert b["summary"]["total"] == 5


def test_execute_forwards_and_validates_test_actions(client):
    calls = []
    fake_execution(calls)
    rid = make_run("http://x.test/", status="parsed")
    assert client.post(f"/test-runs/{rid}/execute", json={"test_actions": False}).status_code == 202
    other = make_run("http://x.test/", status="parsed")
    for bad in ("yes", 1, "false"):
        r = client.post(f"/test-runs/{other}/execute", json={"test_actions": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


# ---- units ---------------------------------------------------------------------------------

def cand(label, href="/x", kind="link", **k):
    return {"label": label, "aria": "", "title": "", "formtext": "", "download": False, "kind": kind, "href": href,
            "abs": f"http://h{href}" if href and href.startswith("/") else href, **k}


def test_signature_and_denylist_units():
    assert actions.normalize_href("/sales/12/edit") == "/sales/:id/edit"
    assert actions.normalize_href("/u/550e8400-e29b-41d4-a716-446655440000") == "/u/:id"
    assert actions.normalize_href(None) == "-"
    assert actions.signature(cand("View", "/s/1")) == actions.signature(cand("view", "/s/2"))
    assert actions.signature(cand("2", "/p?page=2", "pagination")) == actions.signature(cand("3", "/p?page=3", "pagination"))
    origin = "http://h"
    for label in ("Delete", "Remove item", "Refund", "Void invoice", "Purge", "Clear all", "Logout", "Sign out",
                  "Unsubscribe", "Deactivate", "Destroy"):
        assert actions.is_denied(cand(label), origin), label
    assert not actions.is_denied(cand("Voiding"), origin) and not actions.is_denied(cand("View"), origin)
    assert actions.is_denied(cand("Open", "/orders/delete/3"), origin)
    for href in ("#", "", "mailto:a@b.c", "tel:1", "javascript:void(0)", "https://other.com/x", "/f/a.pdf"):
        assert actions.is_denied(cand("Go", href), origin), href
    assert actions.is_denied(cand("Archive"), origin, actions.deny_regex(
        dataclasses.replace(get_settings(), action_deny_extra=("archive",))))
    assert actions.is_denied(cand("Cancel", formtext="/orders/delete Delete order"), origin)
    assert actions.is_denied(cand("", aria="Delete row"), origin)
