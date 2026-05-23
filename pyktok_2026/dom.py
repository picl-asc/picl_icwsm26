"""DOMEngine — sound-only build.

Trimmed down to the single page-JSON read we need: pulling a video's
__UNIVERSAL_DATA_FOR_REHYDRATION__ blob so the demo can extract the sound
ID embedded in `item.music.id`.

The full pyktok_2026 DOMEngine has save_tiktok / save_tiktok_multi_urls /
multi-page scroll / DOM comments — all removed here.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ._browser import BrowserSession
from ._csv import extract_page_json
from ._logging import get_logger

logger = get_logger("dom")


class DOMEngine:
    """Browser-based TikTok page-JSON reader."""

    def __init__(self, session: BrowserSession):
        self.session = session

    def get_tiktok_json(self, video_url: str) -> Optional[Dict[str, Any]]:
        """Navigate to a TikTok video URL and return the page's rehydration JSON."""
        self.session.go(video_url, wait=2.0)
        tt_json = extract_page_json(self.session.page_source())
        if tt_json is None:
            logger.warning("No page JSON found at %s", video_url)
        return tt_json
