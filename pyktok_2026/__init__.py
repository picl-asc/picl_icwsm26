"""pyktok_2026 — no-login demo build.

A trimmed distribution of pyktok_2026 that exposes ONLY TikTok's three
no-login endpoint families:

  * **hashtag**  — videos from a `/tag/<hashtag>` page
  * **keyword**  — videos from TikTok's search bar
  * **sound**    — videos using a particular music ID

…plus the page-JSON reader used to discover hashtags / sound IDs from a
known video.

The full pyktok_2026 (with user archives, comments, related videos, etc.)
lives at github.com/picl-asc/pyktok_2026.
"""
from __future__ import annotations

__version__ = "0.3.0+nolog-only"

from .exceptions import (
    PyktokError,
    SetupRequired,
    SigningFailed,
)
from .facade import (
    close,
    # discovery helper
    get_tiktok_json,
    # hashtag
    get_hashtag_info,
    get_hashtag_videos,
    # keyword search
    search_videos,
    # sound
    get_sound_info,
    get_sound_videos,
    # helpers
    safe,
    set_verbosity,
    setup,
    specify_browser,
)

__all__ = [
    "__version__",
    # setup
    "specify_browser", "close", "set_verbosity", "setup",
    # discovery
    "get_tiktok_json",
    # hashtag
    "get_hashtag_info", "get_hashtag_videos",
    # keyword
    "search_videos",
    # sound
    "get_sound_info", "get_sound_videos",
    # nested-dict access helper
    "safe",
    # exceptions
    "PyktokError", "SetupRequired", "SigningFailed",
]
