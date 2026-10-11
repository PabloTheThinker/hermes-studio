"""Desk Edit page store. The op log is the only writer (docs/oplog.md).

A project is a folder: base.json (version 0), oplog.jsonl, timeline.json (the current doc).
The desk and tests call open / apply / undo / redo. Nothing else writes the timeline.
"""

from __future__ import annotations

import copy
import contextlib
import json
import math
import os
import secrets
import shutil
import subprocess
import threading
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from hermes_studio import grade as _GR
from hermes_studio import oplog as O
from hermes_studio import transitions as _XT
from hermes_studio import timeline as T

HUMAN = O.Session(O.Actor("human", "pablo"))


class EditorError(Exception):
    pass


def root() -> Path:
    return Path(os.environ.get("HERMES_STUDIO_EDITOR") or Path.home() / ".hermes" / "hermes-studio" / "editor")


def _dir(pid: str) -> Path:
    if not T.ID_RE.fullmatch(pid or ""):
        raise EditorError("bad project id")
    return root() / pid


def _cid() -> str:
    return "e" + secrets.token_hex(8)


def _pair_to_float(v: object) -> float:
    """A schema ratio stored as a reduced [num, den] pair, back to a float. A bare number or
    anything unrecognised falls back to 1.0 (full level / real time)."""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        try:
            num, den = float(v[0]), float(v[1])
            if den != 0:
                return num / den
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return 1.0


def _crop_view(v: object) -> dict | None:
    """props.crop is {x, y, w, h} as [num, den] pairs; the page wants plain floats. Returns
    None when there is no crop, so the inspector can tell 'no crop' from a full-frame one."""
    if not isinstance(v, dict):
        return None
    out = {}
    for k in ("x", "y", "w", "h"):
        if k not in v:
            return None
        out[k] = round(_pair_to_float(v[k]), 4)
    return out


def _transform_view(v: object) -> dict | None:
    """props.transform is {x, y, scale, rotate} as [num, den] pairs; the page wants plain
    floats. None when there is no transform."""
    if not isinstance(v, dict):
        return None
    out = {}
    for k in ("x", "y", "scale", "rotate"):
        if k not in v:
            return None
        out[k] = round(_pair_to_float(v[k]), 4)
    return out


def _keyframes_view(v: object, rate: int) -> list[dict] | None:
    """props.keyframes is a list of {at, x, y, scale, rotate} as [num, den] pairs; the page
    wants plain floats with `at` in seconds from the clip start. None when there are none."""
    if not isinstance(v, list) or not v:
        return None
    out = []
    for kf in v:
        if not isinstance(kf, dict) or "at" not in kf:
            return None
        row = {"at": round(_pair_to_float(kf["at"]) if isinstance(kf["at"], (list, tuple)) else kf["at"] / rate, 4)}
        for k in ("x", "y", "scale", "rotate"):
            if k not in kf:
                return None
            row[k] = round(_pair_to_float(kf[k]), 4)
        out.append(row)
    return out or None


# ---- one writer per project ------------------------------------------------------------
# The desk serves requests on parallel threads, and the CLI and MCP server are other processes.
# A project's write is read-modify-write (load the log, check the op against its version, append,
# save timeline.json), so two at once used to both read version N and both append N+1: the log
# was then refused on load ("out of sequence") and the project would not open. Every write now
# holds the project's lock: a thread lock for this process, plus an OS file lock on
# <project>/.lock for other processes. Re-entrant per thread (apply -> _call).
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_HELD = threading.local()


def _os_lock(fh, on: bool) -> None:
    try:
        import fcntl

        fcntl.flock(fh, fcntl.LOCK_EX if on else fcntl.LOCK_UN)
        return
    except ImportError:
        pass
    try:  # Windows (the desktop build)
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK if on else msvcrt.LK_UNLCK, 1)
    except (ImportError, OSError):
        pass  # no OS lock available: the thread lock still serialises this process


@contextlib.contextmanager
def _locked(folder: Path):
    key = str(folder.resolve())
    with _LOCKS_GUARD:
        lk = _LOCKS.setdefault(key, threading.RLock())
    held = getattr(_HELD, "keys", None)
    if held is None:
        held = _HELD.keys = {}
    with lk:
        if held.get(key):  # this thread already holds it (and the OS lock): just nest
            held[key] += 1
            try:
                yield
            finally:
                held[key] -= 1
            return
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / ".lock", "a+b") as fh:
            _os_lock(fh, True)
            held[key] = 1
            try:
                yield
            finally:
                held[key] = 0
                _os_lock(fh, False)


def _save_current(folder: Path, doc: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "timeline.json.tmp"
    tmp.write_text(json.dumps(doc, separators=(",", ":"), sort_keys=True))
    tmp.replace(folder / "timeline.json")


def _log(folder: Path) -> O.Oplog:
    base = json.loads((folder / "base.json").read_text())
    path = folder / "oplog.jsonl"
    if path.exists() and path.stat().st_size:
        return O.Oplog.load(base, path)
    return O.Oplog(base, path=path)


def view(doc: dict) -> dict:
    """Ticks become seconds so the page can draw. The engine still stores ticks."""
    rate = doc["tick_rate"]
    text_at = {
        it.get("at", 0): it.get("text")
        for tr in doc["tracks"]
        if tr.get("role") == "text"
        for it in tr["items"]
        if it.get("text")
    }
    def clip_speed(it: dict) -> float:
        # props.speed is a reduced [num, den] pair; a missing or invalid value is 1.0.
        raw = (it.get("props") or {}).get("speed")
        try:
            if isinstance(raw, (list, tuple)) and len(raw) == 2:
                num, den = float(raw[0]), float(raw[1])
                if den != 0 and num > 0:
                    return num / den
            if isinstance(raw, (int, float)) and raw > 0:
                return float(raw)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        return 1.0

    tracks = []
    end = 0.0
    for tr in doc["tracks"]:
        items = []
        for it in tr["items"]:
            if it["type"] == "transition":
                # A transition is not a clip: it is the overlap between two of them. The page
                # draws it as a badge at the seam, so it needs its own position and the clips
                # it sits between, but it contributes no length of its own.
                a_id, b_id = it["between"]
                span_a = next((i for i in tr["items"] if i.get("id") == a_id), None)
                if span_a is None:
                    continue
                # The seam is where clip A ends *on the timeline*, which speed shortens.
                span_a_dur = T.item_duration(span_a)  # the one length rule (ramps and holds too)
                at = span_a.get("at", 0) + span_a_dur - it.get("dur", 0)
                items.append(
                    {
                        "id": it["id"],
                        "type": "transition",
                        "kind": "fade" if it.get("kind", "fade") == "xfade" else it.get("kind", "fade"),
                        "at": round(at / rate, 3),
                        "dur": round(it.get("dur", 0) / rate, 3),
                        "between": [a_id, b_id],
                        "label": "Dissolve",
                    }
                )
                continue
            speed = clip_speed(it) if it["type"] == "clip" else 1.0
            at = it.get("at", 0) / rate
            # The one length rule (constant speed, or a ramp's integral); text keeps its dur.
            try:
                dur = T.item_duration(it) / rate
            except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError):
                dur = it.get("dur", 0) / rate
            end = max(end, at + dur)
            label = text_at.get(it.get("at")) or it.get("text") or it["id"]
            if it["type"] == "clip" and not text_at.get(it.get("at")):
                media = doc.get("media", {}).get(it.get("media") or "", {})
                stem = Path(str(media.get("path") or it.get("media") or it["id"])).stem
                label = stem.replace("_", " ").replace("-", " ").title()
            row = {
                "id": it["id"],
                "type": it["type"],
                "at": round(at, 3),
                "dur": round(dur, 3),
                "label": label,
            }
            if it["type"] == "text" and isinstance(it.get("title"), dict):
                from hermes_studio import titles as _TT

                t = it["title"]
                row["title"] = {"template": t["template"], "text": t["text"], "sub": t.get("sub", ""), "accent": t.get("accent"),
                                "in": t.get("in", "fade"), "out": t.get("out", "fade"), "key": _TT.key(t),
                                **{k: v for k, v in _TT.fields(t).items() if k in ("x", "y", "scale", "font", "box")},
                                "fade_in": round((it.get("fade_in") or 0) / rate, 3), "fade_out": round((it.get("fade_out") or 0) / rate, 3)}
                row["label"] = t["text"]
            if it["type"] == "clip" and "src" in it:
                row["src_in"] = round(it["src"][0] / rate, 3)
                row["src_out"] = round(it["src"][1] / rate, 3)
                row["speed"] = round(speed, 4)
                props = it.get("props") or {}
                # A legacy props.look (from before looks were grades) reads as that look's grade,
                # so old docs show in the preview the way they render.
                _stored = props.get("grade") or (_GR.look(props["look"]) if props.get("look") in _GR.LOOKS else None)
                row["look"] = _GR.look_name(_stored)
                row["volume"] = _pair_to_float(props.get("volume"))
                row["crop"] = _crop_view(props.get("crop"))
                row["transform"] = _transform_view(props.get("transform"))
                _g = _GR.parse(_stored)
                row["grade"] = _GR.view(_g)
                row["grade_preview"] = _GR.preview(_g)
                row["keyframes"] = _keyframes_view(props.get("keyframes"), rate)
                row["reverse"] = props.get("reverse") is True
                row["hold"] = bool(props.get("hold"))
                curve = T.ramp_curve(it) if it.get("type") == "clip" else None
                row["speed_keys"] = [[round(a, 4), round(v, 4)] for a, v in curve] if curve else None
                gk = props.get("gain_keys")
                row["gain_keys"] = (
                    [{"at": round(k["at"] / rate, 4), "gain": round(_pair_to_float(k["gain"]), 4)} for k in gk]
                    if isinstance(gk, list) and gk else None
                )
                row["fade_in"] = round((it.get("fade_in") or 0) / rate, 3)
                row["fade_out"] = round((it.get("fade_out") or 0) / rate, 3)
                media = doc.get("media", {}).get(it.get("media") or "", {})
                if media.get("dur"):
                    row["media_dur"] = round(media["dur"] / rate, 3)
                row["file"] = Path(str(media.get("path") or "")).name
                row["media"] = it.get("media") or None
            items.append(row)
        row_t = {"id": tr["id"], "role": tr["role"], "items": items}
        if tr["role"] in ("voice", "music"):
            row_t["mute"] = bool(tr.get("mute", False))
            row_t["solo"] = bool(tr.get("solo", False))
            row_t["gain"] = _pair_to_float(tr.get("gain"))
            row_t["pan"] = _pair_to_float(tr.get("pan", [0, 1]))
            if tr.get("role") == "music":
                row_t["duck"] = int(tr.get("duck") or 0)
                env = T.duck_envelope(doc, tr)
                row_t["duck_env"] = [[a, g] for a, g in env] if env else None
        tracks.append(row_t)
    return {
        "id": doc["id"],
        "version": doc["version"],
        "hash": doc["hash"],
        "duration": round(end, 3) or 1,
        "size": list(doc.get("size") or [1920, 1080]),
        # The project's frame rate as [num, den], so the page can step one frame and show
        # timecode (30000/1001 stays exact; a float would drift over an hour).
        "fps": list(doc.get("fps") or [30, 1]),
        "tracks": tracks,
        # The bin: every file in the media table, in import order, with what the source viewer
        # needs (file name to stream, length, rate, sound) and how many clips use it.
        "bin": [
            {"id": mid, "name": m.get("name") or Path(str(m.get("path") or mid)).stem,
             "file": Path(str(m.get("path") or "")).name, "dur": round(m["dur"] / rate, 4),
             "fps": list(m.get("fps") or [30, 1]), "audio": bool(m.get("audio", True)),
             "uses": sum(1 for tr in doc["tracks"] for it in tr["items"] if it.get("media") == mid)}
            for mid, m in (doc.get("media") or {}).items() if isinstance(m, dict) and isinstance(m.get("dur"), int)
        ],
        # Timeline markers, in seconds, in time order. The op log only appends (an undo's inverse
        # must be able to put a marker back where it was), so stored order is insertion order;
        # this is the order clients and the ruler need.
        "markers": [
            {"id": mk["id"], "at": round(mk["at"] / doc["tick_rate"], 4), "label": mk["label"],
             "color": mk.get("color", T.MARKER_DEFAULT_COLOR)}
            for mk in sorted(doc.get("markers") or [], key=lambda m: (m["at"], m["id"]))
        ],
    }


