"""Parsing helpers for TikTok URLs and identifiers."""
from __future__ import annotations

import re
from typing import Optional

TIKTOK_BASE = "https://www.tiktok.com"
URL_REGEX = r"(?<=\.com/)(.+?)(?=\?|$)"
VIDEO_ID_REGEX = r"(?<=/video/)([0-9]+)"


def normalize_username(username: str) -> str:
    return (username or "").strip().lstrip("@").strip()


def normalize_hashtag(hashtag: str) -> str:
    return (hashtag or "").strip().lstrip("#").strip()


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Return the numeric video ID from a TikTok URL or pass through if it already is one."""
    s = str(url_or_id or "")
    m = re.search(VIDEO_ID_REGEX, s)
    if m:
        return m.group(1)
    if s.isdigit():
        return s
    return None


def video_url(username: str, video_id: str) -> str:
    return f"{TIKTOK_BASE}/@{normalize_username(username)}/video/{video_id}"


def user_page_url(username: str) -> str:
    return f"{TIKTOK_BASE}/@{normalize_username(username)}"


def hashtag_page_url(hashtag: str) -> str:
    return f"{TIKTOK_BASE}/tag/{normalize_hashtag(hashtag)}"
