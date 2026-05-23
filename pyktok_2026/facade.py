"""Module-level facade — public API of the sound-only build.

All functions live here and route to a singleton (DOMEngine, APIEngine) pair
that share one BrowserSession. The full pyktok_2026 exposes many more
endpoints; this build deliberately ships only the no-login sound demo
surface so a tester can't accidentally trip endpoints that need auth.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ._browser import BrowserSession
from ._csv import safe as _safe
from ._dispatcher import jupyter_safe, shutdown as _dispatcher_shutdown
from ._logging import get_logger, set_verbosity as _set_verbosity
from ._setup import setup as _setup
from .api import APIEngine
from .dom import DOMEngine
from .exceptions import SetupRequired


def safe(obj, *keys, default=""):
    """Walk a chain of dict keys and return ``default`` if any key is missing.

    Convenience helper re-exported so the demo notebook can read TikTok's
    deeply-nested JSON without reaching into internal modules.
    Example:
        pyk.safe(info, 'musicInfo', 'music', 'title')
    """
    return _safe(obj, *keys, default=default)

logger = get_logger("facade")


class _Pyk:
    """Holds the shared BrowserSession + DOMEngine + APIEngine."""

    def __init__(self, session: BrowserSession):
        self.session = session
        self.dom = DOMEngine(session)
        self.api = APIEngine(session)

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass


_pyk: Optional[_Pyk] = None


def _get_pyk() -> _Pyk:
    if _pyk is None:
        raise RuntimeError(
            "Call pyk.specify_browser('chrome') first before using any other function."
        )
    return _pyk


# ---- setup / teardown ----------------------------------------------------
@jupyter_safe
def specify_browser(
    browser: str = "chrome",
    *,
    headless: bool = True,
    login_if_needed: bool = False,
    data_dir: Optional[str] = None,
    engine: str = "chromium",
) -> None:
    """Initialise the module singleton.

    The sound-only build defaults to ``login_if_needed=False`` because none
    of its endpoints need auth. ``browser`` is accepted for API parity with
    the full build but is ignored (no cookie import path in this slim build).
    """
    global _pyk
    if _pyk is not None:
        _pyk.close()
        _pyk = None

    try:
        session = BrowserSession(
            data_dir=data_dir,
            headless=headless,
            login_if_needed=login_if_needed,
            cookie_browser=None,    # no auth path in sound-only build
            engine=engine,
        ).launch()
    except SetupRequired:
        _setup()
        session = BrowserSession(
            data_dir=data_dir,
            headless=headless,
            login_if_needed=login_if_needed,
            cookie_browser=None,
            engine=engine,
        ).launch()

    _pyk = _Pyk(session)


@jupyter_safe
def close() -> None:
    global _pyk
    if _pyk is not None:
        _pyk.close()
        _pyk = None
    # The dispatcher worker thread is intentionally left alive; Python's
    # atexit cleans it up at interpreter shutdown.


@jupyter_safe
def set_verbosity(level) -> None:
    _set_verbosity(level)


@jupyter_safe
def setup() -> None:
    _setup()


# ---- the endpoints this build exposes -----------------------------------
@jupyter_safe
def get_tiktok_json(video_url: str):
    """Fetch a video page and return its __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON.

    Used in the demo to discover hashtags / sound IDs from a known video
    (``item.textExtra`` / ``item.music.id``). No login required.
    """
    return _get_pyk().dom.get_tiktok_json(video_url)


# ---- hashtag -------------------------------------------------------------
@jupyter_safe
def get_hashtag_info(hashtag: str) -> Optional[Dict]:
    """Return TikTok challenge-detail JSON for a hashtag. No login required."""
    return _get_pyk().api.get_hashtag_info(hashtag)


@jupyter_safe
def get_hashtag_videos(hashtag: str, count: int = 30) -> List[Dict]:
    """Return up to `count` videos using the given hashtag. No login required.

    Routes through `/api/challenge/...` after a warm-up nav to
    `/tag/<hashtag>` (which is what the live website does).
    """
    return _get_pyk().api.get_hashtag_videos(hashtag, count)


# ---- keyword search ------------------------------------------------------
@jupyter_safe
def search_videos(keyword: str, count: int = 30) -> List[Dict]:
    """Return up to `count` videos matching a search keyword. No login required.

    Routes through `/api/search/general/full/` — the endpoint that powers
    the web search bar.
    """
    return _get_pyk().api.search_videos(keyword, count)


# ---- sound ---------------------------------------------------------------
@jupyter_safe
def get_sound_info(sound_id: str) -> Optional[Dict]:
    """Return TikTok music-detail JSON for a sound ID. No login required."""
    return _get_pyk().api.get_sound_info(sound_id)


@jupyter_safe
def get_sound_videos(sound_id: str, count: int = 30) -> List[Dict]:
    """Return up to `count` videos using the given sound ID. No login required."""
    return _get_pyk().api.get_sound_videos(sound_id, count)