def _seed(pid: str) -> dict:
    d = T.new_timeline(pid)
    s = T.TICK_RATE
    d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 120 * s, "fps": [30, 1]}}
    by_id = {t["id"]: t for t in d["tracks"]}
    by_id["V1"]["items"] = [
        {"id": "c1", "type": "clip", "media": "m1", "src": [0, 8 * s], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "c2", "type": "clip", "media": "m1", "src": [20 * s, 32 * s], "at": 8 * s, "fade_in": 0, "fade_out": 0},
        {"id": "c3", "type": "clip", "media": "m1", "src": [50 * s, 62 * s], "at": 20 * s, "fade_in": 0, "fade_out": 0},
    ]
    by_id["T1"]["items"] = [
        {
            "id": "x1",
            "type": "text",
            "dur": 6 * s,
            "text": "Your laptop is owned.",
            "style": "pop",
            "fade_in": 0,
            "fade_out": 0,
            "at": 8 * s,
        },
    ]
    by_id["A1"]["items"] = [
        {"id": "a1", "type": "clip", "media": "m1", "src": [0, 32 * s], "at": 0, "fade_in": 0, "fade_out": 0},
    ]
    return d


def create(pid: str = "demo") -> dict:
    folder = _dir(pid)
    if (folder / "base.json").exists():
        return open_project(pid)
    d, _ = T.stamp_hash(_seed(pid))
    with _locked(folder):
        if (folder / "base.json").exists():  # another request created it while we waited
            return view(_log(folder).doc)
        (folder / "base.json").write_text(json.dumps(d))
        log = O.Oplog(d, path=folder / "oplog.jsonl")
        _save_current(folder, log.doc)
        return view(log.doc)


def open_project(pid: str) -> dict:
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    log = _log(folder)
    return view(log.doc)


def list_projects() -> list[str]:
    r = root()
    if not r.is_dir():
        return []
    return sorted(p.name for p in r.iterdir() if (p / "base.json").exists())


def _call(pid: str, tool: str, args: dict | Callable[[O.Oplog], dict]) -> dict:
    """Run one tool call on the project's log under its lock. ``args`` may be a function of the
    freshly loaded log, for calls that need its current version or history (the desk's edits
    always act on the latest state; reading the version outside the lock let two writes race)."""
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    with _locked(folder):
        log = _log(folder)
        try:
            result = log.call(HUMAN, tool, args(log) if callable(args) else args)
        except O.OplogError as exc:
            raise EditorError(exc.message) from exc
        _save_current(folder, log.doc)
        out = view(log.doc)
    out["summary"] = result.get("summary") or tool
    return out


def apply(pid: str, ops: list[dict], summary: str) -> dict:
    return _call(
        pid,
        "timeline_apply",
        lambda log: {
            "base_version": log.version,
            "ops": ops,
            "summary": summary[:120] or "edit",
            "client_op_id": _cid(),
        },
    )


def trim(
    pid: str,
    item_id: str,
    *,
    src_in: int | None = None,
    src_out: int | None = None,
    dur: int | None = None,
    ripple: bool = False,
) -> dict:
    op: dict = {"op": "trim_clip", "id": item_id, "ripple": bool(ripple)}
    if src_in is not None:
        op["src_in"] = src_in
    if src_out is not None:
        op["src_out"] = src_out
    if dur is not None:
        op["dur"] = dur
    return apply(pid, [op], f"Trim {item_id}")


def nudge(pid: str, item_id: str, edge: str, seconds: float) -> dict:
    """Cut `seconds` off the start or the end of a clip. The page talks in seconds."""
    log = _log(_dir(pid))
    it = next((i for tr in log.doc["tracks"] for i in tr["items"] if i.get("id") == item_id), None)
    if not it or it.get("type") != "clip":
        raise EditorError("select a clip first")
    delta = T.seconds_to_ticks(seconds)
    if edge == "start":
        return trim(pid, item_id, src_in=it["src"][0] + delta)
    if edge == "end":
        return trim(pid, item_id, src_out=it["src"][1] - delta)
    raise EditorError("edge must be start or end")


def _item(pid: str, item_id: str) -> tuple[dict, dict]:
    log = _log(_dir(pid))
    it = next((i for tr in log.doc["tracks"] for i in tr["items"] if i.get("id") == item_id), None)
    if not it or "at" not in it:
        raise EditorError("select a clip first")
    return log.doc, it


def set_edge(pid: str, item_id: str, edge: str, at_seconds: float, *, ripple: bool = False) -> dict:
    """Move one edge of a clip to a timeline time. The page talks in seconds."""
    _, it = _item(pid, item_id)
    start = it["at"]
    if it["type"] == "clip":
        i0, o0 = it["src"]
        dur = o0 - i0
    else:
        i0, dur = 0, it["dur"]
    want = T.seconds_to_ticks(at_seconds)
    floor = T.seconds_to_ticks("0.05")
    if edge == "start":
        new_start = min(max(0, want), start + dur - floor)
        delta = new_start - start
        if it["type"] == "clip":
            return trim(pid, item_id, src_in=i0 + delta, ripple=ripple)
        return trim(pid, item_id, dur=dur - delta, ripple=ripple)
    if edge == "end":
        new_end = max(want, start + floor)
        new_dur = new_end - start
        if it["type"] == "clip":
            return trim(pid, item_id, src_out=i0 + new_dur, ripple=ripple)
        return trim(pid, item_id, dur=new_dur, ripple=ripple)
    raise EditorError("edge must be start or end")


def _neighbour_after(doc: dict, a: dict) -> tuple[dict, int]:
    """The clip that A cuts to on its own track, and the crossfade between them (0 = a hard
    cut). Raises when nothing touches A's end: a roll needs an edit point, not a gap."""
    tr = next(t for t in doc["tracks"] if any(i.get("id") == a["id"] for i in t["items"]))
    a_end = a["at"] + T.item_duration(a)
    xf = {tuple(x["between"]): x["dur"] for x in tr["items"] if x.get("type") == "transition"}
    for b in sorted((i for i in tr["items"] if i.get("type") == "clip" and "at" in i and i["id"] != a["id"]), key=lambda i: i["at"]):
        x = xf.get((a["id"], b["id"]), 0)
        if b["at"] == a_end - x:
            return b, x
    raise EditorError(f"no clip touches the end of {a['id']}: roll moves an edit point between two clips")


def roll(pid: str, item_id: str, by_seconds: float) -> dict:
    """Roll the edit point at the end of ``item_id``: the outgoing clip gets longer by exactly
    what the incoming one loses (Final Cut's and Resolve's roll). Nothing else on the timeline
    moves and the total length is unchanged.

    ``by_seconds`` is timeline time (positive moves the cut later), snapped to whole frames and
    clamped so both clips keep at least a frame (plus any crossfade between them) and neither
    runs past its media. Two trim_clip ops in one apply: one undo step, and the validator only
    sees the finished result, so the clips never overlap mid-edit.
    """
    doc, a = _item(pid, item_id)
    if a["type"] != "clip":
        raise EditorError("only a clip's edit point can be rolled")
    b, x = _neighbour_after(doc, a)
    num, den = doc.get("fps") or [30, 1]
    frame = Fraction(T.TICK_RATE * den, num)
    sa = Fraction(*(a.get("props", {}).get("speed") or [1, 1]))
    sb = Fraction(*(b.get("props", {}).get("speed") or [1, 1]))
    ia, oa = a["src"]
    ib, ob = b["src"]
    media = doc.get("media", {})
    mdur = (media.get(a["media"]) or {}).get("dur")
    # Limits in timeline ticks: A grows into its unused media, B grows into the media before it,
    # and each keeps a frame beyond the crossfade that sits on the cut.
    hi = min(T.item_duration(b) - x - frame, Fraction(mdur - oa) / sa if isinstance(mdur, int) else T.item_duration(b))
    lo = max(-(T.item_duration(a) - x - frame), -Fraction(ib) / sb)
    want = round(Fraction(_frames(doc, by_seconds)) / frame)
    n = max(math.ceil(lo / frame), min(math.floor(hi / frame), want))
    if n == 0:
        raise EditorError(f"the edit point after {item_id} can't move that way")
    d = n * frame
    da, db = d * sa, d * sb
    if da.denominator != 1 or db.denominator != 1:
        raise EditorError("that roll isn't frame-exact at these clip speeds")
    shown = float(T.ticks_to_seconds(int(d)))
    return apply(pid, [
        {"op": "trim_clip", "id": b["id"], "src_in": ib + int(db), "ripple": False},
        {"op": "trim_clip", "id": a["id"], "src_out": oa + int(da), "ripple": False},
    ], f"Roll {a['id']}|{b['id']} {shown:+.2f}s")


