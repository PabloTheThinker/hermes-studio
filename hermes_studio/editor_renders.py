"""Background export jobs for the desk Edit page (one active render per project)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from hermes_studio import render_timeline as R
from hermes_studio.export_presets import ExportPresetError

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _set(pid: str, patch: dict) -> dict:
    with _LOCK:
        st = {**_JOBS.get(pid, {}), **patch, "project_id": pid}
        _JOBS[pid] = st
        return dict(st)


def status(pid: str) -> dict:
    with _LOCK:
        st = _JOBS.get(pid)
        return dict(st) if st else {"project_id": pid, "state": "idle"}


def cancel(pid: str) -> dict:
    with _LOCK:
        st = _JOBS.get(pid)
        if not st or st.get("state") not in ("queued", "running"):
            return {**status(pid), "cancelling": False}
        box = st.get("_cancel_box")
        if isinstance(box, dict):
            box["cancel"] = True
        return {**dict(st), "cancelling": True}


def start(
    pid: str,
    *,
    preset: str | None = None,
    fps: float | None = None,
    quality: str | None = "standard",
    start_s: float | None = None,
    end_s: float | None = None,
    out_path: Path | None = None,
) -> dict:
    cur = status(pid)
    if cur.get("state") in ("queued", "running"):
        return {**cur, "reused": True}

    box = {"cancel": False}

    def cancel_fn() -> bool:
        with _LOCK:
            return bool(box.get("cancel"))

    def progress(f: float) -> None:
        _set(pid, {"progress": round(f, 4), "state": "running"})

    def work() -> None:
        _set(pid, {"state": "running", "progress": 0.0, "error": None, "result": None})
        try:
            res = R.render_project(
                pid,
                out_path,
                start=start_s,
                end=end_s,
                preset=preset,
                fps=fps,
                quality=quality,
                on_progress=progress,
                cancel=cancel_fn,
            )
        except (R.RenderError, ExportPresetError) as exc:
            if cancel_fn():
                _set(pid, {"state": "cancelled", "progress": 0.0, "error": None, "result": None})
            else:
                _set(pid, {"state": "failed", "error": str(exc), "result": None})
            return
        except Exception as exc:  # noqa: BLE001 — a failed export is status, not a dead thread
            _set(pid, {"state": "failed", "error": str(exc)[:600], "result": None})
            return
        _set(pid, {"state": "ready", "progress": 1.0, "error": None, "result": res})

    _set(
        pid,
        {
            "state": "queued",
            "progress": 0.0,
            "preset": preset,
            "quality": quality,
            "fps": fps,
            "error": None,
            "result": None,
            "started": time.time(),
            "_cancel_box": box,
        },
    )
    threading.Thread(target=work, daemon=True, name=f"editor-render-{pid}").start()
    return {**status(pid), "reused": False}


def last_export_file(folder: Path) -> Path | None:
    meta = folder / "cache" / "last-export.json"
    if meta.is_file():
        try:
            import json

            row = json.loads(meta.read_text(encoding="utf-8"))
            name = row.get("path")
            if isinstance(name, str):
                p = folder / name
                if p.is_file():
                    return p
        except (OSError, ValueError, TypeError):
            pass
    legacy = folder / f"{folder.name}-render.mp4"
    return legacy if legacy.is_file() else None
