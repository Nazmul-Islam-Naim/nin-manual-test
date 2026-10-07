import re
from urllib.parse import urlparse

DENY_WORDS = re.compile(r"log\s*-?out|sign\s*-?out|delete|remove", re.I)
DOWNLOAD_EXT = (".pdf", ".zip", ".exe", ".dmg", ".msi", ".rar", ".7z", ".tar", ".gz", ".doc", ".docx", ".xls",
                ".xlsx", ".csv", ".apk")
MENU_SEL = ("nav a[href], header a[href], aside a[href], [role=navigation] a[href], [role=menubar] a[href], "
            "[role=menuitem]")
_CONTAINERS = ("nav", "header", "aside", "[role=navigation]", "[role=menubar]")
TOGGLE_SEL = ", ".join(f"{c} {a}" for c in _CONTAINERS for a in ("[aria-haspopup]", "[aria-expanded]"))

_COLLECT_JS = """(sel) => [...document.querySelectorAll(sel)].map(e => {
  const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  const a = e.tagName === 'A';
  return {label: (e.innerText || e.getAttribute('aria-label') || e.title || '').trim().replace(/\\s+/g, ' '),
          href: a ? e.getAttribute('href') : null, abs: a ? e.href : null,
          toggle: e.hasAttribute('aria-haspopup') || e.hasAttribute('aria-expanded'),
          download: e.hasAttribute('download'),
          visible: r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'};
})"""


def is_denied(item: dict, origin: str) -> bool:
    href, abs_ = item["href"], item["abs"]
    if item["download"] or DENY_WORDS.search(item["label"]):
        return True
    if href is None:
        return False
    if href.strip() in ("", "#") or re.match(r"(mailto|tel|javascript|data|blob):", href.strip(), re.I):
        return True
    u = urlparse(abs_)
    return (f"{u.scheme}://{u.netloc}" != origin or DENY_WORDS.search(u.path) is not None
            or u.path.lower().endswith(DOWNLOAD_EXT))


def discover(page, origin: str) -> list[dict]:
    """Same-origin visible menu items in page order, dropdowns expanded one level, deduped, denylist applied."""
    found: dict[tuple, dict] = {}

    def collect():
        for it in page.evaluate(_COLLECT_JS, MENU_SEL):
            if it["visible"] and it["label"] and not it["toggle"]:
                found.setdefault((it["label"].lower(), it["href"]), it)

    collect()
    toggles = page.locator(TOGGLE_SEL)
    for i in range(toggles.count()):
        t = toggles.nth(i)
        try:
            if not t.is_visible():
                continue
            before = len(found)
            t.hover(timeout=2000)
            collect()
            if len(found) == before:  # hover opened nothing: try click
                t.click(timeout=2000)
                collect()
        except Exception:  # ponytail: a dropdown that won't open is just skipped
            continue
    return [it for it in found.values() if not is_denied(it, origin)]