def _neighbour_before(doc: dict, b: dict) -> tuple[dict, int]:
    """The clip that cuts to B on its own track, and the crossfade between them (0 = hard cut)."""
    tr = next(t for t in doc["tracks"] if any(i.get("id") == b["id"] for i in t["items"]))
    xf = {tuple(x["between"]): x["dur"] for x in tr["items"] if x.get("type") == "transition"}
    for a in (i for i in tr["items"] if i.get("type") == "clip" and "at" in i and i["id"] != b["id"]):
        x = xf.get((a["id"], b["id"]), 0)
        if a["at"] + T.item_duration(a) - x == b["at"]:
            return a, x
    raise EditorError(f"no clip touches the start of {b['id']}: slide needs a clip on each side")


def slide(pid: str, item_id: str, by_seconds: float) -> dict:
    """Slide a clip between its neighbours (Final Cut's and Resolve's slide): it keeps its own
    media and length and moves along the timeline; the clip before it grows (or shrinks) to
    meet it and the clip after it shrinks (or grows) by the same amount. Total length and
    everything outside the three clips stay put.

    Frame-exact and clamped: each neighbour keeps a frame beyond any crossfade, the one before
    can't run past its media, the one after can't reach before its media starts. Three ops in
    one apply: one undo step, validated only as a finished whole.
    """
    doc, b = _item(pid, item_id)
    if b["type"] != "clip":
        raise EditorError("only a clip can be slid")
    a, xa = _neighbour_before(doc, b)
    try:
        c, xc = _neighbour_after(doc, b)
    except EditorError:
        raise EditorError(f"no clip touches the end of {item_id}: slide needs a clip on each side") from None
    num, den = doc.get("fps") or [30, 1]
    frame = Fraction(T.TICK_RATE * den, num)
    sa = Fraction(*(a.get("props", {}).get("speed") or [1, 1]))
    sc = Fraction(*(c.get("props", {}).get("speed") or [1, 1]))
    oa, ic = a["src"][1], c["src"][0]
    mdur = (doc.get("media", {}).get(a["media"]) or {}).get("dur")
    hi = min(Fraction(T.item_duration(c) - xc) - frame,
             Fraction(mdur - oa) / sa if isinstance(mdur, int) else Fraction(T.item_duration(c)))
    lo = max(-(Fraction(T.item_duration(a) - xa) - frame), -Fraction(ic) / sc)
    want = round(Fraction(_frames(doc, by_seconds)) / frame)
    n = max(math.ceil(lo / frame), min(math.floor(hi / frame), want))
    if n == 0:
        raise EditorError(f"{item_id} can't slide that way")
    d = n * frame
    da, dc = d * sa, d * sc
    if da.denominator != 1 or dc.denominator != 1 or d.denominator != 1:
        raise EditorError("that slide isn't frame-exact at these clip speeds")
    shown = float(T.ticks_to_seconds(int(d)))
    return apply(pid, [
        {"op": "trim_clip", "id": c["id"], "src_in": ic + int(dc), "ripple": False},  # C starts later
        {"op": "move_clip", "id": b["id"], "at": b["at"] + int(d)},
        {"op": "trim_clip", "id": a["id"], "src_out": oa + int(da), "ripple": False},  # A meets B
    ], f"Slide {item_id} {shown:+.2f}s")


def slip(pid: str, item_id: str, by_seconds: float) -> dict:
    """Slip a clip: slide its source window under it, as Resolve's and Final Cut's slip does.

    The clip keeps its place and its length on the timeline; only which part of the media
    plays changes. ``by_seconds`` is timeline time (positive shows later media), scaled by the
    clip's speed into source time and clamped to the media, so a slip past either end stops
    at the end instead of failing. One trim_clip op with ripple (which moves nothing when the
    length is unchanged), so it is one undo step and the validator checks the result.
    """
    doc, it = _item(pid, item_id)
    if it["type"] != "clip":
        raise EditorError("only a clip can be slipped")
    i0, o0 = it["src"]
    sp = Fraction(*(it.get("props", {}).get("speed") or [1, 1]))
    d = int(Fraction(_frames(doc, by_seconds)) * sp)  # whole timeline frames, in source ticks
    mdur = (doc.get("media", {}).get(it["media"]) or {}).get("dur")
    lo = -i0
    hi = (mdur - o0) if isinstance(mdur, int) else d
    d = max(lo, min(hi, d))
    if d == 0:
        raise EditorError("the clip is already at the end of its media")
    shown = float(T.ticks_to_seconds(d) / sp)  # back to timeline seconds for the history line
    return apply(pid, [{"op": "trim_clip", "id": item_id, "src_in": i0 + d, "src_out": o0 + d, "ripple": True}],
                 f"Slip {item_id} {shown:+.2f}s")


def move(pid: str, item_id: str, at_seconds: float) -> dict:
    at = max(0, T.seconds_to_ticks(at_seconds))
    return apply(pid, [{"op": "move_clip", "id": item_id, "at": at}], f"Move {item_id}")


def set_transition(pid: str, a_id: str, b_id: str, seconds: float = 0.0, kind: str | None = None) -> dict:
    """Put a transition between two consecutive clips (dur 0 = a hard cut).

    ``kind`` names the ffmpeg xfade to use and defaults to 'fade' (a cross-dissolve). Pass an
    alias like "cross fade" or "dip to black" and it resolves; an unknown name is refused, not
    silently downgraded to a dissolve. ``transitions.kinds()`` lists what this ffmpeg supports
    and ``transitions.catalog()`` the same names grouped for the page."""
    dur = max(0, T.seconds_to_ticks(seconds))
    if dur:
        k = _XT.resolve(kind or "fade")
        if k is None:
            raise EditorError(f"unknown transition kind {kind!r}")
    else:
        k = None
    return apply(pid, [{"op": "set_transition", "between": [a_id, b_id], "dur": dur, "kind": k}],
                 f"{_XT.label(k)} {seconds:g}s" if dur else "Hard cut")


def set_canvas(pid: str, width: int, height: int) -> dict:
    w, h = int(width), int(height)
    if not (1 <= w <= 16384 and 1 <= h <= 16384):
        raise EditorError("canvas must be 1 to 16384 on each side")
    return apply(pid, [{"op": "set_canvas", "width": w, "height": h}], f"Canvas {w}×{h}")


def _linked_sound(pid: str, item_id: str) -> list[str]:
    """The audio items that carry the same footage as a video clip: same media, same source range
    and the same start, on a voice or music track. A film imports as a picture item plus its
    sound items laid over it, so retiming the picture must retime the sound or the two drift."""
    doc = _log(_dir(pid)).doc
    me = None
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["id"] == item_id:
                me = it
    if not me or me.get("type") != "clip" or "src" not in me or "at" not in me:
        return []
    out = []
    for tr in doc["tracks"]:
        if tr.get("role") not in ("voice", "music"):
            continue
        for it in tr["items"]:
            if (it.get("type") == "clip" and it.get("media") == me.get("media")
                    and it.get("src") == me.get("src") and it.get("at") == me.get("at")):
                out.append(it["id"])
    return out


def _retime(pid: str, item_id: str, clip_props: dict, sound_props: dict, label: str) -> dict:
    """Apply a retime (speed, ramp, reverse...) to a clip and its linked sound, and RIPPLE: the
    length change moves every later item on every track by the same amount, so slowing a clip
    pushes the cut out instead of being refused for overlapping its neighbour (Final Cut's
    retime, Resolve's ripple). Anchored items follow their clip. Transitions touching the clip
    are dropped to a hard cut first (their overlap can't survive a new length). One undo step."""
    doc = _log(_dir(pid)).doc
    me = None
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["id"] == item_id:
                me = it
    if me is None:
        raise EditorError(f"no item {item_id!r}")
    if me.get("type") != "clip":
        raise EditorError("only a clip can be retimed")
    if "at" not in me:
        raise EditorError("an anchored clip can't be retimed")
    old_len = T.item_duration(me)
    trial = copy.deepcopy(me)
    trial.setdefault("props", {}).update({k: v for k, v in clip_props.items()})
    try:
        new_len = T.item_duration(trial)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError) as e:
        raise EditorError("that retime gives the clip no usable length") from e
    if new_len <= 0:
        raise EditorError("that retime gives the clip no length")
    old_end = me["at"] + old_len
    linked = set(_linked_sound(pid, item_id))

    ops: list[dict] = []
    delta = new_len - old_len
    if delta:
        # A new length breaks a dissolve's overlap; a same-length retime (reverse) keeps it.
        for tr in _transitions_on(pid, item_id):
            ops.append({"op": "set_transition", "between": list(tr["between"]), "dur": 0})
    ops.append({"op": "set_props", "id": item_id, "props": clip_props})
    for sid in linked:
        ops.append({"op": "set_props", "id": sid, "props": sound_props})
    if delta:
        later = [
            it["id"]
            for tr in doc["tracks"]
            for it in tr["items"]
            if it["id"] != item_id and it["id"] not in linked and it.get("type") != "transition"
            and "at" in it and it["at"] >= old_end
        ]
        if later:
            ops.append({"op": "move_items", "ids": later, "by": delta})
    return apply(pid, ops, label)


def set_speed(pid: str, item_id: str, speed: float) -> dict:
    """Set a clip's playback speed. The schema stores it as a reduced [num, den] pair and
    allows 0.1x to 10x; anything outside that is refused before it reaches the op log.

    Retiming a clip changes how long it occupies, which would break any cross-dissolve that
    overlaps it (the schema requires the overlap to match exactly). Pro editors reset the
    transition when you retime, so a hard cut is dropped in first -- the dissolve can be
    re-applied at the new length afterwards."""
    from fractions import Fraction

    s = float(speed)
    if not (0.1 <= s <= 10.0):
        raise EditorError("speed must be between 0.1 and 10")
    fr = Fraction(s).limit_denominator(1000)
    pair = [fr.numerator, fr.denominator]

    # The sound plays at the same speed; a constant speed on the picture clears any ramp on it.
    return _retime(pid, item_id, {"speed": pair}, {"speed": pair, "speed_keys": None}, f"Speed {s:g}×")


def set_reverse(pid: str, item_id: str, on: bool) -> dict:
    """Play a clip backwards (Final Cut's Reverse Clip, Resolve's Reverse Segment), or forwards
    again. Its sound reverses with it; the length is unchanged, so nothing ripples. Speed and a
    ramp still apply, in played time. One undo step."""
    flag = True if on else None
    return _retime(pid, item_id, {"reverse": flag}, {"reverse": flag}, "Reverse" if on else "Forward")


