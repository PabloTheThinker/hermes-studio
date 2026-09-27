"""One way out to the network: JSON over http(s) only.

URLs for model endpoints can come from environment variables. urllib would happily
open file:// or ftp:// if one were set, which could leak local files into a request
or a log. Everything outbound goes through post_json / get_json, which refuse any
scheme but http and https and cap the response size.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

MAX_BYTES = 8 * 1024 * 1024  # model replies and oEmbed are tiny; refuse anything huge


class BlockedURL(ValueError):
    pass


def check_url(url: str) -> str:
    parts = urllib.parse.urlsplit(str(url or ""))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise BlockedURL(f"only http(s) URLs are allowed, got {parts.scheme or 'none'!r}")
    return url


def _open(req: urllib.request.Request, timeout: float) -> dict:
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - scheme checked above
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("response too large")
    return json.loads(raw.decode("utf-8"))


def post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 30) -> dict:
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(check_url(url), data=json.dumps(body).encode(), headers=h, method="POST")  # noqa: S310
    return _open(req, timeout)


def get_json(url: str, headers: dict | None = None, timeout: float = 10) -> dict:
    req = urllib.request.Request(check_url(url), headers=headers or {}, method="GET")  # noqa: S310
    return _open(req, timeout)
