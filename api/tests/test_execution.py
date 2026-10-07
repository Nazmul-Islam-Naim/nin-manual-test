import dataclasses
import json
import subprocess
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import Manual, TestRun
from app.repositories.execution_repository import ExecutionRepository
from app.routers.test_runs import get_execution_service
from app.services import execution_service
from app.services.execution_service import ExecutionService
from app.services.executor import runner
from app.services.executor.checks import classify
from app.services.executor.menu_discovery import is_denied

NAV = """<nav>
<a href="/">Home</a> <a href="/about">About</a> <a href="/boom">Broken</a> <a href="/console">Console</a>
<a href="/api-fail">Reports</a> <a href="/logout">Logout</a> <a href="mailto:a@b.c">Mail us</a>
<a href="https://example.org/x">Partner</a> <a href="/delete-account">Delete account</a>
<a href="/files/r.pdf">Brochure</a>
<button aria-haspopup="true" aria-expanded="false" onclick="document.getElementById('dd').hidden=false">More</button>
<ul id="dd" hidden><li><a href="/docs">Docs</a></li></ul>
</nav>"""


def page(body, script=""):
    return (f"<html><head><title>T</title></head><body>{NAV}<h1>Welcome</h1><p>{body} some real content here</p>"
            f"<script>{script}</script></body></html>")


PAGES = {
    "/": page("home"), "/about": page("about"), "/docs": page("docs"), "/logout": page("bye"),
    "/console": page("console", "console.error('boom')"),
    "/api-fail": page("reports", "fetch('/api/missing')"),
    "/login-page": page("login") + "<form method=post action=/login-page><input name=u><input type=password name=p></form>",
}


class Handler(BaseHTTPRequestHandler):
    hits, posts = [], []

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Handler.hits.append(self.path)
        if self.path == "/boom":
            return self._send(500, "<h1>Internal Server Error</h1>")
        if self.path in PAGES:
            return self._send(200, PAGES[self.path])
        self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        Handler.hits.append("POST " + self.path)
        Handler.posts.append(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        self._send(200, page("logged in"))


@pytest.fixture(scope="module")
def site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(autouse=True)
def _reset_hits():
    Handler.hits.clear()
    Handler.posts.clear()
    yield
    app.dependency_overrides.clear()


def make_run(url, status="created"):
    with SessionLocal() as db:
        mid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        now = datetime.utcnow()
        db.add(Manual(id=mid, source_type="text", text="x", created_at=now))
        db.add(TestRun(id=rid, manual_id=mid, base_url=url, status=status, created_at=now))
        db.commit()
    return rid


def steps(client, rid):
    return client.get(f"/test-runs/{rid}/steps").json()


def by_label(body):
    return {s["target"]: s for s in body["test_cases"][0]["steps"]}


def fake_execution(calls):
    app.dependency_overrides[get_execution_service] = lambda: ExecutionService(
        ExecutionRepository(SessionLocal()), lambda rid, creds, sf=None, depth=None, ta=None, fm=None: calls.append((rid, creds, sf)))


def test_sweep_discovery_denylist_and_classification(client, site):
    rid = make_run(site + "/")
    runner.run_sweep(rid, None)
    b = steps(client, rid)
    assert b["status"] == "done" and b["note"] == "Forms in modals/wizards are not tested"
    assert [c["title"] for c in b["test_cases"]] == ["Menu sweep"]
    st = by_label(b)
    assert list(st) == ["Home", "About", "Broken", "Console", "Reports", "Docs"]  # page order, dropdown last
    assert all(s["action"] == "visit_menu" and s["expected"] is None and s["unclear"] is False for s in st.values())
    assert st["Docs"]["value"] == "/docs" and st["About"]["result"]["status"] == "passed"
    assert st["Home"]["result"]["status"] == "passed" and st["Docs"]["result"]["status"] == "passed"
    assert st["Broken"]["result"]["status"] == "failed" and st["Broken"]["result"]["http_status"] == 500
    assert st["Console"]["result"]["status"] == "warning" and st["Console"]["result"]["console_errors"] >= 1
    assert st["Reports"]["result"]["status"] == "warning" and st["Reports"]["result"]["failed_requests"] == 1
    assert b["summary"] == {"total": 6, "passed": 3, "failed": 1, "warning": 2, "pending": 0}
    r = st["About"]["result"]
    assert set(r) == {"status", "error", "http_status", "console_errors", "failed_requests", "duration_ms",
                      "error_type", "page_url", "details"}
    assert r["error_type"] is None and r["details"] is None and r["page_url"] == site + "/about"
    b500, con, rep = st["Broken"]["result"], st["Console"]["result"], st["Reports"]["result"]
    assert b500["error_type"] == "server_error" and b500["details"]["excerpt"] == "Internal Server Error"
    assert con["error_type"] == "console_error" and con["page_url"] == site + "/console"
    m = con["details"]["console_messages"][0]
    assert m["type"] == "error" and "boom" in m["text"] and len(m["text"]) <= 300 and con["details"]["failed_requests"] == []
    assert rep["error_type"] == "failed_request" and rep["details"]["console_messages"] == []
    assert rep["details"]["failed_requests"] == [{"method": "GET", "url": site + "/api/missing", "status": 404}]
    # denylisted items were never requested
    assert not {"/logout", "/delete-account", "/files/r.pdf", "/x"} & set(Handler.hits)
    assert len(list((get_settings().storage_dir / "runs" / rid).glob("*.png"))) == 6


def test_max_menus_truncation_and_note(client, site):
    rid = make_run(site + "/")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), max_menus=2))
    b = steps(client, rid)
    assert b["note"] == "Found 6 menus, visited the first 2; Forms in modals/wizards are not tested" and b["summary"]["total"] == 2
    assert list(by_label(b)) == ["Home", "About"] and b["status"] == "done"