def freeze(pid: str, item_id: str, at_seconds: float, hold_seconds: float = 2.0) -> dict:
    """Freeze frame (Final Cut's Add Freeze Frame, Resolve's Freeze Frame): hold the frame under
    ``at_seconds`` for ``hold_seconds``, pushing everything after it out by the hold.

    The clip is cut at the playhead (its sound too) and a one-frame still of the frame shown
    there is inserted between the pieces; the still carries the clip's grade, crop and framing
    but not its motion, and has no sound, so the hold is silent. One undo step."""
    doc = _log(_dir(pid)).doc
    tr_of, me = None, None
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["id"] == item_id:
                tr_of, me = tr, it
    if me is None:
        raise EditorError(f"no item {item_id!r}")
    if me.get("type") != "clip" or tr_of.get("role") != "main" or "at" not in me:
        raise EditorError("freeze a clip on the main track")
    if (me.get("props") or {}).get("hold"):
        raise EditorError("that clip is already a freeze frame")
    hold = _frames(doc, float(hold_seconds))
    if not (T.seconds_to_ticks(0.1) <= hold <= T.seconds_to_ticks(600)):
        raise EditorError("hold between 0.1 and 600 seconds")
    start, length = me["at"], T.item_duration(me)
    cut = _at_frame(doc, float(at_seconds))  # the frame under the playhead, like every edit point
    if not start <= cut < start + length:
        raise EditorError("the playhead isn't on that clip")
    # The frame shown at the playhead, snapped to the media's own frame grid.
    m = doc["media"][me["media"]]
    fps = m.get("fps") or [30, 1]
    frame = T.TICK_RATE * fps[1] // fps[0]
    src = me["src"][0] + T.source_offset(me, cut - start)
    src = (src // frame) * frame
    if isinstance(m.get("dur"), int):
        src = min(src, m["dur"] - frame)
    src = max(0, src)
    tag = secrets.token_hex(3)
    still = f"fz{tag}"
    props = {k: v for k, v in (me.get("props") or {}).items() if k in ("grade", "crop", "transform", "look") and v is not None}
    props["hold"] = hold

    ops: list[dict] = []
    later_from = cut
    pieces: list[str] = []
    if cut > start:
        a, b = f"{item_id}a{tag}", f"{item_id}b{tag}"
        ops.append({"op": "split_clip", "id": item_id, "at": cut, "ids": [a, b]})
        pieces.append(b)
    for sid in _linked_sound(pid, item_id):
        if cut > start:
            ops.append({"op": "split_clip", "id": sid, "at": cut, "ids": [f"{sid}a{tag}", f"{sid}b{tag}"]})
            pieces.append(f"{sid}b{tag}")
    # Everything that starts at or after the cut moves out by the hold (the new right-hand
    # pieces included); anchored items follow their clips.
    later = [it["id"] for tr in doc["tracks"] for it in tr["items"]
             if it.get("type") != "transition" and "at" in it and it["at"] >= later_from and it["id"] != item_id]
    if cut == start:
        later.append(item_id)
        later += [sid for sid in _linked_sound(pid, item_id) if sid not in later]
    move = sorted(set(later + pieces), key=lambda x: (x not in pieces, x))
    if move:
        ops.append({"op": "move_items", "ids": move, "by": hold})
    ops.append({"op": "insert_clip", "track": tr_of["id"], "id": still, "media": me["media"],
                "src": [src, src + frame], "at": cut, "fade_in": 0, "fade_out": 0, "props": props})
    return apply(pid, ops, f"Freeze frame {hold_seconds:g}s")


def _probe(path: Path) -> dict:
    """Length, frame rate and whether there is sound, from ffprobe. Refuses what isn't a video."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,avg_frame_rate,r_frame_rate",
         "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError:
        info = {}
    streams = info.get("streams") or []
    video = next((x for x in streams if x.get("codec_type") == "video"), None)
    if r.returncode != 0 or video is None:
        raise EditorError("that file has no picture the editor can read")
    try:
        dur = float((info.get("format") or {}).get("duration") or 0)
    except ValueError:
        dur = 0.0
    if dur <= 0:
        raise EditorError("that file has no length")
    fps = [30, 1]
    for key in ("avg_frame_rate", "r_frame_rate"):
        num, _, den = str(video.get(key) or "").partition("/")
        try:
            n, d = int(num), int(den or 1)
        except ValueError:
            continue
        if n > 0 and d > 0 and 1 <= n / d <= 240:
            fps = [n, d]
            break
    return {"dur": T.seconds_to_ticks(dur), "fps": fps, "audio": any(x.get("codec_type") == "audio" for x in streams)}


def import_media(pid: str, src: Path, name: str | None = None, *, move: bool = False) -> dict:
    """Bring a video into the project's bin: copy (or move) it under media/, probe it, and add it
    to the media table with an add_media op -- so the import shows in history and undoes.
    Nothing is placed on the timeline; that is what insert / overwrite / append are for."""
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    src = Path(src)
    if not src.is_file():
        raise EditorError("no such file")
    ext = src.suffix.lower()
    if ext not in MEDIA_TYPES or not MEDIA_TYPES[ext].startswith("video/"):
        raise EditorError("import a video file (mp4, mov, m4v, webm, mkv)")
    info = _probe(src)
    label = " ".join((name or src.stem).split())[:80] or "clip"
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in Path(label).stem)[:40].strip("-") or "clip"
    with _locked(folder):
        (folder / "media").mkdir(exist_ok=True)
        dest = folder / "media" / f"{stem}{ext}"
        n = 2
        while dest.exists():
            dest = folder / "media" / f"{stem}-{n}{ext}"
            n += 1
        tmp = dest.with_name("." + dest.name + ".part")
        if move:
            shutil.move(str(src), tmp)
        else:
            shutil.copyfile(src, tmp)
        tmp.replace(dest)
    doc = _log(folder).doc
    n, mid = 1, None
    taken = set(T._all_ids(doc))
    while mid is None or mid in taken:
        mid = f"m{secrets.token_hex(3)}"
    try:
        return apply(pid, [{"op": "add_media", "id": mid, "path": f"media/{dest.name}", "dur": info["dur"],
                            "fps": info["fps"], "name": label, "audio": info["audio"]}], f"Import {label}")
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def _main_track(doc: dict) -> dict:
    tr = next((t for t in doc["tracks"] if t.get("role") == "main"), None)
    if tr is None:
        raise EditorError("this cut has no main track")
    return tr


def _track_end(tr: dict) -> int:
    return max((it["at"] + T.item_duration(it) for it in tr["items"] if "at" in it and it.get("type") != "transition"), default=0)


def place(pid: str, media_id: str, src_in: float, src_out: float, mode: str, at: float | None = None) -> dict:
    """Three-point editing, as in Final Cut and Resolve: a source range [src_in, src_out) of a bin
    clip goes onto the timeline at ``at`` (the playhead or the timeline In mark).

    - ``insert`` (Final Cut W, Resolve F9): everything at or after ``at`` moves out by the clip's
      length, on every track; items under ``at`` are cut there. Nothing is covered.
    - ``overwrite`` (Final Cut D, Resolve F10): the clip replaces what is under it on the main
      track and the sound track; the cut's length only grows if it runs past the end.
    - ``append`` (Final Cut E, Resolve F12): onto the end of the main track; ``at`` is ignored.

    The picture goes on the main track and, if the file has sound, its sound on the first voice
    track, linked (same source range and start, so retimes carry across). One undo step."""
    if mode not in ("insert", "overwrite", "append"):
        raise EditorError("mode is insert, overwrite or append")
    doc = _log(_dir(pid)).doc
    m = doc["media"].get(media_id)
    if not isinstance(m, dict):
        raise EditorError(f"no media {media_id!r} in the bin")
    fps = m.get("fps") or [30, 1]
    frame = Fraction(T.TICK_RATE * fps[1], fps[0])

    def snap(sec: float) -> int:
        return int(round(Fraction(T.seconds_to_ticks(float(sec))) / frame) * frame)

    i0, o1 = max(0, snap(src_in)), min(m["dur"], snap(src_out))
    if o1 - i0 < int(frame):
        raise EditorError("mark a source range at least one frame long")
    length = o1 - i0
    main = _main_track(doc)
    sound = next((t for t in doc["tracks"] if t.get("role") == "voice"), None) if m.get("audio") else None
    if mode == "append":
        cut = _track_end(main)
    else:
        if at is None:
            raise EditorError("place needs a timeline point")
        # Edit points sit on the project's frame grid (a pointer time between frames used to
        # land the clip 0.025 s off the frame the clock showed).
        cut = max(0, _at_frame(doc, float(at)))
        end = _track_end(main)
        if cut > end:
            cut = end  # past the end, an edit lands at the end (no gap made silently)

    tag = secrets.token_hex(3)
    ops: list[dict] = []
    gone_transitions: set[str] = set()

    def cut_at(t: int, tracks: list[dict], suffix: str) -> dict[str, tuple[str, str]]:
        """Split every item strictly straddling t on these tracks. Returns {old: (left, right)}."""
        out = {}
        for tr in tracks:
            for it in tr["items"]:
                if it.get("type") == "transition" or "at" not in it:
                    continue
                s0, s1 = it["at"], it["at"] + T.item_duration(it)
                if s0 < t < s1:
                    a, b = f"{it['id']}{suffix}{tag}l", f"{it['id']}{suffix}{tag}r"
                    ops.append({"op": "split_clip", "id": it["id"], "at": t, "ids": [a, b]})
                    out[it["id"]] = (a, b)
        return out

    def drop_seams(t: int, tracks: list[dict]) -> None:
        # A dissolve whose seam is at t can't survive something coming between its two clips.
        ids = {it["id"]: it for tr in tracks for it in tr["items"]}
        for tr in tracks:
            for x in tr["items"]:
                if x.get("type") == "transition" and x["id"] not in gone_transitions:
                    a_id, b_id = x["between"]
                    if a_id in ids and "at" in ids[b_id] and ids[b_id]["at"] == t:
                        ops.append({"op": "set_transition", "between": [a_id, b_id], "dur": 0})
                        gone_transitions.add(x["id"])

    if mode == "insert":
        drop_seams(cut, doc["tracks"])
        pieces = cut_at(cut, doc["tracks"], "i")
        later = [it["id"] for tr in doc["tracks"] for it in tr["items"]
                 if it.get("type") != "transition" and "at" in it and it["at"] >= cut]
        later += [b for _, b in pieces.values()]
        if later:
            ops.append({"op": "move_items", "ids": sorted(set(later)), "by": length})
    elif mode == "overwrite":
        lanes = [main] + ([sound] if sound else [])
        drop_seams(cut, lanes)
        drop_seams(cut + length, lanes)
        left = cut_at(cut, lanes, "o")
        # Items now covered: the right-hand pieces of the first cut, plus anything starting in
        # the range. A piece that also runs past the end of the range is cut there too.
        covered = []
        for tr in lanes:
            for it in tr["items"]:
                if it.get("type") == "transition" or "at" not in it:
                    continue
                s0, s1 = it["at"], it["at"] + T.item_duration(it)
                rid = left[it["id"]][1] if it["id"] in left else it["id"]
                if it["id"] in left:
                    s0 = cut
                if s1 <= cut or s0 >= cut + length:
                    continue
                if s1 > cut + length:
                    keep = f"{it['id']}e{tag}"
                    ops.append({"op": "split_clip", "id": rid, "at": cut + length, "ids": [f"{it['id']}c{tag}", keep]})
                    covered.append(f"{it['id']}c{tag}")
                else:
                    covered.append(rid)
        if covered:
            ops.append({"op": "delete_items", "ids": covered})
    vid = f"v{tag}"
    ops.append({"op": "insert_clip", "track": main["id"], "id": vid, "media": media_id, "src": [i0, o1],
                "at": cut, "fade_in": 0, "fade_out": 0})
    if sound is not None:
        ops.append({"op": "insert_clip", "track": sound["id"], "id": f"s{tag}", "media": media_id, "src": [i0, o1],
                    "at": cut, "fade_in": 0, "fade_out": 0})
    label = m.get("name") or media_id
    word = {"insert": "Insert", "overwrite": "Overwrite", "append": "Append"}[mode]
    return apply(pid, ops, f"{word} {label}")


def add_title(pid: str, template: str, at: float, *, text: str, sub: str = "", dur: float = 4.0,
              accent: str | None = None, anim_in: str = "fade", anim_out: str = "fade", fade: float = 0.5) -> dict:
    """A designed title on the text track (Final Cut's titles, Resolve's Text+ templates):
    lower-third, title or end-card, drawn by the Design page's renderer so the preview and the
    render show the same pixels. ``fade`` is the length of the in and out motion. One undo."""
    from hermes_studio import titles as TT

    doc = _log(_dir(pid)).doc
    w, h = (doc.get("size") or [1920, 1080])
    try:
        title = TT.make(template, int(w), int(h), text=text, sub=sub, accent=accent, anim_in=anim_in, anim_out=anim_out)
    except ValueError as exc:
        raise EditorError(str(exc)) from exc
    if not title["text"]:
        raise EditorError("a title needs some words")
    length = _frames(doc, float(dur))
    if length < _frames(doc, 0.2):
        raise EditorError("a title lasts at least 0.2 s")
    fade_t = min(_frames(doc, max(0.0, float(fade))), length // 2)
    track = next((t["id"] for t in doc["tracks"] if t.get("role") == "text"), None)
    if track is None:
        raise EditorError("this cut has no text track")
    start = _at_frame(doc, float(at))
    return apply(pid, [{"op": "add_text", "track": track, "id": f"tt{secrets.token_hex(3)}", "dur": length,
                        "text": title["text"], "style": "title", "at": start, "fade_in": fade_t, "fade_out": fade_t,
                        "title": title}], f"Title {title['text'][:40]}")


def edit_title(pid: str, item_id: str, **changes) -> dict:
    """Change a title's words, template, accent or motion. Its layers are rebuilt from the
    template (the validator holds them to it), the canvas size included, so a title follows a
    change of canvas the next time it is edited. One undo step."""
    from hermes_studio import titles as TT

    doc = _log(_dir(pid)).doc
    _, it = _item(pid, item_id)
    t = it.get("title")
    if not isinstance(t, dict):
        raise EditorError("that item isn't a title")
    w, h = (doc.get("size") or [1920, 1080])
    fields = TT.fields(t)
    template = changes.get("template") or t["template"]
    if template != t["template"] and changes.get("box") is None:
        fields["box"] = None  # a new template brings its own panel default
    for k in ("text", "sub", "accent", "anim_in", "anim_out", "x", "y", "scale", "font", "box"):
        if changes.get(k) is not None:
            fields[k] = changes[k]
    try:
        new = TT.make(template, int(w), int(h), **fields)
    except ValueError as exc:
        raise EditorError(str(exc)) from exc
    if not new["text"]:
        raise EditorError("a title needs some words")
    # Say what changed, so the history reads like an edit list ("Move title", "Title font").
    was, now = TT.fields(t), TT.fields(new)
    changed = [k for k in now if now[k] != was[k]] + (["template"] if new["template"] != t["template"] else [])
    names = {"x": "Move", "y": "Move", "scale": "Size", "font": "Font", "box": "Panel", "accent": "Colour",
             "anim_in": "Motion", "anim_out": "Motion", "text": "Words", "sub": "Words", "template": "Template"}
    what = sorted({names[k] for k in changed}, key=list(names.values()).index) or ["Title"]
    label = ("Move title" if what == ["Move"] else f"Title {' + '.join(w.lower() for w in what)}") + f": {new['text'][:32]}"
    return apply(pid, [{"op": "edit_text", "id": item_id, "text": new["text"], "title": new}], label)


def title_png(pid: str, item_id: str) -> bytes:
    """The title's own PNG (the same file the render overlays), for the preview."""
    from hermes_studio import titles as TT

    folder = _dir(pid)
    _, it = _item(pid, item_id)
    if not isinstance(it.get("title"), dict):
        raise EditorError("that item isn't a title")
    return TT.png(it["title"], folder / "cache").read_bytes()


def set_look(pid: str, item_id: str, look: str | None) -> dict:
    """Apply a named look to a clip (it becomes the clip's grade, so the preview, scopes and
    wheels show it and the wheels can take it further), or clear the grade (None). Clears any
    legacy ``props.look`` in the same op. An unknown name is refused, not ignored."""
    name = (look or "").strip().lower() or None
    if name is not None and name not in _GR.LOOKS:
        raise EditorError(f"unknown look {look!r}; choose from {', '.join(_GR.LOOKS)}")
    _, it = _item(pid, item_id)
    if it["type"] != "clip":
        raise EditorError("only a clip can take a look")
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"grade": _GR.look(name), "look": None}}],
                 f"Look {name or 'none'}")


