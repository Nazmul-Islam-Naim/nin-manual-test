import json
import subprocess

import httpx
import pytest

from app.main import app
from app.routers.test_runs import get_url_checker
from app.services import parsing_service
from app.services.llm import LLMError, providers
from app.services.llm.providers import ClaudeCliProvider
from app.services.url_check import UrlChecker


@pytest.fixture(autouse=True)
def _checker():
    app.dependency_overrides[get_url_checker] = lambda: UrlChecker(
        True, 5, httpx.MockTransport(lambda r: httpx.Response(200)))
    yield
    app.dependency_overrides.clear()


def start(client, text="1. Login\n2. Logout"):
    mid = client.post("/manuals", json={"text": text}).json()["id"]
    return client.post("/test-runs", json={"manual_id": mid, "url": "example.com"}).json()


def case(title, *actions):
    return {"title": title, "steps": [{"order": i, "action": a, "target": f"t{i}", "value": None,
                                      "expected": None, "unclear": False} for i, a in enumerate(actions, 1)]}


def test_three_scenarios_in_order(client, llm_fake):
    llm_fake.replies = [json.dumps({"test_cases": [case("A", "open", "click"), case("B", "type"),
                                                   case("C", "assert_text")]})]
    run = start(client)
    assert run["status"] == "created" and run["error"] is None
    assert client.get(f"/test-runs/{run['id']}").json()["status"] == "parsed"
    b = client.get(f"/test-runs/{run['id']}/steps").json()
    assert b["status"] == "parsed" and [c["title"] for c in b["test_cases"]] == ["A", "B", "C"]
    assert [c["order"] for c in b["test_cases"]] == [1, 2, 3]
    assert [s["action"] for s in b["test_cases"][0]["steps"]] == ["open", "click"]
    assert set(b["test_cases"][0]["steps"][0]) == {"id", "order", "action", "target", "value", "expected", "unclear", "result", "meta"}


def test_bangla_unclear_and_fence(client, llm_fake):
    c = {"title": "লগইন", "steps": [{"order": 1, "action": "click", "target": "লগইন বাটন", "value": None,
                                    "expected": "সফল", "unclear": True}]}
    llm_fake.replies = ["```json\n" + json.dumps({"test_cases": [c]}, ensure_ascii=False) + "\n```"]
    run = start(client)
    s = client.get(f"/test-runs/{run['id']}/steps").json()["test_cases"][0]
    assert s["title"] == "লগইন" and s["steps"][0]["unclear"] is True and s["steps"][0]["expected"] == "সফল"


def test_retry_once_then_ok(client, llm_fake):
    llm_fake.replies = ["not json", json.dumps({"test_cases": [case("A", "open")]})]
    run = start(client)
    assert client.get(f"/test-runs/{run['id']}").json()["status"] == "parsed" and len(llm_fake.calls) == 2


def test_schema_mismatch_fails_after_retry(client, llm_fake):
    llm_fake.replies = [json.dumps({"test_cases": [case("A", "teleport")]})]
    run = start(client)
    g = client.get(f"/test-runs/{run['id']}").json()
    assert g["status"] == "failed" and "schema" in g["error"] and len(llm_fake.calls) == 2
    s = client.get(f"/test-runs/{run['id']}/steps")
    assert s.status_code == 200 and s.json() == {"run_id": run["id"], "status": "failed", "test_cases": [], "note": None, "field_rules": [], "started_at": None, "finished_at": None, "max_minutes": None,
                                                "summary": {"total": 0, "passed": 0, "failed": 0, "warning": 0, "pending": 0}}


def test_provider_error_becomes_failed(client, llm_fake):
    llm_fake.replies = [LLMError("claude CLI timed out after 120s.")]
    run = start(client)
    g = client.get(f"/test-runs/{run['id']}").json()
    assert g["status"] == "failed" and g["error"] == "claude CLI timed out after 120s."
    assert len(llm_fake.calls) == 1


def test_unknown_run_steps_404(client):
    r = client.get("/test-runs/nope/steps")
    assert r.status_code == 404 and r.json()["error"]["code"] == "test_run_not_found"


def test_chunking_and_merge(client, llm_fake, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("PARSE_CHUNK_CHARS", "30")
    get_settings.cache_clear()
    try:
        llm_fake.replies = [json.dumps({"test_cases": [case("X", "open")]})]
        run = start(client, "para one aaaaaaaaaa\n\npara two bbbbbbbbbb\n\npara three cccccccccc")
        n = len(llm_fake.calls)
        assert n >= 2
        b = client.get(f"/test-runs/{run['id']}/steps").json()
        assert [c["order"] for c in b["test_cases"]] == list(range(1, n + 1))
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_chunk_text():
    assert parsing_service.chunk_text("a\n\nb", 100) == ["a\n\nb"]
    assert parsing_service.chunk_text("aaaa\n\nbbbb", 6) == ["aaaa", "bbbb"]
    assert all(len(c) <= 5 for c in parsing_service.chunk_text("x" * 12, 5))


def _cli(monkeypatch, run):
    monkeypatch.setattr(providers, "resolve_claude", lambda: "claude")
    monkeypatch.setattr(providers.subprocess, "run", run)


def test_cli_provider_parses_result(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"result": "{}", "is_error": False}), "")

    _cli(monkeypatch, run)
    assert ClaudeCliProvider("sonnet", 5).complete("sys", "hello") == "{}"
    assert seen["input"] == "hello" and "--tools" in seen["cmd"] and seen["timeout"] == 5


def test_cli_provider_errors(monkeypatch):
    monkeypatch.setattr(providers, "resolve_claude", lambda: None)
    with pytest.raises(LLMError, match="not found"):
        ClaudeCliProvider("sonnet", 5).complete("s", "u")

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 5)

    _cli(monkeypatch, boom)
    with pytest.raises(LLMError, match="timed out"):
        ClaudeCliProvider("sonnet", 5).complete("s", "u")

    _cli(monkeypatch, lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, json.dumps({"is_error": True, "result": "Not logged in"}), ""))
    with pytest.raises(LLMError, match="Not logged in"):
        ClaudeCliProvider("sonnet", 5).complete("s", "u")


def test_missing_api_key():
    from app.services.llm.providers import AnthropicProvider, GeminiProvider, OpenRouterProvider
    for p in (AnthropicProvider("", "m", 1), OpenRouterProvider("", "m", 1), GeminiProvider("", "m", 1)):
        with pytest.raises(LLMError, match="not set"):
            p.complete("s", "u")


def test_error_column_added_to_old_table(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    from fastapi.testclient import TestClient
    import app.main as m
    e = create_engine(f"sqlite:///{tmp_path}/old.db")
    with e.begin() as c:
        c.execute(text("CREATE TABLE test_runs (id TEXT PRIMARY KEY)"))
    monkeypatch.setattr(m, "engine", e)
    with TestClient(m.app):
        pass
    assert "error" in {c["name"] for c in inspect(e).get_columns("test_runs")}
