"""APIEngine — no-login demo build.

Hidden-API client limited to TikTok's three no-login endpoint families:
hashtag (``/api/challenge/...``), keyword search (``/api/search/...``),
and music/sound (``/api/music/...``). The full pyktok_2026 ships many
more methods (user / comments / related / trending / playlist / etc.) —
those are intentionally removed here so testers see only the endpoints
that work without TikTok auth.

Browser-based signing (TikTok's own ``byted_acrawler.frontierSign``) and
in-page fetch are unchanged from the full build.
"""
from __future__ import annotations

import json
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, quote

from ._browser import BrowserSession
from ._csv import safe
from ._logging import get_logger
from ._signing import fetch_in_page, frontier_sign, wait_for_acrawler
from .exceptions import SigningFailed
from .targets import TIKTOK_BASE, normalize_hashtag

logger = get_logger("api")


# Intentionally minimal — full pyktok has user / comments / related / etc.
HIDDEN_API_ENDPOINTS = {
    "hashtag_detail":  "/api/challenge/detail/",
    "hashtag_videos":  "/api/challenge/item_list/",
    "search_general":  "/api/search/general/full/",
    "sound_detail":    "/api/music/detail/",
    "sound_videos":    "/api/music/item_list/",
}

# Magic blob TikTok's web search endpoint requires for the general-search route.
# Copied verbatim from the full build; same value the live website sends.
_WEB_SEARCH_CODE = (
    '{"tiktok":{"client_params_x":{"search_engine":'
    '{"ies_mt_user_live_video_card_use_libra":1,'
    '"mt_search_general_user_live_card":1}},"search_server":{}}}'
)