def set_volume(pid: str, item_id: str, volume: float) -> dict:
    """Set an audio clip's level (0 to 4). Stored as a reduced [num, den] pair, like speed."""
    from fractions import Fraction

    v = float(volume)
    if not (0.0 <= v <= 4.0):
        raise EditorError("volume must be between 0 and 4")
    fr = Fraction(v).limit_denominator(1000)
    pair = [fr.numerator, fr.denominator]
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"volume": pair}}], f"Volume {v:g}×")


def set_track(pid: str, track_id: str, *, mute: bool | None = None, solo: bool | None = None,
              gain: float | None = None, pan: float | None = None, duck: int | None = None) -> dict:
    """An audio track's mixer strip. Only what is given changes; one undo step either way."""
    from fractions import Fraction

    op: dict = {"op": "set_track", "id": track_id}
    words = []
    if mute is not None:
        op["mute"] = bool(mute)
        words.append("muted" if mute else "unmuted")
    if solo is not None:
        op["solo"] = bool(solo)
        words.append("solo" if solo else "solo off")
    if gain is not None:
        g = float(gain)
        if not (0.0 <= g <= 4.0):
            raise EditorError("track gain must be between 0 and 4")
        fr = Fraction(g).limit_denominator(1000)
        op["gain"] = [fr.numerator, fr.denominator]
        words.append(f"gain {g:g}×")
    if pan is not None:
        p = round(float(pan), 2)
        if not (-1.0 <= p <= 1.0):
            raise EditorError("pan is between -1 (left) and 1 (right)")
        fr = Fraction(p).limit_denominator(100)
        op["pan"] = [fr.numerator, fr.denominator]
        words.append("pan centre" if p == 0 else f"pan {abs(round(p * 100))}% {'left' if p < 0 else 'right'}")
    if duck is not None:
        d = int(round(float(duck)))
        if not (0 <= d <= T.DUCK_MAX_DB):
            raise EditorError(f"ducking is 0 to {T.DUCK_MAX_DB} dB")
        op["duck"] = d
        words.append("ducking off" if d == 0 else f"ducks {d} dB under voice")
    if len(op) == 2:
        raise EditorError("nothing to set on the track")
    return apply(pid, [op], f"{track_id} " + ", ".join(words))


MARKER_LABEL_MAX = 200


def _marker_label(label: object) -> str:
    import unicodedata

    s = unicodedata.normalize("NFC", str(label or "")).strip()
    if len(s) > MARKER_LABEL_MAX:
        raise EditorError(f"a marker name is at most {MARKER_LABEL_MAX} characters")
    return s


def _marker_color(color: object) -> str | None:
    if color in (None, ""):
        return None
    if color not in T.MARKER_COLORS:
        raise EditorError("a marker colour is one of " + ", ".join(T.MARKER_COLORS))
    return str(color)


def add_marker(pid: str, at: float, label: str = "", color: str | None = None) -> dict:
    """Drop a marker at ``at`` seconds (Resolve's M)."""
    if not (0 <= at < 1e7):
        raise EditorError("a marker must sit at a time from the start of the cut")
    op = {"op": "add_marker", "at": T.seconds_to_ticks(at), "label": _marker_label(label)}
    c = _marker_color(color)
    if c:
        op["color"] = c
    return apply(pid, [op], "Marker" + (f" “{op['label']}”" if op["label"] else ""))


def set_marker(pid: str, marker_id: str, **fields) -> dict:
    """Move (``at`` seconds), rename (``label``) or recolour (``color``) a marker."""
    op: dict = {"op": "set_marker", "id": marker_id}
    if fields.get("at") is not None:
        if not (0 <= fields["at"] < 1e7):
            raise EditorError("a marker must sit at a time from the start of the cut")
        op["at"] = T.seconds_to_ticks(fields["at"])
    if "label" in fields and fields["label"] is not None:
        op["label"] = _marker_label(fields["label"])
    if "color" in fields and fields["color"] is not None:
        op["color"] = _marker_color(fields["color"]) or T.MARKER_DEFAULT_COLOR
    if len(op) == 2:
        raise EditorError("say what to change: at, label or color")
    what = "Marker moved" if "at" in op else "Marker renamed" if "label" in op else "Marker colour"
    return apply(pid, [op], what)


def remove_marker(pid: str, marker_id: str) -> dict:
    return apply(pid, [{"op": "remove_marker", "id": marker_id}], "Marker removed")


