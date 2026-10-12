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
        # (project, render_id) -> the job that owns that render's status: {"cancelled": bool}. A
        # render submitted again after Stop gets a new job; the stopped one keeps running until
        # FFmpeg lets go but no longer writes the status or sends events.
        self.live: dict[tuple[str, str], dict] = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True, name="render").start()

    def is_live(self, pid: str, rid: str) -> bool:
        with self.lock:
            return (pid, rid) in self.live

    def is_stopping(self, pid: str, rid: str) -> bool:
        with self.lock:
            job = self.live.get((pid, rid))
            return bool(job and job["cancelled"])

    def cancel(self, pid: str, rid: str) -> bool:
        """Stop one render (queued or running); False when it isn't live."""
        with self.lock:
            job = self.live.get((pid, rid))
            if job is None:
                return False
            job["cancelled"] = True
            return True

    def cancel_project(self, pid: str) -> None:
        with self.lock:
            for k, job in self.live.items():
                if k[0] == pid:
                    job["cancelled"] = True

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
        job = {"cancelled": False}
        with self.lock:
            self.live[(proj.id, rid)] = job
        M._write_json(status, st)
        self.q.put((proj, rid, doc, size, words, st, style, job))
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
                    if self.live.get((job[0].id, job[1])) is job[-1]:
                        del self.live[(job[0].id, job[1])]

    def _run(
        self, proj: Any, rid: str, doc: dict, size: tuple[int, int], words: list[dict] | None, st: dict, style: str, job: dict
    ) -> None:
        out, status = _paths(proj, rid)
        out.parent.mkdir(exist_ok=True)
        last = [0.0]

        def cancel() -> bool:
            with self.lock:
                return job["cancelled"]

        def mine() -> bool:  # a newer job for the same render owns the status now
            with self.lock:
                return self.live.get((proj.id, rid)) is job

        def save() -> None:
            if mine():
                M._write_json(status, st)

        def send(ev: dict) -> None:
            if mine():
                proj.notify({"type": ev.pop("type"), "project_id": proj.id, "render_id": rid, **ev})

        def progress(f: float) -> None:
            st["progress"] = round(f, 4)
            now = time.monotonic()
            if f >= 1.0 or now - last[0] >= PROGRESS_EVERY_SEC:
                last[0] = now
                save()
                send({"type": "render.progress", "progress": st["progress"]})

        if cancel():  # cancelled while it waited in the queue
            st.update(state="cancelled", error=None)
            save()
            send({"type": "render.cancelled"})
            return
        st["state"] = "running"
        save()
        t0 = time.monotonic()
        try:
            res = R.render(doc, proj.dir, out, size=size, words=words, caption_style=style, on_progress=progress, cancel=cancel)
        except Exception as e:  # noqa: BLE001 - a failed render is a status, never a dead worker
            if cancel():
                st.update(state="cancelled", error=None)
                send({"type": "render.cancelled"})
            else:
                st.update(state="failed", error=f"{e}"[-600:])
                send({"type": "render.failed", "error": st["error"]})
            save()
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
        save()
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
    if st is not None and st["state"] in ("queued", "running", "ready") and not jobs.is_stopping(proj.id, rid):
        return {**st, "reused": True}  # a render being stopped is not reused: this one starts afresh
    return {**jobs.submit(proj, rid, doc, (size[0], size[1]), words, cstyle), "reused": False}


def render_cancel(proj: Any, args: Any, jobs: RenderJobs) -> dict:
    """``{render_id}``: stop a queued or running render. Its status says ``cancelled`` once the
    worker lets go (a ``render.cancelled`` event); ``cancelling`` says whether it was live."""
    st = render_status(proj, args, jobs)
    return {**st, "cancelling": jobs.cancel(proj.id, st["render_id"])}


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
