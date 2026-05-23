"""Playwright wrapper with a persistent on-disk context.

One BrowserSession is shared by DOMEngine and APIEngine. The persistent context
lives at ~/.pyktok_2026/browser_data/ so cookies survive across runs. Three
paths to a logged-in session, in order: persistent context → browser_cookie3
import → interactive headed login.
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import SetupRequired
from ._logging import get_logger
from .targets import TIKTOK_BASE

logger = get_logger("browser")

# Cookies that indicate a real logged-in TikTok session.
# NOTE: tt_chain_token, ttwid, msToken, _ttp all get set for logged-out
# visitors too, so they are NOT included here.
_AUTH_COOKIE_NAMES = {
    "sessionid", "sessionid_ss", "sid_tt", "sid_guard",
    "ssid_ucp_v1", "uid_tt", "passport_csrf_token",
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_DATA_DIR = Path.home() / ".pyktok_2026" / "browser_data"
DEFAULT_STATE_FILE = Path.home() / ".pyktok_2026" / "state.json"


def _has_auth_cookies(cookies) -> bool:
    names = {c["name"] for c in cookies}
    return bool(names & _AUTH_COOKIE_NAMES)


def save_storage_state(context, path: Path) -> None:
    """Dump context cookies + localStorage to a JSON file. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))