def set_gain_keys(pid: str, item_id: str, keys: list | None) -> dict:
    """A clip's volume envelope (the rubber band): [{at: seconds from the clip's start, gain}],
    or None to clear it. The op log validates order, count and range; this only converts
    seconds to ticks and levels to [num, den] pairs."""
    from fractions import Fraction

    if keys is None:
        return apply(pid, [{"op": "set_props", "id": item_id, "props": {"gain_keys": None}}], "Volume keys cleared")
    if not isinstance(keys, list) or not keys:
        raise EditorError("gain keys must be a list of {at, gain}")
    out = []
    for k in keys:
        try:
            at, g = float(k["at"]), float(k["gain"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EditorError("each gain key needs a number 'at' and 'gain'") from exc
        if not (0.0 <= g <= 4.0):
            raise EditorError("a gain key's level must be between 0 and 4")
        fr = Fraction(g).limit_denominator(1000)
        out.append({"at": T.seconds_to_ticks(at), "gain": [fr.numerator, fr.denominator]})
    n = len(out)
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"gain_keys": out}}], f"Volume keys ×{n}")


def set_fade(pid: str, item_id: str, *, fade_in: float = 0.0, fade_out: float = 0.0) -> dict:
    """Fade a clip's picture and sound to/from black over the given seconds. The op log
    validates the pair against the clip's length, so an over-long fade is refused there."""
    fi = max(0, T.seconds_to_ticks(fade_in))
    fo = max(0, T.seconds_to_ticks(fade_out))
    return apply(pid, [{"op": "set_fade", "id": item_id, "fade_in": fi, "fade_out": fo}], f"Fade {fade_in:g}s/{fade_out:g}s")


def set_crop(pid: str, item_id: str, x: float, y: float, w: float, h: float) -> dict:
    """Reframe a clip by keeping a sub-rectangle of its source, which then fills the canvas.
    Each value is a fraction of the source frame (0-1); x+w and y+h must stay within 1.
    Passing the full frame (0,0,1,1) clears the crop. Stored as [num, den] pairs, like speed."""
    from fractions import Fraction

    def pair(v: float) -> list[int]:
        fr = Fraction(v).limit_denominator(1000)
        return [fr.numerator, fr.denominator]

    vals = [float(x), float(y), float(w), float(h)]
    if any(not (0.0 <= v <= 1.0) for v in vals):
        raise EditorError("crop values must be between 0 and 1")
    if w <= 0 or h <= 0 or x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
        raise EditorError("crop box must be non-empty and inside the frame")
    if x == 0.0 and y == 0.0 and w == 1.0 and h == 1.0:
        crop = None
        label = "Crop cleared"
    else:
        crop = {"x": pair(x), "y": pair(y), "w": pair(w), "h": pair(h)}
        label = f"Crop {w:g}×{h:g}"
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"crop": crop}}], label)


_KEEP = object()


def set_grade(pid: str, item_id: str, *, lift=None, gamma=None, gain=None, sat=None, curves=_KEEP,
              temp=None, tint=None) -> dict:
    """Change a clip's grade: lift / gamma / gain per channel ([r, g, b]), saturation, and the
    custom curves ({"m"|"r"|"g"|"b": [[x, y], ...]}). Only the parts given change: the wheels
    send theirs and the curves are kept, the curve editor sends curves and the wheels are kept
    (``curves=None`` clears them). One set_props op: one undo step. See grade.py for the formula
    the render and the preview share; :func:`clear_grade` removes the whole grade."""
    doc, it = _item(pid, item_id)
    if it["type"] != "clip":
        raise EditorError("only a clip can be graded")
    cur = _GR.parse((it.get("props") or {}).get("grade")) or {**_GR.IDENTITY, "curves": None, "temp": 0.0, "tint": 0.0}
    curves_now = {k: [list(p) for p in pts] for k, pts in (cur.get("curves") or {}).items()} or None
    try:
        stored = _GR.store(
            lift=lift if lift is not None else cur["lift"],
            gamma=gamma if gamma is not None else cur["gamma"],
            gain=gain if gain is not None else cur["gain"],
            sat=sat if sat is not None else cur["sat"],
            curves=curves_now if curves is _KEEP else curves,
            temp=temp if temp is not None else cur.get("temp", 0.0),
            tint=tint if tint is not None else cur.get("tint", 0.0),
        )
    except (ValueError, TypeError) as exc:
        raise EditorError(str(exc)) from None
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"grade": stored, "look": None}}],
                 f"Grade {item_id}" if stored else f"Grade {item_id} reset")


def balance_to(pid: str, item_id: str, rgb) -> dict:
    """The eyedropper: set the clip's temperature and tint so ``rgb`` (0..255, the clip's own
    pixel before any grade) comes out grey. Everything else in the grade is kept."""
    try:
        r, g, b = (float(v) / 255.0 for v in rgb)
    except (TypeError, ValueError):
        raise EditorError("pick a colour: three numbers, 0 to 255") from None
    if min(r, g, b) <= 0.0:
        raise EditorError("that spot has no light in one channel; pick a brighter grey")
    temp, tint = _GR.neutralise((r, g, b))
    return set_grade(pid, item_id, temp=temp, tint=tint)


def clear_grade(pid: str, item_id: str) -> dict:
    """Remove a clip's whole grade: wheels, saturation and curves."""
    _, it = _item(pid, item_id)
    if it["type"] != "clip":
        raise EditorError("only a clip can be graded")
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"grade": None, "look": None}}], f"Grade {item_id} reset")


def set_transform(pid: str, item_id: str, *, x: float = 0.0, y: float = 0.0, scale: float = 1.0, rotate: float = 0.0) -> dict:
    """Position, scale, and rotate a clip's picture. Position is a fraction of the canvas,
    scale a positive multiplier, rotate an angle in degrees. Passing the identity clears the
    transform. Stored as [num, den] pairs, like the other props."""
    from fractions import Fraction

    def pair(v: float) -> list[int]:
        fr = Fraction(v).limit_denominator(1000)
        return [fr.numerator, fr.denominator]

    fx, fy, fs, fr_ = float(x), float(y), float(scale), float(rotate)
    if not (-4.0 <= fx <= 4.0 and -4.0 <= fy <= 4.0):
        raise EditorError("position must be within ±4 of the canvas")
    if not (0.01 <= fs <= 100.0):
        raise EditorError("scale must be between 0.01 and 100")
    if not (-3600.0 <= fr_ <= 3600.0):
        raise EditorError("rotate must be within ±3600 degrees")
    if fx == 0.0 and fy == 0.0 and fs == 1.0 and fr_ == 0.0:
        transform = None
        label = "Transform reset"
    else:
        transform = {"x": pair(fx), "y": pair(fy), "scale": pair(fs), "rotate": pair(fr_)}
        label = f"Transform {fs:g}×" if (fs != 1.0 and fx == 0 and fy == 0 and fr_ == 0) else "Transform"
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"transform": transform}}], label)


def set_keyframes(pid: str, item_id: str, keyframes: list[dict] | None) -> dict:
    """Set a clip's animated transform. Each keyframe is {at, x, y, scale, rotate} with `at`
    in seconds from the clip start; values match the transform's ranges. A single-element or
    empty list clears the animation (back to a static transform). Stored as [num, den] pairs
    and validated by the schema (increasing time, within range). Passing None clears it."""
    from fractions import Fraction

    def pair(v: float) -> list[int]:
        fr = Fraction(v).limit_denominator(1000)
        return [fr.numerator, fr.denominator]

    if not keyframes or len(keyframes) < 2:
        return apply(pid, [{"op": "set_props", "id": item_id, "props": {"keyframes": None}}], "Keyframes cleared")
    if len(keyframes) > 64:
        raise EditorError("at most 64 keyframes")
    out = []
    prev = None
    for kf in keyframes:
        at = float(kf.get("at", 0.0))
        fx, fy = float(kf.get("x", 0.0)), float(kf.get("y", 0.0))
        fs, fr_ = float(kf.get("scale", 1.0)), float(kf.get("rotate", 0.0))
        if not (-4.0 <= fx <= 4.0 and -4.0 <= fy <= 4.0):
            raise EditorError("position must be within ±4 of the canvas")
        if not (0.01 <= fs <= 100.0):
            raise EditorError("scale must be between 0.01 and 100")
        if not (-3600.0 <= fr_ <= 3600.0):
            raise EditorError("rotate must be within ±3600 degrees")
        ticks = T.seconds_to_ticks(at)
        if prev is not None and ticks <= prev:
            raise EditorError("keyframes must be in strictly increasing time order")
        prev = ticks
        out.append({"at": ticks, "x": pair(fx), "y": pair(fy), "scale": pair(fs), "rotate": pair(fr_)})
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"keyframes": out}}], f"Animate ({len(out)} keys)")


def set_speed_keys(pid: str, item_id: str, keys: list[dict] | None) -> dict:
    """Set a clip's speed ramp. Each key is {at, speed} with `at` in seconds from the clip's
    start and `speed` a multiplier (0.1 to 10). Between keys the speed ramps linearly; before
    the first and after the last key it holds that key's speed. A ramp replaces the clip's
    constant speed for the render; a single-key or empty list clears it (back to the constant
    props.speed). One set_props op: one undo step. See render_timeline._speed_ramp for how the
    render integrates it exactly."""
    from fractions import Fraction

    def pair(v: float) -> list[int]:
        fr = Fraction(v).limit_denominator(1000)
        return [fr.numerator, fr.denominator]

    if not keys or len(keys) < 2:
        # A ramp needs at least two keys to mean anything; fewer clears it. The constant speed
        # stays whatever it was, so a one-key "ramp" is just that constant.
        return _retime(pid, item_id, {"speed_keys": None, "ramp_at": None}, {"speed_keys": None, "ramp_at": None},
                       "Speed ramp cleared")
    if len(keys) > 64:
        raise EditorError("at most 64 speed keys")
    out = []
    prev = None
    for kf in keys:
        at = float(kf.get("at", 0.0))
        sp = float(kf.get("speed", 1.0))
        if not (0.1 <= sp <= 10.0):
            raise EditorError("speed must be between 0.1 and 10")
        ticks = T.seconds_to_ticks(at)
        if prev is not None and ticks <= prev:
            raise EditorError("speed keys must be in strictly increasing time order")
        prev = ticks
        out.append({"at": ticks, "speed": pair(sp)})
    # The clip's sound follows the same ramp, so picture and sound stay in step.
    # Keys are in this clip's own time, so any split offset into an older ramp is dropped.
    return _retime(pid, item_id, {"speed_keys": out, "ramp_at": None}, {"speed_keys": out, "ramp_at": None},
                   f"Speed ramp ({len(out)} keys)")


