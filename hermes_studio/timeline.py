"""Timeline document: schema ``hs.timeline/1``, validator, canonical hash, OTIO export.

The engine is the only writer of ``timeline.json`` (docs/timeline.md has the full spec). This
module is pure: it validates a document, hashes its content, resolves anchored times, and
converts to and from OpenTimelineIO. It touches the disk only in :func:`write_otio`.

Times are integer ticks at ``TICK_RATE`` (705,600,000 per second, "flicks"), so the document
holds no floats at all: other fractional values (frame rates, speed, volume, crop) are reduced
rationals ``[num, den]``. The half-open overlap test and the per-track capability table are
modelled on OpenCut classic (MIT; see NOTICE).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any

from hermes_studio.api import HermesStudioError

SCHEMA_VERSION = "hs.timeline/1"
TICK_RATE = 705_600_000  # flicks: whole ticks per frame at 24, 25, 30, 60 and x/1.001 fps, and per 48 kHz sample
# OTIO keeps RationalTime values as doubles: every tick count up to this is exact in memory (~147 days).
# No tick value, resolved or derived end (e.g. a source range scaled by speed), rational component or
# version above it can pass validate(), so none can reach canonical_hash() or to_otio().
MAX_TICKS = 2**53

ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
# role -> (track id letter, item types the track holds, may its items overlap). Tracks are listed
# in ROLE_ORDER; within a role, text tracks go highest number first (top of the stack first, as in
# an NLE) and audio tracks lowest number first. V1 is the only video track.
ROLES: dict[str, tuple[str, frozenset[str], bool]] = {
    "text": ("T", frozenset({"text"}), True),
    "main": ("V", frozenset({"clip", "transition"}), False),
    "voice": ("A", frozenset({"clip", "transition"}), False),
    "music": ("A", frozenset({"clip", "transition"}), True),
}
ROLE_ORDER = ("text", "main", "voice", "music")
MAIN_TRACK = "V1"
ATTRIBUTION_KEYS = frozenset({"actor", "author", "created_by", "modified_by", "user", "owner"})

TOP_KEYS = {"schema_version", "id", "version", "tick_rate", "fps", "size", "media", "tracks", "markers"}
TOP_OPTIONAL = {"hash"}
MEDIA_KEYS = {"path", "dur", "fps"}
MEDIA_OPTIONAL = {"proxy"}
TRACK_KEYS = {"id", "role", "items"}
CLIP_KEYS = {"id", "type", "media", "src", "fade_in", "fade_out"}
TEXT_KEYS = {"id", "type", "dur", "text", "style", "fade_in", "fade_out"}
TIMED_OPTIONAL = {"at", "anchor", "split_from"}
CLIP_OPTIONAL = TIMED_OPTIONAL | {"props"}
TRANSITION_KEYS = {"id", "type", "kind", "between", "dur"}
MARKER_KEYS = {"id", "at", "label"}
ANCHOR_KEYS = {"to", "offset"}
PROP_KEYS = {"volume", "speed", "crop", "look"}
CROP_KEYS = {"x", "y", "w", "h"}
DEFAULT_PROPS: dict[str, Any] = {"volume": [1, 1], "speed": [1, 1], "crop": None, "look": None}
VOLUME_MAX = Fraction(4)
SPEED_MIN, SPEED_MAX = Fraction(1, 10), Fraction(10)
NOT_HASHED = ("version", "hash")

# Every rule id the validator can report (docs/timeline.md describes each).
RULES = (
    "not_object", "bad_schema", "bad_tick_rate", "missing_field", "unknown_field", "attribution_field",
    "wrong_type", "not_integer_ticks", "negative_time", "too_large", "bad_rational", "out_of_range",
    "not_nfc", "bad_id", "duplicate_id", "bad_track_id", "bad_track_role", "missing_main_track",
    "track_order", "item_not_allowed_on_track", "unknown_media", "src_out_of_media", "empty_range",
    "non_integer_duration", "fade_too_long", "at_and_anchor", "anchor_not_allowed",
    "anchor_target_missing", "anchor_target_not_main", "anchor_before_zero", "overlap",
    "bad_transition", "transition_overlap_mismatch", "bad_split_from", "bad_fps", "hash_mismatch",
)


@dataclass(frozen=True)
class Problem:
    rule: str
    path: str  # RFC 6901 JSON Pointer into the document ("" is the whole document)
    message: str
    id: str | None = None  # the track item or marker the problem is in, if any

    def as_dict(self) -> dict:
        d = {"rule": self.rule, "path": self.path, "message": self.message}
        if self.id is not None:
            d["id"] = self.id
        return d


class TimelineError(HermesStudioError):
    """An invalid timeline document. ``problems`` is what :func:`validate` returns (every problem
    found); ``rule``, ``path`` and ``id`` are the first one's, ``rules`` the sorted set of rule ids."""

    def __init__(self, problems: list[dict]) -> None:
        first = problems[0]
        super().__init__(f"{first['path'] or '/'}: {first['message']}", code="bad_input",
                         hint=_HINTS.get(first["rule"], ""))
        self.rule = first["rule"]
        self.path = first["path"]
        self.id = first.get("id")
        self.problems = problems
        self.rules = sorted({p["rule"] for p in problems})

    def as_dict(self) -> dict:
        d = super().as_dict()
        d["rule"] = self.rule
        d["path"] = self.path
        if self.id is not None:
            d["id"] = self.id
        d["problems"] = self.problems
        return d


