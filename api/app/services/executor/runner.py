"""Menu sweep executor. Run as: python -m app.services.executor <run_id>  (credentials JSON on stdin)."""
import json
import sys
import time
from urllib.parse import urlparse

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.parse_repository import ParseRepository
from app.services.executor import actions, cases, forms
from app.services.executor.checks import (PAGE_JS, UI, Collector, classify, menu_error_type, menu_excerpt, pace,
                                          sanitize_url)
from app.services.executor.menu_discovery import MENU_SEL, discover

ACTIONS_NOTE = "Actions inside pages opened by an action were not followed"
NO_CHROMIUM = "Chromium is not installed. Run: python -m playwright install chromium"


def _short(e: Exception) -> str:
    return (str(e).strip().splitlines() or [type(e).__name__])[0][:300]


def settle(page) -> None:
    """Best effort: network idle (<=5 s), then the URL unchanged for 600 ms (total cap 8 s). Catches client-side redirects."""
    t0 = time.monotonic()
    url, since = page.url, t0
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    while time.monotonic() - t0 < 8:
        now = time.monotonic()
        if page.url != url:
            url, since = page.url, now
        elif now - since >= 0.6:
            break
        page.wait_for_timeout(100)


def _has_password(page) -> bool:
    try:
        return page.locator("input[type=password]:visible").count() > 0
    except Exception:
        return False


def _discover(page, origin: str) -> list[dict]:
    menus = discover(page, origin)
    if not menus:  # menu may render late: wait for it once, then look again
        try:
            page.locator(MENU_SEL).locator("visible=true").first.wait_for(timeout=5000)
        except Exception:
            pass
        menus = discover(page, origin)
    return menus


def _login(page, creds: dict) -> None:
    pw = page.locator("input[type=password]:visible").first
    if pw.count() == 0:
        return
    user = page.locator("input:visible:not([type=password]):not([type=hidden]):not([type=checkbox])"
                        ":not([type=radio]):not([type=submit]):not([type=button])").first
    if user.count():
        user.fill(creds["username"])
    pw.fill(creds["password"])
    btn = page.locator("form:has(input[type=password]) :is(button:not([type=button]), input[type=submit])").first
    try:
        with page.expect_navigation(timeout=5000):  # SPA logins don't navigate: fall through after 5 s
            if btn.count():
                btn.click()
            else:
                pw.evaluate("e => e.form ? e.form.requestSubmit() : null")  # Enter alone may not submit
    except Exception:
        pass
    page.wait_for_load_state("load")
    settle(page)


def _highlight(page, menu: dict) -> None:
    if not UI.highlight:
        return
    sel = f'a[href="{menu["href"]}"]' if menu["href"] is not None else "[role=menuitem]"
    try:
        loc = page.locator(sel, has_text=menu["label"]).first
        if loc.is_visible():
            loc.evaluate("e => { e.style.outline = '3px solid #f59e0b'; e.style.outlineOffset = '2px'; }")
            loc.scroll_into_view_if_needed(timeout=1000)
    except Exception:  # cosmetic only
        pass
    pace(page)


def _visit(page, menu: dict, start_url: str, col: Collector, timeout_ms: int):
    """-> (http_status, page_info | None, error | None)"""
    try:
        if page.url != start_url:
            page.goto(start_url, wait_until="load")
        _highlight(page, menu)
        col.reset()
        http = None
        if menu["href"] is not None:
            resp = page.goto(menu["abs"], wait_until="load")
            http = resp.status if resp else None
        else:
            # ponytail: items hidden inside a collapsed dropdown fail here; expand-before-click if that matters
            page.locator("[role=menuitem]", has_text=menu["label"]).first.click()
            page.wait_for_load_state("load")
        pace(page)
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        return http, page.evaluate(PAGE_JS), None
    except Exception as e:
        if type(e).__name__ == "TimeoutError":
            return None, None, f"Timed out after {timeout_ms // 1000}s"
        return None, None, _short(e)


