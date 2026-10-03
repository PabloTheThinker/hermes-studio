"""S6 render jobs on the engine: ``render_timeline`` and ``render_status``.

A render is identified by what it renders: ``v<version>-<w>x<h>[-cap]``. Asking again for the
same version, size and captions returns the existing job (or file) instead of rendering twice.
Output: ``<project>/exports/<project>-v<version>-<w>x<h>[-cap].mp4`` (0600). Progress goes to the
project's SSE clients as ``render.progress`` / ``render.ready`` / ``render.failed`` (no ``id``,
like S4's media events); ``cache/render/<render_id>.json`` is the durable status."""

from __future__ import annotations

import contextlib
import os
import queue
import re
import threading
import time
from typing import Any

from hermes_studio import media as M
from hermes_studio import media_jobs as MJ
from hermes_studio import oplog as O
from hermes_studio import render_timeline as R

MAX_SIDE = 3840
PROGRESS_EVERY_SEC = 0.5


def _bad(path: str, rule: str, msg: str) -> O.OplogError:
    return O.OplogError("invalid_op", msg, rule=rule, path=path)


def _paths(proj: Any, rid: str) -> tuple[Any, Any]:
    return proj.dir / "exports" / f"{proj.id}-{rid}.mp4", proj.dir / "cache" / "render" / f"{rid}.json"


class RenderJobs:
    """One render at a time per engine (FFmpeg already uses every core)."""

    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        self.live: set[tuple[str, str]] = set()
        self.cancelled: set[tuple[str, str]] = set()
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True, name="render").start()

    def is_live(self, pid: str, rid: str) -> bool:
        with self.lock:
            return (pid, rid) in self.live

    def cancel_project(self, pid: str) -> None:
        with self.lock:
            self.cancelled |= {k for k in self.live if k[0] == pid}

    def submit(self, proj: Any, rid: str, doc: dict, size: tuple[int, int], words: list[dict] | None, style: str = "pop") -> dict:
        out, status = _paths(proj, rid)
        st = {
            "render_id": rid,
            "state": "queued",
            "progress": 0.0,
            "version": doc["version"],
            "hash": doc["hash"],
            "size": list(size),
            "captions": words is not None,
            "path": str(out.relative_to(proj.dir).as_posix()),
            "error": None,
        }
        M._write_json(status, st)
        with self.lock:
            self.live.add((proj.id, rid))
            self.cancelled.discard((proj.id, rid))
        self.q.put((proj, rid, doc, size, words, st, style))
        return st

    def _work(self) -> None:
        while True:
            job = self.q.get()
            try:
                self._run(*job)
            except Exception:
                pass
            finally:
                with self.lock:
                    self.live.discard((job[0].id, job[1]))

    def _run(self, proj: Any, rid: str, doc: dict, size: tuple[int, int], words: list[dict] | None, st: dict, style: str) -> None:
        out, status = _paths(proj, rid)
        out.parent.mkdir(exist_ok=True)
        last = [0.0]

        def cancel() -> bool:
            with self.lock:
                return (proj.id, rid) in self.cancelled

        def send(ev: dict) -> None:
            proj.notify({"type": ev.pop("type"), "project_id": proj.id, "render_id": rid, **ev})

        def progress(f: float) -> None:
            st["progress"] = round(f, 4)
            now = time.monotonic()
            if f >= 1.0 or now - last[0] >= PROGRESS_EVERY_SEC:
                last[0] = now
                M._write_json(status, st)
                send({"type": "render.progress", "progress": st["progress"]})

        st["state"] = "running"
        M._write_json(status, st)
        t0 = time.monotonic()
        try:
            res = R.render(doc, proj.dir, out, size=size, words=words, caption_style=style, on_progress=progress, cancel=cancel)
        except Exception as e:  # noqa: BLE001 - a failed render is a status, never a dead worker
            if cancel():
                st.update(state="cancelled", error=None)
            else:
                st.update(state="failed", error=f"{e}"[-600:])
                send({"type": "render.failed", "error": st["error"]})
            M._write_json(status, st)
            return
        with contextlib.suppress(OSError):
            os.chmod(out, 0o600)
        st.update(
            state="ready",
            progress=1.0,
            segments=res["segments"],
            clips=res["clips"],
            seconds=round(time.monotonic() - t0, 2),
            bytes=out.stat().st_size,
        )
        M._write_json(status, st)
        send({"type": "render.ready", "path": st["path"], "version": st["version"]})


def _read(proj: Any, rid: str, jobs: RenderJobs | None) -> dict | None:
    out, status = _paths(proj, rid)
    st = M.read_json(status)
    if not isinstance(st, dict):
        return None
    if st.get("state") in ("queued", "running") and not (jobs and jobs.is_live(proj.id, rid)):
        st["state"] = "interrupted"
    if st.get("state") == "ready" and not out.is_file():
        st["state"] = "missing"  # the file was deleted after it was made
    return st


def render_timeline(proj: Any, args: Any, jobs: RenderJobs) -> dict:
    """``{width?, height?, captions?}``: render the current version in the background."""
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    for k in sorted(args, key=repr):
        if k not in ("width", "height", "captions", "caption_style"):
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    with proj.mutex:
        doc = proj.oplog().doc
    size = list(doc["size"])
    for i, k in enumerate(("width", "height")):
        if k in args:
            v = args[k]
            if not O._int_arg(v) or not 16 <= v <= MAX_SIDE or v % 2:
                raise _bad(f"/{k}", "bad_arg", f"'{k}' must be an even number of pixels, 16-{MAX_SIDE}")
            size[i] = v
    cap = args.get("captions", True)
    if not isinstance(cap, bool):
        raise _bad("/captions", "bad_arg", "'captions' must be true or false")
    from hermes_studio.captions import STYLES

    cstyle = args.get("caption_style", "pop")
    if cstyle not in STYLES:
        raise _bad("/caption_style", "bad_arg", "caption_style is one of " + ", ".join(STYLES))
    if R.timeline_end(doc) <= 0:
        raise _bad("", "bad_arg", "the timeline is empty: nothing to render")
    words = MJ.get_transcript(proj, {})["words"] if cap else None
    if words is not None and not words:
        words = None  # no words file: nothing to caption
    rid = f"v{doc['version']:06d}-{size[0]}x{size[1]}" + (
        "" if words is None else "-cap" if cstyle == "pop" else f"-cap-{cstyle}"
    )
    st = _read(proj, rid, jobs)
    if st is not None and st["state"] in ("queued", "running", "ready"):
        return {**st, "reused": True}
    return {**jobs.submit(proj, rid, doc, (size[0], size[1]), words, cstyle), "reused": False}


def render_status(proj: Any, args: Any, jobs: RenderJobs | None) -> dict:
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    for k in sorted(args, key=repr):
        if k != "render_id":
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    rid = args.get("render_id")
    if not isinstance(rid, str):
        raise _bad("/render_id", "bad_arg" if "render_id" in args else "missing_arg", "'render_id' must be a render id")
    if not re.fullmatch(r"v[0-9]{6}-[0-9]{2,4}x[0-9]{2,4}(-cap(-[a-z]{1,16})?)?", rid):
        raise O.OplogError("not_found", f"no render {rid!r}", rule="not_found", path="/render_id", id=rid)
    st = _read(proj, rid, jobs)
    if st is None:
        raise O.OplogError("not_found", f"no render {rid!r}", rule="not_found", path="/render_id", id=rid)
    return st
