import httpx
import pytest

from app.errors import AppError
from app.main import app
from app.routers.test_runs import get_url_checker
from app.services import url_check
from app.services.url_check import UrlChecker, normalize_url


def use_checker(handler, allow_private=True):
    app.dependency_overrides[get_url_checker] = lambda: UrlChecker(
        allow_private, 5, httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _clean():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def manual_id(client):
    return client.post("/manuals", json={"text": "step 1"}).json()["id"]


def ok(_req):
    return httpx.Response(200)


def err(r):
    return r.json()["error"]["code"]


def test_normalize():
    assert normalize_url("  example.com ") == "https://example.com"
    assert normalize_url("http://a.com/x#frag") == "http://a.com/x"
    for bad in ["", "  ", "ftp://x", "https://", "a b.com", "http://a.com:99999x"]:
        with pytest.raises(AppError) as e:
            normalize_url(bad)
        assert e.value.code == "invalid_url"


def test_create_and_get(client, manual_id):
    use_checker(ok)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "example.com"})
    assert r.status_code == 201
    b = r.json()
    assert b["base_url"] == "https://example.com" and b["status"] == "created"
    assert b["manual_id"] == manual_id and b["warning"] is None and b["created_at"].endswith("Z")
    g = client.get(f"/test-runs/{b['id']}")
    assert g.status_code == 200 and g.json()["id"] == b["id"] and g.json()["base_url"] == b["base_url"]


def test_404_page_gives_warning(client, manual_id):
    use_checker(lambda _r: httpx.Response(404))
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "https://example.com"})
    assert r.status_code == 201
    assert r.json()["warning"] == "Site responded with HTTP 404"


def test_head_falls_back_to_get(client, manual_id):
    methods = []

    def handler(req):
        methods.append(req.method)
        return httpx.Response(405 if req.method == "HEAD" else 200)

    use_checker(handler)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "https://example.com"})
    assert r.status_code == 201 and r.json()["warning"] is None
    assert methods == ["HEAD", "GET"]


def test_redirects_followed_and_capped(client, manual_id):
    def handler(req):
        if req.url.path == "/start":
            return httpx.Response(302, headers={"location": "/end"})
        return httpx.Response(200)

    use_checker(handler)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "https://a.com/start"})
    assert r.status_code == 201 and r.json()["warning"] is None

    use_checker(lambda _r: httpx.Response(302, headers={"location": "/loop"}))  # endless loop
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "https://a.com/start"})
    assert r.status_code == 201  # cap reached; still "any response = reachable"


def test_unreachable(client, manual_id):
    def boom(req):
        raise httpx.ConnectTimeout("t", request=req)

    use_checker(boom)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "https://down.example"})
    assert r.status_code == 400 and err(r) == "url_unreachable"


def test_invalid_url_422(client, manual_id):
    use_checker(ok)
    for u in ["ftp://x", "", "http://"]:
        r = client.post("/test-runs", json={"manual_id": manual_id, "url": u})
        assert r.status_code == 422 and err(r) == "invalid_url"


def test_invalid_request_422(client, manual_id):
    for body in [{"url": "a.com"}, {"manual_id": manual_id}, {"manual_id": 1, "url": "a.com"},
                 {"manual_id": manual_id, "url": None}]:
        r = client.post("/test-runs", json=body)
        assert r.status_code == 422 and err(r) == "invalid_request"
    r = client.post("/test-runs", content=b"{nope", headers={"content-type": "application/json"})
    assert r.status_code == 422 and err(r) == "invalid_request"


def test_unknown_manual_404(client):
    use_checker(ok)
    r = client.post("/test-runs", json={"manual_id": "nope", "url": "example.com"})
    assert r.status_code == 404 and err(r) == "manual_not_found"


def test_unknown_run_404(client):
    r = client.get("/test-runs/nope")
    assert r.status_code == 404 and err(r) == "test_run_not_found"


def test_private_blocked(client, manual_id, monkeypatch):
    monkeypatch.setattr(url_check.socket, "getaddrinfo", lambda h, p: [(2, 1, 6, "", ("127.0.0.1", 0))])
    use_checker(ok, allow_private=False)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "http://127.0.0.1"})
    assert r.status_code == 400 and err(r) == "private_url_blocked"


def test_private_allowed_by_default(client, manual_id):
    use_checker(ok, allow_private=True)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "http://127.0.0.1"})
    assert r.status_code == 201


def test_redirect_to_private_blocked(client, manual_id, monkeypatch):
    ips = {"public.example": "93.184.216.34", "internal.example": "10.0.0.5"}
    monkeypatch.setattr(url_check.socket, "getaddrinfo", lambda h, p: [(2, 1, 6, "", (ips[h], 0))])
    use_checker(lambda _r: httpx.Response(302, headers={"location": "http://internal.example/"}), allow_private=False)
    r = client.post("/test-runs", json={"manual_id": manual_id, "url": "https://public.example"})
    assert r.status_code == 400 and err(r) == "private_url_blocked"