def _j(base: str, *parts: Any) -> str:
    """Extend an RFC 6901 JSON Pointer: each part escaped (``~`` -> ``~0``, ``/`` -> ``~1``)."""
    return base + "".join("/" + str(x).replace("~", "~0").replace("/", "~1") for x in parts)


_HINTS = {
    "attribution_field": "Who made an edit lives in the op log, never in the timeline, so it can't change the hash.",
    "not_integer_ticks": f"Times are integer ticks at {TICK_RATE}/s; use timeline.seconds_to_ticks().",
    "bad_tick_rate": f"tick_rate must be {TICK_RATE} (flicks).",
    "bad_rational": "Write fractional values as a reduced [num, den] pair with den >= 1.",
    "not_nfc": "Normalize strings to Unicode NFC (unicodedata.normalize('NFC', s)).",
    "overlap": "Clips on main and voice tracks may only overlap through an xfade transition.",
    "anchor_not_allowed": "Only text items and clips on music tracks can be anchored.",
    "track_order": "List tracks as text, main, voice, music (text highest number first, audio lowest first).",
}


# --------------------------------------------------------------------------- time


def seconds_to_ticks(x: int | Fraction | Decimal | str | float) -> int:
    """Seconds to ticks. Exact for int, Fraction, Decimal and str ("19.15", "1001/30000"): raises
    ValueError if the value is not a whole number of ticks. A float is taken at its exact binary
    value and rounded half to even to the nearest tick."""
    if isinstance(x, bool):
        raise TypeError("seconds must be a number, not a bool")
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError("seconds must be finite")
        return round(Fraction(x) * TICK_RATE)  # Fraction rounds half to even
    if isinstance(x, (int, Fraction, Decimal)):
        f = Fraction(x)
    elif isinstance(x, str):
        f = Fraction(x.strip())
    else:
        raise TypeError(f"cannot convert {type(x).__name__} to ticks")
    t = f * TICK_RATE
    if t.denominator != 1:
        raise ValueError(f"{x} s is not a whole number of ticks")
    return int(t)


def seconds_to_ticks_nearest(x: int | Fraction | Decimal | float) -> tuple[int, Fraction]:
    """The nearest tick to ``x`` seconds, rounding an exact half to even, and the seconds that tick
    stands for: ``(ticks, Fraction(ticks, TICK_RATE))``. Takes int, Fraction, Decimal and float
    (a float at its exact binary value); negative values pass through. Raises TypeError for a
    bool, a str (even ``"1"``) or any other non-number, and ValueError for NaN or +-infinity."""
    if isinstance(x, bool) or not isinstance(x, (int, Fraction, Decimal, float)):
        raise TypeError(f"seconds must be an int, Fraction, Decimal or float, not {type(x).__name__}")
    if isinstance(x, (float, Decimal)) and not (math.isfinite(x) if isinstance(x, float) else x.is_finite()):
        raise ValueError("seconds must be finite")
    t = round(Fraction(x) * TICK_RATE)  # Fraction.__round__ rounds half to even
    return t, Fraction(t, TICK_RATE)


def ticks_to_seconds(t: int) -> Fraction:
    return Fraction(t, TICK_RATE)


def _rate(rate: int | Fraction | str | tuple | list) -> Fraction:
    if isinstance(rate, (tuple, list)):
        return Fraction(rate[0], rate[1])
    return Fraction(rate)


def ticks_per_frame(rate: int | Fraction | str | tuple | list) -> int:
    """Ticks in one frame (or sample) at ``rate`` per second; ValueError unless exact."""
    t = TICK_RATE / _rate(rate)
    if t.denominator != 1:
        raise ValueError(f"{rate} per second is not a whole number of ticks")
    return int(t)


def frames_to_ticks(frames: int, rate: int | Fraction | str | tuple | list) -> int:
    return frames * ticks_per_frame(rate)


def ticks_to_frames(t: int, rate: int | Fraction | str | tuple | list) -> Fraction:
    """Frames at ``rate``, as a Fraction (whole when ``t`` is on a frame boundary)."""
    return Fraction(t, ticks_per_frame(rate))


# --------------------------------------------------------------------------- validation


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _rational(v: Any) -> Fraction | None:
    if (isinstance(v, list) and len(v) == 2 and all(_is_int(n) for n in v) and v[1] >= 1
            and math.gcd(v[0], v[1]) == 1):
        return Fraction(v[0], v[1])
    return None


