"""Form submit testing (instruction 011) against a local http.server fixture site with forms."""
import dataclasses
import re
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer

import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.parse_repository import ParseRepository
from app.services.executor import forms, runner
from app.services.llm import LLMError
from app.services.parsing_service import ParsingService
from tests.test_execution import Handler, _reset_hits, fake_execution, make_run, steps  # noqa: F401

FNAV = ('<nav><a href="/">Home</a> <a href="/req">Req</a> <a href="/valid">Valid</a> <a href="/err">Err</a> '
        '<a href="/nv">NoValid</a> <a href="/del">Del</a> <a href="/many">Many</a></nav>')


def fpage(forms_html):
    return f"<html><head><title>T</title></head><body>{FNAV}<h1>Forms</h1><p>some real content here</p>{forms_html}</body></html>"


FORM_PAGES = {
    "/": fpage(""),
    "/req": fpage('<form method=post action=/req-post name=Contact><input name=n required><button>Go</button></form>'),
    "/valid": fpage('<form method=post action=/valid-post><label>Mail <input type=email name=e></label>'
                    '<input type=tel name=t><input type=number name=n min=5 max=9><input type=date name=d>'
                    '<input type=password name=p><input name=x><select name=s><option value="">--</option>'
                    '<option value=a>A</option></select><input type=checkbox name=c required>'
                    '<input type=radio name=r value=1><input type=radio name=r value=2><button>Save</button></form>'),
    "/err": fpage('<form method=post action=/err-post><input name=q><button>Send</button></form>'),
    "/nv": fpage('<form method=post action=/nv-post novalidate><input name=q required><button>Send</button></form>'),
    "/del": fpage('<form method=post action=/del-post><input name=q><button>Delete</button></form>'),
    "/nrstart": '<html><head><title>T</title></head><body><nav><a href="/nr">NoReact</a> <a href="/ban">Banner</a></nav>'
                '<h1>Start</h1><p>some real content here</p></body></html>',
    "/nr": fpage('<form onsubmit="return false"><input name=q><button>Go</button></form>'),
    "/ban": fpage('<form method=post action=/ban-post><input name=q><button>Go</button></form>'),
    "/many": fpage("".join(f'<form method=post action=/m{i}-post><input name=q><button>Go{i}</button></form>'
                           for i in range(3))),
}


