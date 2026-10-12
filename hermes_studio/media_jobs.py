"""S4 media import on the engine: probe, ``add_media`` through the log, then derived files in the
background with progress on the project's event stream.

The import itself is one ordinary log entry (``add_media``), so it is undoable, replays and shows
up as ``op.applied`` like any other write. The derived files (proxy, thumbnails, waveform, words)
are cache: they live under ``<project>/cache/`` and never change the timeline. Their progress is
sent to the project's SSE clients as ``media.progress`` / ``media.ready`` / ``media.failed``
events. Those carry no ``id`` (they are not log entries), so ``Last-Event-ID`` never replays them;
``media_status`` is the durable record (``cache/media/<id>.json``).
"""

from __future__ import annotations

import contextlib
import math
import queue
import secrets
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

from hermes_studio import media as M
from hermes_studio import oplog as O
from hermes_studio import project as P
from hermes_studio import timeline as T
from hermes_studio.api import HermesStudioError

# How much of the overall bar each stage takes (words is slow; it only counts when asked for).
WEIGHTS = {"proxy": 0.6, "thumbs": 0.2, "wave": 0.2, "scenes": 0.1, "words": 1.0}
PROGRESS_EVERY_SEC = 0.25
WORKERS = 2


def _bad(path: str, rule: str, message: str) -> O.OplogError:
    return O.OplogError("invalid_op", message, rule=rule, path=path)


def _stages(args: dict) -> list[str]:
    raw = args.get("stages", ["proxy", "thumbs", "wave"])
    if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
        raise _bad("/stages", "bad_arg", "'stages' must be a list of: " + ", ".join(M.STAGES))
    for i, s in enumerate(raw):
        if s not in M.STAGES:
            raise _bad(f"/stages/{i}", "bad_arg", f"unknown stage {s!r}; use: " + ", ".join(M.STAGES))
    return [s for s in M.STAGES if s in raw]  # fixed order, no repeats


def _source(raw: Any) -> Path:
    from hermes_studio.download import local_source

    if not isinstance(raw, str) or not raw.strip():
        raise _bad("/path", "bad_arg", "'path' must be a local video or audio file")
    if "://" in raw:
        raise _bad("/path", "bad_arg", "import takes a local file; download links with `hermes-studio run` first")
    try:
        return Path(local_source(raw.strip()))
    except FileNotFoundError:
        raise O.OplogError("not_found", f"no file {raw!r}", rule="not_found", path="/path") from None
    except (ValueError, OSError) as e:
        raise _bad("/path", "bad_arg", str(e)[:200] or "not a video or audio file") from None


class Status:
    """``cache/media/<id>.json``: the durable state of one media's derived files."""

    def __init__(self, project_dir: Path, mid: str, stages: list[str], info: dict) -> None:
        self.paths = M.cache_paths(project_dir, mid)
        self.data: dict[str, Any] = {
            "media_id": mid,
            "state": "queued",
            "progress": 0.0,
            "stage": None,
            "error": None,
            "probe": info,
            "stages": {s: {"state": "queued"} for s in stages},
        }
        self.save()

    def save(self) -> None:
        M._write_json(self.paths["status"], self.data)


def read_status(project_dir: Path, mid: str, live: set[str]) -> dict | None:
    """The stored status; a ``running``/``queued`` one that no worker in this engine owns (the
    app was closed mid-import) reads as ``interrupted``."""
    data = M.read_json(M.cache_paths(project_dir, mid)["status"])
    if not isinstance(data, dict):
        return None
    if data.get("state") in ("queued", "running") and mid not in live:
        data["state"] = "interrupted"
    return data


