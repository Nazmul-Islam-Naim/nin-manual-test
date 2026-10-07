"""Validation matrix (instruction 013): headless Playwright against a local http.server fixture, plus parsing of
field_rules, the execute body, startup ALTER and unit tests of the case generator."""
import dataclasses
import html
import json
import re
import threading
import uuid
from datetime import datetime
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import FieldRule
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.parse_repository import ParseRepository
from app.routers.test_runs import get_execution_service
from app.services.execution_service import ExecutionService
from app.services.executor import cases, runner
from app.services.llm import LLMError
from app.services.parsing_service import ParsingService
from tests.test_execution import Handler, _reset_hits, make_run, steps  # noqa: F401
from tests.test_parsing import _checker, case as parse_case, start  # noqa: F401

EMAIL_OK = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[a-z]+$")


def vpage(body):
    return f"<html><head><title>T</title></head><body><h1>Form</h1><p>some real content here</p>{body}</body></html>"


FORMS = {
    "good": '<form method=post action=/good-post name=Signup><label>Email <input type=email name=email required></label>'
            '<label>Phone <input type=tel name=phone required></label><button>Join</button></form>',
    "sloppy": '<form method=post action=/sloppy-post name=Feedback><label>Email <input name=email></label>'
              '<label>Note <input name=note></label><button>Send</button></form>',
    "vuln": '<form method=post action=/echo-post name=Echo><label>Comment <input name=comment></label>'
            '<button>Post</button></form>'
            '<form method=post action=/sql-post name=Search><label>Search <input name=q></label><button>Find</button></form>',
    "picky": '<form method=post action=/picky-post name=Contact><label>Phone <input type=tel name=phone></label>'
             '<label>Password <input type=password name=pw autocomplete=new-password></label><button>Go</button></form>',
    "ml": '<form method=post action=/ml-post name=Code><label>Code <input name=code maxlength=5></label>'
          '<button>Go</button></form>',
}
PAGES = {f"/{k}": vpage(v) for k, v in FORMS.items()}
PAGES.update({f"/start-{k}": f'<html><head><title>S</title></head><body><nav><a href="/{k}">Page {k}</a></nav>'
                             '<h1>Start</h1><p>some real content here</p></body></html>' for k in FORMS})


class VHandler(Handler):
    def do_GET(self):
        Handler.hits.append(self.path)
        self._send(200, PAGES[self.path]) if self.path in PAGES else self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        Handler.hits.append("POST " + self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        Handler.posts.append(raw)
        d = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        ok = vpage("<p>Saved successfully</p>")
        if self.path == "/good-post":
            good = EMAIL_OK.match(d.get("email", "")) and re.fullmatch(r"01\d{9}", d.get("phone", ""))
            return self._send(200, ok) if good else self._send(422, vpage("<div class=error>Invalid input</div>"))
        if self.path == "/sloppy-post":  # accepts anything, escapes output
            return self._send(200, vpage(f"<p>Saved successfully: {html.escape(d.get('note', ''))}</p>"))
        if self.path == "/echo-post":  # raw HTML echo
            return self._send(200, vpage(f"<p>Saved successfully</p><div>Comment: {d.get('comment', '')}</div>"))
        if self.path == "/sql-post":
            if "'" in d.get("q", ""):
                return self._send(200, vpage("<p>You have an error in your SQL syntax near ''</p>"))
            return self._send(200, ok)
        if self.path == "/picky-post":  # rejects every phone not starting 019, even valid ones
            if re.fullmatch(r"019\d{8}", d.get("phone", "")) and len(d.get("pw", "").strip()) >= 8:
                return self._send(200, ok)
            return self._send(422, vpage(f"<div role=alert>Rejected phone={html.escape(d.get('phone', ''))} "
                                         f"pw={html.escape(d.get('pw', ''))}</div>"))
        self._send(200, ok)


@pytest.fixture(scope="module")
def vsite():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), VHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def sweep(client, site, page, depth, rules=None, settings=None):
    rid = make_run(f"{site}/start-{page}")
    if rules:
        with SessionLocal() as db:
            db.add_all(FieldRule(id=str(uuid.uuid4()), run_id=rid, field=f, rule=None, valid=v, invalid=i)
                       for f, v, i in rules)
            db.commit()
    runner.run_sweep(rid, None, settings, submit_forms=True, validation_depth=depth)
    return rid, steps(client, rid)


def case_steps(b):
    return [s for s in b["test_cases"][0]["steps"] if s["meta"] and s["meta"]["category"] not in ("empty", "valid_sample")]


