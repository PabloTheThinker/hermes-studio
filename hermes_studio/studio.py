from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from hermes_studio.download import LIVE_DEFAULT_SEC, LIVE_MAX_SEC, probe
from hermes_studio.pipeline import (
    execute_job,
    import_legacy,
    job_dir,
    library_root,
    list_jobs,
    load_job,
    new_job,
    organize_library,
    safe_clip_file,
    safe_job_id,
)

UI_DIR = Path(__file__).resolve().parent / "ui"
HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 3870

# --------------------------------------------------------------------------- security
# The desk is a loopback app. These guards stop the classic attacks on local web apps:
# - DNS rebinding: a web page re-points its own domain at 127.0.0.1 and calls the API.
#   Blocked by the Host allow-list (only loopback names, *.ts.net, or HERMES_STUDIO_ALLOWED_HOSTS).
# - CSRF from any open tab: POSTs need Content-Type application/json (forces a CORS
#   preflight we never answer) and, when the browser sends Origin, it must match Host.
# - Clickjacking / sniffing / injection: CSP, frame-ancestors none, nosniff, no referrer.
# - Oversized bodies: 1 MB cap.
MAX_BODY = 1024 * 1024
MAX_IMAGE_BODY = 32 * 1024 * 1024  # design uploads + exported pages (base64 in JSON)
DESIGN_STATIC = {  # fixed names only; nothing derived from the request path is opened
    "fabric.min.js": ("vendor/fabric.min.js", "text/javascript; charset=utf-8"),
    "design.js": ("design.js", "text/javascript; charset=utf-8"),
}
FONT_FILES = {"Archivo.ttf", "PlayfairDisplay-Italic.ttf", "Caveat.ttf", "JetBrainsMono.ttf", "OpenSans.ttf"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg"}
LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1", "[::1]"}
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _extra_hosts() -> set[str]:
    raw = os.environ.get("HERMES_STUDIO_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def host_allowed(host_header: str | None) -> bool:
    """Host header without port must be loopback, a Tailscale name, or explicitly allowed."""
    if not host_header:
        return False
    h = host_header.strip().lower()
    name = h.rsplit(":", 1)[0] if not h.endswith("]") else h
    if name.startswith("[") and "]" in name:
        name = name[: name.index("]") + 1]
    return name in LOOPBACK_NAMES or name.endswith(".ts.net") or name in _extra_hosts()


def origin_ok(origin: str | None, host_header: str | None) -> bool:
    """No Origin (curl, agents) is fine; a browser Origin must be this same host."""
    if not origin:
        return True
    if origin == "null":
        return False
    return urlparse(origin).netloc.lower() == (host_header or "").strip().lower()


def is_loopback(host: str) -> bool:
    return host in LOOPBACK_NAMES or host.startswith("127.")


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
        threading.Thread(target=_worker, name=f"hermes-studio-jobs-{i}", daemon=True).start()


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


class BodyRefused(ValueError):
    """A request body we won't read: answered with 400 and a closed connection (D27(d))."""


def body_length(handler: BaseHTTPRequestHandler) -> int:
    """The request body length, from headers only (nothing is read). Any Transfer-Encoding is
    refused first; then there must be at most one Content-Length, whose value (spaces and tabs
    stripped) is 1-8 ASCII digits. No Content-Length is 0, as before."""
    from hermes_studio.jsonrpc import content_length

    if handler.headers.get_all("Transfer-Encoding"):
        raise BodyRefused("unsupported transfer encoding")
    values = handler.headers.get_all("Content-Length") or []
    if not values:
        return 0
    if len(values) != 1:
        raise BodyRefused("invalid content length")
    try:
        raw = values[0].encode("latin-1")
    except (UnicodeEncodeError, AttributeError):
        raise BodyRefused("invalid content length") from None
    n, _ = content_length(raw)
    if n is None:
        raise BodyRefused("invalid content length")
    return n


def no_body(handler: BaseHTTPRequestHandler) -> None:
    """D27(d) for every method that takes no body (GET, HEAD, OPTIONS), checked before routing:
    Transfer-Encoding, then exactly one valid Content-Length, then a valid length > 0 (over the
    cap included) is refused. Nothing is read; the caller answers 400 and closes."""
    if body_length(handler) > 0:
        raise BodyRefused("request body not allowed")


def path_segments(raw: str) -> list[str]:
    """Split the raw URL path on '/' first, then percent-decode each segment once, so an
    encoded '/' (%2F) stays inside its segment (GET and POST alike)."""
    return [unquote(seg) for seg in raw.split("/")]


def is_project_route(segs: list[str]) -> bool:
    return len(segs) >= 4 and segs[1] == "api" and segs[2] == "projects"


def _read_json(handler: BaseHTTPRequestHandler, limit: int = MAX_BODY) -> dict:
    length = body_length(handler)
    if length > limit:
        raise BodyRefused("request body too large")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def valid_id(job_id: str) -> bool:
    return safe_job_id(job_id)


def valid_file(name: str) -> bool:
    return safe_clip_file(name)


def check_src(src: str) -> str | None:
    """None if the source is acceptable, else a short reason. URLs: http(s) only.
    Local paths: existing video/audio files only (never a key file or /etc/passwd)."""
    from hermes_studio.download import is_url, local_source

    if is_url(src):
        return None if urlparse(src).hostname else "bad URL"
    if "://" in src:
        return "only http(s) links or local video files"
    try:
        local_source(src)
    except (ValueError, FileNotFoundError, OSError) as exc:
        return str(exc)[:200] or "not a video file"
    return None


# Only these types are ever served, keyed by suffix. Fixed strings, never derived from input.
MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".json": "application/json; charset=utf-8",
    ".srt": "text/plain; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def _inside(base: Path, name: str) -> str | None:
    """base/name as a normalised string if it stays inside base, else None."""
    root = os.path.normpath(str(base))
    full = os.path.normpath(os.path.join(root, name))
    real = os.path.realpath(full)
    prefix = os.path.realpath(root).rstrip(os.sep) + os.sep
    if not real.startswith(prefix):
        return None
    return real


def _safe_media(job_id: str, name: str) -> Path | None:
    if not valid_id(job_id) or not valid_file(name):
        return None
    if os.path.splitext(name)[1].lower() not in MEDIA_TYPES:
        return None
    d = job_dir(job_id)
    if not d:
        return None
    real = _inside(d, name)
    lib = os.path.realpath(str(library_root())).rstrip(os.sep) + os.sep
    if not real or not real.startswith(lib) or not os.path.isfile(real):
        return None
    return Path(real)


def _safe_trash(job_id: str, name: str) -> Path | None:
    if not valid_id(job_id) or not valid_file(name) or not name.endswith(".mp4"):
        return None
    d = job_dir(job_id)
    if not d:
        return None
    real = _inside(d / ".trash", name)
    lib = os.path.realpath(str(library_root())).rstrip(os.sep) + os.sep
    if not real or not real.startswith(lib) or not os.path.isfile(real):
        return None
    return Path(real)


class StudioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "HermesStudio"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def end_headers(self) -> None:
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def _refuse(self, code: int, why: str) -> None:
        body = json.dumps({"ok": False, "error": why}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _guard(self, write: bool) -> bool:
        """True if the request may go on. Refuses and answers otherwise."""
        if not host_allowed(self.headers.get("Host")):
            self._refuse(421, "host not allowed")
            return False
        if write:
            if not origin_ok(self.headers.get("Origin"), self.headers.get("Host")):
                self._refuse(403, "cross-origin request refused")
                return False
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._refuse(415, "Content-Type must be application/json")
                return False
        return True

    def _no_body(self, segs: list[str] | None = None) -> bool:
        """True if the request carries no body; refuses (400 + close, nothing read) otherwise."""
        try:
            no_body(self)
            return True
        except BodyRefused as exc:
            if segs == ["", "mcp"]:
                from hermes_studio import http_engine

                http_engine._mcp_refuse(self)
            else:
                self._refuse(400, str(exc))
            return False

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._no_body():
            return
        # No CORS: cross-site preflights get nothing to work with.
        self._refuse(405, "no cross-origin access")

    def do_HEAD(self) -> None:  # noqa: N802
        if not self._guard(write=False) or not self._no_body():
            return
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/media/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                media = _safe_media(parts[1], parts[2])
                if media:
                    ctype = MEDIA_TYPES[media.suffix.lower()]
                    size = media.stat().st_size
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(size))
                    self.end_headers()
                    return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard(write=False):
            return
        parsed = urlparse(self.path)
        segs = path_segments(parsed.path)  # split first, then decode each segment
        if not self._no_body(segs):  # D27(d) before any route
            return
        path = "/".join(segs)
        if path in {"/", "/index.html"}:
            return self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
        if is_project_route(segs) or segs == ["", "mcp"]:
            from hermes_studio import http_engine

            return http_engine.get(self, segs, parsed.query)
        if segs == ["", "api", "projects"]:
            from hermes_studio import http_engine

            return http_engine.projects_route(self, "GET")
        if path in ("/edit/edit.js", "/sw.js"):  # the Edit page and its media header worker
            return self._file(UI_DIR / path.rsplit("/", 1)[1], "text/javascript; charset=utf-8")
        if path.startswith("/api/probe"):
            qs = parse_qs(parsed.query)
            src = (qs.get("src") or [""])[0]
            if not src:
                return _json(self, 400, {"ok": False, "error": "src required"})
            bad = check_src(src)
            if bad:
                return _json(self, 400, {"ok": False, "error": bad})
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
        if path.startswith("/api/recommend"):
            qs = parse_qs(parsed.query)
            src = (qs.get("src") or [""])[0]
            if not src:
                return _json(self, 400, {"ok": False, "error": "src required"})
            bad = check_src(src)
            if bad:
                return _json(self, 400, {"ok": False, "error": bad})
            try:
                from hermes_studio.recommend import recommend_for

                info, rec = recommend_for(src)
                return _json(
                    self,
                    200,
                    {
                        "ok": True,
                        "title": info.title,
                        "is_live": info.is_live,
                        "duration": info.duration,
                        "recommendation": rec.as_job(),
                    },
                )
            except Exception as exc:
                return _json(self, 400, {"ok": False, "error": str(exc)[-800:]})
        if path.startswith("/api/copy"):
            qs = parse_qs(parsed.query)
            job_id = (qs.get("job") or [""])[0]
            clip_title = (qs.get("clip") or [""])[0]
            job = load_job(job_id)
            if not job:
                return _json(self, 404, {"ok": False, "error": "job not found"})
            try:
                from hermes_studio.copy import copy_from_job_dir

                pack = copy_from_job_dir(Path(job.dir), clip_title)
                return _json(self, 200, {"ok": True, **pack})
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
        if path == "/api/tools":
            from hermes_studio.tools import catalogue

            return _json(self, 200, {"ok": True, **catalogue()})
        if path == "/api/caption-styles":
            from hermes_studio.captions import preview_styles

            return _json(self, 200, {"ok": True, **preview_styles()})
        if path == "/api/library":
            jobs = [asdict(j) for j in list_jobs() if j.status == "completed"]
            counts: dict[str, int] = {}
            for j in jobs:
                counts[j["platform"]] = counts.get(j["platform"], 0) + 1
            folders = [{"name": k, "runs": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
            return _json(self, 200, {"ok": True, "runs": jobs, "folders": folders, "root": "library"})
        if path.startswith("/api/trash"):
            qs = parse_qs(parsed.query)
            job = load_job((qs.get("job") or [""])[0])
            if not job:
                return _json(self, 404, {"ok": False, "error": "job not found"})
            from hermes_studio.edit import list_trash

            return _json(self, 200, {"ok": True, "files": list_trash(Path(job.dir))})
        if path == "/api/doctor":
            from hermes_studio.api import doctor
            from hermes_studio.mcp import client_config

            return _json(self, 200, {**doctor(), "mcp": client_config()})
        if path.startswith("/design/"):
            return self._design_get(path)
        if path == "/api/designs":
            from hermes_studio import design

            return _json(self, 200, {"ok": True, "designs": design.list_designs(), "sizes": {
                k: {"w": w, "h": h, "label": lab} for k, (w, h, lab) in design.SIZES.items()},
                "templates": design.templates(), "fonts": {k: [v[1], v[2]] for k, v in design.FONTS.items()}})
        if path.startswith("/api/design-template/"):
            from hermes_studio import design

            q = parse_qs(urlparse(self.path).query)
            try:
                pages = design.template_pages(path.split("/")[3], int(q.get("w", ["1080"])[0]), int(q.get("h", ["1350"])[0]))
            except (design.DesignError, ValueError) as exc:
                return _json(self, 400, {"ok": False, "error": str(exc)})
            return _json(self, 200, {"ok": True, "pages": pages})
        if path.startswith("/api/design/"):
            from hermes_studio import design

            did = path.split("/")[3] if len(path.split("/")) > 3 else ""
            try:
                return _json(self, 200, {"ok": True, "design": design.load(did)})
            except design.DesignError as exc:
                return _json(self, 404, {"ok": False, "error": str(exc)})
        if path.startswith("/media/"):
            parts = path.strip("/").split("/")
            if len(parts) != 3:
                self.send_error(404)
                return
            media = _safe_media(parts[1], parts[2])
            if not media:
                self.send_error(404)
                return
            return self._file(media, MEDIA_TYPES[media.suffix.lower()])
        # The desk is a single page; nothing else under ui/ is served.
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard(write=True):
            return
        segs = path_segments(urlparse(self.path).path)
        if segs == ["", "mcp"]:
            from hermes_studio import http_engine

            return http_engine.mcp_post(self)
        try:
            body_length(self)  # Transfer-Encoding and Content-Length checked before any route
            self._post()
        except BodyRefused as exc:  # nothing more is read: one response, then the connection closes
            return self._refuse(400, str(exc))
        except ValueError as exc:  # bad JSON
            return _json(self, 400, {"ok": False, "error": str(exc)[:200]})

    def _post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        segs = path_segments(path)  # split first, then decode each segment, as on GET
        if is_project_route(segs):
            from hermes_studio import http_engine

            return http_engine.rest_post(self, segs)
        if segs == ["", "api", "projects"]:
            from hermes_studio import http_engine

            return http_engine.projects_route(self, "POST")
        if path == "/api/design" or path.startswith("/api/design/"):
            return self._design_post(path)
        if path == "/api/jobs":
            body = _read_json(self)
            src = str(body.get("src") or "").strip()
            if not src:
                return _json(self, 400, {"ok": False, "error": "src required"})
            bad = check_src(src)
            if bad:
                return _json(self, 400, {"ok": False, "error": bad})
            rec = None
            if body.get("recommend"):
                from hermes_studio.recommend import recommend_for

                try:
                    _info, rec = recommend_for(src)
                except Exception as exc:
                    return _json(self, 400, {"ok": False, "error": str(exc)[-800:]})
            live_seconds = int((rec.live_seconds if rec else body.get("live_seconds")) or LIVE_DEFAULT_SEC)
            live_seconds = max(60, min(live_seconds, LIVE_MAX_SEC))
            start_time = body.get("start_time")
            end_time = body.get("end_time")
            job = new_job(
                src,
                max_clips=int((rec.max_clips if rec else body.get("max_clips")) or 3),
                whisper=str(body.get("whisper") or "tiny"),
                pacing=str((rec.pacing if rec else body.get("pacing")) or "tight"),
                style=str((rec.style if rec else body.get("style")) or "pop"),
                plan=str((rec.plan if rec else body.get("plan")) or "heuristic"),
                layout=str((rec.layout if rec else body.get("layout")) or "fit"),
                live_seconds=live_seconds,
                live_from_start=bool(body.get("live_from_start")),
                aspect=str((rec.aspect if rec else body.get("aspect")) or "9:16"),
                captions=(rec.captions if rec else body.get("captions", True)) is not False,
                min_sec=float((rec.min_sec if rec else body.get("min_sec")) or 12),
                max_sec=float((rec.max_sec if rec else body.get("max_sec")) or 45),
                start_time=_seconds(start_time),
                end_time=_seconds(end_time),
                prompt=str((rec.prompt if rec and rec.prompt else body.get("prompt")) or ""),
                hook=(rec.hook if rec else body.get("hook", True)) is not False,
                mode=str((rec.mode if rec else body.get("mode")) or "clip"),
                keywords=str((getattr(rec, "keywords", "") if rec else body.get("keywords")) or ""),
                look=body.get("look") if isinstance(body.get("look"), dict) else None,
                fixes=body.get("fixes"),
            )
            if rec:
                job.message = "Hermes pick · " + "; ".join(rec.why[:2])
                job.save()
            _q.put(job.id)
            return _json(self, 202, {"ok": True, "job": asdict(job)})
        if path == "/api/restyle":
            body = _read_json(self)
            from hermes_studio.pipeline import restyle_clip

            def _f(k):
                v = body.get(k)
                return _seconds(v) if v not in (None, "") else None

            res = restyle_clip(
                str(body.get("job") or ""), str(body.get("file") or ""),
                look=body.get("look") if isinstance(body.get("look"), dict) else None,
                style=body.get("style") or None,
                captions=body.get("captions") if body.get("captions") in (True, False) else None,
                hook=body.get("hook") if body.get("hook") in (True, False) else None,
                start=_f("start"), end=_f("end"),
                fixes=body.get("fixes"), title=body.get("title") or None,
            )
            return _json(self, 200 if res.get("ok") else 400, res)
        if path == "/api/name":
            body = _read_json(self)
            from hermes_studio.pipeline import name_job

            res = name_job(str(body.get("job") or ""))
            return _json(self, 200 if res.get("ok") else 400, res)
        if path == "/api/clipmeta":
            body = _read_json(self)
            from hermes_studio.pipeline import set_clip_meta

            liked = body.get("liked")
            res = set_clip_meta(str(body.get("job") or ""), str(body.get("file") or ""), liked if liked in (True, False) else None)
            return _json(self, 200 if res.get("ok") else 400, res)
        if path == "/api/rename":
            body = _read_json(self)
            from hermes_studio.pipeline import rename_clip

            res = rename_clip(str(body.get("job") or ""), str(body.get("file") or ""), str(body.get("title") or ""))
            return _json(self, 200 if res.get("ok") else 400, res)
        if path == "/api/edit":
            body = _read_json(self)
            job = load_job(str(body.get("job") or ""))
            name = str(body.get("file") or "")
            if not job or not name:
                return _json(self, 400, {"ok": False, "error": "job and file required"})
            op = str(body.get("op") or "trim")
            try:
                from hermes_studio.edit import drop_file, duplicate_file, restore_file, split_file, trim_file

                if op == "restore":
                    trash = _safe_trash(job.id, name)
                    if not trash:
                        return _json(self, 404, {"ok": False, "error": "not in trash"})
                    path, meta = restore_file(trash)
                    extra = dict(meta)
                    extra["file"] = path.name
                    extra.setdefault("title", Path(name).stem)
                    extra.setdefault("thumb", "")
                    job.clips = list(job.clips or []) + [extra]
                    job.save()
                    return _json(self, 200, {"ok": True, "op": "restore", "file": path.name})
                media = _safe_media(job.id, name)
                if not media:
                    return _json(self, 404, {"ok": False, "error": "clip not found"})
                if op == "split":
                    a, b = split_file(media, float(body.get("at") or 0))
                    extra = [
                        {"file": a.name, "title": (Path(name).stem + " A"), "start": 0, "end": float(body.get("at") or 0), "score": 0, "virality": 0, "thumb": ""},
                        {"file": b.name, "title": (Path(name).stem + " B"), "start": float(body.get("at") or 0), "end": 0, "score": 0, "virality": 0, "thumb": ""},
                    ]
                    job.clips = list(job.clips or []) + extra
                    job.save()
                    return _json(self, 200, {"ok": True, "op": "split", "files": [a.name, b.name]})
                if op == "duplicate":
                    path = duplicate_file(media)
                    clip = next((c for c in (job.clips or []) if c.get("file") == name), {}) or {}
                    extra = dict(clip)
                    extra["file"] = path.name
                    extra["title"] = (clip.get("title") or Path(name).stem) + " copy"
                    extra["thumb"] = ""
                    job.clips = list(job.clips or []) + [extra]
                    job.save()
                    return _json(self, 200, {"ok": True, "op": "duplicate", "file": path.name})
                if op == "drop":
                    clip = next((c for c in (job.clips or []) if c.get("file") == name), {}) or {}
                    drop_file(media, clip)
                    job.clips = [c for c in (job.clips or []) if c.get("file") != name]
                    job.save()
                    return _json(self, 200, {"ok": True, "op": "drop", "file": name})
                if op == "reorder":
                    clips = list(job.clips or [])
                    names = [c.get("file") for c in clips]
                    if name not in names:
                        return _json(self, 400, {"ok": False, "error": "clip not in run"})
                    i = names.index(name)
                    delta = -1 if str(body.get("dir") or "up") == "up" else 1
                    j = i + delta
                    if j < 0 or j >= len(clips):
                        return _json(self, 200, {"ok": True, "op": "reorder", "files": names})
                    clips[i], clips[j] = clips[j], clips[i]
                    job.clips = clips
                    job.save()
                    return _json(self, 200, {"ok": True, "op": "reorder", "files": [c.get("file") for c in clips]})
                start = _seconds(body.get("start")) or 0.0
                end = _seconds(body.get("end")) or 0.0
                dest = media.with_name(media.stem + "-trim" + media.suffix)
                path = trim_file(media, dest, start, end)
                return _json(self, 200, {"ok": True, "op": "trim", "file": path.name})
            except Exception as exc:
                return _json(self, 400, {"ok": False, "error": str(exc)[-800:]})
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

    # ------------------------------------------------------------------ design

    def _design_get(self, path: str) -> None:
        """/design/fabric.min.js · /design/fonts/<file> · /design/<id>/(assets|export)/<file>."""
        from hermes_studio import design

        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[1] in DESIGN_STATIC:
            rel, ctype = DESIGN_STATIC[parts[1]]
            return self._file(UI_DIR / rel, ctype, cache=parts[1] != "design.js")
        if len(parts) == 3 and parts[1] == "fonts" and parts[2] in FONT_FILES:
            return self._file(design.FONT_DIR / parts[2], "font/ttf", cache=True)
        if len(parts) == 4 and parts[2] in ("assets", "export") and design.safe_id(parts[1]):
            ext = os.path.splitext(parts[3])[1].lower()
            if ext in IMAGE_TYPES and design.ASSET_RE.match("assets/" + parts[3]):
                try:
                    base = design.design_dir(parts[1]) / parts[2]
                except design.DesignError:
                    base = None
                real = _inside(base, parts[3]) if base else None
                if real and os.path.isfile(real):
                    return self._file(Path(real), IMAGE_TYPES[ext])
        self.send_error(404)

    def _design_post(self, path: str) -> None:
        import base64

        from hermes_studio import design, photo

        parts = path.strip("/").split("/")  # api, design, <id>, <action>
        big = len(parts) == 4 and parts[3] in ("asset", "export")
        body = _read_json(self, MAX_IMAGE_BODY if big else MAX_BODY)

        def b64(field: str = "data") -> bytes:
            raw = str(body.get(field) or "")
            if "," in raw[:80]:
                raw = raw.split(",", 1)[1]
            try:
                return base64.b64decode(raw, validate=True)
            except ValueError:
                raise design.DesignError("data must be base64") from None

        try:
            if len(parts) == 2:  # create
                doc = design.create(str(body.get("title") or ""), str(body.get("size") or "tiktok-carousel"),
                                    str(body.get("template") or "blank"), body.get("w"), body.get("h"))
                return _json(self, 200, {"ok": True, "design": doc})
            if len(parts) != 4:
                return _json(self, 404, {"ok": False, "error": "unknown design route"})
            did, act = parts[2], parts[3]
            if act == "save":
                return _json(self, 200, {"ok": True, "design": design.save(did, body.get("design") or {})})
            if act == "asset":
                rel = design.add_asset(did, b64(), name_hint=str(body.get("name") or "img"))
                return _json(self, 200, {"ok": True, "src": rel})
            if act == "photo":  # cutout / enhance / look on an asset -> a new asset
                src = design.asset_path(did, str(body.get("src") or ""))
                img = photo.decode(src.read_bytes())
                op = str(body.get("op") or "")
                if op == "cutout":
                    res = photo.cutout(img)
                elif op == "enhance":
                    res = photo.enhance(img, float(body.get("strength") or 1))
                elif op == "look":
                    res = photo.look(img, str(body.get("look") or "none"))
                else:
                    raise design.DesignError("op must be cutout, enhance or look")
                ext = ".png" if res.shape[2] == 4 else ".jpg"
                rel = design.add_asset(did, photo.encode(res, ext), name_hint=op)
                return _json(self, 200, {"ok": True, "src": rel})
            if act == "export":
                rel = design.save_export(did, int(body.get("page") or 1), b64())
                return _json(self, 200, {"ok": True, "file": rel})
            if act == "render":
                res = design.render(did, fmt="jpg" if body.get("format") == "jpg" else "png")
                return _json(self, 200, {"ok": True, "files": [f"export/{Path(f).name}" for f in res["files"]]})
            if act == "from-clip":  # a clip thumbnail from the library becomes a design image
                media = _safe_media(str(body.get("job") or ""), str(body.get("file") or ""))
                if not media or media.suffix.lower() != ".jpg":
                    raise design.DesignError("no such clip image")
                rel = design.add_asset(did, media.read_bytes(), name_hint="clip")
                return _json(self, 200, {"ok": True, "src": rel})
            if act == "resize":
                doc = design.resize(did, str(body.get("size") or ""), body.get("w"), body.get("h"))
                return _json(self, 200, {"ok": True, "design": doc})
            if act == "duplicate":
                return _json(self, 200, {"ok": True, "design": design.duplicate(did)})
            if act == "delete":
                return _json(self, 200, design.delete(did))
            return _json(self, 404, {"ok": False, "error": "unknown design action"})
        except (design.DesignError, photo.PhotoError) as exc:
            return _json(self, 400, {"ok": False, "error": str(exc)[:300]})

    def _file(self, path: Path, content_type: str, cache: bool = False) -> None:
        size = path.stat().st_size
        if content_type.startswith("video/"):
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                spec = rng.split("=", 1)[1]
                a, _, b = spec.partition("-")
                try:
                    start = int(a) if a else 0
                    end = int(b) if b else size - 1
                except ValueError:
                    start, end = 0, size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                self.send_response(206)
            else:
                self.send_response(200)
            length = end - start + 1
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if rng:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            with path.open("rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = HOST_DEFAULT, port: int = PORT_DEFAULT) -> None:
    if not is_loopback(host) and os.environ.get("HERMES_STUDIO_ALLOW_REMOTE") != "1":
        raise SystemExit(
            f"Refusing to listen on {host}: the desk has no login. Keep it on 127.0.0.1 and use "
            "`tailscale serve` for other devices, or set HERMES_STUDIO_ALLOW_REMOTE=1 if you really mean it."
        )
    import_legacy()
    try:
        organize_library()
    except Exception:
        pass
    _start_worker()
    httpd = ThreadingHTTPServer((host, port), StudioHandler)
    from hermes_studio import http_engine

    engine = http_engine.start(httpd.server_address[1])  # the timeline engine: locks its projects (D5, D6)
    print(f"Hermes Studio  http://{host}:{port}/", flush=True)
    if not engine.ui_token_given:  # a browser has no app to hand it over: the person pastes it once
        print(f"Edit page code (paste it when the Edit page asks; keep it private): {http_engine.UI_TOKEN}", flush=True)
    print("Library  Create  Jobs  — loopback only. Does not post.", flush=True)
    try:
        httpd.serve_forever()
    finally:
        http_engine.stop(engine)