def _transitions_on(pid: str, item_id: str) -> list[dict]:
    """Every transition whose seam involves the given clip."""
    doc = _log(_dir(pid)).doc
    out = []
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it.get("type") == "transition" and item_id in (it.get("between") or []):
                out.append(it)
    return out


def lift(pid: str, item_id: str, *, ripple: bool = False) -> dict:
    return apply(pid, [{"op": "delete_clip", "id": item_id, "ripple": bool(ripple)}], f"Lift {item_id}")


def _known_ids(pid: str, ids: list, *, what: str = "item") -> list[str]:
    """Check a group of ids exists and is a list of distinct id strings before any op runs."""
    if not isinstance(ids, list) or not ids:
        raise EditorError(f"{what} ids must be a non-empty list")
    out = []
    for iid in ids:
        if not isinstance(iid, str):
            raise EditorError(f"every {what} id must be a string")
        if iid in out:
            raise EditorError(f"{iid!r} is listed twice")
        out.append(iid)
    have = {it["id"] for tr in _log(_dir(pid)).doc["tracks"] for it in tr["items"]}
    missing = [i for i in out if i not in have]
    if missing:
        raise EditorError(f"no such {what}: {', '.join(missing)}")
    return out


def _frames(doc: dict, seconds: float) -> int:
    """``seconds`` as ticks, rounded to the nearest whole frame of the project's rate.

    The page works in seconds rounded to 3 decimals, so frame maths done there drifts
    (20.033 - 1/30 lands a hair before 20 and collides with the clip that ends there).
    Relative edits (a nudge, a group move, a slip) snap here, in exact ticks, instead.
    """
    num, den = (doc.get("fps") or [30, 1])
    frame = Fraction(T.TICK_RATE * den, num)  # ticks per frame; whole at the supported rates
    return int(round(Fraction(seconds) * T.TICK_RATE / frame) * frame)


def _at_frame(doc: dict, seconds: float) -> int:
    """A timeline POINT (the playhead, an In mark) as ticks: the start of the frame that point
    is in. The page's clock floors (frameOf), so this is the frame the user sees under the
    playhead; lengths round instead (_frames)."""
    import math

    num, den = (doc.get("fps") or [30, 1])
    frame = Fraction(T.TICK_RATE * den, num)
    return int(math.floor(Fraction(seconds) * T.TICK_RATE / frame + Fraction(1, 10**6)) * frame)


def move_items(pid: str, ids: list[str], by_seconds: float) -> dict:
    """Move several items together by one offset (a group drag): one undo step for the group."""
    out = _known_ids(pid, ids)
    n = len(out)
    by = _frames(_log(_dir(pid)).doc, by_seconds)
    if by == 0:
        raise EditorError("that move is less than a frame")
    return apply(pid, [{"op": "move_items", "ids": out, "by": by}],
                 f"Move {n} item{'s' if n > 1 else ''} {by_seconds:+.2f}s")


def delete_items(pid: str, ids: list[str], *, ripple: bool = False) -> dict:
    """Delete several items as one step. With ``ripple``, later items close the holes."""
    out = _known_ids(pid, ids)
    n = len(out)
    return apply(pid, [{"op": "delete_items", "ids": out, "ripple": bool(ripple)}],
                 f"{'Ripple' if ripple else 'Lift'} {n} item{'s' if n > 1 else ''}")


DEMO = "demo"


def reset(pid: str = DEMO) -> dict:
    """Rebuild the demo project from scratch. Only the demo: a reset deletes the project's
    folder (media, history, transcript), and this used to run for any project the page or an
    API call named, so the inspector's "Reset demo" button would have wiped a real film."""
    if pid != DEMO:
        raise EditorError("reset only rebuilds the demo project; use undo on a film")
    folder = _dir(pid)
    with _locked(folder):
        # Clear everything but the lock file we hold, then build the demo again in place.
        for child in folder.iterdir():
            if child.name == ".lock":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        return create(pid)


def split(pid: str, item_id: str, at_seconds: float) -> dict:
    at = T.seconds_to_ticks(at_seconds)
    return apply(pid, [{"op": "split_clip", "id": item_id, "at": at}], f"Split {item_id}")


def _latest(log: O.Oplog, *, redo: bool) -> str:
    """The entry the next undo or redo acts on, with the stack rules every editor uses.

    The op log can undo any entry, including an undo (that is what a redo is) or a redo. So an
    entry is a *do* or an *undo* by its chain: a fresh edit is a do; undoing a do is an undo;
    undoing an undo (a redo) is a do again. Entries something else has undone are skipped.

    Undo takes the newest live do (a fresh edit or a redo). Redo takes the newest live undo,
    walking back past redos, but stops at a fresh edit: a new edit after an undo clears the
    redo stack. (It used to treat every entry with ``undoes`` as redoable, so a second redo
    "redid" the first redo -- undoing it -- and an undo after a redo skipped the redone step
    and undid an older edit.)
    """
    entries = log.history_list(0)
    by_id = {e["op_id"]: e for e in entries}
    undone = {oid for e in entries for oid in (e.get("undoes") or [])}
    kind: dict[str, str] = {}

    def kind_of(e: dict) -> str:
        oid = e["op_id"]
        if oid not in kind:
            targets = [by_id[t] for t in (e.get("undoes") or []) if t in by_id]
            kind[oid] = "do" if not targets else ("undo" if kind_of(targets[0]) == "do" else "do")
        return kind[oid]

    for e in reversed(entries):
        if e["op_id"] in undone:
            continue
        k = kind_of(e)
        if not redo and k == "do":
            return e["op_id"]
        if redo:
            if k == "undo":
                return e["op_id"]
            if not e.get("undoes"):
                break  # a fresh edit: nothing left to redo
    raise EditorError("nothing to redo" if redo else "nothing to undo")


def undo(pid: str) -> dict:
    return _call(pid, "history_undo", lambda log: {"client_op_id": _cid(), "op_id": _latest(log, redo=False)})


def redo(pid: str) -> dict:
    return _call(pid, "history_redo", lambda log: {"client_op_id": _cid(), "op_id": _latest(log, redo=True)})


def source_time(doc: dict, seconds: float) -> tuple[str, float] | None:
    """Timeline seconds to (media id, source seconds) on the main track. None in a gap."""
    ticks = T.seconds_to_ticks(seconds)
    rate = doc["tick_rate"]
    for tr in doc["tracks"]:
        if tr.get("role") != "main":
            continue
        for it in tr["items"]:
            if it.get("type") != "clip" or "at" not in it or "src" not in it:
                continue
            start, dur = it["at"], T.item_duration(it)
            if start <= ticks < start + dur:
                # Speed, ramps (and reverse) map through the one time rule the render uses.
                return it["media"], (it["src"][0] + T.source_offset(it, ticks - start)) / rate
    return None


def resolve_media(folder: Path, rel: str) -> Path:
    """A project-relative media path. Absolute paths and '..' are refused."""
    parts = Path(rel or "").parts
    if not parts or Path(rel).is_absolute() or ".." in parts:
        raise EditorError("media path leaves the project")
    path = (folder / rel).resolve()
    root = folder.resolve()
    if path != root and root not in path.parents:
        raise EditorError("media path leaves the project")
    return path


def _ensure_demo_plate(folder: Path, path: Path) -> None:
    """Draw the demo plate once, under the project lock. The page asks for a frame and for the
    file at the same moment after a reset; unlocked, both drew into one temp file and one of
    the two requests failed (a 404 picture on a fresh demo)."""
    with _locked(folder):
        if not path.is_file():
            _demo_plate(path)


