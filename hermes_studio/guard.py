"""What a caller (a person, or an agent's tool call) may make the engine read, write and fetch.

* Local inputs: an existing media (or image) file under a media root
  (``download.local_source`` / ``image_source``).
* Outputs: inside the Studio folder (``~/.hermes/clips``) or a folder listed in
  ``HERMES_STUDIO_OUT_ROOTS``; an existing file is never overwritten.
* Network: public http(s) hosts only. Every connection the fetcher opens is checked
  after DNS resolution (so every redirect hop, CDN hop and DNS answer is covered):
  loopback, private, link-local (169.254.169.254), CGNAT, unspecified, multicast,
  reserved, and their IPv6 / v4-mapped forms are refused.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.parse
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class PathRefused(ValueError):
    pass


class URLRefused(ValueError):
    pass


# --------------------------------------------------------------------------- paths


def studio_root() -> Path:
    from hermes_studio.pipeline import library_root

    return library_root().parent


def out_roots() -> list[str]:
    roots = [str(studio_root())]
    roots += [r for r in os.environ.get("HERMES_STUDIO_OUT_ROOTS", "").split(os.pathsep) if r]
    return [os.path.realpath(os.path.normpath(os.path.expanduser(r))) for r in roots]


def _real_target(p: str | Path) -> str:
    """Absolute path with symlinks resolved, also when the leaf (or some parents) do not exist yet."""
    norm = os.path.normpath(os.path.abspath(os.path.expanduser(str(p))))
    return os.path.realpath(norm)


def _under(path: str, roots: list[str]) -> bool:
    for root in roots:
        prefix = root.rstrip(os.sep) + os.sep
        if path == root or path.startswith(prefix):
            return True
    return False


def inside_out_roots(p: str | Path) -> bool:
    norm = os.path.normpath(os.path.abspath(os.path.expanduser(str(p))))
    return _under(norm, out_roots()) and _under(_real_target(norm), out_roots())


def out_dir(p: str | Path) -> Path:
    """An output / work folder. Must sit inside the Studio folder (or HERMES_STUDIO_OUT_ROOTS)."""
    if not inside_out_roots(p):
        raise PathRefused("output folders must be inside the Studio folder (~/.hermes/clips) or HERMES_STUDIO_OUT_ROOTS")
    real = Path(_real_target(p))
    if real.exists() and not real.is_dir():
        raise PathRefused(f"not a folder: {real.name}")
    return real


def out_file(p: str | Path, exts: set[str] | None = None) -> Path:
    """An explicit output file: inside the out roots, an allowed extension, and not there yet."""
    if not inside_out_roots(p):
        raise PathRefused("output files must be inside the Studio folder (~/.hermes/clips) or HERMES_STUDIO_OUT_ROOTS")
    real = Path(_real_target(p))
    if exts is not None and real.suffix.lower() not in exts:
        raise PathRefused(f"output must end in one of: {' '.join(sorted(exts))}")
    if real.exists() or real.is_symlink():
        raise PathRefused(f"refusing to overwrite an existing file: {real.name}")
    return real


def default_out_file(src: Path, suffix_name: str, ext: str | None = None, sub: str = "edits") -> Path:
    """Next to ``src`` when src lives in the Studio folder, else ``<studio>/<sub>/``; never an existing file."""
    ext = ext or src.suffix
    folder = src.parent if inside_out_roots(src.parent) else studio_root() / sub
    folder.mkdir(parents=True, exist_ok=True)
    cand = folder / f"{src.stem}{suffix_name}{ext}"
    n = 2
    while cand.exists() or cand.is_symlink():
        cand = folder / f"{src.stem}{suffix_name}-{n}{ext}"
        n += 1
    return cand


def studio_file(src: str | Path) -> Path:
    """An existing file that must already live inside the Studio folder (drop / restore move it)."""
    if not inside_out_roots(src):
        raise PathRefused("only files inside the Studio folder can be dropped or restored")
    real = Path(_real_target(src))
    if not real.is_file():
        raise FileNotFoundError(real.name)
    return real


# --------------------------------------------------------------------------- network


def ip_allowed(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped or addr.sixtofour
        if mapped is not None:
            return ip_allowed(str(mapped))
        if addr.teredo:
            return False
        if addr in ipaddress.ip_network("64:ff9b::/96") or addr in ipaddress.ip_network("64:ff9b:1::/48"):
            return ip_allowed(str(ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)))
    if isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10"):
        return False  # CGNAT
    return addr.is_global and not (
        addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
    )


def check_url(url: str) -> str:
    """Scheme, shape and every DNS answer of a media URL. Raises URLRefused."""
    parts = urllib.parse.urlsplit(str(url or "").strip())
    if parts.scheme not in ("http", "https"):
        raise URLRefused(f"only http(s) links are allowed, got {parts.scheme or 'none'!r}")
    host = parts.hostname
    if not host:
        raise URLRefused("link has no host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise URLRefused("bad port in link") from None
    check_host(host, port)
    return url


def check_host(host: str, port: int = 443) -> None:
    try:
        infos = _real_getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except OSError as exc:
        raise URLRefused(f"cannot resolve {host}: {exc}") from None
    if not infos:
        raise URLRefused(f"cannot resolve {host}")
    for info in infos:
        if not ip_allowed(str(info[4][0])):
            raise URLRefused(f"{host} resolves to a non-public address ({info[4][0]})")


_real_getaddrinfo = socket.getaddrinfo


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    infos = _real_getaddrinfo(host, port, *args, **kwargs)
    for info in infos:
        if info[0] in (socket.AF_INET, socket.AF_INET6) and not ip_allowed(str(info[4][0])):
            raise OSError(f"hermes-studio: refused connection to non-public address {info[4][0]} ({host})")
    return infos


def install_socket_guard() -> None:
    """Refuse every outbound connection to a non-public address in this process. Connections
    resolve through getaddrinfo, so the addresses checked are the ones actually used."""
    socket.getaddrinfo = _guarded_getaddrinfo
