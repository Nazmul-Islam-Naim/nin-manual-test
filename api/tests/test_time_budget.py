"""Instruction 015: time budget, two-phase scheduling, graceful stop, started/finished/max_minutes, fast mode."""
import dataclasses
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.repositories.execution_repository import ExecutionRepository
from app.routers.test_runs import get_execution_service
from app.services.execution_service import ExecutionService
from app.services.executor import cases, checks, runner
from tests.test_execution import make_run, steps

FORM = ('<form method=post action=/post name="{n}"><label>Email <input type=email name=email></label>'
        '<label>Phone <input type=tel name=phone></label><button>Send</button></form>')


def html(body):
    return f"<html><head><title>T</title></head><body><h1>Hi</h1><p>some real content here</p>{body}</body></html>"


PAGES = {
    "/": html('<nav><a href="/a">Page A</a> <a href="/b">Page B</a> <a href="/c">Page C</a></nav>'),
    "/a": html(FORM.format(n="FormA")), "/b": html(FORM.format(n="FormB")), "/c": html("<p>plain</p>"),
}


class H(BaseHTTPRequestHandler):
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
        self._send(200, PAGES[self.path]) if self.path in PAGES else self._send(404, "<h1>Not Found</h1>")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send(200, html("<p>Saved successfully</p>"))


@pytest.fixture(scope="module")
def tsite():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(autouse=True)
def _clean():
    yield
    app.dependency_overrides.clear()


def sweep(site, settings=None):
    rid = make_run(site + "/")
    runner.run_sweep(rid, None, settings, submit_forms=True, validation_depth="standard")
    return rid


def case_steps(b):
    return [s for s in b["test_cases"][0]["steps"] if s["meta"] and s["meta"]["category"] not in ("empty", "valid_sample")]


# ---- scheduling ---------------------------------------------------------------------------------

def test_round_robin_creates_steps_on_first_turn_and_keeps_step_order(client, tsite, monkeypatch):
    events = []
    prep, nxt = cases.prepare, cases.run_next
    monkeypatch.setattr(cases, "prepare", lambda page, repo, job, *a: (events.append(("prepare", job.form["name"])),
                                                                         prep(page, repo, job, *a))[1])
    monkeypatch.setattr(cases, "run_next", lambda page, repo, job, col: (events.append(("run", job.form["name"])),
                                                                          nxt(page, repo, job, col))[1])
    rid = sweep(tsite)
    # first round: each job is prepared right before its first case; then one case per form per round
    assert events[:6] == [("prepare", "FormA"), ("run", "FormA"), ("prepare", "FormB"), ("run", "FormB"),
                          ("run", "FormA"), ("run", "FormB")]
    runs = [f for k, f in events if k == "run"]
    assert runs == ["FormA", "FormB"] * (len(runs) // 2) and len(runs) == 20
    b = steps(client, rid)
    st = b["test_cases"][0]["steps"]
    assert [s["order"] for s in st] == list(range(1, len(st) + 1)) and b["status"] == "done" and b["summary"]["pending"] == 0
    # unchanged layout: menu, its form (empty skipped: no required fields; sample), its cases, next menu ...
    assert [s["target"].split(" > ")[0] for s in st if s["action"] == "visit_menu"] == ["Page A", "Page B", "Page C"]
    assert [s["action"] for s in st[:3]] == ["visit_menu", "submit_form", "submit_form"]
    a_idx = [i for i, s in enumerate(st) if "Page A > FormA" in s["target"]]
    b_idx = [i for i, s in enumerate(st) if "Page B > FormB" in s["target"]]
    assert a_idx == list(range(a_idx[0], a_idx[-1] + 1)) and a_idx[-1] < st.index(next(s for s in st if s["target"] == "Page B"))
    assert b_idx[-1] == len(st) - 2 and st[-1]["target"] == "Page C"  # Page C has no form
    assert len(case_steps(b)) == 20 and not hasattr(cases, "pace")  # case runs never pace


def test_graceful_stop_at_time_limit_keeps_done_and_pending(client, tsite, monkeypatch):
    # the runner clock jumps past the 10 min budget after 3 cases: deterministic, no sleeping
    offset, real = [0.0], time.monotonic
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: real() + offset[0]))
    nxt, count = cases.run_next, [0]

    def run_next(page, repo, job, col):
        nxt(page, repo, job, col)
        count[0] += 1
        if count[0] == 3:
            offset[0] = 10_000
    monkeypatch.setattr(cases, "run_next", run_next)
    rid = sweep(tsite, dataclasses.replace(get_settings(), exec_overall_timeout_s=600))
    b, run = steps(client, rid), client.get(f"/test-runs/{rid}").json()
    assert b["status"] == "done" and run["status"] == "done" and run["error"] is None
    assert count[0] == 3
    menus = [s for s in b["test_cases"][0]["steps"] if s["action"] == "visit_menu"]
    assert len(menus) == 3 and all(m["result"]["status"] == "passed" for m in menus)  # phase 1 finished
    pending = b["summary"]["pending"]
    assert pending > 0 and b["summary"]["total"] == len(b["test_cases"][0]["steps"])
    assert f"Stopped at the time limit (10 min); {pending} checks were not run" in b["note"]
    # both jobs were started (steps exist); only 3 cases ran, the rest stay pending ("failed" here = lax fixture accepts invalid data)
    assert len(case_steps(b)) == 20 and sum(1 for s in case_steps(b) if s["result"]) == 3
    assert "Overall time limit" not in str(b)
    assert b["max_minutes"] == 10 and b["started_at"] and b["finished_at"]