def _menu(page, repo, run_id, n, menu, step_id, start_url, col, timeout_ms, shots, submit_forms, test_actions,
          creds, s, form_state, notes, deadline, depth, rules) -> None:
    """Phase 1 for one menu: visit, save result, then its forms' empty/sample and page actions (cases are queued)."""
    repo.save_result(step_id, status="running")
    t0 = time.monotonic()
    http, info, err = _visit(page, menu, start_url, col, timeout_ms)
    status, msg = ("failed", err) if err else classify(http, info, col.console_errors, col.failed_requests)
    shot = None
    try:
        page.screenshot(path=str(shots / f"{n}.png"))
        shot = f"runs/{run_id}/{n}.png"
    except Exception:
        pass
    etype = menu_error_type(status, http, msg, col.failed_requests)
    try:
        final_url = sanitize_url(page.url)
    except Exception:
        final_url = None
    repo.save_result(step_id, status=status, error=msg, http_status=http,
                     console_errors=col.console_errors, failed_requests=col.failed_requests,
                     duration_ms=int((time.monotonic() - t0) * 1000), screenshot_path=shot,
                     error_type=etype, page_url=final_url,
                     details=col.details(menu_excerpt(info) if etype in (
                         "server_error", "client_error", "error_page") else None) if etype else None)
    if (submit_forms or test_actions) and status != "failed":
        murl = page.url
        if submit_forms:
            forms.test_page_forms(page, repo, step_id, menu["label"], {"url": murl, "action": None}, col,
                                  creds, s, form_state, notes, deadline, depth, rules)
        if test_actions:
            actions.test_page_actions(page, repo, step_id, menu["label"], murl, col, creds, s,
                                      form_state, notes, deadline, depth, rules, submit_forms)


def run_sweep(run_id: str, credentials: dict | None, settings: Settings | None = None,
              submit_forms: bool | None = None, validation_depth: str | None = None,
              test_actions: bool | None = None, fast_mode: bool | None = None) -> None:
    s = settings or get_settings()
    with SessionLocal() as db:
        repo = ExecutionRepository(db)
        try:
            _sweep(repo, run_id, credentials, s, s.exec_submit_forms if submit_forms is None else submit_forms,
                   validation_depth or s.exec_validation_depth,
                   s.exec_test_actions if test_actions is None else test_actions, bool(fast_mode))
        except Exception as e:
            repo.set_status(run_id, "failed", _short(e))