class APIEngine:
    """Sound/hashtag/search TikTok client. Browser-based signing, no login needed."""

    def __init__(self, session: BrowserSession):
        self.session = session
        self._base_params: Optional[Dict[str, str]] = None
        self._last_ok: Dict[str, Any] = {}

    # ---- session params (cached) ---------------------------------------
    def _ensure_base_params(self) -> Dict[str, str]:
        if self._base_params is not None:
            return self._base_params

        page = self.session.page

        def _js(expr: str, default: str = "") -> str:
            try:
                val = page.evaluate(f"() => ({expr})")
                return str(val) if val is not None else default
            except Exception:
                return default

        user_agent    = _js("navigator.userAgent",
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36")
        language      = _js("navigator.language || navigator.userLanguage", "en")
        platform      = _js("navigator.platform", "MacIntel")
        tz_name       = _js("Intl.DateTimeFormat().resolvedOptions().timeZone", "America/New_York")
        screen_height = _js("window.screen && window.screen.height", "1080")
        screen_width  = _js("window.screen && window.screen.width", "1920")

        # NOTE: from_page='user' is the most universally accepted default.
        # The hashtag endpoint specifically rejects from_page='challenge'
        # (statusCode=100002 in 2026); 'user' is what the original full build
        # uses for hashtag too. Search overrides this in its own call.
        self._base_params = {
            "aid":              "1988",
            "app_language":     language,
            "app_name":         "tiktok_web",
            "browser_language": language,
            "browser_name":     "Mozilla",
            "browser_online":   "true",
            "browser_platform": platform,
            "browser_version":  user_agent,
            "channel":          "tiktok_web",
            "cookie_enabled":   "true",
            "device_id":        str(random.randint(10**18, 10**19 - 1)),
            "device_platform":  "web_pc",
            "focus_state":      "true",
            "from_page":        "user",
            "history_len":      str(random.randint(1, 10)),
            "is_fullscreen":    "false",
            "is_page_visible":  "true",
            "language":         language,
            "os":               platform,
            "priority_region":  "",
            "referer":          "",
            "region":           "US",
            "screen_height":    screen_height,
            "screen_width":     screen_width,
            "tz_name":          tz_name,
            "webcast_language": language,
        }
        return self._base_params

    # ---- core fetch ----------------------------------------------------
    def fetch_api(self, endpoint_key: str, params: Dict[str, Any]) -> Optional[Dict]:
        """Sign and fetch one hidden-API request. Returns parsed JSON or None."""
        path = HIDDEN_API_ENDPOINTS[endpoint_key]
        base_url = TIKTOK_BASE + path

        if not wait_for_acrawler(self.session, attempts=5):
            logger.error("byted_acrawler never loaded; cannot sign requests")
            return None

        base_params = self._ensure_base_params()

        def _expected_keys(key: str) -> List[str]:
            if key == "hashtag_detail":  return ["challengeInfo"]
            if key == "search_general":  return ["data", "item_list", "itemList"]
            if key == "sound_detail":    return ["musicInfo", "music"]
            return ["itemList"]

        max_retries = 5
        sleep_range = (2.0, 4.0)

        for attempt in range(1, max_retries + 1):
            try:
                ms_token = self.session.get_ms_token() or ""
                merged = {**base_params, **params, "msToken": ms_token}

                query = urlencode(merged, safe="=", quote_via=quote)
                full_url = f"{base_url}?{query}"

                try:
                    x_bogus = frontier_sign(self.session, full_url)
                except SigningFailed as exc:
                    logger.warning("Signing failed: %s", exc)
                    x_bogus = ""

                signed_url = full_url + (f"&X-Bogus={x_bogus}" if x_bogus else "")
                result = fetch_in_page(self.session, signed_url)
                if result is None:
                    status, body = "?", ""
                else:
                    status, body = result
                logger.info("hidden_api %s -> HTTP %s, body length %d",
                            endpoint_key, status, len(body or ""))

                if not body or len(body) < 10:
                    if attempt < max_retries:
                        delay = random.uniform(*sleep_range)
                        logger.warning("[%s] empty body (attempt %d/%d). Sleeping %.1fs",
                                       endpoint_key, attempt, max_retries, delay)
                        time.sleep(delay)
                        continue
                    return None

                data = json.loads(body)

                if data.get("statusCode") == 0 or any(k in data for k in _expected_keys(endpoint_key)):
                    return data

                # Hashtag-specific block code (TikTok rejecting the call)
                if endpoint_key == "hashtag_videos" and data.get("statusCode") == 100002:
                    logger.warning("[%s] API blocked (statusCode=100002)", endpoint_key)
                    return None

                if attempt < max_retries:
                    delay = random.uniform(*sleep_range)
                    logger.warning("[%s] statusCode=%s (attempt %d/%d)",
                                   endpoint_key, data.get("statusCode"), attempt, max_retries)
                    time.sleep(delay)
                    continue
                return None

            except json.JSONDecodeError as exc:
                if attempt < max_retries:
                    time.sleep(random.uniform(*sleep_range))
                    continue
                logger.error("[%s] JSON decode failed: %s", endpoint_key, exc)
                return None
            except Exception as exc:
                if attempt < max_retries:
                    time.sleep(random.uniform(*sleep_range))
                    continue
                logger.error("[%s] fetch failed: %s", endpoint_key, exc)
                return None

        return None

    # ---- caches --------------------------------------------------------
    def _cache_set(self, key: str, value: Any) -> None:
        if value:
            self._last_ok[key] = value

    def _cache_get(self, key: str, default: Any = None) -> Any:
        return self._last_ok.get(key, default)

    # ---- hashtag endpoints --------------------------------------------
    def get_hashtag_info(self, hashtag: str) -> Optional[Dict]:
        """Return TikTok's challenge-detail JSON for a hashtag (challenge name)."""
        hashtag = normalize_hashtag(hashtag)
        resp = self.fetch_api("hashtag_detail", {"challengeName": hashtag})
        self._cache_set(f"hashtag_detail:{hashtag}", resp)
        return resp

    def get_hashtag_videos(self, hashtag: str, count: int = 30) -> List[Dict]:
        """Return up to `count` videos using the given hashtag.

        Two-step under the hood: hashtag_detail to resolve the challengeID,
        then hashtag_videos (with a warm-up navigation to /tag/<hashtag> so
        TikTok grants the same request context the live site uses).
        """
        hashtag = normalize_hashtag(hashtag)
        detail = self.fetch_api("hashtag_detail", {"challengeName": hashtag})
        if not detail:
            logger.warning("hashtag_detail unavailable for #%s", hashtag)
            return []
        challenge_id = safe(detail, "challengeInfo", "challenge", "id", default="")
        if not challenge_id:
            logger.warning("no challengeID for #%s", hashtag)
            return []

        # Warm-up: navigate to the hashtag's own page so TikTok serves the
        # request context expected by /api/challenge/item_list/.
        try:
            self.session.go(f"{TIKTOK_BASE}/tag/{hashtag}", wait=3.0)
        except Exception:
            pass

        videos: List[Dict] = []
        cursor = 0
        blocked = 0
        while len(videos) < count:
            resp = self.fetch_api("hashtag_videos", {
                "challengeID": challenge_id,
                "count":       30,
                "cursor":      cursor,
            })
            if not resp:
                blocked += 1
                if blocked > 3:
                    logger.warning("hashtag_videos blocked for #%s; giving up", hashtag)
                    break
                self._base_params = None
                try:
                    self.session.go(f"{TIKTOK_BASE}/tag/{hashtag}", wait=3.0)
                except Exception:
                    pass
                time.sleep(random.uniform(2, 4))
                continue

            blocked = 0
            for item in resp.get("itemList") or []:
                videos.append(item)
                if len(videos) >= count:
                    break
            if not resp.get("hasMore", False):
                break
            cursor = resp.get("cursor", 0)

        self._cache_set(f"hashtag_videos:{hashtag}", videos[:count])
        return videos[:count]

    # ---- search endpoint ----------------------------------------------
    def search_videos(self, keyword: str, count: int = 30) -> List[Dict]:
        """Return up to `count` videos matching a search keyword.

        Calls /api/search/general/full/ — the same endpoint that powers the
        web search bar. Returns video items.
        """
        def _extract(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for item in resp.get("item_list", []) or []:
                if isinstance(item, dict):
                    out.append(item)
            for item in resp.get("itemList") or []:
                if isinstance(item, dict):
                    out.append(item)
            for entry in resp.get("data", []) or []:
                if not isinstance(entry, dict):
                    continue
                cand = entry.get("item") or entry.get("item_info") or entry.get("itemInfo")
                if isinstance(cand, dict):
                    out.append(cand)
            return out

        videos: List[Dict] = []
        cursor = 0
        while len(videos) < count:
            resp = self.fetch_api("search_general", {
                "keyword":         keyword,
                "cursor":          cursor,
                "from_page":       "search",
                "web_search_code": _WEB_SEARCH_CODE,
            })
            if not resp:
                break
            for item in _extract(resp):
                videos.append(item)
                if len(videos) >= count:
                    break
            has_more = bool(resp.get("has_more", False) or resp.get("hasMore", False))
            if not has_more:
                break
            try:
                next_cursor = int(resp.get("cursor", 0))
            except Exception:
                break
            if next_cursor == cursor:
                break
            cursor = next_cursor

        self._cache_set(f"search_videos:{keyword}", videos[:count])
        return videos[:count]

    # ---- sound endpoints ----------------------------------------------
    def get_sound_info(self, sound_id: str) -> Optional[Dict]:
        resp = self.fetch_api("sound_detail", {"musicId": str(sound_id)})
        self._cache_set(f"sound_detail:{sound_id}", resp)
        return resp

    def get_sound_videos(self, sound_id: str, count: int = 30) -> List[Dict]:
        videos: List[Dict] = []
        cursor = 0
        while len(videos) < count:
            resp = self.fetch_api("sound_videos", {
                "musicID": str(sound_id), "count": 30, "cursor": cursor,
            })
            if not resp:
                break
            for item in resp.get("itemList") or []:
                videos.append(item)
                if len(videos) >= count:
                    break
            if not resp.get("hasMore", False):
                break
            cursor = resp.get("cursor", 0)
        self._cache_set(f"sound_videos:{sound_id}", videos[:count])
        return videos[:count]