class MediaJobs:
    """A small worker pool on the engine. One job per (project, media)."""

    def __init__(self, workers: int = WORKERS) -> None:
        self.q: queue.Queue = queue.Queue()
        self.live: dict[str, set[str]] = {}  # project id -> media ids queued or running here
        self.cancelled: set[tuple[str, str]] = set()
        self.lock = threading.Lock()
        self.threads = [threading.Thread(target=self._work, daemon=True, name=f"media-{i}") for i in range(workers)]
        for t in self.threads:
            t.start()

    def live_for(self, pid: str) -> set[str]:
        with self.lock:
            return set(self.live.get(pid, ()))

    def submit(self, proj: P.Project, mid: str, src: Path, info: dict, stages: list[str], model: str) -> dict:
        st = Status(proj.dir, mid, stages, info)
        with self.lock:
            self.live.setdefault(proj.id, set()).add(mid)
            self.cancelled.discard((proj.id, mid))
        self.q.put((proj, mid, src, info, stages, model, st))
        return st.data

    def cancel_project(self, pid: str) -> None:
        with self.lock:
            for mid in self.live.get(pid, ()):
                self.cancelled.add((pid, mid))

    def _work(self) -> None:
        while True:
            job = self.q.get()
            try:
                self._run(*job)
            except Exception:  # a worker never dies; _run records failures itself
                pass
            finally:
                with self.lock:
                    self.live.get(job[0].id, set()).discard(job[1])

    def _run(self, proj: P.Project, mid: str, src: Path, info: dict, stages: list[str], model: str, st: Status) -> None:
        total = sum(WEIGHTS[s] for s in stages) or 1.0
        done_w = 0.0
        last = [0.0]

        def cancel() -> bool:
            with self.lock:
                return (proj.id, mid) in self.cancelled

        def send(ev: dict) -> None:
            proj.notify({"type": ev.pop("type"), "project_id": proj.id, "media_id": mid, **ev})

        def progress(stage: str, frac: float) -> None:
            overall = round((done_w + WEIGHTS[stage] * frac) / total, 4)
            st.data.update(progress=overall, stage=stage)
            st.data["stages"][stage]["progress"] = round(frac, 4)
            now = time.monotonic()
            if frac >= 1.0 or now - last[0] >= PROGRESS_EVERY_SEC:
                last[0] = now
                st.save()
                send({"type": "media.progress", "stage": stage, "stage_progress": round(frac, 4), "progress": overall})

        st.data["state"] = "running"
        st.save()
        p = st.paths
        failed: list[str] = []
        for stage in stages:
            st.data["stages"][stage] = {"state": "running", "progress": 0.0}
            try:
                if stage == "proxy":
                    M.make_proxy(src, p["proxy"], info, progress, cancel)
                    out = {"path": str(p["proxy"].relative_to(proj.dir).as_posix())}
                elif stage == "thumbs":
                    out = M.make_thumbs(src, p["thumbs"], p["thumbs_index"], info, progress, cancel)
                elif stage == "wave":
                    out = M.make_wave(src, p["wave"], info, progress, cancel)
                elif stage == "scenes":
                    out = M.make_scenes(src, p["scenes"], info, progress, cancel)
                else:
                    work = proj.dir / "cache" / "work" / mid
                    work.mkdir(parents=True, exist_ok=True)
                    out = M.make_words(src, p["words"], work, model, progress)
                st.data["stages"][stage] = {"state": "ready", "progress": 1.0, **out}
            except HermesStudioError as e:
                if cancel():
                    st.data.update(state="cancelled", error=None)
                    st.save()
                    return
                failed.append(stage)
                st.data["stages"][stage] = {"state": "failed", "error": e.message}
                send({"type": "media.failed", "stage": stage, "error": e.message})
            except Exception as e:  # noqa: BLE001 - a stage that crashes is a failed stage, not a dead worker
                failed.append(stage)
                st.data["stages"][stage] = {"state": "failed", "error": f"{type(e).__name__}: {e}"[:300]}
                send({"type": "media.failed", "stage": stage, "error": st.data["stages"][stage]["error"]})
            done_w += WEIGHTS[stage]
            st.save()
        st.data.update(
            state="failed" if failed and len(failed) == len(stages) else "ready",
            progress=1.0,
            stage=None,
            error=(f"{', '.join(failed)} failed" if failed else None),
        )
        st.save()
        send(
            {
                "type": "media.ready",
                "state": st.data["state"],
                "failed": failed,
                "stages": {k: v["state"] for k, v in st.data["stages"].items()},
            }
        )


