#!/usr/bin/env python3
"""Desktop frame helper. Ships with the plugin. No house script.

Prints one JSON object on stdout. Binds a loopback proxy that only forwards
to the local desk, and only under an unguessable /e/<slug>/ prefix. The open
desk stays unframed. A stranger's agent does not need this machine's paths.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DESK = os.environ.get("HERMES_STUDIO_DESK", "http://127.0.0.1:3870").rstrip("/")
PROXY_HOST = "127.0.0.1"
PROXY_PORT = int(os.environ.get("HERMES_STUDIO_FRAME_PORT", "3872"))
EMBED_FILE = Path.home() / ".hermes" / "clips" / "desktop-embed.json"
_SLUG_MIN = 20


def _origin() -> str:
    env = os.environ.get("HERMES_STUDIO_FRAME", "").strip().rstrip("/")
    if env.startswith("http://") or env.startswith("https://"):
        return env
    marker = Path.home() / ".hermes" / "clips" / "desktop-frame-origin"
    try:
        saved = marker.read_text(encoding="utf-8").strip().rstrip("/")
    except OSError:
        saved = ""
    if saved.startswith("http://") or saved.startswith("https://"):
        return saved
    return f"http://{PROXY_HOST}:{PROXY_PORT}"


def _slug() -> str:
    now = time.time()
    try:
        data = json.loads(EMBED_FILE.read_text(encoding="utf-8"))
        slug = str(data.get("desk") or "")
        exp = float(data.get("exp") or 0)
        if len(slug) >= _SLUG_MIN and exp > now + 60:
            return slug
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    slug = secrets.token_urlsafe(32)
    EMBED_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = EMBED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"desk": slug, "exp": now + 12 * 3600}), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(EMBED_FILE)
    return slug


def _desk_up() -> bool:
    try:
        with urllib.request.urlopen(DESK + "/", timeout=2) as resp:
            return resp.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _start_desk() -> None:
    import shutil
    import subprocess

    exe = shutil.which("hermes-studio")
    if not exe:
        return
    subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [exe, "studio", "--host", "127.0.0.1", "--port", "3870", "--no-browser"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _embed_live(origin: str, slug: str) -> bool:
    url = origin + "/e/" + slug + "/"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200 and b"Hermes Studio" in resp.read(4000)
    except (OSError, urllib.error.URLError):
        return False


def _rewrite(body: bytes, slug: str) -> bytes:
    prefix = "/e/" + slug
    text = body.decode("utf-8", "replace")
    text = text.replace('src="/', f'src="{prefix}/')
    text = text.replace("src='/", f"src='{prefix}/")
    text = text.replace('href="/', f'href="{prefix}/')
    boot = (
        "<script>(function(){var P=" + json.dumps(prefix) + ";"
        "function fix(u){return typeof u==='string'&&u.charAt(0)==='/'&&u.indexOf(P+'/')!==0?P+u:u;}"
        "var f=window.fetch;window.fetch=function(u,o){return f.call(this,fix(u),o);};"
        "function patch(proto,prop){var d=Object.getOwnPropertyDescriptor(proto,prop);if(!d||!d.set)return;"
        "Object.defineProperty(proto,prop,{set:function(v){d.set.call(this,fix(v));},get:d.get});}"
        "if(window.HTMLImageElement)patch(HTMLImageElement.prototype,'src');"
        "if(window.HTMLMediaElement)patch(HTMLMediaElement.prototype,'src');"
        "})();</script>"
    )
    if "<head>" in text:
        text = text.replace("<head>", "<head>" + boot, 1)
    else:
        text = boot + text
    return text.encode("utf-8")


class _Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _handle(self) -> None:
        slug = _slug()
        path = urlsplit(self.path).path
        prefix = "/e/" + slug
        if path != prefix and not path.startswith(prefix + "/"):
            self.send_error(404)
            return
        rest = path[len(prefix):] or "/"
        if not rest.startswith("/"):
            rest = "/" + rest
        query = urlsplit(self.path).query
        target = rest + (("?" + query) if query else "")
        desk = urlsplit(DESK)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        import http.client

        conn = http.client.HTTPConnection(desk.hostname or "127.0.0.1", desk.port or 80, timeout=60)
        headers = {
            "Host": f"{PROXY_HOST}:{PROXY_PORT}",
            "Accept": self.headers.get("Accept", "*/*"),
        }
        if self.headers.get("Content-Type"):
            headers["Content-Type"] = self.headers["Content-Type"]
        if self.headers.get("Range"):
            headers["Range"] = self.headers["Range"]
        if self.headers.get("Origin"):
            headers["Origin"] = self.headers["Origin"]
        try:
            conn.request(self.command, target, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except OSError:
            self.send_error(502)
            return
        finally:
            conn.close()
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype:
            data = _rewrite(data, slug)
        self.send_response(resp.status)
        for key, value in resp.headers.items():
            low = key.lower()
            if low in {"transfer-encoding", "content-length", "connection", "x-frame-options", "content-security-policy"}:
                continue
            self.send_header(key, value)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors *; default-src 'self' 'unsafe-inline' data: blob: https://fonts.googleapis.com https://fonts.gstatic.com")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()


def _proxy_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://{PROXY_HOST}:{PROXY_PORT}/", timeout=1) as resp:
            return resp.status in {200, 404}
    except urllib.error.HTTPError as exc:
        return exc.code in {404, 421}
    except (OSError, urllib.error.URLError):
        return False


def _serve() -> None:
    ThreadingHTTPServer((PROXY_HOST, PROXY_PORT), _Proxy).serve_forever()


def _ensure_proxy() -> None:
    if _proxy_up():
        return
    import subprocess

    subprocess.Popen(  # noqa: S603 - this file, no shell
        [sys.executable, str(Path(__file__).resolve()), "--serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(40):
        if _proxy_up():
            return
        time.sleep(0.05)
    raise SystemExit("frame proxy did not bind")


def main() -> int:
    if "--serve" in sys.argv:
        _serve()
        return 0
    if not _desk_up():
        _start_desk()
        for _ in range(16):
            if _desk_up():
                break
            time.sleep(0.25)
    if not _desk_up():
        json.dump({"ok": False, "error": "studio desk is not running on 127.0.0.1:3870"}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    slug = _slug()
    origin = _origin()
    if origin.startswith("https://") and _embed_live(origin, slug):
        frame = origin + "/e/" + slug + "/"
    else:
        _ensure_proxy()
        frame = f"http://{PROXY_HOST}:{PROXY_PORT}/e/" + slug + "/"
    json.dump({"ok": True, "frame": frame}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - one JSON error for the plugin
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        raise SystemExit(1)
