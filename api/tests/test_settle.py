"""Menu discovery must wait for client-side redirects / late rendering (headless local fixture sites)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services.executor import runner
from tests.test_execution import make_run, steps  # noqa: F401  (client fixture comes from conftest)

SECRET = "Sup3r-S3cret-pw"
NAV = "<nav><a href='/dashboard'>Dash</a> <a href='/reports'>Reports</a></nav>"


def html(body):
    return f"<html><body>{body}<p>some real content here</p></body></html>"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, code=200, headers=()):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        authed = "s=1" in self.headers.get("Cookie", "")
        p = self.path
        if p == "/dashboard":
            return self._send(html(NAV + "<h1>Dash</h1>") if authed else html(
                "<h1>loading</h1><script>addEventListener('load',()=>setTimeout(()=>location.replace('/login'),300))</script>"))
        if p == "/login":
            return self._send(html("<form method=post action=/login><input name=u><input type=password name=p>"
                                   "<button>Sign in</button></form>"))
        if p == "/home":
            return self._send(html("<nav><a href='/home'>Home only</a></nav>"))
        if p == "/late":
            return self._send(html("<h1>late</h1><script>addEventListener('load',()=>setTimeout(()=>{"
                                   "document.body.insertAdjacentHTML('afterbegin',\"<nav><a href='/a'>Alpha</a> "
                                   "<a href='/b'>Beta</a></nav>\")},700))</script>"))
        if p in ("/reports", "/a", "/b"):
            return self._send(html(NAV + "<h1>x</h1>"))
        if p == "/stuck":
            return self._send(html("<form method=post action=/stuck><input type=password name=p><button>Go</button></form>"))
        if p == "/bare":
            return self._send(html("<h1>nothing here</h1>"))
        self._send("nf", 404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/stuck":
            return self.do_GET()
        # lands on /home (not the requested /dashboard) so the sweep must go back to /dashboard
        self._send("", 303, [("Location", "/home"), ("Set-Cookie", "s=1; Path=/")])


@pytest.fixture(scope="module")
def site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_login_gated_without_credentials_fails_clearly(client, site):
    rid = make_run(site + "/dashboard")
    runner.run_sweep(rid, None)
    r = client.get(f"/test-runs/{rid}").json()
    assert r["status"] == "failed"
    assert r["error"] == ("The site asks for a login (/login). Enter the Username and Password under Login "
                          "(optional) and run again.")


def test_login_gated_with_credentials_sweeps_requested_page(client, site):
    rid = make_run(site + "/dashboard")
    runner.run_sweep(rid, {"username": "alice", "password": SECRET})
    b = steps(client, rid)
    assert b["status"] == "done"
    assert [s["target"] for s in b["test_cases"][0]["steps"]] == ["Dash", "Reports"]  # /dashboard, not /home
    assert SECRET not in json.dumps(b) + json.dumps(client.get(f"/test-runs/{rid}").json())


def test_wrong_credentials_message(client, site):
    rid = make_run(site + "/stuck")
    runner.run_sweep(rid, {"username": "a", "password": SECRET})
    r = client.get(f"/test-runs/{rid}").json()
    assert r["status"] == "failed" and r["error"] == (
        "Still on the login page after signing in (/stuck). Check the Username and Password.")


def test_late_rendered_nav_is_discovered(client, site):
    rid = make_run(site + "/late")
    runner.run_sweep(rid, None)
    b = steps(client, rid)
    assert b["status"] == "done" and [s["target"] for s in b["test_cases"][0]["steps"]] == ["Alpha", "Beta"]


def test_no_menus_no_login_is_done_with_note(client, site):
    rid = make_run(site + "/bare")
    runner.run_sweep(rid, None)
    b = steps(client, rid)
    assert b["status"] == "done" and "No menus were found on this page" in b["note"]