def test_rerun_replaces_sweep(client, site):
    rid = make_run(site + "/")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), max_menus=2))
    fake_execution([])
    assert client.post(f"/test-runs/{rid}/execute").status_code == 202
    b = steps(client, rid)
    assert b["status"] == "running" and b["test_cases"] == [] and b["summary"]["total"] == 0 and b["note"] is None


def test_unreachable_base_url_fails_run(client):
    rid = make_run("http://127.0.0.1:1/")
    runner.run_sweep(rid, None)
    r = client.get(f"/test-runs/{rid}").json()
    assert r["status"] == "failed" and r["error"].startswith("Could not open")


def test_chromium_missing_message(client, site, monkeypatch):
    import playwright.sync_api as api

    class Boom:
        def __enter__(self):
            class PW:
                class chromium:
                    @staticmethod
                    def launch(**kw):
                        raise Exception("BrowserType.launch: Executable doesn't exist at C:\\x")
            return PW

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(api, "sync_playwright", lambda: Boom())
    rid = make_run(site + "/")
    runner.run_sweep(rid, None)
    assert client.get(f"/test-runs/{rid}").json()["error"] == \
        "Chromium is not installed. Run: python -m playwright install chromium"


def test_credentials_used_but_never_logged_or_stored(client, site, capsys, caplog):
    secret = "Sup3r-S3cret-pw"
    rid = make_run(site + "/login-page")
    with caplog.at_level("DEBUG"):
        runner.run_sweep(rid, {"username": "alice", "password": secret})
    assert any(secret in p for p in Handler.posts)  # login really happened
    out = capsys.readouterr()
    assert secret not in out.out + out.err + caplog.text
    with engine.connect() as c:
        dump = "\n".join(c.connection.iterdump())
    assert secret not in dump and secret not in json.dumps(steps(client, rid)) \
        and secret not in json.dumps(client.get(f"/test-runs/{rid}").json())


