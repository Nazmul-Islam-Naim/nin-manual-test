import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from app.errors import AppError

MAX_REDIRECTS = 5


def normalize_url(raw: str) -> str:
    url = raw.strip()
    bad = AppError(422, "invalid_url", "URL is invalid. Use a http(s) address like https://example.com.")
    if not url or any(c.isspace() for c in url):
        raise bad
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlsplit(url)
        parts.port  # raises ValueError on a malformed port
    except ValueError:
        raise bad
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise bad
    return parts._replace(fragment="").geturl()


def _assert_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise AppError(400, "url_unreachable", f"Could not resolve host '{host}'.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_reserved:
            raise AppError(400, "private_url_blocked", "Private or local addresses are not allowed.")


class UrlChecker:
    def __init__(self, allow_private: bool, timeout_s: float, transport: httpx.BaseTransport | None = None):
        self.allow_private, self.timeout_s, self.transport = allow_private, timeout_s, transport

    def check(self, url: str) -> str | None:
        """Return a warning string if the site answers 4xx/5xx, None if fine. Raises AppError if unreachable/blocked."""
        try:
            with httpx.Client(timeout=self.timeout_s, follow_redirects=False, transport=self.transport) as client:
                resp = self._request(client, url)
        except (httpx.TransportError, httpx.InvalidURL):  # DNS failure, refused, timeout, ...
            raise AppError(400, "url_unreachable", "The website could not be reached (DNS failure, connection refused or timeout).")
        return f"Site responded with HTTP {resp.status_code}" if resp.status_code >= 400 else None

    def _request(self, client: httpx.Client, url: str) -> httpx.Response:
        method = "HEAD"
        redirects = 0
        while True:
            if not self.allow_private:  # checked on every hop so redirects can't reach internal hosts
                _assert_public(urlsplit(url).hostname or "")
            resp = client.request(method, url)
            if resp.status_code in (403, 405) and method == "HEAD":
                method = "GET"
                continue
            loc = resp.headers.get("location")
            if resp.is_redirect and loc and redirects < MAX_REDIRECTS:
                redirects += 1
                url = urljoin(url, loc)
                continue  # ponytail: method stays as-is across hops; fine for HEAD/GET
            return resp
