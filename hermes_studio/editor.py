"""Desk Edit page store. The op log is the only writer (docs/oplog.md).

A project is a folder: base.json (version 0), oplog.jsonl, timeline.json (the current doc).
The desk and tests call open / apply / undo / redo. Nothing else writes the timeline.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
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
                media = doc.get("media", {}).get(it.get("media") or "", {})
                if media.get("dur"):
                    row["media_dur"] = round(media["dur"] / rate, 3)
                row["file"] = Path(str(media.get("path") or "")).name
            items.append(row)
        tracks.append({"id": tr["id"], "role": tr["role"], "items": items})
    return {
        "id": doc["id"],
        "version": doc["version"],
        "hash": doc["hash"],
        "duration": round(end, 3) or 1,
        "size": list(doc.get("size") or [1920, 1080]),
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


def reset(pid: str = "demo") -> dict:
    folder = _dir(pid)
    if folder.exists():
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


def project_media(pid: str, name: str) -> Path:
    if Path(name).name != name or Path(name).suffix.lower() not in {".mp4", ".webm", ".mov", ".mkv"}:
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
