"""JSON-RPC message parsing shared by stdio /mcp, HTTP /mcp and the REST body reader (D27).

One :func:`parse_message` for every framing: a body that isn't UTF-8 JSON (bad UTF-8, bad
JSON, an integer past Python's digit limit, nesting too deep) is a parse error, answered with
``-32700`` and ``id: null``; it never raises. One :func:`content_length` check for stdio and
HTTP: ASCII digits only, at most 8 of them, the value never handed to ``int()`` otherwise.
"""

from __future__ import annotations

import json
import re
from typing import Any

from hermes_studio.studio import MAX_BODY  # the one cap (studio.py:38); never a second copy

DRAIN_MAX = 16 * MAX_BODY  # over-cap bodies up to this size are drained; larger ones close the session
DRAIN_CHUNK = 64 * 1024
MAX_DIGITS = 8
_DIGITS = re.compile(rb"[0-9]+")

PARSE_ERROR = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
INVALID_REQUEST = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}


class _ParseFailed(Exception):
    pass


def parse_message(raw: bytes) -> tuple[bool, Any]:
    """``(True, value)`` for a body that parses as UTF-8 JSON, else ``(False, None)``."""
    try:
        return True, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return False, None


def content_length(value: bytes) -> tuple[int | None, str]:
    """The length a ``Content-Length`` value gives, or ``(None, reason)``. The value is the
    text after the colon with surrounding spaces and tabs stripped (only those). It must be
    ASCII digits (``re.fullmatch``, so a trailing CR, LF, VT or FF fails) and at most 8 of them,
    counted as digits, not by value: ``000000007`` fails. ``int()`` only sees what passes."""
    v = value.strip(b" \t")
    if not _DIGITS.fullmatch(v):
        return None, "malformed Content-Length value"
    if len(v) > MAX_DIGITS:
        return None, f"Content-Length has more than {MAX_DIGITS} digits"
    return int(v), ""


def dumps(msg: Any) -> bytes:
    """Protocol output: ASCII-only JSON (D17), so a lone surrogate can never stop a reply."""
    return json.dumps(msg, ensure_ascii=True, default=str).encode("ascii")