def import_media(proj: P.Project, session: O.Session, args: Any, jobs: MediaJobs) -> dict:
    """``import_media{path, client_op_id?, id?, stages?, whisper?}``: probe, then one ``add_media``
    entry, then the derived files in the background. Returns the write result plus ``media_id``,
    the probe and the initial status. A retry with the same ``client_op_id`` returns the cached
    write and does not start a second job."""
    from hermes_studio import gate

    gate.refuse_in_ask(proj, session)
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    known = {"path", "client_op_id", "id", "stages", "whisper", "summary"}
    for k in sorted(args, key=repr):
        if k not in known:
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument {k!r}")
    stages = _stages(args)
    model = args.get("whisper", "tiny")
    if not isinstance(model, str) or model not in ("tiny", "base", "small", "medium"):
        raise _bad("/whisper", "bad_arg", "'whisper' must be one of tiny, base, small, medium")
    src = _source(args.get("path"))
    info = M.probe(src)
    if not info["has_video"]:
        stages = [s for s in stages if s not in ("thumbs", "scenes")]
    if not info["has_audio"]:
        stages = [s for s in stages if s not in ("wave", "words")]
    op: dict[str, Any] = {"op": "add_media", **M.media_entry(src, info)}
    if "id" in args:
        op["id"] = args["id"]
    with proj.mutex:
        log = proj.oplog()
        call = {
            "client_op_id": args["client_op_id"] if "client_op_id" in args else f"import-{secrets.token_hex(8)}",
            "base_version": log.version,
            "summary": args["summary"] if "summary" in args else unicodedata.normalize("NFC", f"Import {src.name}")[:200],
            "ops": [op],
        }
        actor = (session.actor.kind, session.actor.id)
        prior = next(
            (
                e
                for e in log._entries
                if (e["actor"]["kind"], e["actor"]["id"]) == actor and e["client_op_id"] == call["client_op_id"]
            ),
            None,
        )
        if prior is not None:  # a retry: the engine's dedupe needs the call as first sent
            call["base_version"] = prior["base_version"]
        before = len(log._entries)
        after = {
            "kind": "media",
            "src": str(src),
            "info": info,
            "stages": stages,
            "model": model,
            "client_op_id": call["client_op_id"],
            "actor": {"kind": session.actor.kind, "id": session.actor.id},
        }
        res = proj.write_locked(session, "timeline_apply", call, after=after)  # S8: may park (needs_approval)
        if res.get("status") == "skipped":
            return {**res, "media_id": None, "probe": info, "status": None}
        fresh = len(log._entries) > before
        entry = next(e for e in reversed(log._entries) if e["op_id"] == res["op_id"])
    mid = next(o["id"] for o in entry["ops"] if o["op"] == "add_media")
    status = jobs.submit(proj, mid, src, info, stages, model) if fresh else read_status(proj.dir, mid, jobs.live_for(proj.id))
    return {**res, "media_id": mid, "probe": info, "status": status}


def _locked(proj: Any) -> Any:
    return proj.mutex if hasattr(proj, "mutex") else contextlib.nullcontext()  # a ClosedProject has none


def media_status(proj: Any, args: Any, live: set[str]) -> dict:
    """The derived-file status of one media (works with the app closed: nothing is live then)."""
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    mid = args.get("media_id")
    if not isinstance(mid, str):
        raise _bad("/media_id", "bad_arg" if "media_id" in args else "missing_arg", "'media_id' must be a media id")
    with _locked(proj):
        doc = proj.oplog().doc
    if mid not in doc["media"]:
        raise O.OplogError("not_found", f"no media {mid!r}", rule="not_found", path="/media_id", id=mid)
    st = read_status(proj.dir, mid, live)
    return st or {"media_id": mid, "state": "none", "progress": 0.0, "stages": {}}


TEXT_LINE_PAUSE_S = 0.7  # format "text": a pause this long, a sentence end or 12 words starts a line
TEXT_LINE_WORDS = 12


def _secs(args: dict, k: str) -> float | None:
    if k not in args:
        return None
    v = args[k]
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or v < 0:
        raise _bad(f"/{k}", "bad_arg", f"'{k}' must be a number of seconds, 0 or more")
    return float(v)


def _as_text(rows: list[dict]) -> str:
    """Lines of ``[start_s] words``: a new line at a pause, a sentence end or every 12 words."""
    lines: list[list[dict]] = []
    for r in rows:
        cur = lines[-1] if lines else None
        if (
            cur is None
            or r["at_s"] - cur[-1]["end_s"] > TEXT_LINE_PAUSE_S
            or cur[-1]["w"][-1:] in ".!?"
            or len(cur) >= TEXT_LINE_WORDS
        ):
            lines.append([r])
        else:
            cur.append(r)
    return "\n".join(f"[{ln[0]['at_s']:.2f}] " + " ".join(r["w"] for r in ln) for ln in lines)