class FormHandler(Handler):
    def do_GET(self):
        Handler.hits.append(self.path)
        if self.path in FORM_PAGES:
            return self._send(200, FORM_PAGES[self.path])
        self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        Handler.hits.append("POST " + self.path)
        Handler.posts.append(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        if self.path == "/err-post":
            return self._send(500, "<h1>Internal Server Error</h1>")
        if self.path == "/ban-post":
            return self._send(200, fpage('<div role=alert>Error: bad value Test@12345</div>'))
        self._send(200, fpage("<p>Saved successfully</p>"))


@pytest.fixture(scope="module")
def fsite():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FormHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def results(body):
    return [(s["target"], s["value"], s["result"]["status"]) for s in body["test_cases"][0]["steps"]
            if s["action"] == "submit_form"]


def test_form_submit_outcomes_and_ordering(client, fsite):
    rid = make_run(fsite + "/")
    runner.run_sweep(rid, None)
    b = steps(client, rid)
    assert b["status"] == "done"
    st = b["test_cases"][0]["steps"]
    order = [(s["action"], s["target"], s["value"]) for s in st]
    assert [o[1] for o in order if o[0] == "visit_menu"] == ["Home", "Req", "Valid", "Err", "NoValid", "Del", "Many"]
    # menu, its forms (empty then sample), next menu
    assert order[:5] == [("visit_menu", "Home", "/"), ("visit_menu", "Req", "/req"),
                         ("submit_form", "Req > Contact", "empty"), ("submit_form", "Req > Contact", "sample"),
                         ("visit_menu", "Valid", "/valid")]
    assert [s["order"] for s in st] == list(range(1, len(order) + 1))
    res = {(t, v): s for t, v, s in results(b)}
    assert res[("Req > Contact", "empty")] == "passed" and res[("Req > Contact", "sample")] == "passed"
    assert res[("Valid > Save", "empty")] == "passed" and res[("Valid > Save", "sample")] == "passed"
    assert res[("Err > Send", "sample")] == "failed" and ("Err > Send", "empty") not in res  # no required fields
    assert res[("NoValid > Send", "empty")] == "warning" and res[("NoValid > Send", "sample")] == "passed"
    err = next(s for s in st if s["target"] == "Err > Send")["result"]
    assert err["http_status"] == 500 and err["error"] == "HTTP 500"
    nv = next(s for s in st if s["target"] == "NoValid > Send" and s["value"] == "empty")["result"]
    assert nv["error"] == "No validation feedback on empty submit"
    # destructive form: no step and the server never saw a request
    assert not any(t.startswith("Del >") for t, _, _ in results(b)) and "POST /del-post" not in Handler.hits
    # sample data was really posted, by field type
    posted = next(p for p in Handler.posts if "e=test%2B" in p)
    assert re.search(r"t=017\d{8}(&|$)", posted)  # phone is unique per submission now
    for part in ("%40example.com", "n=5", "p=Test%40", "s=a", "c=on", "r=1", "x=Test+x"):
        assert part in posted
    assert b["summary"]["total"] == len(order) and b["summary"]["pending"] == 0
    assert b["summary"]["failed"] == 1 and b["summary"]["warning"] == 1
    assert "Forms in modals/wizards are not tested" in b["note"]


def test_submit_forms_false_has_no_form_steps(client, fsite):
    rid = make_run(fsite + "/")
    runner.run_sweep(rid, None, submit_forms=False)
    b = steps(client, rid)
    assert b["status"] == "done" and not results(b) and b["note"] is None and b["summary"]["total"] == 7
    assert not [h for h in Handler.hits if h.startswith("POST")]


def test_env_default_disables_form_submit(client, fsite):
    rid = make_run(fsite + "/")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), exec_submit_forms=False))
    assert not results(steps(client, rid)) and not [h for h in Handler.hits if h.startswith("POST")]


def test_max_forms_and_per_page_caps(client, fsite):
    rid = make_run(fsite + "/")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), max_forms=2, max_forms_per_page=1))
    b = steps(client, rid)
    assert len({t for t, _, _ in results(b)}) == 2  # total cap counts forms
    assert "Reached MAX_FORMS (2), remaining forms skipped" in b["note"] and "Forms in modals" in b["note"]
    rid = make_run(fsite + "/")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), max_forms_per_page=2))
    b = steps(client, rid)
    assert len([1 for t, _, _ in results(b) if t.startswith("Many >")]) == 2
    assert "'Many' has 3 forms, tested the first 2" in b["note"]