def _sweep(repo: ExecutionRepository, run_id: str, creds: dict | None, s: Settings,
           submit_forms: bool, depth: str = "basic", test_actions: bool = False, fast_mode: bool = False) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        repo.set_status(run_id, "failed", "Playwright is not installed. Run: pip install playwright")
        return
    run = repo.get_run(run_id)
    limit_s = run.max_minutes * 60 if run.max_minutes else s.exec_overall_timeout_s
    minutes = max(1, round(limit_s / 60))
    repo.begin(run_id, minutes)
    deadline = time.monotonic() + limit_s
    UI.pace_ms, UI.highlight = (0, False) if fast_mode else (s.exec_slow_mo_ms, True)
    timeout_ms = int(s.exec_page_timeout_s * 1000)
    shots = s.storage_dir / "runs" / run_id
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            args = ["--start-maximized"] if s.exec_headed else []
            browser = pw.chromium.launch(headless=not s.exec_headed, args=args)
        except Exception as e:
            missing = "executable doesn't exist" in str(e).lower()
            repo.set_status(run_id, "failed", NO_CHROMIUM if missing else _short(e))
            return
        try:
            ctx = browser.new_context() if not s.exec_headed else browser.new_context(no_viewport=True)
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)
            page.on("dialog", lambda d: d.dismiss())  # confirm()/alert() never block or confirm anything
            col = Collector(page)
            if creds:
                col.secrets.append(creds.get("password"))
            try:
                page.goto(run.base_url, wait_until="load")
            except Exception as e:
                repo.set_status(run_id, "failed", f"Could not open {run.base_url}: {_short(e)}")
                return
            settle(page)
            if creds:
                login_path = urlparse(page.url).path
                try:
                    _login(page, creds)
                    if (urlparse(page.url).path != login_path and page.url != run.base_url
                            and urlparse(run.base_url).path != login_path):
                        page.goto(run.base_url, wait_until="load")  # land on the page the user asked for
                        settle(page)
                except Exception:
                    repo.set_status(run_id, "failed", "Login failed")  # never include credentials
                    return
            start_url = page.url
            u = urlparse(start_url)
            menus = _discover(page, f"{u.scheme}://{u.netloc}")
            notes = []
            if not menus:
                if _has_password(page):
                    path = urlparse(page.url).path or "/"
                    repo.set_status(run_id, "failed", (
                        f"Still on the login page after signing in ({path}). Check the Username and Password."
                        if creds else f"The site asks for a login ({path}). Enter the Username and Password "
                                      "under Login (optional) and run again."))
                    return
                notes.append("No menus were found on this page (the menu may be built from elements this tool "
                             "does not recognise)")
            if len(menus) > s.max_menus:
                notes.append(f"Found {len(menus)} menus, visited the first {s.max_menus}")
                menus = menus[: s.max_menus]
            if submit_forms:
                notes.append(forms.MODAL_NOTE)
            if test_actions:
                notes.append(ACTIONS_NOTE)
            rules = []
            if submit_forms and depth != "basic":
                parse_repo = ParseRepository(repo.db)  # rules are read once, at execution start
                rules = [{"field": r.field, "valid": r.valid or [], "invalid": r.invalid or []}
                         for r in parse_repo.field_rules(run_id)]
                if not rules and not parse_repo.has_manual_cases(run_id):
                    notes.append("Manual rules were not available yet (manual parsing had not finished)")
            step_ids = repo.create_sweep(run_id, [(m["label"], m["href"]) for m in menus], "; ".join(notes) or None)
            form_state = {"tested": 0, "cases": 0, "jobs": []}
            try:
                for n, (menu, step_id) in enumerate(zip(menus, step_ids), 1):  # phase 1: breadth
                    if time.monotonic() > deadline:
                        raise forms.DeadlineExceeded()
                    _menu(page, repo, run_id, n, menu, step_id, start_url, col, timeout_ms, shots, submit_forms,
                          test_actions, creds, s, form_state, notes, deadline, depth, rules)
                active = list(form_state["jobs"])  # phase 2: depth, one case per form per round
                while active:
                    for job in list(active):
                        if time.monotonic() > deadline:
                            raise forms.DeadlineExceeded()
                        if job.cases is None:
                            cases.prepare(page, repo, job, s, form_state, notes, depth, rules)
                        if not job.finished:
                            cases.run_next(page, repo, job, col)
                        if job.finished:
                            active.remove(job)
            except forms.DeadlineExceeded:  # not a failure: finish gracefully, the rest stays pending
                skipped = sum(1 for j in form_state["jobs"] if j.cases is None)
                left = repo.pending_count(run_id) + skipped
                notes.append(f"Stopped at the time limit ({minutes} min); {left} checks were not run"
                             + (f" (validation cases for {skipped} forms were not started)" if skipped else ""))
            repo.set_note(run_id, "; ".join(notes) or None)
            repo.set_status(run_id, "done", None)
        finally:
            browser.close()


def main(argv: list[str]) -> int:
    run_id = argv[0]
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    run_sweep(run_id, data.get("credentials"), submit_forms=data.get("submit_forms"),
              validation_depth=data.get("validation_depth"), test_actions=data.get("test_actions"),
              fast_mode=data.get("fast_mode"))
    return 0
