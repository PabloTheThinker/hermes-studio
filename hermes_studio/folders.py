"""Library folders by platform: YouTube, Twitch, Kick, X, TikTok … Local files, Other.

Layout: <library>/<Platform>/<Clear Title> [<job id>]/job.json
Unknown sites get their own folder named after the site, so every source has a home.
"""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from hermes_studio.net import get_json

HOSTS = [
    ("YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
    ("Twitch", ("twitch.tv",)),
    ("Kick", ("kick.com",)),
    ("X", ("x.com", "twitter.com")),
    ("TikTok", ("tiktok.com",)),
    ("Instagram", ("instagram.com",)),
    ("Facebook", ("facebook.com", "fb.watch")),
    ("Rumble", ("rumble.com",)),
    ("Vimeo", ("vimeo.com",)),
    ("Reddit", ("reddit.com", "redd.it")),
    ("Dailymotion", ("dailymotion.com", "dai.ly")),
    ("Bilibili", ("bilibili.com", "b23.tv")),
    ("SoundCloud", ("soundcloud.com",)),
    ("LinkedIn", ("linkedin.com",)),
    ("Loom", ("loom.com",)),
]
EXTRACTORS = {
    "youtube": "YouTube", "youtube:tab": "YouTube", "twitch:stream": "Twitch", "twitch:vod": "Twitch",
    "twitch:clips": "Twitch", "kick": "Kick", "kick:live": "Kick", "kick:vod": "Kick", "twitter": "X",
    "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook", "rumble": "Rumble",
    "vimeo": "Vimeo", "reddit": "Reddit", "x": "X",
}
LOCAL = "Local files"
FILE_HINT = re.compile(r"^(youtube|yt|twitch|kick|tiktok|x|twitter|instagram|rumble)[_\- ]", re.I)
YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _is_url(src: str) -> bool:
    return bool(re.match(r"^https?://", str(src or "").strip(), re.I))


def platform_of(src: str, extractor: str = "") -> str:
    """Folder name for a source. URLs by host, then yt-dlp extractor, local files by name hint."""
    src = str(src or "").strip()
    if _is_url(src):
        host = (urllib.parse.urlparse(src).hostname or "").lower().removeprefix("www.").removeprefix("m.")
        for name, hosts in HOSTS:
            if any(host == h or host.endswith("." + h) for h in hosts):
                return name
        ex = (extractor or "").lower()
        if ex in EXTRACTORS:
            return EXTRACTORS[ex]
        site = host.split(".")[-2] if host.count(".") >= 1 else host
        return site[:1].upper() + site[1:] if site else "Other"
    stem = Path(src).stem
    m = FILE_HINT.match(stem)
    if m:
        key = m.group(1).lower()
        return {"yt": "YouTube", "youtube": "YouTube", "twitter": "X", "x": "X", "tiktok": "TikTok"}.get(key, key.capitalize())
    # hermes-studio's own YouTube download cache: .../hermes-studio-<11-char id>/source.mp4
    parent = Path(src).parent.name
    if parent.startswith("hermes-studio-") and YT_ID.match(parent[len("hermes-studio-"):]):
        return "YouTube"
    return LOCAL


def youtube_id(src: str, title: str = "") -> str:
    """Best-effort YouTube id from a URL, a cache path or a filename."""
    s = str(src or "")
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    parent = Path(s).parent.name
    if parent.startswith("hermes-studio-") and YT_ID.match(parent[11:]):
        return parent[11:]
    m = re.match(r"^(?:youtube|yt)[_\- ]([A-Za-z0-9_-]{11})$", Path(s).stem, re.I)
    if m:
        return m.group(1)
    t = re.sub(r"-(fit|v\d+)$", "", title or "")
    return t if YT_ID.match(t) else ""


def youtube_title(video_id: str, timeout: float = 6.0) -> str:
    """Public oEmbed title. No key, no download. Empty on any failure."""
    if not video_id:
        return ""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={video_id}")
    try:
        return str(get_json(url, headers={"User-Agent": "hermes-studio"}, timeout=timeout).get("title") or "")
    except Exception:
        return ""


def pretty_title(title: str, src: str = "") -> str:
    """Human title: file stems lose underscores and platform prefixes."""
    t = str(title or "").strip()
    if not t or t == src or "/" in t:
        t = Path(src).stem if src else t
    t = FILE_HINT.sub("", t) if FILE_HINT.match(t) else t
    t = re.sub(r"[_]+", " ", t).strip()
    return t or "Untitled"


def folder_name(title: str, job_id: str) -> str:
    """Clear, filesystem-safe run folder: '<Title> [<id>]'."""
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or "").strip(" .")
    t = re.sub(r"\s+", " ", t)[:80].rstrip(" .") or "Untitled"
    return f"{t} [{job_id}]"
