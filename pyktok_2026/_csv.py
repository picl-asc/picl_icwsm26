"""Minimal helpers used by the sound-only demo build.

This is a stripped-down version. The full pyktok_2026 ships richer schema
helpers (DATA_COLUMNS, generate_data_row, deduplicate, …) — see the main
repo if you need them. Here we only need `safe()` and the page-JSON
extractors used by get_tiktok_json.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def safe(obj, *keys, default=""):
    """Walk nested dicts; return default if any key is missing."""
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k)
        else:
            return default
    return obj if obj is not None else default


def extract_page_json(html: str) -> Optional[Dict[str, Any]]:
    """Pull __UNIVERSAL_DATA_FOR_REHYDRATION__ (current) or SIGI_STATE (legacy)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for script_id in ("__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"):
        tag = soup.find("script", {"id": script_id})
        if tag and tag.string:
            try:
                return json.loads(tag.string)
            except json.JSONDecodeError:
                continue
    return None


def extract_video_struct(tt_json: Dict[str, Any]):
    """Return (video_id, itemStruct) from either current or legacy page JSON."""
    if "__DEFAULT_SCOPE__" in tt_json:
        vd = tt_json["__DEFAULT_SCOPE__"].get("webapp.video-detail", {})
        item_info = vd.get("itemInfo")
        if item_info is None:
            return None, None
        struct = item_info.get("itemStruct", {})
        return struct.get("id"), struct
    if "ItemModule" in tt_json and tt_json["ItemModule"]:
        vid_id = next(iter(tt_json["ItemModule"]))
        return vid_id, tt_json["ItemModule"][vid_id]
    return None, None