def test_stale_running_marked_failed_on_startup(client):
    rid = make_run("http://x.test/", status="running")
    with TestClient(app):  # lifespan runs the cleanup
        pass
    r = client.get(f"/test-runs/{rid}").json()
    assert r["status"] == "failed" and r["error"] == "Interrupted"


# ---- execute endpoint -------------------------------------------------------------------------

def test_execute_endpoint_codes(client):
    calls = []
    fake_execution(calls)
    assert client.post("/test-runs/nope/execute").status_code == 404
    assert client.post("/test-runs/nope/execute").json()["error"]["code"] == "test_run_not_found"
    rid = make_run("http://x.test/", status="parsed")
    r = client.post(f"/test-runs/{rid}/execute", json={"credentials": {"username": "u", "password": "p"}})
    assert r.status_code == 202 and r.json() == {"id": rid, "status": "running"}
    assert calls == [(rid, {"username": "u", "password": "p"}, None)]
    assert client.get(f"/test-runs/{rid}").json()["status"] == "running"
    r = client.post(f"/test-runs/{rid}/execute")
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_busy"
    assert client.post(f"/test-runs/{make_run('http://x.test/', 'parsing')}/execute").status_code == 202  # allowed while parsing
    other = make_run("http://x.test/", status="failed")
    for bad in ({"credentials": {"username": "u"}}, {"credentials": "x"}, {"credentials": {"username": 1, "password": 2}}):
        r = client.post(f"/test-runs/{other}/execute", json=bad)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert client.get(f"/test-runs/{other}").json()["status"] == "failed"  # 422 changed nothing
    assert client.post(f"/test-runs/{other}/execute", json={"credentials": None}).status_code == 202
    assert client.post(f"/test-runs/{make_run('http://x.test/', 'done')}/execute").status_code == 202


def test_spawn_sends_credentials_via_stdin_only(monkeypatch):
    seen = {}

    class FakeStdin:
        def write(self, b):
            seen["stdin"] = b

        def close(self):
            pass

    class FakePopen:
        def __init__(self, args, **kw):
            seen["args"], seen["kw"] = args, kw
            self.stdin = FakeStdin()

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    execution_service.spawn_executor("run-1", {"username": "u", "password": "pw-secret"})
    assert seen["args"][1:] == ["-m", "app.services.executor", "run-1"]
    assert "pw-secret" not in " ".join(seen["args"]) and "pw-secret" not in json.dumps(seen["kw"].get("env", {}))
    assert json.loads(seen["stdin"]) == {"credentials": {"username": "u", "password": "pw-secret"}, "submit_forms": None,
                                         "validation_depth": None, "test_actions": None, "fast_mode": None}


def test_execute_real_subprocess_end_to_end(client, site):
    rid = make_run(site + "/", status="parsed")
    assert client.post(f"/test-runs/{rid}/execute").status_code == 202
    deadline = time.time() + 120
    while time.time() < deadline and client.get(f"/test-runs/{rid}").json()["status"] == "running":
        time.sleep(1)
    b = steps(client, rid)
    assert b["status"] == "done", client.get(f"/test-runs/{rid}").json()
    assert b["summary"] == {"total": 6, "passed": 3, "failed": 1, "warning": 2, "pending": 0}


# ---- units ------------------------------------------------------------------------------------

def item(label, href, abs_=None, download=False):
    return {"label": label, "href": href, "download": download,
            "abs": abs_ or (f"http://h{href}" if href and href.startswith("/") else href)}


@pytest.mark.parametrize("it,denied", [
    (item("Dashboard", "/dash"), False),
    (item("Log out", "/x"), True), (item("Sign Out", "/x"), True), (item("Logout", "/x"), True),
    (item("Delete item", "/x"), True), (item("Remove", "/x"), True),
    (item("Account", "/account/delete"), True),
    (item("Ext", "https://other.com/", "https://other.com/"), True),
    (item("Mail", "mailto:a@b.c", "mailto:a@b.c"), True), (item("Call", "tel:123", "tel:123"), True),
    (item("Top", "#"), True), (item("File", "/f.pdf"), True), (item("Dl", "/f", download=True), True),
    (item("Menu item", None), False),
])
def test_denylist(it, denied):
    assert is_denied(it, "http://h") is denied


