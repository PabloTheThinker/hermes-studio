from __future__ import annotations

from dataclasses import asdict
import json
import mimetypes
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from hermesclip.download import LIVE_DEFAULT_SEC, LIVE_MAX_SEC, probe
from hermesclip.pipeline import (
    execute_job,
    import_legacy,
    library_root,
    list_jobs,
    load_job,
    new_job,
)

UI_DIR = Path(__file__).resolve().parent / "ui"
HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 3870

_q: queue.Queue = queue.Queue()
_lock = threading.Lock()
_busy: set[str] = set()
MAX_PARALLEL_JOBS = 2


def _worker() -> None:
    while True:
        job_id = _q.get()
        try:
            job = load_job(job_id)
            if not job or job.status in {"cancelled", "completed"}:
                continue
            with _lock:
                _busy.add(job_id)
            execute_job(job)
        except Exception:
            pass
        finally:
            with _lock:
                _busy.discard(job_id)
            _q.task_done()


def _start_worker() -> None:
    for i in range(MAX_PARALLEL_JOBS):
        threading.Thread(target=_worker, name=f"hermesclip-jobs-{i}", daemon=True).start()


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict | list) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _seconds(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(text)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _safe_media(job_id: str, name: str) -> Path | None:
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    root = library_root().resolve()
    path = (root / job_id / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    if not (name.endswith(".mp4") or name.endswith(".jpg") or name.endswith(".json")):
        return None
    return path


class StudioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in {"/", "/index.html"}:
            return self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
        if path.startswith("/api/probe"):
            qs = parse_qs(parsed.query)
            src = (qs.get("src") or [""])[0]
            if not src:
                return _json(self, 400, {"ok": False, "error": "src required"})
            try:
                info = probe(src)
                return _json(
                    self,
                    200,
                    {
                        "ok": True,
                        "title": info.title,
                        "is_live": info.is_live,
                        "live_status": info.live_status,
                        "duration": info.duration,
                        "extractor": info.extractor,
                        "id": info.video_id,
                    },
                )
            except Exception as exc:
                return _json(self, 400, {"ok": False, "error": str(exc)[-800:]})
        if path == "/api/jobs":
            return _json(self, 200, {"ok": True, "jobs": [asdict(j) for j in list_jobs()], "busy": sorted(_busy)})
        if path.startswith("/api/jobs/"):
            job_id = path.split("/")[3]
            job = load_job(job_id)
            if not job:
                return _json(self, 404, {"ok": False, "error": "not found"})
            return _json(self, 200, {"ok": True, "job": asdict(job)})
        if path == "/api/library":
            jobs = [asdict(j) for j in list_jobs() if j.status == "completed"]
            return _json(self, 200, {"ok": True, "runs": jobs})
        if path.startswith("/media/"):
            parts = path.strip("/").split("/")
            if len(parts) != 3:
                self.send_error(404)
                return
            media = _safe_media(parts[1], parts[2])
            if not media:
                self.send_error(404)
                return
            ctype = mimetypes.guess_type(str(media))[0] or "application/octet-stream"
            return self._file(media, ctype)
        # static from ui/
        rel = path.lstrip("/")
        candidate = (UI_DIR / rel).resolve()
        try:
            candidate.relative_to(UI_DIR.resolve())
        except ValueError:
            self.send_error(404)
            return
        if candidate.is_file():
            ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
            return self._file(candidate, ctype)
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/jobs":
            body = _read_json(self)
            src = str(body.get("src") or "").strip()
            if not src:
                return _json(self, 400, {"ok": False, "error": "src required"})
            live_seconds = int(body.get("live_seconds") or LIVE_DEFAULT_SEC)
            live_seconds = max(60, min(live_seconds, LIVE_MAX_SEC))
            start_time = body.get("start_time")
            end_time = body.get("end_time")
            job = new_job(
                src,
                max_clips=int(body.get("max_clips") or 3),
                whisper=str(body.get("whisper") or "tiny"),
                pacing=str(body.get("pacing") or "tight"),
                style=str(body.get("style") or "pop"),
                plan=str(body.get("plan") or "heuristic"),
                layout=str(body.get("layout") or "fit"),
                live_seconds=live_seconds,
                live_from_start=bool(body.get("live_from_start")),
                aspect=str(body.get("aspect") or "9:16"),
                captions=body.get("captions", True) is not False,
                min_sec=float(body.get("min_sec") or 12),
                max_sec=float(body.get("max_sec") or 45),
                start_time=_seconds(start_time),
                end_time=_seconds(end_time),
            )
            _q.put(job.id)
            return _json(self, 202, {"ok": True, "job": asdict(job)})
        if path.startswith("/api/jobs/") and path.endswith("/retry"):
            job_id = path.split("/")[3]
            job = load_job(job_id)
            if not job:
                return _json(self, 404, {"ok": False, "error": "not found"})
            if job.status not in {"failed", "cancelled"}:
                return _json(self, 400, {"ok": False, "error": "only failed or cancelled jobs retry"})
            job.status = "queued"
            job.stage = "queued"
            job.progress = 0
            job.error = None
            job.message = "Retry queued"
            job.finished_at = None
            job.save()
            _q.put(job.id)
            return _json(self, 202, {"ok": True, "job": asdict(job)})
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[3]
            job = load_job(job_id)
            if not job:
                return _json(self, 404, {"ok": False, "error": "not found"})
            if job.status in {"queued"}:
                job.status = "cancelled"
                job.message = "Cancelled"
                job.save()
            return _json(self, 200, {"ok": True, "job": asdict(job)})
        self.send_error(404)

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if content_type.startswith("video/"):
            self.send_header("Accept-Ranges", "none")
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = HOST_DEFAULT, port: int = PORT_DEFAULT) -> None:
    import_legacy()
    _start_worker()
    httpd = ThreadingHTTPServer((host, port), StudioHandler)
    print(f"Hermes Studio  http://{host}:{port}/", flush=True)
    print("Library  Create  Jobs  — loopback only. Does not post.", flush=True)
    httpd.serve_forever()
