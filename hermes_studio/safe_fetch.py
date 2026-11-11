"""Run yt-dlp with every outbound connection checked: ``python -m hermes_studio.safe_fetch <yt-dlp args>``.

* In this process, ``socket.getaddrinfo`` refuses non-public answers (``guard.install_socket_guard``),
  so every request yt-dlp makes (each redirect hop, API call, manifest, fragment) is checked against
  the address it actually connects to. ``curl_cffi`` (libcurl, which resolves outside Python) is
  disabled, and yt-dlp is told to connect directly (``--proxy ""``).
* Child processes yt-dlp starts to fetch media (ffmpeg for live HLS and some formats) get
  ``http_proxy`` / ``https_proxy`` pointing at a loopback proxy in this process. The proxy checks
  the host of every request and CONNECT tunnel (so every hop ffmpeg follows) with the same guard.
"""

from __future__ import annotations

import os
import socket
import socketserver
import sys
import threading
import urllib.parse

from hermes_studio.guard import install_socket_guard

_HEAD_MAX = 64 * 1024


def _split_hostport(target: str, default_port: int) -> tuple[str, int]:
    if target.startswith("["):
        host, _, rest = target[1:].partition("]")
        port = int(rest[1:]) if rest.startswith(":") else default_port
        return host, port
    host, sep, port = target.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return target, default_port


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (dst,):
            try:
                s.shutdown(socket.SHUT_WR)
            except OSError:
                pass


class _Handler(socketserver.BaseRequestHandler):
    def _refuse(self, why: str) -> None:
        body = why.encode("utf-8", "replace")[:400]
        try:
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: "
                                 + str(len(body)).encode() + b"\r\n\r\n" + body)
        except OSError:
            pass

    def handle(self) -> None:
        sock: socket.socket = self.request
        sock.settimeout(60)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return
            buf += chunk
            if len(buf) > _HEAD_MAX:
                return self._refuse("request head too large")
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            return self._refuse("bad request line")
        try:
            if method.upper() == "CONNECT":
                host, port = _split_hostport(target, 443)
                upstream = socket.create_connection((host, port), timeout=30)  # guarded getaddrinfo
                sock.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                first = rest
            else:
                u = urllib.parse.urlsplit(target)
                if u.scheme != "http" or not u.hostname:
                    return self._refuse("only absolute http:// requests or CONNECT")
                host, port = u.hostname, u.port or 80
                upstream = socket.create_connection((host, port), timeout=30)
                path = (u.path or "/") + (f"?{u.query}" if u.query else "")
                kept = [h for h in lines[1:] if h.split(":", 1)[0].strip().lower()
                        not in ("connection", "proxy-connection", "proxy-authorization", "keep-alive")]
                # One request per connection: a later request to another host can never ride this tunnel.
                first = (f"{method} {path} {version}\r\n" + "\r\n".join([*kept, "Connection: close"])
                         + "\r\n\r\n").encode("latin-1") + rest
        except OSError as exc:
            return self._refuse(str(exc))
        with upstream:
            if first:
                upstream.sendall(first)
            back = threading.Thread(target=_pipe, args=(upstream, sock), daemon=True)
            back.start()
            _pipe(sock, upstream)
            back.join(timeout=4 * 60 * 60)


class _Proxy(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_proxy() -> str:
    srv = _Proxy(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}"


def main(argv: list[str]) -> int:
    install_socket_guard()
    sys.modules["curl_cffi"] = None  # type: ignore[assignment]  # libcurl resolves outside the guard
    proxy = start_proxy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        os.environ[k] = proxy  # for ffmpeg and other fetching children only
    for k in ("no_proxy", "NO_PROXY"):
        os.environ.pop(k, None)
    import yt_dlp

    try:
        yt_dlp.main(["--proxy", "", "--no-exec", *argv])
    except SystemExit as exc:
        return int(exc.code or 0) if not isinstance(exc.code, str) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