def test_classify():
    ok = {"title": "Home", "h1": "Hi", "body": "hello world"}
    assert classify(200, ok, 0, 0) == ("passed", None)
    assert classify(200, ok, 1, 0)[0] == "warning" and classify(200, ok, 0, 2)[0] == "warning"
    assert classify(404, ok, 0, 0)[0] == "failed" and classify(500, ok, 3, 0)[0] == "failed"
    assert classify(200, {**ok, "body": ""}, 0, 0) == ("failed", "Page is blank")
    assert classify(200, {**ok, "h1": "404 Not Found"}, 0, 0)[0] == "failed"
    assert classify(200, {**ok, "body": "Internal Server Error"}, 0, 0)[0] == "failed"
    assert classify(200, {**ok, "body": "x" * 400 + " 404"}, 0, 0)[0] == "passed"


def test_error_type_mapping_and_sanitizing():
    from app.services.executor.checks import Collector, menu_error_type, redact, sanitize_url
    assert menu_error_type("passed", 200, None, 0) is None
    assert menu_error_type("failed", 503, "HTTP 503", 0) == "server_error"
    assert menu_error_type("failed", 404, "HTTP 404", 0) == "client_error"
    assert menu_error_type("failed", 200, "Error page detected", 0) == "error_page"
    assert menu_error_type("failed", 200, "Page is blank", 0) == "blank_page"
    assert menu_error_type("failed", None, "Timed out after 15s", 0) == "timeout"
    assert menu_error_type("failed", None, "net::ERR_X", 0) == "navigation_failed"
    assert menu_error_type("warning", 200, "x", 0) == "console_error"
    assert menu_error_type("warning", 200, "x", 2) == "failed_request"  # both -> failed_request
    assert sanitize_url("http://h/p?token=abc&a=1&Password=x#frag") == "http://h/p?token=***&a=1&Password=***"
    assert redact("pw Test@12345 end", ["Test@12345", "Sup3r"]) == "pw *** end" and len(redact("x" * 999, [])) == 300

    class P:
        def on(self, *a):
            pass
    c = Collector(P())
    c.secrets.append("Sup3r")
    for i in range(8):
        c._msg("error", f"bad Sup3r {i}", None)
        c._req("GET", f"http://h/a?secret=Sup3r&i={i}", 500)
    d = c.details()
    assert len(d["console_messages"]) == 5 and len(d["failed_requests"]) == 5 and "Sup3r" not in str(d)
    assert "secret=***" in d["failed_requests"][0]["url"]


def test_alter_adds_error_columns_to_old_db(client):
    from sqlalchemy import inspect
    new = ("error_type", "page_url", "details")
    with engine.begin() as c:
        for col in new:
            c.exec_driver_sql(f"ALTER TABLE step_results DROP COLUMN {col}")
    assert not set(new) & {c["name"] for c in inspect(engine).get_columns("step_results")}
    with TestClient(app):
        pass
    assert set(new) <= {c["name"] for c in inspect(engine).get_columns("step_results")}


def test_stale_running_step_becomes_interrupted(client):
    from app.models import Step, StepResult, TestCase
    rid = make_run("http://x.test/", status="running")
    with SessionLocal() as db:
        repo = ExecutionRepository(db)
        (sid,) = repo.create_sweep(rid, [("A", "/a")], None)
        repo.save_result(sid, status="running")
    with TestClient(app):
        pass
    r = steps(client, rid)["test_cases"][0]["steps"][0]["result"]
    assert r["status"] == "failed" and r["error_type"] == "interrupted"