class BrowserSession:
    """Playwright Chromium context with auth handling via storage_state.

    Auth flow (each is tried in order; first hit wins):
      1. ``state.json`` (Playwright storage_state) exists and has TikTok auth cookies
      2. ``browser_cookie3.<name>(domain_name='.tiktok.com')`` returns auth cookies
      3. Interactive headed login (if ``login_if_needed=True``)

    On every successful login we write ``state.json`` so future runs skip
    the interactive flow entirely.
    """

    def __init__(
        self,
        data_dir: Optional[os.PathLike] = None,
        state_file: Optional[os.PathLike] = None,
        headless: bool = True,
        login_if_needed: bool = True,
        login_timeout: int = 300,
        cookie_browser: Optional[str] = "chrome",
        engine: str = "chromium",
    ):
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.state_file = Path(state_file) if state_file else DEFAULT_STATE_FILE
        self.headless = headless
        self.login_if_needed = login_if_needed
        self.login_timeout = login_timeout
        self.cookie_browser = cookie_browser
        self.engine = engine if engine in ("chromium", "webkit", "firefox") else "chromium"

        self._pw = None
        self._context = None
        self._page = None
        self.auth_username: Optional[str] = None
        self.auth_path: str = "none"  # "state_file" / "browser_cookie3" / "interactive" / "none"

    # --- lifecycle -----------------------------------------------------
    def launch(self) -> "BrowserSession":
        self._start_runtime_context()
        self._establish_auth()
        return self

    def _start_runtime_context(self) -> None:
        """Launch the headless Chromium for normal runtime use."""
        from playwright.sync_api import sync_playwright
        try:
            from playwright._impl._errors import Error as PWError  # type: ignore
        except Exception:
            PWError = Exception  # type: ignore

        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self._pw is None:
            self._pw = sync_playwright().start()

        # Chromium / Firefox accept Chromium-style command-line flags; WebKit
        # ignores them. We only pass them when applicable.
        # NOTE: --no-sandbox / --disable-dev-shm-usage are Docker/Linux-only
        # hardening flags. On macOS they trigger an "unsupported command-line
        # flag" banner that TikTok can use as a bot signal. Drop them on
        # non-Linux platforms.
        # Chromium shows a "You are using an unsupported command-line flag"
        # banner for flags on its hardcoded list — including
        # --disable-blink-features=AutomationControlled, --no-sandbox, etc.
        # TikTok's bot detection uses this banner's appearance as one signal.
        # Strip --enable-automation via ignore_default_args (below) and DON'T
        # add any of these flags here. On Linux we have to keep --no-sandbox
        # for container/CI environments, but on macOS / Windows we don't.
        import platform as _platform
        _chromium_args = []
        if _platform.system() == "Linux":
            _chromium_args += ["--no-sandbox", "--disable-dev-shm-usage"]
        # Playwright's default args include `--enable-automation`, which
        # makes Chromium show the "Chrome is being controlled by automated
        # test software" banner AND sets navigator.webdriver=true. TikTok
        # uses both signals for bot detection. Strip them via
        # ignore_default_args.
        _ignore_defaults = [
            "--enable-automation",
            "--enable-blink-features=IdleDetection",
            "--no-sandbox",                 # strip if Playwright adds it
            "--disable-dev-shm-usage",      # strip if Playwright adds it
        ]
        launch_args = dict(
            user_data_dir=str(self.data_dir),
            headless=self.headless,
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
        )
        if self.engine == "webkit":
            engine_obj = self._pw.webkit
            engine_label = "WebKit"
        elif self.engine == "firefox":
            engine_obj = self._pw.firefox
            launch_args["args"] = _chromium_args
            engine_label = "Firefox"
        else:
            engine_obj = self._pw.chromium
            launch_args["args"] = _chromium_args
            launch_args["ignore_default_args"] = _ignore_defaults
            engine_label = "Chromium"

        try:
            self._context = engine_obj.launch_persistent_context(**launch_args)
        except PWError as exc:  # type: ignore
            msg = str(exc)
            if "Executable doesn't exist" in msg or "browserType.launch" in msg:
                self._pw.stop()
                self._pw = None
                raise SetupRequired(
                    f"Playwright's {engine_label} binary is missing. "
                    f"Run: playwright install {self.engine}"
                ) from exc
            raise

        self._context.add_init_script(_STEALTH_INIT)

        # If state.json exists, seed our cookies from it (storage_state is the
        # only thing that reliably round-trips TikTok auth across runs).
        self._load_state_file_into_context()

        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()
        self._page.set_default_navigation_timeout(45000)
        self._page.set_default_timeout(30000)

        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(self._page)
        except Exception as exc:
            logger.debug("playwright_stealth not applied: %s", exc)

    def _load_state_file_into_context(self) -> None:
        """If state.json exists, inject its cookies/localStorage into the live context."""
        if not self.state_file.exists():
            return
        try:
            import json as _json
            state = _json.loads(self.state_file.read_text())
            cookies = state.get("cookies") or []
            if cookies:
                self._context.add_cookies(cookies)
                logger.debug("Loaded %d cookies from %s", len(cookies), self.state_file)
        except Exception as exc:
            logger.warning("Could not load %s: %s", self.state_file, exc)

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        self._context = None
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._page = None

    def __enter__(self):
        return self.launch()

    def __exit__(self, *_):
        self.close()

    # --- auth ----------------------------------------------------------
    def _establish_auth(self) -> None:
        # 1. state.json was loaded in _start_runtime_context — check it took
        if self.has_auth():
            u = self.current_username() or "?"
            self.auth_path = "state_file"
            self.auth_username = u
            logger.warning("Resumed login as @%s (from %s)", u, self.state_file.name)
            return

        # 2. browser_cookie3 fallback
        if self.cookie_browser:
            try:
                if self._seed_from_browser_cookie3(self.cookie_browser):
                    if self.has_auth():
                        u = self.current_username() or "?"
                        self.auth_path = "browser_cookie3"
                        self.auth_username = u
                        logger.warning("Imported login from system %s as @%s",
                                       self.cookie_browser, u)
                        # Persist for next run
                        try:
                            save_storage_state(self._context, self.state_file)
                        except Exception as exc:
                            logger.debug("Could not save state file: %s", exc)
                        return
            except Exception as exc:
                logger.debug("browser_cookie3 import failed: %s", exc)

        # 3. Interactive headed login
        if self.login_if_needed:
            self._interactive_login()
            if self.has_auth():
                u = self.current_username() or "?"
                self.auth_path = "interactive"
                self.auth_username = u
                logger.warning("Interactive login completed as @%s; saved to %s",
                               u, self.state_file)
                return

        logger.warning(
            "No TikTok auth cookies found. DOM mode will return empty for "
            "restricted profiles; API mode mostly works without login."
        )

    def has_auth(self) -> bool:
        try:
            cookies = self._context.cookies()
        except Exception:
            return False
        # Only count cookies on tiktok.com (or its subdomains)
        tt = [c for c in cookies if "tiktok" in c.get("domain", "")]
        return _has_auth_cookies(tt)

    def current_username(self) -> Optional[str]:
        """Return @username of the logged-in user, or None."""
        try:
            self.go(TIKTOK_BASE, wait=1.5)
            html = self._page.content()
        except Exception:
            return None
        from ._csv import extract_page_json, safe
        js = extract_page_json(html)
        if not js:
            return None
        u = safe(js, "__DEFAULT_SCOPE__", "webapp.app-context", "user", "uniqueId", default="")
        return u or None

    def _seed_from_browser_cookie3(self, browser_name: str) -> bool:
        """Pull cookies for .tiktok.com from system Chrome (or other supported browser)
        into the persistent context. Returns True if any cookies were injected."""
        import browser_cookie3
        getter = getattr(browser_cookie3, browser_name, None)
        if getter is None:
            return False
        jar = getter(domain_name=".tiktok.com")
        cookies_to_add: List[Dict[str, Any]] = []
        for c in jar:
            if not c.value:
                continue
            cookie: Dict[str, Any] = {
                "name": c.name,
                "value": c.value,
                "domain": c.domain or ".tiktok.com",
                "path": c.path or "/",
            }
            if c.expires:
                try:
                    cookie["expires"] = float(c.expires)
                except Exception:
                    pass
            cookie["secure"] = bool(getattr(c, "secure", False))
            cookies_to_add.append(cookie)
        if not cookies_to_add:
            return False
        try:
            self._context.add_cookies(cookies_to_add)
        except Exception as exc:
            logger.debug("add_cookies failed: %s", exc)
            return False
        return True

    def _interactive_login(self) -> None:
        """Open a headed browser, wait for the user to log in, save state.json,
        then re-seed the runtime context.

        We use a SEPARATE non-persistent context (different data_dir under
        a temp suffix) so the user can complete OAuth without races with the
        headless runtime profile. After login we explicitly export
        ``storage_state`` to disk — that's the only reliable persistence path."""
        _label = {"webkit": "WebKit", "firefox": "Firefox"}.get(self.engine, "Chromium")
        logger.warning(
            "Opening visible %s for TikTok login. "
            "Sign in with Google / email / phone / QR within %d seconds. "
            "Window closes automatically once auth cookies appear.",
            _label, self.login_timeout,
        )

        # Reuse the existing playwright handle (we can't start a second
        # sync_playwright in the same thread). Tear down the runtime context
        # so its user_data_dir lock is released — Playwright errors if two
        # Chromiums share the same dir.
        had_runtime = self._context is not None
        if had_runtime:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()

        import tempfile
        login_dir = Path(tempfile.mkdtemp(prefix="pyktok_login_"))
        # Use the same engine for login so cookies are written by the same
        # browser that the runtime context will later read them with.
        # Match the runtime context: no banner-triggering flags for the
        # headed login window either. Strip --enable-automation by default.
        if self.engine == "webkit":
            login_engine = self._pw.webkit
            login_kwargs = {}
        elif self.engine == "firefox":
            login_engine = self._pw.firefox
            login_kwargs = {}
        else:
            login_engine = self._pw.chromium
            login_kwargs = {
                "ignore_default_args": [
                    "--enable-automation",
                    "--enable-blink-features=IdleDetection",
                ],
            }
        try:
            login_ctx = login_engine.launch_persistent_context(
                user_data_dir=str(login_dir),
                headless=False,
                user_agent=_USER_AGENT,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York",
                **login_kwargs,
            )
            page = login_ctx.pages[0] if login_ctx.pages else login_ctx.new_page()
            try:
                page.goto(f"{TIKTOK_BASE}/login", wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                logger.debug("login page goto error (continuing): %s", exc)

            self._wait_for_auth(login_ctx)

            try:
                save_storage_state(login_ctx, self.state_file)
                logger.warning("Saved auth state to %s", self.state_file)
            except Exception as exc:
                logger.error("Could not save state file: %s", exc)

            try:
                login_ctx.close()
            except Exception:
                pass
        finally:
            try:
                import shutil
                shutil.rmtree(login_dir, ignore_errors=True)
            except Exception:
                pass

        # Fully tear down the Playwright instance after the login dance so
        # no orphan cleanup callbacks fire on greenlets we no longer hold.
        # Without this we get noisy "Cannot switch to a different thread"
        # callback errors after the second context teardown.
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

        # Re-launch the runtime context (fresh playwright) if we had one before
        if had_runtime:
            self._start_runtime_context()

    def _wait_for_auth(self, context) -> bool:
        deadline = time.time() + self.login_timeout
        while time.time() < deadline:
            try:
                cookies = context.cookies()
                if _has_auth_cookies(cookies):
                    # Settle: give a few seconds for additional cookies / localStorage
                    # to land after the redirect.
                    time.sleep(3)
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    # --- navigation ----------------------------------------------------
    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    def go(self, url: str, wait: float = 2.0) -> None:
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            logger.debug("goto(%s) raised %s — continuing", url, type(exc).__name__)
        # Simple sleep is more reliable than networkidle for TikTok — many of
        # TikTok's pages keep analytics/beacon connections open indefinitely,
        # so networkidle would always burn the full timeout and slow us down.
        if wait:
            time.sleep(wait + random.uniform(0.0, 0.6))
        # Small human-like mouse jitter (per davidteather/TikTok-Api pattern).
        try:
            self._page.mouse.move(random.randint(10, 300), random.randint(10, 300))
        except Exception:
            pass

    def page_source(self) -> str:
        try:
            return self._page.content()
        except Exception:
            return ""

    def get_ms_token(self) -> Optional[str]:
        try:
            cookies = self._context.cookies("https://www.tiktok.com")
        except Exception:
            return None
        for c in cookies:
            if c["name"] == "msToken":
                return c["value"]
        return None

    # ---------------- JS evaluation helpers ----------------
    def eval_js(self, expr: str, *args):
        return self._page.evaluate(expr, *args) if args else self._page.evaluate(expr)


# ---------------------------------------------------------------------------
# Stealth init script applied to every new document in the context
# ---------------------------------------------------------------------------
_STEALTH_INIT = """
(function(){
    try { Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined }); } catch(e){}
    if(!window.chrome){ window.chrome = {}; }
    if(!window.chrome.runtime){
        window.chrome.runtime = { id: undefined, connect: null, sendMessage: null };
    }
    try {
        const nd = Object.getPrototypeOf(navigator);
        Object.defineProperty(nd,'languages',{get:()=>['en-US','en']});
        Object.defineProperty(nd,'platform',{get:()=>'MacIntel'});
        Object.defineProperty(nd,'vendor',{get:()=>'Google Inc.'});
    } catch(e){}
    try {
        const gp = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p){
            if(p===37445) return 'Intel Inc.';
            if(p===37446) return 'Intel Iris OpenGL Engine';
            return gp.apply(this, arguments);
        };
    } catch(e){}
})();
"""