def test_execute_forwards_submit_forms_and_validates(client):
    calls = []
    fake_execution(calls)
    rid = make_run("http://x.test/", status="parsed")
    assert client.post(f"/test-runs/{rid}/execute", json={"submit_forms": False}).status_code == 202
    assert calls == [(rid, None, False)]
    other = make_run("http://x.test/", status="parsed")
    r = client.post(f"/test-runs/{other}/execute", json={"submit_forms": "maybe"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_execute_during_parsing_and_parse_completion_keeps_running(client, llm_fake):
    fake_execution([])
    rid = make_run("http://x.test/", status="parsing")
    assert client.post(f"/test-runs/{rid}/execute").status_code == 202
    with SessionLocal() as db:
        ExecutionRepository(db).create_sweep(rid, [("Home", "/")], "n")
        ParsingService(ParseRepository(db), llm_fake, 12000).parse_run(rid)  # parse finishes after execute started
    b = steps(client, rid)
    assert b["status"] == "running"  # not overwritten with parsed
    assert [(c["title"], c["order"]) for c in b["test_cases"]] == [("Menu sweep", 1), ("T", 2)]
    assert [s["action"] for s in b["test_cases"][0]["steps"]] == ["visit_menu"]  # sweep untouched
    rid2 = make_run("http://x.test/", status="parsing")  # a normal parse still ends in parsed
    with SessionLocal() as db:
        ParsingService(ParseRepository(db), llm_fake, 12000).parse_run(rid2)
    assert client.get(f"/test-runs/{rid2}").json()["status"] == "parsed"


def test_parse_failure_does_not_overwrite_running(client, llm_fake):
    fake_execution([])
    llm_fake.replies = [LLMError("boom")]
    rid = make_run("http://x.test/", status="parsing")
    client.post(f"/test-runs/{rid}/execute")
    with SessionLocal() as db:
        ParsingService(ParseRepository(db), llm_fake, 12000).parse_run(rid)
    assert client.get(f"/test-runs/{rid}").json()["status"] == "running"


def test_form_unit_helpers():
    now = datetime(2026, 10, 7, 12, 0)

    def f(**k):
        return {"type": "text", "label": "Name", "min": None, "max": None, "maxlength": None, **k}

    assert forms.sample_value(f(), now) == "Test Name"
    assert forms.sample_value(f(type="date"), now) == "2026-10-07"
    assert re.fullmatch(r"017\d{8}", forms.sample_value(f(type="tel"), now))
    assert forms.sample_value(f(type="tel"), now) != forms.sample_value(f(type="tel"), now)
    code = forms.sample_value(f(label="Product code"), now)
    assert re.fullmatch(r"Test Product code \d{6}", code) and code != forms.sample_value(f(label="Product code"), now)
    assert len(forms.sample_value(f(name="sku", maxlength=8), now)) == 8
    assert forms.sample_value(f(type="password"), now) == "Test@12345"
    assert forms.sample_value(f(type="number", min="5", max="9"), now) == "5"
    assert forms.sample_value(f(type="number", max="0"), now) == "0"
    assert forms.sample_value(f(type="email"), now).endswith("@example.com")
    assert forms.sample_value(f(maxlength=6), now) == "Test N"
    assert forms.classify_empty([422], False)[0] == "passed" and forms.classify_empty([], True)[0] == "passed"
    assert forms.classify_empty([200], False) == ("warning", forms.NO_VALIDATION, 200)
    assert forms.classify_empty([500], False)[0] == "failed"
    assert forms.classify_sample([200], ["Error: bad"], 0, 0, True, False, False)[0] == "failed"
    assert forms.classify_sample([200], [], 0, 0, True, True, False) == ("warning", "File input skipped", 200)
    assert forms.classify_sample([], [], 0, 0, False, False, False)[0] == "warning"
    assert forms.classify_sample([302, 200], ["Saved"], 0, 0, True, False, False)[0] == "passed"
    assert forms.plan({"required": True, "login": True}, None) == ["empty"]
    assert forms.plan({"required": False, "login": True}, {"username": "u", "password": "p"}) == ["sample"]


def test_form_error_types_and_details(client, fsite):
    rid = make_run(fsite + "/")
    runner.run_sweep(rid, None)
    st = {(s["target"], s["value"]): s["result"] for s in steps(client, rid)["test_cases"][0]["steps"]
          if s["action"] == "submit_form"}
    nv = st[("NoValid > Send", "empty")]
    assert nv["error_type"] == "validation_missing" and nv["page_url"].startswith(fsite)
    err = st[("Err > Send", "sample")]
    assert err["error_type"] == "form_error_banner" and err["http_status"] == 500
    assert st[("Req > Contact", "empty")]["error_type"] is None and st[("Req > Contact", "empty")]["details"] is None


def test_form_no_reaction_and_banner_without_leaking_password(client, fsite):
    rid = make_run(fsite + "/nrstart")
    runner.run_sweep(rid, None)
    st = {(s["target"], s["value"]): s["result"] for s in steps(client, rid)["test_cases"][0]["steps"]
          if s["action"] == "submit_form"}
    nr = next(r for (t, _), r in st.items() if t.startswith("NoReact"))
    assert nr["status"] == "warning" and nr["error_type"] == "no_reaction"
    ban = next(r for (t, _), r in st.items() if t.startswith("Banner"))
    assert ban["error_type"] == "form_error_banner" and ban["status"] == "failed"
    assert ban["details"]["excerpt"] == "Error: bad value ***"  # typed sample password masked
    assert "Test@12345" not in str(steps(client, rid))
