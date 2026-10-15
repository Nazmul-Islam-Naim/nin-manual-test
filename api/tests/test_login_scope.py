"""Instruction 019: manual-driven login scope (parse fallback, 422, login-link discovery, ordering, failed login)."""
import json
import threading
import uuid
from datetime import datetime
from http.server import ThreadingHTTPServer

import pytest

from app.db import SessionLocal
from app.models import Manual, TestRun
from app.services.executor import runner
from tests.test_execution import Handler, _reset_hits, fake_execution, make_run, steps  # noqa: F401
from tests.test_parsing import _checker, case, start  # noqa: F401

PUBLIC = '<nav><a href="/">Home</a> <a href="/pricing">Pricing</a> <a href="/login">Log in</a></nav>'
PRIVATE = '<nav><a href="/dashboard">Dashboard</a> <a href="/pos">POS</a> <a href="/pricing">Pricing</a></nav>'
LOGIN_FORM = ('<form method=post action=/login><input name=u><input type=password name=p><button>Sign in</button>'
              '</form>')


def pg(nav, body):
    return f"<html><head><title>T</title></head><body>{nav}<h1>{body}</h1><p>{body} some real content here</p></body></html>"


PAGES = {"/": pg(PUBLIC, "home"), "/pricing": pg(PUBLIC, "pricing"), "/login": pg("", "login") + LOGIN_FORM,
         "/dashboard": pg(PRIVATE, "dashboard"), "/pos": pg(PRIVATE, "pos")}


class LoginHandler(Handler):
    def do_GET(self):
        Handler.hits.append(self.path)
        if self.path in PAGES:
            return self._send(200, PAGES[self.path])
        self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        Handler.posts.append(body)
        if "p=demo1234" in body:
            self.send_response(302)
            self.send_header("Location", "/dashboard")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        self._send(200, PAGES["/login"])


@pytest.fixture(scope="module")
def lsite():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), LoginHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def make(url, password="demo1234", scope="after_login", order=None, user="cashier@rahim.demo", store_user=True,
         text=None):
    with SessionLocal() as db:
        mid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        now = datetime.utcnow()
        db.add(Manual(id=mid, source_type="text", created_at=now,
                      text=text or f"Demo login `{user}` / `{password}`\n1. Open the dashboard"))
        db.add(TestRun(id=rid, manual_id=mid, base_url=url, status="parsed", created_at=now, access_scope=scope,
                       login_user=user if store_user else None, access_order=order))
        db.commit()
    return rid


def labels(b):
    return [s["target"] for s in b["test_cases"][0]["steps"] if s["action"] == "visit_menu"]


# ---- parsing / API ----------------------------------------------------------------------------

def test_access_parsed_and_persisted(client, llm_fake):
    access = {"scope": "both", "login_user": " cashier@rahim.demo ", "order": "login_first", "password": "x"}
    llm_fake.replies = [json.dumps({"test_cases": [case("A", "open")], "access": access})]
    run = client.get(f"/test-runs/{start(client)['id']}").json()
    assert run["access_scope"] == "both" and run["login_user"] == "cashier@rahim.demo"
    assert "password" not in json.dumps(run)


@pytest.mark.parametrize("access", [None, "after_login", {"scope": "sometimes"}, {"login_user": "u"}, []])
def test_bad_or_missing_access_falls_back_to_null(client, llm_fake, access):
    reply = {"test_cases": [case("A", "open")]}
    if access is not None:
        reply["access"] = access
    llm_fake.replies = [json.dumps(reply)]
    run = client.get(f"/test-runs/{start(client)['id']}").json()
    assert run["status"] == "parsed" and run["access_scope"] is None and run["login_user"] is None


def test_old_run_has_null_access(client):
    run = client.get(f"/test-runs/{make_run('http://x.test/')}").json()
    assert run["access_scope"] is None and run["login_user"] is None


def test_execute_access_scope_override_and_422(client):
    fake_execution([])
    rid = make("http://x.test/", scope="after_login")
    assert client.post(f"/test-runs/{rid}/execute", json={"access_scope": "nope"}).status_code == 422
    assert client.get(f"/test-runs/{rid}").json()["access_scope"] == "after_login"
    r = client.post(f"/test-runs/{rid}/execute", json={"access_scope": "before_login"})
    assert r.status_code == 202
    assert client.get(f"/test-runs/{rid}").json()["access_scope"] == "before_login"
    other = make("http://x.test/", scope="both")
    assert client.post(f"/test-runs/{other}/execute", json={}).status_code == 202
    assert client.get(f"/test-runs/{other}").json()["access_scope"] == "both"  # no body value keeps the parsed one


def test_manual_password_helper():
    f = runner.manual_password
    assert f("Demo login `a@b.c` / `demo1234`", "a@b.c") == "demo1234"
    assert f("User: a@b.c\nPassword: s3cret!", "a@b.c") == "s3cret!"
    assert f("পাসওয়ার্ড `pw-99`", "a@b.c") == "pw-99"
    assert f("no secrets here", "a@b.c") is None


# ---- executor ---------------------------------------------------------------------------------

def test_after_login_finds_login_link_and_skips_public_menus(client, lsite):
    rid = make(lsite + "/")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    b = steps(client, rid)
    assert b["status"] == "done"
    assert labels(b) == ["Dashboard", "POS"] and b["note"] is None
    assert any("p=demo1234" in p for p in Handler.posts)  # manual password really used
    assert "demo1234" not in json.dumps(b) + json.dumps(client.get(f"/test-runs/{rid}").json())


def test_body_credentials_win_over_manual(client, lsite):
    rid = make(lsite + "/", password="badpass1")  # manual password is wrong, typed one is right
    runner.run_sweep(rid, {"username": "u", "password": "demo1234"}, submit_forms=False, test_actions=False)
    assert labels(steps(client, rid)) == ["Dashboard", "POS"]


def test_both_public_first_then_login_first(client, lsite):
    rid = make(lsite + "/", scope="both")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    got = labels(steps(client, rid))
    assert got[-2:] == ["Dashboard", "POS"] and "Home" in got and "Pricing" in got
    rid = make(lsite + "/", scope="both", order="login_first")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    got = labels(steps(client, rid))
    assert got[:2] == ["Dashboard", "POS"] and "Home" in got[2:]


def test_login_found_in_manual_text_when_parse_stored_no_user(client, lsite):
    rid = make(lsite + "/", store_user=False)  # parse had not saved login_user (or the LLM omitted it)
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    b = steps(client, rid)
    assert labels(b) == ["Dashboard", "POS"] and b["note"] is None
    assert "demo1234" not in json.dumps(b)


def test_after_login_without_any_login_in_manual_says_so(client, lsite):
    rid = make(lsite + "/", store_user=False, text="1. Open the home page")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    b = steps(client, rid)
    assert "Home" in labels(b) and "no login was found in the manual" in b["note"]


def test_before_login_ignores_manual_credentials(client, lsite):
    rid = make(lsite + "/", scope="before_login")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    assert "Dashboard" not in labels(steps(client, rid)) and not Handler.posts


def test_failed_login_keeps_going_with_public_pages(client, lsite):
    rid = make(lsite + "/", password="badpass1")
    runner.run_sweep(rid, None, submit_forms=False, test_actions=False)
    b = steps(client, rid)
    assert b["status"] == "done" and "Home" in labels(b) and "Dashboard" not in labels(b)
    assert b["note"].startswith("Login was not completed (") and b["note"].count("tested public pages only") == 1
    dump = json.dumps(b) + json.dumps(client.get(f"/test-runs/{rid}").json())
    assert "badpass1" not in dump and "demo1234" not in dump