def by_cat(b, field=None):
    out = {}
    for s in case_steps(b):
        if field is None or s["meta"]["field"] == field:
            out.setdefault(s["meta"]["category"], []).append(s)
    return out


# ---- executor ------------------------------------------------------------------------------

def test_well_validated_form_passes_every_case_and_step_shape(client, vsite):
    rid, b = sweep(client, vsite, "good", "standard")
    st = b["test_cases"][0]["steps"]
    cs = case_steps(b)
    assert len(cs) == 10 and all(s["result"]["status"] == "passed" for s in cs)
    # order: menu, empty, sample, then the cases; orders are consecutive
    assert [s["value"] for s in st[:3]] == ["/good", "empty", "sample"]
    assert st[3]["id"] == cs[0]["id"]
    assert [s["order"] for s in st] == list(range(1, len(st) + 1))
    assert st[1]["meta"] == {"kind": "invalid", "category": "empty", "field": None, "form": "Signup", "source": "auto"}
    assert st[2]["meta"]["kind"] == "valid" and st[2]["meta"]["category"] == "valid_sample"
    assert st[0]["meta"] is None
    first = cs[0]
    assert first["target"] == "Page good > Signup > Email" and first["expected"] == "rejected"
    assert first["value"] == "Invalid format: plainaddress"
    assert first["meta"] == {"kind": "invalid", "category": "format", "field": "Email", "form": "Signup", "source": "auto"}
    long_case = next(s for s in cs if s["value"].endswith("…"))
    assert len(long_case["value"]) <= 80
    assert b["summary"]["pending"] == 0 and b["summary"]["failed"] == 0
    # the page was reloaded before every case (1 menu visit + 1 reload per step + per-case snapshots)
    assert Handler.hits.count("/good") >= len(cs) + 3
    assert b["note"] == "Forms in modals/wizards are not tested; Manual rules were not available yet (manual parsing had not finished)"


def test_sloppy_form_accepts_invalid_and_escaped_xss_passes(client, vsite):
    rid, b = sweep(client, vsite, "sloppy", "thorough")
    email = by_cat(b, "Email")
    assert len(email["format"]) == 5
    for s in email["format"]:
        r = s["result"]
        assert r["status"] == "failed" and r["error_type"] == "invalid_accepted" and s["expected"] == "rejected"
    note = by_cat(b, "Note")
    assert {k for k in note} == {"special", "unicode", "long", "xss", "sqli"}
    assert all(s["result"]["status"] == "passed" for k in ("special", "unicode", "long", "sqli") for s in note[k])
    for s in note["xss"]:  # escaped by the server: accepted but inert -> passed with a note (no warning any more)
        assert s["result"]["status"] == "passed" and s["result"]["error_type"] is None
        assert s["result"]["error"].startswith("Accepted but not executed")
        assert s["meta"]["kind"] == "security" and s["expected"] == "rejected"
    assert all(s["expected"] == "no server error" for s in note["special"] + note["sqli"])
    assert not any("DROP" in p.upper() for p in Handler.posts)


def test_xss_rendered_and_sql_error_detected(client, vsite):
    rid, b = sweep(client, vsite, "vuln", "thorough")
    comment = by_cat(b, "Comment")
    for s in comment["xss"]:
        r = s["result"]
        assert r["status"] == "failed" and r["error_type"] == "xss_risk", s["value"]
    assert all(s["result"]["status"] == "passed" for s in comment["sqli"])  # echoed, no SQL error
    search = by_cat(b, "Search")
    for s in search["sqli"]:
        r = s["result"]
        assert r["status"] == "failed" and r["error_type"] == "sql_error"
        assert "SQL syntax" in r["details"]["excerpt"] and len(r["details"]["excerpt"]) <= 300
    assert all(s["result"]["status"] == "passed" for s in search["special"] + search["unicode"])
    assert all(s["result"]["status"] == "passed" for s in search["xss"])  # not echoed: accepted but inert