def _demo_plate(dest: Path) -> None:
    """A short 9:16 plate so the demo has a real picture. Not a stand-in for a user's film."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name("." + dest.stem + ".tmp" + dest.suffix)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            # As long as the media entry says (120 s), so a slip or slow-down never runs off it.
            "testsrc2=size=360x640:rate=15:duration=120",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(tmp),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise EditorError("could not draw the preview plate")
    tmp.replace(dest)


def frame_jpeg(pid: str, seconds: float) -> bytes:
    """One JPEG at the playhead. The file must live inside the project."""
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    doc = _log(folder).doc
    hit = source_time(doc, max(0.0, seconds))
    if not hit:
        raise EditorError("no picture at this time")
    media_id, src_s = hit
    return _media_jpeg(folder, doc, media_id, src_s)


def media_frame(pid: str, media_id: str, seconds: float) -> bytes:
    """One JPEG of a bin file at a source second (the bin thumbnail; the source viewer's still).
    The same per-media cache as the playhead frame."""
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    doc = _log(folder).doc
    m = doc.get("media", {}).get(media_id)
    if not isinstance(m, dict):
        raise EditorError("no such media")
    return _media_jpeg(folder, doc, media_id, max(0.0, min(float(seconds), m["dur"] / doc["tick_rate"] - 0.04)))


def _media_jpeg(folder: Path, doc: dict, media_id: str, src_s: float) -> bytes:
    rel = str(doc.get("media", {}).get(media_id, {}).get("path") or "")
    path = resolve_media(folder, rel)
    if not path.is_file():
        if rel == "media/talk.mp4" and doc.get("id") == DEMO:
            _ensure_demo_plate(folder, path)
        else:
            raise EditorError("picture file is missing")
    # One still per SOURCE FRAME (the file's own rate), not per fifth of a second: a paused
    # frame used to be up to three frames off what the render shows.
    m = doc.get("media", {}).get(media_id, {})
    mf = m.get("fps") or [30, 1]
    rate_f = mf[0] / mf[1] if mf[1] else 30.0
    slot = max(0, int(src_s * rate_f + 1e-6))
    # Seek a quarter frame BEFORE the frame: an accurate -ss drops every frame that starts
    # earlier than the seek, so aiming mid-frame handed back the next frame.
    src_s = max(0.0, (slot - 0.25) / rate_f)
    # Keyed by media as well as time: two clips from different files at the same source second
    # used to share one cached JPEG, so the preview showed the other file's picture. The media
    # id is made filename-safe (ids are free strings); a hash keeps two ids from colliding.
    import hashlib as _hl

    mkey = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(media_id))[:40]
    mkey += "-" + _hl.sha1(str(media_id).encode()).hexdigest()[:8]
    cache = folder / "frames" / mkey / f"f{slot:07d}.jpg"
    if not cache.is_file() or cache.stat().st_size < 100:
        cache.parent.mkdir(parents=True, exist_ok=True)
        # A temp name of its own: two requests for one frame (the playhead still and a bin
        # thumbnail, say) used to write the same temp file and one of them failed.
        tmp = cache.with_name(f".{cache.stem}.{secrets.token_hex(4)}.tmp.jpg")
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{src_s:.6f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "5",
                str(tmp),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0 or not tmp.is_file():
            tmp.unlink(missing_ok=True)
            raise EditorError("could not read that frame")
        tmp.replace(cache)
    return cache.read_bytes()


def write_import(pid: str, title: str, placed: list[tuple[str, float, str]]) -> dict:
    """Lay named clips end to end. Each tuple is (filename, seconds, title)."""
    if not placed:
        raise EditorError("that run has no picture")
    d = T.new_timeline(pid)
    media: dict = {}
    v_items: list[dict] = []
    a_items: list[dict] = []
    t_items: list[dict] = []
    at = 0
    for i, (name, seconds, label) in enumerate(placed, 1):
        ticks = T.seconds_to_ticks(seconds)
        if ticks <= 0:
            raise EditorError("a clip has no length")
        mid = f"m{i}"
        media[mid] = {"path": f"media/{name}", "dur": ticks, "fps": [30, 1]}
        v_items.append({"id": f"c{i}", "type": "clip", "media": mid, "src": [0, ticks], "at": at, "fade_in": 0, "fade_out": 0})
        a_items.append({"id": f"a{i}", "type": "clip", "media": mid, "src": [0, ticks], "at": at, "fade_in": 0, "fade_out": 0})
        text = " ".join((label or "").split())[:80]
        if text:
            t_items.append(
                {
                    "id": f"x{i}",
                    "type": "text",
                    "dur": min(ticks, T.seconds_to_ticks(8)),
                    "text": text,
                    "style": "pop",
                    "fade_in": 0,
                    "fade_out": 0,
                    "at": at,
                }
            )
        at += ticks
    by_id = {t["id"]: t for t in d["tracks"]}
    d["media"] = media
    by_id["V1"]["items"] = v_items
    by_id["A1"]["items"] = a_items
    by_id["T1"]["items"] = t_items
    d, _ = T.stamp_hash(d)
    folder = _dir(pid)
    with _locked(folder):
        (folder / "base.json").write_text(json.dumps(d))
        # An imported cut starts with an empty log, but the log file must exist: without it
        # the film has no history surface until somebody happens to make an edit.
        log = O.Oplog(d, path=folder / "oplog.jsonl")
        (folder / "oplog.jsonl").touch(exist_ok=True)
        _save_current(folder, log.doc)
    out = view(log.doc)
    out["summary"] = f"Opened {title}"[:120]
    out["title"] = title
    return out


def _run_clips(folder: Path) -> list[Path]:
    root = folder.resolve()
    found = []
    for p in sorted(root.glob("clip-*.mp4")):
        if not p.is_file() or ".trash" in p.parts:
            continue
        rp = p.resolve()
        if root not in rp.parents:
            continue
        found.append(rp)
    return found


def list_films() -> list[dict]:
    from hermes_studio.pipeline import library_root, list_jobs

    lib = library_root().resolve()
    out = []
    for job in list_jobs():
        if (job.title or "") == "demo-cli-test":
            continue
        run = Path(job.dir).resolve()
        if lib not in run.parents:
            continue
        clips = _run_clips(run)
        if not clips:
            continue
        out.append({"id": job.id, "title": job.title or job.id, "clips": len(clips)})
    return out


WAVE_RATE = 50  # peaks per second of source audio
_WAVE_HZ = 8000  # decode rate; 160 samples per peak is plenty for a drawn envelope


def waveform(pid: str, media_id: str) -> dict:
    """The audio envelope of one media file: WAVE_RATE peaks per source second.

    Each peak is the loudest sample in its slot on a linear 0..1000 scale (full scale =
    1000), so a quiet file draws quiet -- the page maps it to dB for display. Peaks are
    cached next to the project, keyed on the file's size and mtime. A file with no audio
    stream returns no peaks and ``silent: True`` rather than an error.
    """
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    doc = _log(folder).doc
    media = doc.get("media", {}).get(media_id)
    if not isinstance(media, dict):
        raise EditorError("no such media")
    path = resolve_media(folder, str(media.get("path") or ""))
    if not path.is_file():
        return {"media": media_id, "rate": WAVE_RATE, "peaks": [], "silent": True}
    st = path.stat()
    key = f"{st.st_size}:{int(st.st_mtime)}"
    cache = folder / "waves" / f"{media_id}.json"
    if cache.is_file():
        try:
            hit = json.loads(cache.read_text())
            if hit.get("key") == key:
                return {k: hit[k] for k in ("media", "rate", "peaks", "silent")}
        except (OSError, ValueError, KeyError):
            pass
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(_WAVE_HZ), "-f", "s16le", "-"],
        capture_output=True,
        timeout=180,
    )
    import array
    import sys

    pcm = array.array("h")
    if proc.returncode == 0:
        pcm.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
        if sys.byteorder == "big":
            pcm.byteswap()
    step = _WAVE_HZ // WAVE_RATE
    peaks = [
        min(1000, max(max(s), -min(s)) * 1000 // 32768)
        for s in (pcm[i : i + step] for i in range(0, len(pcm), step))
    ]
    out = {"media": media_id, "rate": WAVE_RATE, "peaks": peaks, "silent": not peaks or max(peaks) == 0}
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name("." + cache.name + ".tmp")
    tmp.write_text(json.dumps({**out, "key": key}))
    tmp.replace(cache)
    return out


# What the desk will serve from a project's media folder, and as what. Sound files are here
# because music tracks hold them and the preview mixer has to fetch them.
MEDIA_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac",
}


def project_media(pid: str, name: str) -> Path:
    if Path(name).name != name or Path(name).suffix.lower() not in MEDIA_TYPES:
        raise EditorError("bad media name")
    path = resolve_media(_dir(pid), f"media/{name}")
    if not path.is_file() and pid == DEMO and name == "talk.mp4":
        # The demo's plate is drawn on first use. frame_jpeg drew it, but playback asks for the
        # file directly, so a freshly reset demo handed the <video> a 404 and Play did nothing.
        _ensure_demo_plate(_dir(pid), path)
    if not path.is_file():
        raise EditorError("no such picture")
    return path


def _copy_transcript(run: Path, dest: Path, placed: list[dict]) -> None:
    """Carry the run's own words into the project, timed to the cut.

    Each clip was cut from a window of the source, so a word only belongs on the
    timeline if the source said it inside that window. Assuming every clip starts at
    source zero would give every clip the same opening words.
    """
    src = run / "work" / "transcript.json"
    if not src.is_file():
        return
    try:
        data = json.loads(src.read_text())
    except (OSError, ValueError):
        return
    words = [w for w in (data.get("words") or []) if isinstance(w, dict) and "start" in w and "end" in w]
    if not words:
        return
    at = 0.0
    out: list[dict] = []
    for clip in placed:
        start, end = float(clip["start"]), float(clip["end"])
        for w in words:
            s, e = float(w["start"]), float(w["end"])
            if e <= start or s >= end:
                continue
            out.append(
                {
                    "text": str(w.get("text") or "").strip(),
                    "start": round(at + max(0.0, s - start), 3),
                    "end": round(at + min(end - start, e - start), 3),
                }
            )
        at += end - start
    out = [w for w in out if w["text"] and w["end"] > w["start"]]
    if not out:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"source": str(src), "words": out}, separators=(",", ":")))


def history(pid: str, since_version: int = 0) -> list[dict]:
    """Who did what to this cut, oldest first. Empty history is an empty list, not an error."""
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    out = []
    for e in _log(folder).history_diff(max(0, int(since_version))):
        actor = e.get("actor") or {}
        kind = str(actor.get("kind") or "human")
        who = str(actor.get("id") or "unknown")
        out.append(
            {
                "seq": e.get("seq"),
                "summary": str(e.get("summary") or ""),
                "actor": who,
                "kind": kind,
                "step": e.get("step"),
                "from": e.get("base_version"),
                "to": e.get("new_version"),
                "ids": list(e.get("changed_ids") or []),
                "undone": bool(e.get("undoes")),
            }
        )
    return out


def transcript(pid: str) -> list[dict]:
    """Words on the timeline, in order. Empty when the cut has no words to show."""
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    path = folder / "transcript.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    words = []
    for w in data.get("words") or []:
        if not isinstance(w, dict):
            continue
        try:
            s, e = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        text = " ".join(str(w.get("text") or "").split())
        if text and e > s:
            words.append({"start": round(s, 3), "end": round(e, 3), "text": text})
    words.sort(key=lambda w: (w["start"], w["end"]))
    return words


def import_run(job_id: str) -> dict:
    """Copy a library run's clips into a project and open that cut. Does not read outside the library."""
    if not T.ID_RE.fullmatch(job_id or ""):
        raise EditorError("bad project id")
    folder = _dir(job_id)
    if (folder / "base.json").exists():
        opened = open_project(job_id)
        opened["summary"] = "Opened the cut."
        return opened
    from hermes_studio.pipeline import library_root, load_job

    job = load_job(job_id)
    if not job:
        raise EditorError("no such film")
    run = Path(job.dir).resolve()
    lib = library_root().resolve()
    if lib not in run.parents:
        raise EditorError("that film is not in the library")
    clips = _run_clips(run)
    if not clips:
        raise EditorError("that run has no picture")
    titles = {str(c.get("file") or ""): str(c.get("title") or "") for c in (job.clips or [])}
    by_file = {str(c.get("file") or ""): c for c in (job.clips or [])}
    (folder / "media").mkdir(parents=True, exist_ok=True)
    placed: list[dict] = []
    for i, src in enumerate(clips, 1):
        name = f"c{i:02d}.mp4"
        dest = folder / "media" / name
        if not dest.exists():
            shutil.copy2(src, dest)
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            raise EditorError("could not read the film")
        seconds = float(proc.stdout.strip() or "0")
        # The run knows where in the source this clip came from; that window is what
        # makes the transcript land under the right picture.
        meta = by_file.get(src.name) or {}
        try:
            start, end = float(meta.get("start") or 0.0), float(meta.get("end") or 0.0)
        except (TypeError, ValueError):
            start, end = 0.0, 0.0
        if end <= start:
            start, end = 0.0, seconds
        placed.append({"name": name, "seconds": seconds, "title": titles.get(src.name) or src.stem, "start": start, "end": end})
    out = write_import(job_id, job.title or job_id, [(c["name"], c["seconds"], c["title"]) for c in placed])
    _copy_transcript(run, folder / "transcript.json", placed)
    out["words"] = len(transcript(job_id))
    return out
