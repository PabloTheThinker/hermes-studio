"""Desk Edit page store. The op log is the only writer (docs/oplog.md).

A project is a folder: base.json (version 0), oplog.jsonl, timeline.json (the current doc).
The desk and tests call open / apply / undo / redo. Nothing else writes the timeline.
"""

from __future__ import annotations

import json
import math
import os
import secrets
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from hermes_studio import oplog as O
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
                span_a_dur = (span_a["src"][1] - span_a["src"][0]) / clip_speed(span_a)
                at = span_a.get("at", 0) + span_a_dur - it.get("dur", 0)
                items.append(
                    {
                        "id": it["id"],
                        "type": "transition",
                        "kind": it.get("kind", "xfade"),
                        "at": round(at / rate, 3),
                        "dur": round(it.get("dur", 0) / rate, 3),
                        "between": [a_id, b_id],
                        "label": "Dissolve",
                    }
                )
                continue
            speed = clip_speed(it) if it["type"] == "clip" else 1.0
            at = it.get("at", 0) / rate
            # A clip occupies (source range) / speed ticks on the timeline; text keeps dur.
            dur = ((it["src"][1] - it["src"][0]) / speed if it["type"] == "clip" else it.get("dur", 0)) / rate
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
            if it["type"] == "clip" and "src" in it:
                row["src_in"] = round(it["src"][0] / rate, 3)
                row["src_out"] = round(it["src"][1] / rate, 3)
                row["speed"] = round(speed, 4)
                props = it.get("props") or {}
                row["look"] = props.get("look") or None
                row["volume"] = _pair_to_float(props.get("volume"))
                row["crop"] = _crop_view(props.get("crop"))
                row["transform"] = _transform_view(props.get("transform"))
                row["keyframes"] = _keyframes_view(props.get("keyframes"), rate)
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
    folder.mkdir(parents=True, exist_ok=True)
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


def _call(pid: str, tool: str, args: dict) -> dict:
    folder = _dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    log = _log(folder)
    try:
        result = log.call(HUMAN, tool, args)
    except O.OplogError as exc:
        raise EditorError(exc.message) from exc
    _save_current(folder, log.doc)
    out = view(log.doc)
    out["summary"] = result.get("summary") or tool
    return out


def apply(pid: str, ops: list[dict], summary: str) -> dict:
    folder = _dir(pid)
    log = _log(folder)
    return _call(
        pid,
        "timeline_apply",
        {
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


def set_transition(pid: str, a_id: str, b_id: str, seconds: float = 0.0) -> dict:
    """Cross-dissolve (or remove it) between two consecutive clips. dur 0 = a hard cut."""
    dur = max(0, T.seconds_to_ticks(seconds))
    return apply(pid, [{"op": "set_transition", "between": [a_id, b_id], "dur": dur}],
                 f"Dissolve {seconds:g}s" if dur else "Hard cut")


def set_canvas(pid: str, width: int, height: int) -> dict:
    w, h = int(width), int(height)
    if not (1 <= w <= 16384 and 1 <= h <= 16384):
        raise EditorError("canvas must be 1 to 16384 on each side")
    return apply(pid, [{"op": "set_canvas", "width": w, "height": h}], f"Canvas {w}×{h}")


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

    ops: list[dict] = []
    # Any transition touching this clip is removed (dur 0 == a hard cut) before the retime.
    for tr in _transitions_on(pid, item_id):
        a_id, b_id = tr["between"]
        ops.append({"op": "set_transition", "between": [a_id, b_id], "dur": 0})
    ops.append({"op": "set_props", "id": item_id, "props": {"speed": pair}})
    return apply(pid, ops, f"Speed {s:g}×")


def set_look(pid: str, item_id: str, look: str | None) -> dict:
    """Apply a named colour grade to a clip, or clear it (None). The render maps the name to
    an eq/colorbalance chain; an unknown name is refused here rather than silently ignored."""
    from hermes_studio.render_timeline import _LOOKS

    name = (look or "").strip().lower() or None
    if name is not None and name not in _LOOKS:
        raise EditorError(f"unknown look {look!r}; choose from {', '.join(sorted(_LOOKS))}")
    return apply(pid, [{"op": "set_props", "id": item_id, "props": {"look": name}}], f"Look {name or 'none'}")


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
              gain: float | None = None) -> dict:
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


def reset(pid: str = "demo") -> dict:
    folder = _dir(pid)
    if folder.exists():
        shutil.rmtree(folder)
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
    log = _log(_dir(pid))
    return _call(pid, "history_undo", {"client_op_id": _cid(), "op_id": _latest(log, redo=False)})


def redo(pid: str) -> dict:
    log = _log(_dir(pid))
    return _call(pid, "history_redo", {"client_op_id": _cid(), "op_id": _latest(log, redo=True)})


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
            start, dur = it["at"], it["src"][1] - it["src"][0]
            if start <= ticks < start + dur:
                return it["media"], (it["src"][0] + (ticks - start)) / rate
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


def _demo_plate(dest: Path) -> None:
    """A short 9:16 plate so the demo has a real picture. Not a stand-in for a user's film."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=360x640:rate=15:duration=70",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0 or not dest.is_file():
        raise EditorError("could not draw the preview plate")


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
    rel = str(doc.get("media", {}).get(media_id, {}).get("path") or "")
    path = resolve_media(folder, rel)
    if not path.is_file():
        if rel == "media/talk.mp4":
            _demo_plate(path)
        else:
            raise EditorError("picture file is missing")
    slot = max(0, int(round(src_s * 5)))
    cache = folder / "frames" / f"{slot:05d}.jpg"
    if not cache.is_file() or cache.stat().st_size < 100:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name("." + cache.stem + ".tmp.jpg")
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{src_s:.3f}",
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
    folder.mkdir(parents=True, exist_ok=True)
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