def get_transcript(proj: Any, args: Any) -> dict:
    """Words on the timeline (``media.timeline_words``) from every media that has a words file,
    with ``seconds`` beside the ticks. ``media_id`` limits it to one media; ``from_s`` / ``to_s``
    to the words said in that window of the timeline; ``format: "text"`` gives lines of
    ``[start_s] words`` instead of one row per word (far fewer tokens for a long talk)."""
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    for k in sorted(args, key=repr):
        if k not in ("media_id", "from_s", "to_s", "format"):
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    lo, hi = _secs(args, "from_s"), _secs(args, "to_s")
    if lo is not None and hi is not None and hi <= lo:
        raise _bad("/to_s", "bad_arg", "'to_s' must be after 'from_s'")
    fmt = args.get("format", "words")
    if fmt not in ("words", "text"):
        raise _bad("/format", "bad_arg", "format is words or text")
    with _locked(proj):
        doc = proj.oplog().doc
    only = args.get("media_id")
    if only is not None and not isinstance(only, str):
        raise _bad("/media_id", "bad_arg", "'media_id' must be a media id")
    if only is not None and only not in doc["media"]:
        raise O.OplogError("not_found", f"no media {only!r}", rule="not_found", path="/media_id", id=only)
    words: dict[str, list[dict]] = {}
    for mid in doc["media"]:
        if only is not None and mid != only:
            continue
        data = M.read_json(M.cache_paths(proj.dir, mid)["words"])
        if isinstance(data, dict) and isinstance(data.get("words"), list):
            words[mid] = data["words"]
    rows = M.timeline_words(doc, words)
    sec = T.TICK_RATE
    for r in rows:
        r["at_s"], r["end_s"] = r["at"] / sec, r["end"] / sec
    if lo is not None or hi is not None:
        rows = [r for r in rows if (hi is None or r["at_s"] < hi) and (lo is None or r["end_s"] > lo)]
    out = {"version": doc["version"], "hash": doc["hash"], "media": sorted(words)}
    if fmt == "text":
        return {**out, "count": len(rows), "text": _as_text(rows)}
    return {**out, "words": rows}


def after_import(proj: P.Project, after: dict) -> None:
    """S8: a parked import was applied by a person: start its derived files now."""
    key = (after["actor"]["kind"], after["actor"]["id"])
    entry = next(
        (
            e
            for e in reversed(proj.oplog()._entries)
            if (e["actor"]["kind"], e["actor"]["id"]) == key and e["client_op_id"] == after["client_op_id"]
        ),
        None,
    )
    if entry is None:
        return
    mid = next(o["id"] for o in entry["ops"] if o["op"] == "add_media")
    proj.engine.media.submit(proj, mid, Path(after["src"]), after["info"], after["stages"], after["model"])


def get_scenes(proj: Any, args: Any) -> dict:
    """Shot changes on the timeline (``media.timeline_scenes``) from every media imported with
    the ``scenes`` stage; ``media_id`` limits it to one media."""
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    with _locked(proj):
        doc = proj.oplog().doc
    only = args.get("media_id")
    if only is not None and (not isinstance(only, str) or only not in doc["media"]):
        if not isinstance(only, str):
            raise _bad("/media_id", "bad_arg", "'media_id' must be a media id")
        raise O.OplogError("not_found", f"no media {only!r}", rule="not_found", path="/media_id", id=only)
    scenes: dict[str, list[int]] = {}
    for mid in doc["media"]:
        if only is not None and mid != only:
            continue
        data = M.read_json(M.cache_paths(proj.dir, mid)["scenes"])
        if isinstance(data, dict) and isinstance(data.get("cuts"), list):
            scenes[mid] = data["cuts"]
    rows = M.timeline_scenes(doc, scenes)
    for r in rows:
        r["at_s"] = r["at"] / T.TICK_RATE
    return {"version": doc["version"], "media": sorted(scenes), "cuts": rows}
