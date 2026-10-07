"""Desk Edit page store. The op log is the only writer (docs/oplog.md).

A project is a folder: base.json (version 0), oplog.jsonl, timeline.json (the current doc).
The desk and tests call open / apply / undo / redo. Nothing else writes the timeline.
"""

from __future__ import annotations

import json
import os
import secrets
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
    tracks = []
    end = 0.0
    for tr in doc["tracks"]:
        items = []
        for it in tr["items"]:
            if it["type"] == "transition":
                continue
            at = it.get("at", 0) / rate
            dur = ((it["src"][1] - it["src"][0]) if it["type"] == "clip" else it.get("dur", 0)) / rate
            end = max(end, at + dur)
            label = it.get("text") or it["id"]
            if it["type"] == "clip":
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
                media = doc.get("media", {}).get(it.get("media") or "", {})
                if media.get("dur"):
                    row["media_dur"] = round(media["dur"] / rate, 3)
            items.append(row)
        tracks.append({"id": tr["id"], "role": tr["role"], "items": items})
    return {
        "id": doc["id"],
        "version": doc["version"],
        "hash": doc["hash"],
        "duration": round(end, 3) or 1,
        "tracks": tracks,
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


def move(pid: str, item_id: str, at_seconds: float) -> dict:
    at = max(0, T.seconds_to_ticks(at_seconds))
    return apply(pid, [{"op": "move_clip", "id": item_id, "at": at}], f"Move {item_id}")


def lift(pid: str, item_id: str, *, ripple: bool = False) -> dict:
    return apply(pid, [{"op": "delete_clip", "id": item_id, "ripple": bool(ripple)}], f"Lift {item_id}")


def reset(pid: str = "demo") -> dict:
    folder = _dir(pid)
    if folder.exists():
        import shutil

        shutil.rmtree(folder)
    return create(pid)


def split(pid: str, item_id: str, at_seconds: float) -> dict:
    at = T.seconds_to_ticks(at_seconds)
    return apply(pid, [{"op": "split_clip", "id": item_id, "at": at}], f"Split {item_id}")


def _latest(log: O.Oplog, *, redo: bool) -> str:
    entries = log.history_list(0)
    undone = {oid for e in entries for oid in (e.get("undoes") or [])}
    for e in reversed(entries):
        if e["op_id"] in undone:
            continue
        if redo and e.get("undoes"):
            return e["op_id"]
        if not redo and not e.get("undoes"):
            return e["op_id"]
    raise EditorError("nothing to redo" if redo else "nothing to undo")


def undo(pid: str) -> dict:
    log = _log(_dir(pid))
    return _call(pid, "history_undo", {"client_op_id": _cid(), "op_id": _latest(log, redo=False)})


def redo(pid: str) -> dict:
    log = _log(_dir(pid))
    return _call(pid, "history_redo", {"client_op_id": _cid(), "op_id": _latest(log, redo=True)})