class _Checker:
    def __init__(self) -> None:
        self.problems: list[Problem] = []
        self.cur: str | None = None  # id of the track item or marker being checked

    def bad(self, rule: str, path: str, message: str) -> None:
        self.problems.append(Problem(rule, path, message, self.cur))

    def keys(self, obj: Any, path: str, required: set[str], optional: set[str] = frozenset()) -> bool:
        if not isinstance(obj, dict):
            self.bad("not_object", path, "must be an object")
            return False
        ok = True
        for k in sorted(set(obj) - required - optional, key=repr):  # keys may not be strings
            if k in ATTRIBUTION_KEYS:
                self.bad("attribution_field", _j(path, k), f"'{k}' is not allowed in a timeline")
            else:
                self.bad("unknown_field", _j(path, k), f"unknown field '{k}'")
            ok = False
        for k in sorted(required - set(obj)):
            self.bad("missing_field", _j(path, k), f"'{k}' is required")
            ok = False
        return ok

    def ticks(self, v: Any, path: str, *, positive: bool = False, signed: bool = False) -> bool:
        if not _is_int(v):
            self.bad("not_integer_ticks", path, f"must be an integer number of ticks, got {v!r}")
            return False
        if abs(v) > MAX_TICKS:
            self.bad("too_large", path, f"must be at most {MAX_TICKS} ticks")
            return False
        if not signed and v < 0:
            self.bad("negative_time", path, "must not be negative")
            return False
        if positive and v == 0:
            self.bad("empty_range", path, "must be greater than 0")
            return False
        return True

    def string(self, v: Any, path: str, *, empty: bool = False) -> bool:
        if not isinstance(v, str):
            self.bad("wrong_type", path, "must be a string")
            return False
        if not empty and not v:
            self.bad("wrong_type", path, "must not be empty")
            return False
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            self.bad("wrong_type", path, "must be valid Unicode text (no lone surrogates)")
            return False
        if unicodedata.normalize("NFC", v) != v:
            self.bad("not_nfc", path, "must be NFC-normalized Unicode")
            return False
        return True

    def ident(self, v: Any, path: str) -> bool:
        if not self.string(v, path):
            return False
        if not ID_RE.fullmatch(v):
            self.bad("bad_id", path, f"id {v!r} must match {ID_RE.pattern}")
            return False
        return True

    def ratio(self, v: Any, path: str, lo: Fraction | None = None, hi: Fraction | None = None,
              *, lo_open: bool = False) -> Fraction | None:
        f = _rational(v)
        if f is None:
            self.bad("bad_rational", path, f"must be a reduced [num, den] pair of integers, got {v!r}")
            return None
        if abs(v[0]) > MAX_TICKS or v[1] > MAX_TICKS:
            self.bad("out_of_range", path, f"each part of a [num, den] pair must be at most {MAX_TICKS}")
            return None
        if (lo is not None and (f < lo or (lo_open and f == lo))) or (hi is not None and f > hi):
            self.bad("out_of_range", path, f"{f} is out of range")
            return None
        return f


def _problems(doc: Any, *, check_hash: bool = True) -> list[Problem]:
    """Every rule the document breaks (an empty list means it is valid). A problem keeps its
    ``id`` only when that id names exactly one valid item: never for bad_id / duplicate_id
    (they rely on ``path``), nor for an item whose id is malformed or used twice in the doc."""
    found = _collect(doc, check_hash=check_hash)
    if not any(p.id is not None for p in found):
        return found
    seen: dict[str, int] = {}
    for i in _all_ids(doc):
        seen[i] = seen.get(i, 0) + 1

    def names_one(i: str) -> bool:
        return seen.get(i) == 1 and bool(ID_RE.fullmatch(i)) and unicodedata.normalize("NFC", i) == i

    return [p if p.id is None or (p.rule not in ("bad_id", "duplicate_id") and names_one(p.id))
            else Problem(p.rule, p.path, p.message) for p in found]


def _all_ids(doc: dict) -> list[str]:
    """Every id string in the doc: media keys, track ids, item ids, marker ids."""
    out: list[str] = []
    if isinstance(doc.get("media"), dict):
        out += [k for k in doc["media"] if isinstance(k, str)]
    for tr in doc.get("tracks") if isinstance(doc.get("tracks"), list) else []:
        if isinstance(tr, dict):
            out += [tr["id"]] if isinstance(tr.get("id"), str) else []
            for it in tr.get("items") if isinstance(tr.get("items"), list) else []:
                if isinstance(it, dict) and isinstance(it.get("id"), str):
                    out.append(it["id"])
    for mk in doc.get("markers") if isinstance(doc.get("markers"), list) else []:
        if isinstance(mk, dict) and isinstance(mk.get("id"), str):
            out.append(mk["id"])
    return out