def test_manual_rules_valid_rejected_and_no_secret_leak(client, vsite):
    rules = [("phone", ["01712345678"], ["12345"]), ("Unrelated thing", ["zzz"], ["yyy"])]
    rid, b = sweep(client, vsite, "picky", "standard", rules)
    man = [s for s in case_steps(b) if s["meta"]["source"] == "manual"]
    assert [(s["meta"]["category"], s["meta"]["kind"], s["meta"]["field"]) for s in man] == [
        ("manual_valid", "valid", "Phone"), ("manual_invalid", "invalid", "Phone")]
    valid, invalid = man
    assert valid["value"] == "Manual valid: 01712345678" and valid["expected"] == "accepted"
    assert valid["result"]["status"] == "failed" and valid["result"]["error_type"] == "valid_rejected"
    assert valid["result"]["details"]["excerpt"].startswith("Rejected phone=01712345678")
    assert invalid["expected"] == "rejected" and invalid["result"]["status"] == "passed"
    assert "zzz" not in json.dumps(b["test_cases"])  # unmatched rule adds nothing
    assert "Manual rules were not available" not in b["note"]  # rules existed at start
    assert "Test@12345" not in json.dumps(b)  # sample password never reaches results
    assert "pw=***" in valid["result"]["details"]["excerpt"]


def test_maxlength_uses_real_typing_and_counts_as_rejected(client, vsite):
    rid, b = sweep(client, vsite, "ml", "standard")
    (s,) = case_steps(b)
    assert s["meta"]["category"] == "boundary" and s["result"]["status"] == "passed" and s["expected"] == "rejected"
    assert Handler.hits.count("POST /ml-post") == 1  # only the sample submit; the truncated case is not sent


def test_basic_depth_has_no_case_steps_and_standard_skips_thorough_categories(client, vsite):
    _, b = sweep(client, vsite, "sloppy", "basic")
    assert not case_steps(b) and b["note"] == "Forms in modals/wizards are not tested"
    assert [s["meta"]["category"] for s in b["test_cases"][0]["steps"] if s["meta"]] == ["valid_sample"]
    _, b = sweep(client, vsite, "sloppy", "standard")
    assert set(by_cat(b)) == {"format"}  # Note field only has special/unicode/long/xss/sqli (thorough)


def test_caps_and_note(client, vsite):
    s = dataclasses.replace(get_settings(), max_cases_per_form=3)
    _, b = sweep(client, vsite, "sloppy", "standard", settings=s)
    assert len(case_steps(b)) == 3 and "'Page sloppy > Feedback' had 5 cases, ran the first 3" in b["note"]
    s = dataclasses.replace(get_settings(), max_cases=2)
    _, b = sweep(client, vsite, "sloppy", "standard", settings=s)
    assert len(case_steps(b)) == 2 and "Reached MAX_CASES (2), remaining cases skipped" in b["note"]


def test_submit_forms_false_ignores_depth(client, vsite):
    rid = make_run(f"{vsite}/start-sloppy")
    runner.run_sweep(rid, None, submit_forms=False, validation_depth="thorough")
    assert not [s for s in steps(client, rid)["test_cases"][0]["steps"] if s["action"] == "submit_form"]


# ---- API: execute body, defaults, ALTER ------------------------------------------------------