def test_tiny_budget_stops_before_menus_without_failing(client, tsite):
    rid = sweep(tsite, dataclasses.replace(get_settings(), exec_overall_timeout_s=0.001))
    b = steps(client, rid)
    assert b["status"] == "done" and client.get(f"/test-runs/{rid}").json()["error"] is None
    assert b["summary"]["pending"] == 3 and b["summary"]["passed"] == 0
    assert b["note"].endswith("Stopped at the time limit (1 min); 3 checks were not run")


def test_unreachable_site_is_still_failed_and_finished(client):
    rid = make_run("http://127.0.0.1:1/")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), exec_overall_timeout_s=0.001))
    r = client.get(f"/test-runs/{rid}").json()
    assert r["status"] == "failed" and r["error"].startswith("Could not open") and r["finished_at"]


def test_started_finished_max_minutes_exposed(client, tsite):
    rid = make_run(tsite + "/c")
    before = client.get(f"/test-runs/{rid}").json()
    assert (before["started_at"], before["finished_at"], before["max_minutes"]) == (None, None, None)
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), exec_overall_timeout_s=1800))
    r, b = client.get(f"/test-runs/{rid}").json(), steps(client, rid)
    for body in (r, b):
        assert body["max_minutes"] == 30
        s, f = (datetime.fromisoformat(body[k].replace("Z", "+00:00")) for k in ("started_at", "finished_at"))
        assert s <= f and body["started_at"].endswith("Z")


# ---- pace / fast mode ----------------------------------------------------------------------------

def test_pace_and_fast_mode(client, tsite, monkeypatch):
    class P:
        waits = []

        def wait_for_timeout(self, ms):
            self.waits.append(ms)

    checks.UI.pace_ms = 0
    checks.pace(P())
    checks.UI.pace_ms = 25
    checks.pace(P())
    assert P.waits == [25]
    rid = make_run(tsite + "/c")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), exec_slow_mo_ms=7), fast_mode=True)
    assert (checks.UI.pace_ms, checks.UI.highlight) == (0, False)
    rid = make_run(tsite + "/c")
    runner.run_sweep(rid, None, dataclasses.replace(get_settings(), exec_slow_mo_ms=7))
    assert (checks.UI.pace_ms, checks.UI.highlight) == (7, True)
    checks.UI.pace_ms = 0


def test_no_browser_level_slow_mo(client, tsite, monkeypatch):
    import playwright.sync_api as api
    seen = {}

    class Boom:
        def __enter__(self):
            class PW:
                class chromium:
                    @staticmethod
                    def launch(**kw):
                        seen.update(kw)
                        raise Exception("stop")
            return PW

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(api, "sync_playwright", lambda: Boom())
    runner.run_sweep(make_run(tsite + "/"), None, dataclasses.replace(get_settings(), exec_slow_mo_ms=400))
    assert "slow_mo" not in seen and "headless" in seen


def test_defaults_300_and_3600(monkeypatch):
    for k in ("EXEC_SLOW_MO_MS", "EXEC_OVERALL_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)
    s = get_settings.__wrapped__()
    assert (s.exec_slow_mo_ms, s.exec_overall_timeout_s) == (300, 3600)


# ---- API -----------------------------------------------------------------------------------------

def test_execute_body_max_minutes_and_fast_mode(client):
    calls = []
    app.dependency_overrides[get_execution_service] = lambda: ExecutionService(
        ExecutionRepository(SessionLocal()), lambda *a: calls.append(a))
    rid = make_run("http://x.test/", status="parsed")
    r = client.post(f"/test-runs/{rid}/execute", json={"max_minutes": 15, "fast_mode": True})
    assert r.status_code == 202 and calls[-1][5] is True
    assert client.get(f"/test-runs/{rid}").json()["max_minutes"] == 15
    assert client.get(f"/test-runs/{rid}").json()["started_at"] and client.get(f"/test-runs/{rid}").json()["finished_at"] is None
    for ok in (1, 240):
        assert client.post(f"/test-runs/{make_run('http://x.test/')}/execute", json={"max_minutes": ok}).status_code == 202
    other = make_run("http://x.test/", status="parsed")
    for bad in ({"max_minutes": 0}, {"max_minutes": 241}, {"max_minutes": -5}, {"max_minutes": "5"},
                {"max_minutes": 1.5}, {"max_minutes": True}, {"fast_mode": "yes"}, {"fast_mode": 1}):
        r = client.post(f"/test-runs/{other}/execute", json=bad)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request", bad
    assert client.get(f"/test-runs/{other}").json()["status"] == "parsed"
    # omitted -> env default (3600 s = 60 min)
    d = make_run("http://x.test/", status="parsed")
    assert client.post(f"/test-runs/{d}/execute").status_code == 202
    assert client.get(f"/test-runs/{d}").json()["max_minutes"] == round(get_settings().exec_overall_timeout_s / 60)


def test_startup_alter_adds_time_columns_to_old_db(client):
    new = ("started_at", "finished_at", "max_minutes")
    with engine.begin() as c:
        for col in new:
            c.exec_driver_sql(f"ALTER TABLE test_runs DROP COLUMN {col}")
    assert not set(new) & {c["name"] for c in inspect(engine).get_columns("test_runs")}
    with TestClient(app):
        pass
    assert set(new) <= {c["name"] for c in inspect(engine).get_columns("test_runs")}
    with TestClient(app):  # idempotent
        pass


def test_stale_running_gets_finished_at(client):
    rid = make_run("http://x.test/", status="running")
    with TestClient(app):
        pass
    r = client.get(f"/test-runs/{rid}").json()
    assert r["status"] == "failed" and r["finished_at"]