def _collect(doc: Any, *, check_hash: bool) -> list[Problem]:
    c = _Checker()
    if not isinstance(doc, dict):
        c.bad("not_object", "", "a timeline must be a JSON object")
        return c.problems
    if doc.get("schema_version") != SCHEMA_VERSION:
        c.bad("bad_schema", "/schema_version", f"schema_version must be {SCHEMA_VERSION!r}")
        return c.problems
    if not _is_int(doc.get("tick_rate")) or doc["tick_rate"] != TICK_RATE:
        c.bad("bad_tick_rate", "/tick_rate", f"tick_rate must be {TICK_RATE}")
        return c.problems
    c.keys(doc, "", TOP_KEYS, TOP_OPTIONAL)
    if any(p.rule == "missing_field" for p in c.problems):
        return c.problems
    c.ident(doc["id"], "/id")
    if not _is_int(doc["version"]) or doc["version"] < 0:
        c.bad("wrong_type", "/version", "must be an integer >= 0")
    elif doc["version"] > MAX_TICKS:
        c.bad("out_of_range", "/version", f"must be at most {MAX_TICKS}")
    if "hash" in doc and not (isinstance(doc["hash"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", doc["hash"])):
        c.bad("wrong_type", "/hash", "must be 'sha256:' and 64 lowercase hex digits")
    fps = c.ratio(doc["fps"], "/fps", Fraction(0), lo_open=True)
    if fps is not None and (TICK_RATE / fps).denominator != 1:
        c.bad("bad_fps", "/fps", f"{fps} fps is not a whole number of ticks per frame")
    size = doc["size"]
    if not (isinstance(size, list) and len(size) == 2 and all(_is_int(n) and 0 < n <= 16384 for n in size)):
        c.bad("wrong_type", "/size", "must be [width, height], integers 1-16384")

    ids: dict[str, str] = {}

    def claim(i: str, path: str) -> None:
        if i in ids:
            c.bad("duplicate_id", path, f"id {i!r} is already used at {ids[i]}")
        else:
            ids[i] = path

    media = doc["media"]
    if not isinstance(media, dict):
        c.bad("not_object", "/media", "must be an object of id -> media")
        media = {}
    for mid, m in media.items():
        p = _j("", "media", mid)
        if c.ident(mid, p):
            claim(mid, p)
        if not c.keys(m, p, MEDIA_KEYS, MEDIA_OPTIONAL):
            continue
        c.string(m["path"], _j(p, "path"))
        c.ticks(m["dur"], _j(p, "dur"), positive=True)
        if m["fps"] is not None:
            c.ratio(m["fps"], _j(p, "fps"), Fraction(0), lo_open=True)
        if m.get("proxy") is not None:
            c.string(m["proxy"], _j(p, "proxy"))

    tracks = doc["tracks"]
    if not isinstance(tracks, list):
        c.bad("wrong_type", "/tracks", "must be a list")
        tracks = []
    items: dict[str, dict] = {}  # id -> {"item", "track", "role", "path"}
    seen: list[tuple[str, str]] = []
    for ti, tr in enumerate(tracks):
        tp = _j("", "tracks", ti)
        if not c.keys(tr, tp, TRACK_KEYS):
            continue
        role, tid = tr["role"], tr["id"]
        if not isinstance(role, str) or role not in ROLES:
            c.bad("bad_track_role", _j(tp, "role"), f"role must be one of {', '.join(ROLE_ORDER)}")
            continue
        if not c.ident(tid, _j(tp, "id")):
            continue
        letter, num = ROLES[role][0], tid[1:]
        if not (tid[:1] == letter and num.isdigit() and num[0] != "0"):
            c.bad("bad_track_id", _j(tp, "id"), f"a {role} track id is {letter}<n>, got {tid!r}")
            continue
        if (role == "main") != (tid == MAIN_TRACK):
            c.bad("bad_track_id", _j(tp, "id"), f"{MAIN_TRACK} is the main track, and the only one")
            continue
        claim(tid, tp)
        seen.append((role, tid))
        if not isinstance(tr["items"], list):
            c.bad("wrong_type", _j(tp, "items"), "must be a list")
            continue
        for ii, it in enumerate(tr["items"]):
            ip = _j(tp, "items", ii)
            c.cur = it.get("id") if isinstance(it, dict) and isinstance(it.get("id"), str) else None
            if not isinstance(it, dict):
                c.bad("not_object", ip, "must be an object")
                continue
            typ = it.get("type")
            if typ not in ("clip", "text", "transition"):
                c.bad("wrong_type", _j(ip, "type"), "type must be clip, text or transition")
                continue
            if typ not in ROLES[role][1]:
                c.bad("item_not_allowed_on_track", _j(ip, "type"), f"a {role} track can't hold a {typ}")
                continue
            if c.ident(it.get("id"), _j(ip, "id")):
                claim(it["id"], ip)
                items[it["id"]] = {"item": it, "track": tid, "role": role, "path": ip}
            _check_item(c, it, typ, role, ip, media)
        c.cur = None
    if ("main", MAIN_TRACK) not in seen:
        c.bad("missing_main_track", "/tracks", f"the main video track {MAIN_TRACK} is required")
    if seen != sorted(seen, key=_track_key):
        c.bad("track_order", "/tracks", "tracks must be listed as text, main, voice, music")

    markers = doc["markers"]
    if not isinstance(markers, list):
        c.bad("wrong_type", "/markers", "must be a list")
        markers = []
    for mi, mk in enumerate(markers):
        mp = _j("", "markers", mi)
        c.cur = mk.get("id") if isinstance(mk, dict) and isinstance(mk.get("id"), str) else None
        if not c.keys(mk, mp, MARKER_KEYS):
            continue
        if c.ident(mk["id"], _j(mp, "id")):
            claim(mk["id"], mp)
        c.ticks(mk["at"], _j(mp, "at"))
        c.string(mk["label"], _j(mp, "label"), empty=True)
    c.cur = None

    if not c.problems:
        _check_relations(c, doc, items)
        c.cur = None
    if not c.problems and check_hash and "hash" in doc and doc["hash"] != _hash(doc):
        c.bad("hash_mismatch", "/hash", "hash does not match the content")
    return c.problems


def _track_key(rt: tuple[str, str]) -> tuple[int, int]:
    role, tid = rt
    n = int(tid[1:])
    return ROLE_ORDER.index(role), (n if ROLES[role][0] == "A" else -n)


def _check_item(c: _Checker, it: dict, typ: str, role: str, ip: str, media: dict) -> None:
    if typ == "transition":
        if not c.keys(it, ip, TRANSITION_KEYS):
            return
        if it["kind"] != "xfade":
            c.bad("bad_transition", _j(ip, "kind"), "the only transition kind is 'xfade'")
        c.ticks(it["dur"], _j(ip, "dur"), positive=True)
        b = it["between"]
        if not (isinstance(b, list) and len(b) == 2 and all(isinstance(x, str) for x in b) and b[0] != b[1]):
            c.bad("bad_transition", _j(ip, "between"), "between must be two different clip ids")
        return
    if not c.keys(it, ip, CLIP_KEYS if typ == "clip" else TEXT_KEYS, CLIP_OPTIONAL if typ == "clip" else TIMED_OPTIONAL):
        return
    if ("at" in it) == ("anchor" in it):
        c.bad("at_and_anchor", ip, "give exactly one of 'at' or 'anchor'")
    elif "at" in it:
        c.ticks(it["at"], _j(ip, "at"))
    elif not (typ == "text" or role == "music"):
        c.bad("anchor_not_allowed", _j(ip, "anchor"), f"a {typ} on a {role} track can't be anchored")
    elif c.keys(it["anchor"], _j(ip, "anchor"), ANCHOR_KEYS):
        c.string(it["anchor"]["to"], _j(ip, "anchor", "to"))
        c.ticks(it["anchor"]["offset"], _j(ip, "anchor", "offset"), signed=True)
    if "split_from" in it and c.ident(it["split_from"], _j(ip, "split_from")) and it["split_from"] == it.get("id"):
        c.bad("bad_split_from", _j(ip, "split_from"), "an item can't be split from itself")
    dur = None
    if typ == "text":
        c.string(it["text"], _j(ip, "text"), empty=True)
        c.string(it["style"], _j(ip, "style"))
        if c.ticks(it["dur"], _j(ip, "dur"), positive=True):
            dur = it["dur"]
    else:
        speed: Fraction | None = Fraction(1)
        if "props" in it and c.keys(it["props"], _j(ip, "props"), set(), PROP_KEYS):
            pr = it["props"]
            if "volume" in pr:
                c.ratio(pr["volume"], _j(ip, "props", "volume"), Fraction(0), VOLUME_MAX)
            if "speed" in pr:
                speed = c.ratio(pr["speed"], _j(ip, "props", "speed"), SPEED_MIN, SPEED_MAX)
            if pr.get("crop") is not None and c.keys(pr["crop"], _j(ip, "props", "crop"), CROP_KEYS):
                cr = {k: c.ratio(pr["crop"][k], _j(ip, "props", "crop", k), Fraction(0), Fraction(1)) for k in "xywh"}
                if None not in cr.values() and (cr["w"] == 0 or cr["h"] == 0 or cr["x"] + cr["w"] > 1 or cr["y"] + cr["h"] > 1):
                    c.bad("out_of_range", _j(ip, "props", "crop"), "crop must be a non-empty box inside the frame")
            if pr.get("look") is not None:
                c.string(pr["look"], _j(ip, "props", "look"))
        mid, src = it["media"], it["src"]
        if not (isinstance(src, list) and len(src) == 2):
            c.bad("wrong_type", _j(ip, "src"), "src must be [in, out] in ticks")
        elif not (isinstance(mid, str) and mid in media):
            c.bad("unknown_media", _j(ip, "media"), f"no media {mid!r}")
        elif c.ticks(src[0], _j(ip, "src", 0)) and c.ticks(src[1], _j(ip, "src", 1)):
            mdur = media[mid].get("dur") if isinstance(media[mid], dict) else None
            if src[0] >= src[1]:
                c.bad("empty_range", _j(ip, "src"), "src in must be before src out")
            elif _is_int(mdur) and src[1] > mdur:
                c.bad("src_out_of_media", _j(ip, "src"), "src out is past the end of the media")
            elif speed is not None:
                d = Fraction(src[1] - src[0]) / speed
                if d.denominator != 1:
                    c.bad("non_integer_duration", _j(ip, "src"), "(out - in) / speed must be a whole number of ticks")
                elif d > MAX_TICKS:
                    c.bad("out_of_range", _j(ip, "src"), f"(out - in) / speed must be at most {MAX_TICKS} ticks")
                else:
                    dur = int(d)
    if dur is not None and _is_int(it.get("at")) and 0 <= it["at"] <= MAX_TICKS and it["at"] + dur > MAX_TICKS:
        c.bad("out_of_range", ip, f"the item must end by {MAX_TICKS} ticks")
    fi, fo = it["fade_in"], it["fade_out"]
    if c.ticks(fi, _j(ip, "fade_in")) and c.ticks(fo, _j(ip, "fade_out")) and dur is not None and fi + fo > dur:
        c.bad("fade_too_long", ip, "fade_in + fade_out must not exceed the item's duration")


def item_duration(item: dict) -> int:
    """Timeline duration in ticks of a valid clip, text or transition item."""
    if item["type"] in ("text", "transition"):
        return item["dur"]
    sp = item.get("props", {}).get("speed", [1, 1])
    return int(Fraction(item["src"][1] - item["src"][0]) * Fraction(sp[1], sp[0]))


def _check_relations(c: _Checker, doc: dict, items: dict[str, dict]) -> None:
    starts: dict[str, int] = {}
    for iid, rec in items.items():
        it = rec["item"]
        c.cur = iid
        if it["type"] == "transition":
            continue
        if "at" in it:
            starts[iid] = it["at"]
            continue
        a = it["anchor"]
        tgt = items.get(a["to"])
        if tgt is None:
            c.bad("anchor_target_missing", _j(rec['path'], "anchor", "to"), f"no item {a['to']!r}")
        elif tgt["track"] != MAIN_TRACK or tgt["item"]["type"] != "clip":
            c.bad("anchor_target_not_main", _j(rec['path'], "anchor", "to"), f"{a['to']!r} is not a clip on {MAIN_TRACK}")
        elif tgt["item"]["at"] + a["offset"] < 0:
            c.bad("anchor_before_zero", _j(rec['path'], "anchor"), "the anchored item would start before 0")
        elif tgt["item"]["at"] + a["offset"] + item_duration(it) > MAX_TICKS:
            c.bad("out_of_range", rec["path"], f"the anchored item must end by {MAX_TICKS} ticks")
        else:
            starts[iid] = tgt["item"]["at"] + a["offset"]
    if c.problems:
        return
    for tr in doc["tracks"]:
        timed = sorted((starts[i["id"]], i["id"]) for i in tr["items"] if i["type"] != "transition")
        order = [iid for _, iid in timed]
        span = {iid: (s, s + item_duration(items[iid]["item"])) for s, iid in timed}
        pairs: set[tuple[str, str]] = set()
        left: set[str] = set()
        right: set[str] = set()
        for it in tr["items"]:
            if it["type"] != "transition":
                continue
            ip = items[it["id"]]["path"]
            c.cur = it["id"]
            a, b = it["between"]
            if a not in span or b not in span:
                c.bad("bad_transition", _j(ip, "between"), f"both ids must be clips on {tr['id']}")
                continue
            if order.index(b) != order.index(a) + 1 or span[b][1] <= span[a][1]:
                c.bad("bad_transition", _j(ip, "between"), "between must be two consecutive clips, in timeline order")
                continue
            if a in left or b in right:
                c.bad("bad_transition", _j(ip, "between"), "a clip can start or end only one transition")
                continue
            left.add(a)
            right.add(b)
            if span[a][1] - span[b][0] != it["dur"] or it["dur"] > min(e - s for s, e in (span[a], span[b])):
                c.bad("transition_overlap_mismatch", _j(ip, "dur"),
                      "the clips must overlap by exactly the transition's dur, which must fit in both clips")
            pairs.add((a, b))
        if ROLES[tr["role"]][2]:
            continue
        for x, (_, i1) in enumerate(timed):
            for s2, i2 in timed[x + 1:]:
                # Half-open spans [start, end) overlap when each starts before the other ends.
                if s2 >= span[i1][1]:
                    break
                if (i1, i2) not in pairs:
                    c.cur = i2
                    c.bad("overlap", items[i2]["path"], f"{i2!r} overlaps {i1!r} on {tr['id']}")


def validate(doc: Any) -> list[dict]:
    """Every problem with ``doc`` as ``{rule, path, message, id?}``; empty when it is a valid
    hs.timeline/1 document. ``path`` is an RFC 6901 JSON Pointer; ``id`` names the track item or
    marker the problem is in. A stored ``hash`` must match the content."""
    return [p.as_dict() for p in _problems(doc)]


def validate_or_raise(doc: Any) -> dict:
    """Return ``doc`` if it is valid; raise TimelineError (carrying every problem) otherwise."""
    found = validate(doc)
    if found:
        raise TimelineError(found)
    return doc


def _raise_unless_valid(doc: Any, *, check_hash: bool) -> None:
    found = [p.as_dict() for p in _problems(doc, check_hash=check_hash)]
    if found:
        raise TimelineError(found)


# --------------------------------------------------------------------------- canonical form


def resolve(doc: dict) -> dict[str, tuple[int, int]]:
    """Absolute (start, end) ticks of every item in a valid doc. An anchored item starts at its
    V1 target's ``at`` + ``offset``, so it moves with that clip; a transition spans its overlap."""
    by_id = {it["id"]: it for tr in doc["tracks"] for it in tr["items"]}
    out: dict[str, tuple[int, int]] = {}
    for it in by_id.values():
        if it["type"] != "transition":
            s = it["at"] if "at" in it else by_id[it["anchor"]["to"]]["at"] + it["anchor"]["offset"]
            out[it["id"]] = (s, s + item_duration(it))
    for it in by_id.values():
        if it["type"] == "transition":
            s = out[it["between"][1]][0]
            out[it["id"]] = (s, s + it["dur"])
    return out


def normalize(doc: dict) -> dict:
    """A copy of a valid doc in canonical form: clip ``props`` filled with defaults, each track's
    items sorted by (start, id) (anchored items at their resolved start, a transition at the start
    of its overlap) and markers sorted by (at, id). Tracks keep their validated role order."""
    d = copy.deepcopy(doc)
    when = resolve(d)
    for tr in d["tracks"]:
        for it in tr["items"]:
            if it["type"] == "clip":
                it["props"] = {**DEFAULT_PROPS, **it.get("props", {})}
        tr["items"].sort(key=lambda it: (when[it["id"]][0], it["id"]))
    d["markers"].sort(key=lambda m: (m["at"], m["id"]))
    return d


def _canonical_bytes(doc: dict) -> bytes:
    body = {k: v for k, v in normalize(doc).items() if k not in NOT_HASHED}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(doc: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(doc)).hexdigest()


def canonical_json(doc: dict) -> bytes:
    """The bytes the hash covers: normalize(doc) without ``version`` and ``hash``, as UTF-8 JSON
    with sorted keys, separators (',', ':') and ensure_ascii=False. Raises TimelineError for any
    invalid doc, a stored ``hash`` that doesn't match (hash_mismatch) included."""
    _raise_unless_valid(doc, check_hash=True)
    return _canonical_bytes(doc)


def canonical_hash(doc: dict) -> str:
    """``sha256:<hex>`` of :func:`canonical_json`. Equal content gives an equal hash. Raises
    TimelineError for any invalid doc, hash_mismatch included; use :func:`stamp_hash` to set it."""
    return "sha256:" + hashlib.sha256(canonical_json(doc)).hexdigest()


def stamp_hash(doc: dict) -> tuple[dict, str]:
    """Validate everything except the stored-hash check, then return ``(copy with the correct
    hash set, that hash)``. This is how a document gets its ``hash`` before it is written."""
    _raise_unless_valid(doc, check_hash=False)
    h = _hash(doc)
    d = copy.deepcopy(doc)
    d["hash"] = h
    return d, h


def new_timeline(project_id: str, *, fps: tuple[int, int] = (30, 1), size: tuple[int, int] = (1080, 1920)) -> dict:
    """An empty document with Glyph's four tracks: T1 text, V1 main, A1 voice, A2 music."""
    return {
        "schema_version": SCHEMA_VERSION, "id": project_id, "version": 0, "tick_rate": TICK_RATE,
        "fps": list(fps), "size": list(size), "media": {},
        "tracks": [{"id": "T1", "role": "text", "items": []}, {"id": "V1", "role": "main", "items": []},
                   {"id": "A1", "role": "voice", "items": []}, {"id": "A2", "role": "music", "items": []}],
        "markers": [],
    }


# --------------------------------------------------------------------------- OpenTimelineIO

_META = "hermes_studio"
TEXT_GENERATOR = "hermes_studio.text"


def to_otio(doc: dict):
    """An ``opentimelineio.schema.Timeline`` for a valid doc; every time is
    ``RationalTime(ticks, TICK_RATE)``.

    Gaps (implied by ``at``) become Gap items. An xfade becomes a Transition at the start of the
    overlap (in_offset 0, out_offset dur) with the outgoing clip trimmed by dur. Text items are
    clips with a GeneratorReference. A track whose items may overlap (text, music) is split into
    lanes named ``T1``, ``T1.1``, .... What OTIO has no field for (fades, props, anchor,
    split_from, ids, media table) is kept in ``metadata["hermes_studio"]``, so :func:`from_otio`
    returns the same document."""
    import opentimelineio as otio

    validate_or_raise(doc)
    doc = normalize(doc)

    def rt(t: int):
        return otio.opentime.RationalTime(t, TICK_RATE)

    def rng(start: int, dur: int):
        return otio.opentime.TimeRange(rt(start), rt(dur))

    when = resolve(doc)
    tl = otio.schema.Timeline(name=doc["id"], global_start_time=rt(0))
    tl.metadata[_META] = {k: copy.deepcopy(doc[k]) for k in ("schema_version", "id", "version", "tick_rate", "fps", "size", "media")}
    if "hash" in doc:
        tl.metadata[_META]["hash"] = doc["hash"]
    for track in doc["tracks"]:
        kind = otio.schema.TrackKind.Audio if track["role"] in ("voice", "music") else otio.schema.TrackKind.Video
        into = {t["between"][1]: t for t in track["items"] if t["type"] == "transition"}
        outof = {t["between"][0]: t for t in track["items"] if t["type"] == "transition"}
        lanes: list[list[dict]] = []
        for it in (i for i in track["items"] if i["type"] != "transition"):
            for lane in lanes:
                last = lane[-1]["id"]
                if when[last][1] <= when[it["id"]][0] or outof.get(last, {}).get("between", [None, None])[1] == it["id"]:
                    lane.append(it)
                    break
            else:
                lanes.append([it])
        for ln, lane in enumerate(lanes or [[]]):
            ot = otio.schema.Track(name=track["id"] if ln == 0 else f"{track['id']}.{ln}", kind=kind)
            ot.metadata[_META] = {"id": track["id"], "role": track["role"], "lane": ln}
            pos = 0
            for it in lane:
                s, e = when[it["id"]]
                if it["id"] in into:
                    t = into[it["id"]]
                    x = otio.schema.Transition(name=t["id"], transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
                                               in_offset=rt(0), out_offset=rt(t["dur"]))
                    x.metadata[_META] = {"id": t["id"], "kind": t["kind"], "between": list(t["between"])}
                    ot.append(x)
                elif s > pos:
                    ot.append(otio.schema.Gap(source_range=rng(0, s - pos)))
                trim = outof[it["id"]]["dur"] if it["id"] in outof else 0
                meta = {k: copy.deepcopy(v) for k, v in it.items() if k not in ("at", "src", "dur", "media", "text", "style")}
                if it["type"] == "text":
                    ref = otio.schema.GeneratorReference(name=it["id"], generator_kind=TEXT_GENERATOR,
                                                         parameters={"text": it["text"], "style": it["style"]},
                                                         available_range=rng(0, it["dur"]))
                    clip = otio.schema.Clip(name=it["id"], media_reference=ref, source_range=rng(0, e - s - trim))
                else:
                    m = doc["media"][it["media"]]
                    ref = otio.schema.ExternalReference(target_url=m["path"], available_range=rng(0, m["dur"]))
                    ref.metadata[_META] = {"media": it["media"]}
                    clip = otio.schema.Clip(name=it["id"], media_reference=ref, source_range=rng(it["src"][0], e - s - trim))
                    sp = it["props"]["speed"]
                    if sp != [1, 1]:
                        clip.effects.append(otio.schema.LinearTimeWarp(name="speed", time_scalar=sp[0] / sp[1]))
                clip.metadata[_META] = meta
                ot.append(clip)
                pos = e - trim
            tl.tracks.append(ot)
    for mk in doc["markers"]:
        m = otio.schema.Marker(name=mk["label"], marked_range=rng(mk["at"], 0))
        m.metadata[_META] = {"id": mk["id"]}
        tl.tracks.markers.append(m)
    return tl


def _ticks(t) -> int:
    v = t.rescaled_to(TICK_RATE).value
    if v != int(v):
        raise ValueError(f"{t} is not a whole number of ticks")
    return int(v)


def _plain(v: Any) -> Any:
    """OTIO AnyDictionary / AnyVector to plain dict / list."""
    if isinstance(v, (str, bytes)):
        return v
    if hasattr(v, "items"):
        return {str(k): _plain(x) for k, x in v.items()}
    if hasattr(v, "__iter__"):
        return [_plain(x) for x in v]
    return v


def from_otio(tl) -> dict:
    """The document a :func:`to_otio` timeline came from, in :func:`normalize` form. Item times
    and durations are read from the OTIO ranges; the rest from ``metadata["hermes_studio"]``."""
    import opentimelineio as otio

    head = _plain(tl.metadata[_META])
    doc: dict[str, Any] = {k: head[k] for k in ("schema_version", "id", "version", "tick_rate", "fps", "size", "media")}
    if "hash" in head:
        doc["hash"] = head["hash"]
    doc["tracks"], doc["markers"] = [], []
    src_end: dict[str, Fraction] = {}
    for ot in tl.tracks:
        tm = _plain(ot.metadata[_META])
        if tm["lane"] == 0:
            doc["tracks"].append({"id": tm["id"], "role": tm["role"], "items": []})
        out = doc["tracks"][-1]["items"]
        pos = 0
        for child in ot:
            if isinstance(child, otio.schema.Gap):
                pos += _ticks(child.source_range.duration)
                continue
            if isinstance(child, otio.schema.Transition):
                xm = _plain(child.metadata[_META])
                t = {"id": xm["id"], "type": "transition", "kind": xm["kind"], "between": xm["between"],
                     "dur": _ticks(child.out_offset)}
                out.append(t)
                prev = next(i for i in out if i["id"] == t["between"][0])  # the outgoing clip, trimmed on export
                src_end[prev["id"]] += t["dur"] * Fraction(*prev["props"]["speed"])
                continue
            it = _plain(child.metadata[_META])
            dur = _ticks(child.source_range.duration)
            if "anchor" not in it:
                it["at"] = pos
            if isinstance(child.media_reference, otio.schema.GeneratorReference):
                it["dur"] = dur
                it["text"] = child.media_reference.parameters["text"]
                it["style"] = child.media_reference.parameters["style"]
            else:
                it["media"] = _plain(child.media_reference.metadata[_META])["media"]
                start = _ticks(child.source_range.start_time)
                it["src"] = [start, None]
                src_end[it["id"]] = start + dur * Fraction(*it["props"]["speed"])
            out.append(it)
            pos += dur
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["type"] == "clip":
                end = src_end[it["id"]]
                if end.denominator != 1:
                    raise ValueError(f"{it['id']}: source end is not a whole number of ticks")
                it["src"][1] = int(end)
    for mk in tl.tracks.markers:
        doc["markers"].append({"id": _plain(mk.metadata[_META])["id"], "at": _ticks(mk.marked_range.start_time),
                               "label": mk.name})
    return normalize(validate_or_raise(doc))


def write_otio(doc: dict, path: str) -> str:
    """Write ``doc`` as an .otio file (OTIO JSON) and return the path."""
    import opentimelineio as otio

    otio.adapters.write_to_file(to_otio(doc), str(path))
    return str(path)