def test_execute_validation_depth_body(client):
    calls = []
    app.dependency_overrides[get_execution_service] = lambda: ExecutionService(
        ExecutionRepository(SessionLocal()), lambda *a: calls.append(a))
    rid = make_run("http://x.test/", status="parsed")
    assert client.post(f"/test-runs/{rid}/execute", json={"validation_depth": "standard"}).status_code == 202
    assert calls == [(rid, None, None, "standard", None, None)]
    other = make_run("http://x.test/", status="parsed")
    for bad in ("deep", "", 3, "THOROUGH"):
        r = client.post(f"/test-runs/{other}/execute", json={"validation_depth": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert client.get(f"/test-runs/{other}").json()["status"] == "parsed"
    app.dependency_overrides.clear()


def test_depth_and_caps_settings(monkeypatch):
    fresh = get_settings.__wrapped__
    for k in ("EXEC_VALIDATION_DEPTH", "MAX_CASES_PER_FORM", "MAX_CASES"):
        monkeypatch.delenv(k, raising=False)
    s = fresh()
    assert (s.exec_validation_depth, s.max_cases_per_form, s.max_cases) == ("thorough", 25, 200)
    monkeypatch.setenv("EXEC_VALIDATION_DEPTH", "standard")
    assert fresh().exec_validation_depth == "standard"
    monkeypatch.setenv("EXEC_VALIDATION_DEPTH", "nonsense")
    assert fresh().exec_validation_depth == "thorough"


def test_startup_adds_meta_column_to_old_database(client):
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE steps DROP COLUMN meta"))
    assert "meta" not in {c["name"] for c in inspect(engine).get_columns("steps")}
    with TestClient(app) as c:  # lifespan runs the ALTER
        assert "meta" in {col["name"] for col in inspect(engine).get_columns("steps")}
        assert c.get("/test-runs/nope/steps").status_code == 404
    with TestClient(app):  # idempotent
        pass


# ---- parsing of field_rules -------------------------------------------------------------------

def _reply(llm_fake, rules, extra=None):
    llm_fake.replies = [json.dumps({"test_cases": [parse_case("A", "open")], "field_rules": rules, **(extra or {})})]


def test_field_rules_parsed_persisted_and_exposed(client, llm_fake):
    _reply(llm_fake, [{"field": "Phone", "rule": "11 digits starting with 01", "valid": ["01712345678"],
                       "invalid": ["123", "abc"] + [str(i) for i in range(10)]},
                      {"field": "Email", "valid": ["a@b.co"]},
                      {"rule": "no field name"}, "junk", {"field": "  "}])
    run = start(client)
    b = client.get(f"/test-runs/{run['id']}/steps").json()
    assert b["status"] == "parsed"
    assert b["field_rules"] == [
        {"field": "Phone", "rule": "11 digits starting with 01", "valid": ["01712345678"],
         "invalid": ["123", "abc", "0", "1", "2"]},
        {"field": "Email", "rule": None, "valid": ["a@b.co"], "invalid": []}]
    from app.services.parsing_service import SYSTEM_PROMPT
    assert "field_rules" in SYSTEM_PROMPT and "Do NOT invent" in SYSTEM_PROMPT


@pytest.mark.parametrize("bad", ["nope", {"field": "x"}, 5, None])
def test_bad_field_rules_never_fail_the_parse(client, llm_fake, bad):
    _reply(llm_fake, bad)
    run = start(client)
    b = client.get(f"/test-runs/{run['id']}/steps").json()
    assert b["status"] == "parsed" and b["field_rules"] == [] and len(b["test_cases"]) == 1


def test_missing_field_rules_defaults_to_empty_and_reparse_replaces(client, llm_fake):
    llm_fake.replies = [json.dumps({"test_cases": [parse_case("A", "open")]})]
    run = start(client)
    assert client.get(f"/test-runs/{run['id']}/steps").json()["field_rules"] == []
    _reply(llm_fake, [{"field": "Age", "valid": ["30"], "invalid": ["-1"]}])
    with SessionLocal() as db:
        ParsingService(ParseRepository(db), llm_fake, 12000).parse_run(run["id"])
    _reply(llm_fake, [{"field": "Zip", "valid": ["1200"], "invalid": []}])
    with SessionLocal() as db:
        ParsingService(ParseRepository(db), llm_fake, 12000).parse_run(run["id"])
    assert [r["field"] for r in client.get(f"/test-runs/{run['id']}/steps").json()["field_rules"]] == ["Zip"]


def test_llm_error_still_fails_run_with_no_rules(client, llm_fake):
    llm_fake.replies = [LLMError("boom")]
    run = start(client)
    g = client.get(f"/test-runs/{run['id']}").json()
    assert g["status"] == "failed" and client.get(f"/test-runs/{run['id']}/steps").json()["field_rules"] == []


# ---- generator unit tests ----------------------------------------------------------------------

def F(**k):
    return {"i": 0, "tag": "input", "type": "text", "name": "x", "label": "X", "placeholder": "", "required": False,
            "min": None, "max": None, "step": None, "maxlength": None, "disabled": False, "readonly": False,
            "visible": True, "pattern": None, **k}


def test_field_kind_inference():
    assert cases.infer_kind(F(type="email")) == "email" and cases.infer_kind(F(type="tel")) == "phone"
    assert cases.infer_kind(F(name="user_email")) == "email" and cases.infer_kind(F(label="Mobile No")) == "phone"
    assert cases.infer_kind(F(placeholder="Your website")) == "url" and cases.infer_kind(F(label="Date of birth")) == "date"
    assert cases.infer_kind(F(label="Age")) == "number" and cases.infer_kind(F(type="textarea", label="Bio")) == "text"
    assert cases.infer_kind(F(type="checkbox")) is None and cases.infer_kind(F(tag="select", type="select-one")) is None
    assert cases.infer_kind(F(disabled=True)) is None and cases.infer_kind(F(type="file")) is None


def test_catalog_boundaries_and_depth():
    num = cases.auto_cases(F(type="number", min="5", max="9"), "standard")
    assert [c.value for c in num] == ["4", "10", "1.5", "99999999999999999999"]
    assert [c.value for c in cases.auto_cases(F(type="number", step="0.5"), "standard")][0] == "-1"
    d = cases.auto_cases(F(type="date", min="2026-01-10", max="2026-02-01"), "standard")
    assert [c.value for c in d] == ["2026-01-09", "2026-02-02"]
    assert cases.auto_cases(F(type="date"), "standard") == []
    txt = cases.auto_cases(F(required=True), "thorough")
    assert {c.category for c in txt} == {"blank", "special", "unicode", "long", "xss", "sqli"}
    assert {c.category for c in cases.auto_cases(F(required=True), "standard")} == {"blank"}
    assert cases.auto_cases(F(), "basic") == []
    ml = cases.auto_cases(F(maxlength=4), "standard")
    assert ml[0].value == "xxxxx" and ml[0].category == "boundary" and ml[0].kind == "invalid"
    assert "long" not in {c.category for c in cases.auto_cases(F(maxlength=4), "thorough")}
    url = {c.value: c.kind for c in cases.auto_cases(F(type="url"), "thorough")}
    assert url["javascript:alert(1)"] == "security"
    every = " ".join(c.value for t in ("email", "tel", "number", "password", "url", "text", "date")
                     for c in cases.auto_cases(F(type=t, required=True), "thorough")).upper()
    assert not re.search(r"\b(DROP|DELETE|UPDATE|TRUNCATE|INSERT)\b", every)


def test_rule_matching_and_ordering():
    phone = F(i=0, label="Phone number", name="phone")
    other = F(i=1, label="Name", name="n")
    assert cases.matches(phone, "phone") and cases.matches(phone, "PHONE NUMBER - BD")
    assert cases.matches(phone, "Phone Number") and cases.matches(F(name="mobile_no", label="x"), "mobile no")
    assert not cases.matches(other, "Unrelated") and not cases.matches(F(label="e", name="e"), "Email")
    rules = [{"field": "phone", "valid": ["01712345678"], "invalid": ["12"]}]
    cs = cases.build_cases([phone, other], rules, "standard")
    assert [(c.category, c.source) for c in cs[:2]] == [("manual_valid", "manual"), ("manual_invalid", "manual")]
    assert cs[0].expected == "accepted" and cs[1].expected == "rejected"
    # round-robin: both fields appear before any field's second case
    both = cases.build_cases([F(i=0, label="Email", type="email"), F(i=1, label="Phone", type="tel")], [], "standard")
    assert [c.field for c in both[:4]] == ["Email", "Phone", "Email", "Phone"]
    assert cases.build_cases([phone], rules, "basic") == []


def test_classification_matrix():
    def c(kind, cat):
        return cases.Case(kind, cat, 0, "X", "v")

    def o(**k):
        return {"statuses": [200], "rejected": False, "message": "msg", "xss": None, "sql": None, **k}

    cl = cases.classify_case
    assert cl(c("invalid", "format"), o())[:3] == ("failed", "Invalid data was accepted", "invalid_accepted")
    assert cl(c("invalid", "format"), o(rejected=True))[0] == "passed"
    assert cl(c("valid", "manual_valid"), o(rejected=True)) == ("failed", "Valid data was rejected", "valid_rejected", "msg")
    assert cl(c("valid", "manual_valid"), o())[0] == "passed"
    assert cl(c("security", "xss"), o(xss="was executed"))[2] == "xss_risk" and cl(c("security", "xss"), o(xss="x"))[0] == "failed"
    assert cl(c("security", "xss"), o())[:3] == ("passed", cases.XSS_INERT, None)
    assert cl(c("security", "xss"), o(rejected=True))[0] == "passed"
    assert cl(c("security", "sqli"), o(sql="near syntax"))[2:] == ("sql_error", "near syntax")
    assert cl(c("security", "sqli"), o(statuses=[500]))[2] == "sql_error" and cl(c("security", "sqli"), o())[0] == "passed"
    assert cl(c("tolerant", "special"), o(statuses=[500]))[2] == "server_error"
    assert cl(c("tolerant", "unicode"), o(statuses=[422], rejected=True))[0] == "passed"
    assert cl(c("tolerant", "long"), o())[0] == "passed"
    assert cases.sql_excerpt("ok\nWarning: mysql SQL syntax error near x\nmore") == "Warning: mysql SQL syntax error near x"
    for t in ("SQLSTATE[42000]", "ORA-00933", "Unclosed quotation mark", "sqlite3.OperationalError", "PG::SyntaxError"):
        assert cases.sql_excerpt(f"x {t} y")
    assert cases.sql_excerpt("all fine") is None
