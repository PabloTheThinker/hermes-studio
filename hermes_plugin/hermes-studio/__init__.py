"""Hermes Studio plugin — tools other Hermes agents can call. Does not post."""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path

__plugin_name__ = "hermes-studio"
__plugin_version__ = "0.6.2"

_HERE = Path(__file__).resolve().parent
_ENGINE_TAG = "v0.6.2"  # oldest engine with path confinement and the URL guard
_MIN_ENGINE = (0, 6, 2)
_INSTALL = f"uv tool install git+https://github.com/PabloTheThinker/hermes-studio@{_ENGINE_TAG}"


def _source_checkouts() -> list[Path]:
    env = os.environ.get("HERMES_STUDIO_HOME")
    homes = [Path(env)] if env else []
    projects = Path.home() / "projects"
    return homes + [projects / "hermes-studio", projects / "hermesclip"]


def _command() -> tuple[list[str], dict, str | None]:
    """How to start Hermes Studio: the installed command first, then a source checkout."""
    exe = shutil.which("hermes-studio")
    if exe:
        return [exe], {}, None
    for root in _source_checkouts():
        py = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if py.is_file() and (root / "hermes_studio").is_dir():
            return [str(py), "-m", "hermes_studio"], {"PYTHONPATH": str(root)}, str(root)
    return [sys.executable, "-m", "hermes_studio"], {}, None


def _missing_engine() -> dict:
    """Actionable error when the engine CLI is not on this host."""
    return {
        "ok": False,
        "code": "missing_dependency",
        "error": "Hermes Studio engine is not installed. The chat tools need the hermes-studio CLI.",
        "hint": "Install the engine (separate from this plugin), then retry: " + _INSTALL,
    }


def _engine_available() -> bool:
    """True when the hermes-studio CLI, a source checkout, or this interpreter can import the engine."""
    if shutil.which("hermes-studio"):
        return True
    for root in _source_checkouts():
        py = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if py.is_file() and (root / "hermes_studio").is_dir():
            return True
    try:
        import importlib.util
        return importlib.util.find_spec("hermes_studio") is not None
    except (ImportError, ValueError):
        return False


# ---------------------------------------------------------------- environment and storage

_ENV_KEEP = ("PATH", "HOME", "LANG", "TMPDIR", "PYTHONPATH")
_ENV_KEEP_NT = ("SYSTEMROOT", "SYSTEMDRIVE", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
                "COMSPEC", "PATHEXT", "WINDIR")  # Windows cannot start Python without these


def _engine_env(extra: dict | None = None) -> dict:
    """Minimal environment for the engine: PATH, HOME, LANG, TMPDIR, PYTHONPATH (when set) and the
    HERMES_STUDIO_* settings it reads. Nothing else from the agent's environment is passed on."""
    keep = _ENV_KEEP + (_ENV_KEEP_NT if os.name == "nt" else ())
    env = {k: os.environ[k] for k in keep if os.environ.get(k)}
    env.update({k: v for k, v in os.environ.items() if k.startswith("HERMES_STUDIO_")})
    env.update(extra or {})
    return env


def _data_dir() -> Path:
    """<hermes home>/plugin-data/hermes-studio/ for the active profile (cues, desk log)."""
    try:
        from plugins.plugin_storage import plugin_data_dir

        return plugin_data_dir("hermes-studio")
    except Exception:
        pass
    try:
        from hermes_constants import get_hermes_home

        home = Path(get_hermes_home())
    except Exception:
        home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    d = home / "plugin-data" / "hermes-studio"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- what a tool call may touch
# The engine (>= 0.6.2) enforces the same rules itself; the plugin checks first so a call is
# refused before any process starts, and refuses an older engine that does not enforce them.

_MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".ts", ".m4v", ".avi", ".flv", ".ogv", ".mpg", ".mpeg",
               ".3gp", ".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class _Refused(ValueError):
    pass


def _studio_root() -> Path:
    return Path.home() / ".hermes" / "clips"


def _norm(p: str | Path) -> str:
    return os.path.normpath(os.path.abspath(os.path.expanduser(str(p))))


def _under(path: str, roots: list[str]) -> bool:
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def _media_roots() -> list[str]:
    roots = [str(Path.home()), "/mnt", "/media", "/srv", str(_studio_root() / "library")]
    roots += [r for r in os.environ.get("HERMES_STUDIO_MEDIA_ROOTS", "").split(os.pathsep) if r]
    return [_norm(r) for r in roots]


def _out_roots() -> list[str]:
    roots = [str(_studio_root())]
    roots += [r for r in os.environ.get("HERMES_STUDIO_OUT_ROOTS", "").split(os.pathsep) if r]
    return [os.path.realpath(_norm(r)) for r in roots]


def _local_in(src: str, exts: set[str], what: str) -> str:
    norm = _norm(src)
    real = os.path.realpath(norm)
    if os.path.splitext(norm)[1].lower() not in exts or os.path.splitext(real)[1].lower() not in exts:
        raise _Refused(f"not {what}: {os.path.basename(norm)}")
    roots = _media_roots()
    if not (_under(norm, roots) and _under(real, roots)):
        raise _Refused("local files must be in your home folder, a mounted drive or the library")
    if not os.path.isfile(real):
        raise _Refused(f"file not found: {os.path.basename(norm)}")
    return real


def _ip_ok(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address):
        inner = a.ipv4_mapped or a.sixtofour
        if inner is not None:
            return _ip_ok(str(inner))
        if a.teredo or a in ipaddress.ip_network("64:ff9b::/96") or a in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    if isinstance(a, ipaddress.IPv4Address) and a in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return a.is_global and not (a.is_loopback or a.is_private or a.is_link_local or a.is_multicast
                                or a.is_reserved or a.is_unspecified)


def _check_link(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise _Refused("only http(s) links are allowed")
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
        infos = socket.getaddrinfo(u.hostname, port, 0, socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise _Refused(f"cannot resolve {u.hostname}: {exc}") from None
    for info in infos:
        if not _ip_ok(str(info[4][0])):
            raise _Refused(f"{u.hostname} resolves to a non-public address ({info[4][0]})")
    return url


def _src(src: str, exts: set[str] = _MEDIA_EXTS, what: str = "a video or audio file", links: bool = True) -> str:
    s = str(src or "").strip()
    if "://" in s:
        if not links:
            raise _Refused("links are not accepted here; pass a local file")
        return _check_link(s)
    return _local_in(s, exts, what)


def _out_dir(out: str) -> str:
    norm = _norm(out)
    roots = _out_roots()
    if not (_under(norm, roots) and _under(os.path.realpath(norm), roots)):
        raise _Refused("output folders must be inside ~/.hermes/clips (or HERMES_STUDIO_OUT_ROOTS)")
    return os.path.realpath(norm)


def _out_file(out: str, exts: set[str]) -> str:
    real = _out_dir(out)
    if os.path.splitext(real)[1].lower() not in exts:
        raise _Refused(f"output must end in one of: {' '.join(sorted(exts))}")
    if os.path.lexists(real):
        raise _Refused(f"refusing to overwrite an existing file: {os.path.basename(real)}")
    return real


def _refused(exc: Exception) -> str:
    return json.dumps({"ok": False, "code": "refused", "error": str(exc),
                       "hint": "Sources: media in your home folder, a mounted drive or the library, or a public "
                               "http(s) link. Outputs: new files or folders inside ~/.hermes/clips."})


_ENGINE_OK: dict = {}


def _engine_version_ok(cmd: list[str], extra_env: dict, cwd: str | None) -> bool:
    key = tuple(cmd)
    if key not in _ENGINE_OK:
        ok = False
        try:
            proc = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=60,
                                  env=_engine_env(extra_env), cwd=cwd)
            ver = (proc.stdout or "").strip().split()[-1]
            ok = tuple(int(x) for x in ver.split(".")[:3]) >= _MIN_ENGINE
        except Exception:
            ok = False
        _ENGINE_OK[key] = ok
    return _ENGINE_OK[key]


def _outdated_engine() -> dict:
    return {
        "ok": False,
        "code": "missing_dependency",
        "error": f"The installed Hermes Studio engine is older than {_ENGINE_TAG}; it does not enforce the path and link checks.",
        "hint": "Upgrade the engine, then retry: " + _INSTALL + " --force",
    }


def _run_mod(argv: list[str], timeout: int = 3600) -> dict:
    """Run the CLI with --json: stdout is exactly one JSON object, progress goes to stderr."""
    if not _engine_available():
        return _missing_engine()
    cmd, extra_env, cwd = _command()
    if not _engine_version_ok(cmd, extra_env, cwd):
        return _outdated_engine()
    if "--json" not in argv:
        argv = [*argv, "--json"]
    try:
        proc = subprocess.run([*cmd, *argv], capture_output=True, text=True,
                              env=_engine_env(extra_env), timeout=timeout, cwd=cwd)
    except FileNotFoundError:
        return _missing_engine()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    err = proc.stderr or ""
    if proc.returncode != 0 and "No module named hermes_studio" in err:
        return _missing_engine()
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:
        return {"ok": proc.returncode == 0, "error": (err or proc.stdout or "")[-2000:], "exit_code": proc.returncode}


def hermes_studio_run(
    src: str,
    out: str = "",
    max_clips: int = 3,
    whisper: str = "tiny",
    pacing: str = "tight",
    style: str = "pop",
    plan: str = "heuristic",
    layout: str = "fit",
    live_seconds: int = 1200,
    live_from_start: bool = False,
    prompt: str = "",
    aspect: str = "9:16",
    mode: str = "clip",
    hook: bool = True,
    min_sec: float = 12,
    max_sec: float = 45,
    keywords: str = "",
    captions: bool | None = None,
    face: str = "",
    face_size: float | None = None,
    face_box: str = "",
    filter: str = "",
    caption_pos: str = "",
    audio: str = "",
    progress: bool = False,
    fixes: str = "",
) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    try:
        src = _src(src)
        out = _out_dir(out) if out else ""
    except _Refused as exc:
        return _refused(exc)
    argv = [
        "run",
        src,
        *(["--out", out] if out else []),
        "--max-clips",
        str(int(max_clips) or 3),
        "--whisper",
        whisper or "tiny",
        "--pacing",
        pacing if pacing in ("tight", "natural") else "tight",
        "--style",
        style if style in ("pop", "impact", "clean", "glow", "neon", "boxed") else "pop",
        "--plan",
        plan if plan in ("auto", "heuristic", "grok") else "heuristic",
        "--layout",
        layout if layout in ("auto", "fit", "fill", "split") else "auto",
        "--live-seconds",
        str(int(live_seconds) or 1200),
        "--aspect",
        aspect if aspect in ("9:16", "16:9", "1:1", "4:5", "source") else "9:16",
        "--mode",
        mode if mode in ("clip", "captions", "reframe", "tighten", "transcript") else "clip",
        "--min-sec",
        str(float(min_sec) or 12),
        "--max-sec",
        str(float(max_sec) or 45),
    ]
    if prompt:
        argv += ["--prompt", str(prompt)]
    if keywords:
        argv += ["--keywords", str(keywords)]
    if not hook:
        argv.append("--no-hook")
    if captions is False:
        argv.append("--no-captions")
    if live_from_start:
        argv.append("--live-from-start")
    argv += _look_argv(face=face, face_size=face_size, face_box=face_box, filter=filter,
                       caption_pos=caption_pos, audio=audio, progress=progress, fixes=fixes)
    return json.dumps(_run_mod(argv))


def hermes_studio_captions(
    src: str,
    out: str = "",
    lines: list | None = None,
    style: str = "pop",
    layout: str = "fit",
    aspect: str = "9:16",
    hook: str = "",
) -> str:
    """Burn caption lines the calling agent wrote. Does not call a speech model."""
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    if not lines:
        return json.dumps({
            "ok": False,
            "error": "You write the caption lines. Pass lines.",
            "hint": "transcribe is a draft ear only. Rewrite the words, then pass lines: [{text, start, end}].",
        })
    try:
        src = _src(src)
        if out:
            out = _out_file(out, {".mp4"}) if out.lower().endswith(".mp4") else _out_dir(out)
    except _Refused as exc:
        return _refused(exc)
    cue_path = _data_dir() / "agent-cues.json"
    cue_path.write_text(json.dumps({"hook": hook, "lines": lines}), encoding="utf-8")
    argv = [
        "captions",
        src,
        "--cues",
        str(cue_path),
        "--style",
        style if style in ("pop", "impact", "clean", "glow", "neon", "boxed") else "pop",
        "--layout",
        layout if layout in ("auto", "fit", "fill", "split") else "fit",
        "--aspect",
        aspect if aspect in ("9:16", "16:9", "1:1", "4:5") else "9:16",
    ]
    if out:
        argv += ["--out", out]
    if not hook:
        argv.append("--no-hook")
    result = _run_mod(argv)
    if isinstance(result, dict):
        result["writer"] = result.get("writer") or "agent"
    return json.dumps(result)


def hermes_studio_edit(
    src: str,
    start: float = 0,
    end: float = 0,
    out: str = "",
    op: str = "trim",
    at: float | None = None,
) -> str:
    if not src:
        return json.dumps({"ok": False, "error": "src is required"})
    op = op if op in ("trim", "split", "duplicate", "drop", "restore") else "trim"
    try:
        if op in ("drop", "restore"):  # these move files: only clips already in the Studio folder
            path = _out_dir(src)
            if not os.path.isfile(path):
                raise _Refused(f"file not found: {os.path.basename(path)}")
        else:
            path = _src(src, links=False)
        out = _out_file(out, _MEDIA_EXTS) if out and op in ("trim", "duplicate") else ""
    except _Refused as exc:
        return _refused(exc)
    argv = ["edit", path, "--op", op]
    if op == "split":
        argv += ["--at", str(float(at if at is not None else 0))]
    elif op == "duplicate":
        if out:
            argv += ["--out", out]
    elif op == "trim":
        argv += ["--start", str(float(start)), "--end", str(float(end))]
        if out:
            argv += ["--out", out]
    result = _run_mod(argv, timeout=600)
    return json.dumps(result)


def _look_argv(face="", face_size=None, face_box="", filter="", caption_pos="", audio="", progress=False, fixes="", layout="") -> list[str]:
    argv: list[str] = []
    if layout in ("auto", "fit", "fill", "split"):
        argv += ["--layout", layout]
    if face in ("top", "bottom"):
        argv += ["--face", face]
    if face_size:
        argv += ["--face-size", str(float(face_size))]
    if face_box:
        argv += ["--face-box", str(face_box)]
    if filter in ("none", "punch", "warm", "cool", "cinematic", "vintage", "bw", "bright"):
        argv += ["--filter", filter]
    if caption_pos in ("auto", "top", "middle", "bottom"):
        argv += ["--caption-pos", caption_pos]
    if audio in ("off", "clean"):
        argv += ["--audio", audio]
    if progress:
        argv.append("--progress")
    for part in str(fixes or "").split(","):
        if "=" in part:
            argv += ["--fix", part.strip()]
    return argv


def hermes_studio_restyle(
    job: str,
    file: str,
    layout: str = "",
    face: str = "",
    face_size: float | None = None,
    face_box: str = "",
    filter: str = "",
    caption_pos: str = "",
    audio: str = "",
    progress: bool = False,
    fixes: str = "",
    style: str = "",
    captions: bool | None = None,
    start: float | None = None,
    end: float | None = None,
    title: str = "",
) -> str:
    if not job or not file:
        return json.dumps({"ok": False, "error": "job and file are required"})
    argv = ["restyle", job, file] + _look_argv(face, face_size, face_box, filter, caption_pos, audio, progress, fixes, layout)
    if style in ("pop", "impact", "clean", "glow", "neon", "boxed"):
        argv += ["--style", style]
    if captions is False:
        argv.append("--no-captions")
    if start is not None:
        argv += ["--start", str(float(start))]
    if end is not None:
        argv += ["--end", str(float(end))]
    if title:
        argv += ["--title", title]
    result = _run_mod(argv, timeout=900)
    return json.dumps(result)


def hermes_studio_name(job: str, file: str = "", title: str = "") -> str:
    if not job:
        return json.dumps({"ok": False, "error": "job is required"})
    argv = ["name", job]
    if file:
        argv += ["--file", file, "--title", title]
    result = _run_mod(argv, timeout=900)
    return json.dumps(result)


def hermes_studio_recommend(src: str) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    try:
        src = _src(src)
    except _Refused as exc:
        return _refused(exc)
    return json.dumps(_run_mod(["recommend", src], timeout=120))


def hermes_studio_copy(src: str, clip_title: str = "") -> str:
    if not src:
        return json.dumps({"ok": False, "error": "src is required"})
    argv = ["copy", str(src)]
    if clip_title:
        argv += ["--clip-title", clip_title]
    result = _run_mod(argv, timeout=60)
    return json.dumps(result)


def hermes_studio_transcribe(src: str, work: str = "", whisper: str = "tiny") -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    try:
        src = _src(src)
        work = _out_dir(work) if work else ""
    except _Refused as exc:
        return _refused(exc)
    argv = ["transcribe", src, "--whisper", whisper or "tiny"]
    if work:
        argv += ["--work", work]
    result = _run_mod(argv)
    return json.dumps(result)


def hermes_studio_plan(transcript: str, max_clips: int = 3, plan: str = "heuristic") -> str:
    if not transcript:
        return json.dumps({"ok": False, "error": "transcript path is required"})
    try:
        transcript = _local_in(transcript, {".json"}, "a transcript.json")
    except _Refused as exc:
        return _refused(exc)
    result = _run_mod(
        [
            "plan",
            transcript,
            "--max-clips",
            str(int(max_clips) or 3),
            "--plan",
            plan if plan in ("auto", "heuristic", "grok") else "heuristic",
        ]
    )
    return json.dumps(result)


def hermes_studio_list(out: str = "") -> str:
    argv = ["list"]
    if out:
        try:
            argv += ["--out", _out_dir(out)]
        except _Refused as exc:
            return _refused(exc)
    result = _run_mod(argv, timeout=30)
    return json.dumps(result)


def hermes_studio_probe(src: str) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    try:
        src = _src(src)
    except _Refused as exc:
        return _refused(exc)
    result = _run_mod(["probe", src], timeout=90)
    return json.dumps(result)


def hermes_studio_desk(port: int = 3870) -> str:
    """Start localhost Studio if it is not already up. Loopback (127.0.0.1) only. Does not post."""
    import time
    import urllib.request

    host = "127.0.0.1"
    port = int(port or 3870)
    if not 1024 <= port <= 65535:
        return json.dumps({"ok": False, "error": "port must be 1024-65535"})
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:  # noqa: S310 - fixed loopback URL
            if r.status == 200:
                return json.dumps({"ok": True, "url": url, "already": True})
    except Exception:
        pass
    if not _engine_available():
        return json.dumps(_missing_engine())
    cmd, extra_env, cwd = _command()
    if not _engine_version_ok(cmd, extra_env, cwd):
        return json.dumps(_outdated_engine())
    log = _data_dir() / "studio.log"
    with log.open("ab") as fh:
        subprocess.Popen(
            [*cmd, "studio", "--host", host, "--port", str(port), "--no-browser"],
            stdout=fh,
            stderr=fh,
            env=_engine_env(extra_env),
            cwd=cwd,
            start_new_session=True,
        )
    for _ in range(20):
        time.sleep(0.25)
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return json.dumps({"ok": True, "url": url, "already": False})
        except Exception:
            continue
    return json.dumps({"ok": False, "error": f"studio did not bind {url}", "log": str(log)})


def hermes_studio_design(action: str = "list", id: str = "", title: str = "", size: str = "", template: str = "",
                         ops: list | None = None, pages: list | None = None, format: str = "png") -> str:
    """Canva-style designs through the CLI contract: new, list, show, edit, render, resize, options."""
    action = (action or "list").strip()
    if action == "new":
        argv = ["design", "new", "--size", size or "tiktok-carousel", "--template", template or "blank"]
        if title:
            argv += ["--title", title]
    elif action in ("list", "options"):
        argv = ["design", action]
    elif action in ("show", "edit", "render", "resize"):
        if not id:
            return json.dumps({"ok": False, "error": "id is required"})
        if action == "show":
            argv = ["design", "show", id]
        elif action == "edit":
            argv = ["design", "edit", id, json.dumps(ops or [])]
        elif action == "resize":
            argv = ["design", "resize", id, "--size", size or "story"]
        else:
            argv = ["design", "render", id, "--format", "jpg" if format == "jpg" else "png"]
            if pages:
                argv += ["--pages", ",".join(str(int(p)) for p in pages)]
    else:
        return json.dumps({"ok": False, "error": "action must be new, list, show, edit, render, resize or options"})
    return json.dumps(_run_mod(argv, timeout=600))


def hermes_studio_photo(op: str, src: str, out: str = "", look: str = "", strength: float = 1.0) -> str:
    if op not in ("cutout", "enhance", "look") or not src:
        return json.dumps({"ok": False, "error": "op (cutout|enhance|look) and src are required"})
    try:
        src = _src(src, _IMAGE_EXTS, "a PNG, JPEG or WebP image", links=False)
        out = _out_file(out, _IMAGE_EXTS) if out else ""
    except _Refused as exc:
        return _refused(exc)
    argv = ["photo", op, src]
    if out:
        argv += ["--out", out]
    if look:
        argv += ["--look", look]
    if strength != 1.0:
        argv += ["--strength", str(float(strength))]
    return json.dumps(_run_mod(argv, timeout=600))


def register(ctx) -> None:
    ctx.register_tool(
        name="hermes_studio_design",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_design",
            "description": (
                "Hermes Studio Design: Canva-style carousels, story covers, square posts, YouTube thumbnails and X posts. "
                "action=new (size: tiktok-carousel|story|square|youtube-thumb|x-post; template: blank|carousel|quote|thumbnail|announcement) "
                "returns an id and the design JSON (pages -> layers in pixels). action=show reads it. action=edit applies ops in order: "
                "{op:add_page, bg?, after?} {op:delete_page, page} {op:add, page, layer:{type:text|rect|ellipse|line,...}} "
                "{op:add_image, page, path, x?, y?, w?, h?, fit?, radius?} {op:update, page, index, set:{...}} {op:remove, page, index} "
                "{op:background, page, color} {op:title, title}. Pages 1-based, layer index 0-based bottom to top. Text keys: text, x, y, "
                "w (wraps), size, font archivo|playfair|caveat|mono|opensans, weight, italic, color #rrggbb, align, line, spacing, upper, bg. "
                "action=render exports PNG/JPG paths (look at them before you hand them over); action=resize copies into another size. "
                "The person sees and edits the same design live in the desk's Design page. Never posts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["new", "list", "show", "edit", "render", "resize", "options"]},
                    "id": {"type": "string", "description": "design id (d-...)"},
                    "title": {"type": "string"},
                    "size": {"type": "string", "enum": ["tiktok-carousel", "story", "square", "youtube-thumb", "x-post"]},
                    "template": {"type": "string", "enum": ["blank", "carousel", "quote", "thumbnail", "announcement"]},
                    "ops": {"type": "array", "items": {"type": "object"}},
                    "pages": {"type": "array", "items": {"type": "integer"}},
                    "format": {"type": "string", "enum": ["png", "jpg"]},
                },
                "required": ["action"],
            },
        },
        handler=lambda args, **kw: hermes_studio_design(**{k: v for k, v in (args or {}).items() if k in (
            "action", "id", "title", "size", "template", "ops", "pages", "format")}),
        description="Hermes Studio: Canva-style designs. Local. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_photo",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_photo",
            "description": "Hermes Studio: edit an image file locally. cutout = remove background (transparent PNG); enhance = light, contrast and sharpening with skin texture kept; look = bw|warm|cool|punch|fade|noir. Source: an image in your home folder, a mounted drive or the library. Writes a new file (never overwrites) inside ~/.hermes/clips.",
            "parameters": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["cutout", "enhance", "look"]},
                    "src": {"type": "string", "description": "PNG, JPEG or WebP path"},
                    "out": {"type": "string"},
                    "look": {"type": "string", "enum": ["bw", "warm", "cool", "punch", "fade", "noir"]},
                    "strength": {"type": "number", "default": 1.0},
                },
                "required": ["op", "src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_photo(**{k: v for k, v in (args or {}).items() if k in ("op", "src", "out", "look", "strength")}),
        description="Hermes Studio: background removal, enhance, looks. Local.",
    )
    ctx.register_tool(
        name="hermes_studio_run",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_run",
            "description": "Hermes Studio tools on a local video or URL: mode=clip (hook-first shorts), captions, reframe (change aspect), tighten (cut ums and dead air), transcript (SRT/VTT/TXT). Look: layout auto/fill/split/fit, face top|bottom for streams, colour filter, caption position, audio clean-up, progress bar, word fixes. whisper=fast|balanced|accurate. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Local video path or http(s) URL"},
                    "out": {"type": "string", "description": "Extra copy folder inside ~/.hermes/clips (clips always land in the library)"},
                    "max_clips": {"type": "integer", "default": 3},
                    "whisper": {"type": "string", "default": "fast", "description": "fast | balanced | accurate (or a faster-whisper model)"},
                    "pacing": {"type": "string", "enum": ["tight", "natural"], "default": "tight"},
                    "style": {"type": "string", "enum": ["pop", "impact", "clean", "glow", "neon", "boxed"], "default": "pop"},
                    "plan": {"type": "string", "enum": ["heuristic", "grok", "auto"], "default": "heuristic"},
                    "layout": {"type": "string", "enum": ["auto", "fit", "fill", "split"], "default": "auto", "description": "auto = Hermes picks from the frame. fill = speaker crop. split = facecam band + screen/game. fit = whole frame on blur."},
                    "face": {"type": "string", "enum": ["top", "bottom"], "description": "split: facecam band on top (default) or bottom"},
                    "face_size": {"type": "number", "description": "split: face band % of height, 20-60 (default 35)"},
                    "face_box": {"type": "string", "description": "split: manual camera box x,y,w,h in % of the source, e.g. 76,64,22,30"},
                    "filter": {"type": "string", "enum": ["none", "punch", "warm", "cool", "cinematic", "vintage", "bw", "bright"]},
                    "caption_pos": {"type": "string", "enum": ["auto", "top", "middle", "bottom"], "description": "auto keeps captions out of the platform UI zone; on split it sits on the seam"},
                    "audio": {"type": "string", "enum": ["off", "clean"], "description": "clean = denoise + loudness to -14 LUFS"},
                    "progress": {"type": "boolean", "description": "thin amber progress bar"},
                    "fixes": {"type": "string", "description": "caption word fixes: cloud=Claude, marz=Mars"},
                    "prompt": {"type": "string"},
                    "keywords": {"type": "string", "description": "Words to highlight in captions"},
                    "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1", "4:5", "source"]},
                    "mode": {
                        "type": "string",
                        "enum": ["clip", "captions", "reframe", "tighten", "transcript"],
                        "default": "clip",
                        "description": "Studio tool: clip=hook-first shorts; captions=caption full take; reframe=change aspect; tighten=cut filler/pauses; transcript=SRT/VTT/TXT only",
                    },
                    "captions": {"type": "boolean", "description": "Burn captions (default on for clip/captions)"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_run(**{k: (args or {}).get(k) for k in ("src", "out", "max_clips", "whisper", "pacing", "style", "plan", "layout", "prompt", "keywords", "aspect", "mode", "captions", "face", "face_size", "face_box", "filter", "caption_pos", "audio", "progress", "fixes") if (args or {}).get(k) is not None} | {"src": (args or {}).get("src") or ""}),
        description="Hermes Studio: clips, captions, reframe, tighten or transcript. Local only. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_transcribe",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_transcribe",
            "description": "Draft ear only. Returns words for YOU to rewrite. Do not burn these words. Pass your rewritten lines to hermes_studio_captions. No post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "work": {"type": "string"},
                    "whisper": {"type": "string", "default": "tiny"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_transcribe(
            src=(args or {}).get("src") or "",
            work=(args or {}).get("work") or "",
            whisper=(args or {}).get("whisper") or "tiny",
        ),
        description="Hermes Studio: local Whisper transcript.json only. No render. No post.",
    )
    ctx.register_tool(
        name="hermes_studio_plan",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_plan",
            "description": "Hermes Studio: score hook-first clip windows from a transcript.json. No render.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transcript": {"type": "string", "description": "Path to transcript.json"},
                    "max_clips": {"type": "integer", "default": 3},
                    "plan": {"type": "string", "enum": ["heuristic", "grok", "auto"], "default": "heuristic"},
                },
                "required": ["transcript"],
            },
        },
        handler=lambda args, **kw: hermes_studio_plan(
            transcript=(args or {}).get("transcript") or "",
            max_clips=int((args or {}).get("max_clips") or 3),
            plan=(args or {}).get("plan") or "heuristic",
        ),
        description="Hermes Studio: score hook-first clip windows from a transcript.json. No render.",
    )
    ctx.register_tool(
        name="hermes_studio_list",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_list",
            "description": "Hermes Studio: list rendered clips from a manifest.json directory.",
            "parameters": {
                "type": "object",
                "properties": {"out": {"type": "string", "description": "Directory with manifest.json"}},
            },
        },
        handler=lambda args, **kw: hermes_studio_list(out=(args or {}).get("out") or ""),
        description="Hermes Studio: list the local clip library (or a manifest folder). Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_probe",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_probe",
            "description": "Hermes Studio: probe a URL or file for title and live status. No download.",
            "parameters": {
                "type": "object",
                "properties": {"src": {"type": "string"}},
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_probe(src=(args or {}).get("src") or ""),
        description="Hermes Studio: probe a URL or file for title and live status. No download.",
    )
    ctx.register_tool(
        name="hermes_studio_desk",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_desk",
            "description": "Start localhost Hermes Studio (Create / Library / Jobs) on loopback. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "default": 3870},
                },
            },
        },
        handler=lambda args, **kw: hermes_studio_desk(port=int((args or {}).get("port") or 3870)),
        description="Start localhost Hermes Studio (Create / Library / Jobs) on loopback. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_captions",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_captions",
            "description": "Burn caption lines YOU wrote. Pass lines: [{text, start, end}]. Do not send raw speech-model words. transcribe is a draft ear only. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "out": {"type": "string"},
                    "lines": {"type": "array", "items": {"type": "object"}, "description": "Caption lines you wrote: {text, start, end} in seconds."},
                    "style": {"type": "string", "default": "pop"},
                    "layout": {"type": "string", "enum": ["auto", "fit", "fill", "split"], "default": "fit"},
                    "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1", "4:5"], "default": "9:16"},
                    "hook": {"type": "string", "description": "Short title you wrote. Empty skips the hook card."},
                },
                "required": ["src", "lines"],
            },
        },
        handler=lambda args, **kw: hermes_studio_captions(
            src=(args or {}).get("src") or "",
            out=(args or {}).get("out") or "",
            lines=(args or {}).get("lines") or None,
            style=(args or {}).get("style") or "pop",
            layout=(args or {}).get("layout") or "fit",
            aspect=(args or {}).get("aspect") or "9:16",
            hook=(args or {}).get("hook") or "",
        ),
        description="Burn the calling agent's caption lines. Does not call a speech model. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_edit",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_edit",
            "description": "Hermes Studio: trim, split, duplicate, drop, or restore a clip. Local FFmpeg. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "op": {"type": "string", "enum": ["trim", "split", "duplicate", "drop", "restore"], "default": "trim"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "at": {"type": "number", "description": "Split point in seconds"},
                    "out": {"type": "string"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_edit(
            src=(args or {}).get("src") or "",
            start=float((args or {}).get("start") or 0),
            end=float((args or {}).get("end") or 0),
            out=(args or {}).get("out") or "",
            op=(args or {}).get("op") or "trim",
            at=(args or {}).get("at"),
        ),
        description="Hermes Studio: trim or split a clip. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_restyle",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_restyle",
            "description": "Hermes Studio: edit one library clip after the run. Change layout (auto/fill/split/fit), put the face on top or bottom, band size, colour filter, caption position/style, audio clean-up, progress bar, fix caption words, or move start/end on the source. Old file goes to .trash (restorable). Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job": {"type": "string", "description": "Library run id"},
                    "file": {"type": "string", "description": "Clip file, e.g. clip-01.mp4"},
                    "layout": {"type": "string", "enum": ["auto", "fit", "fill", "split"], "description": "auto = Hermes picks from the frame. fill = speaker crop. split = facecam band + screen/game. fit = whole frame on blur."},
                    "face": {"type": "string", "enum": ["top", "bottom"], "description": "split: facecam band on top (default) or bottom"},
                    "face_size": {"type": "number", "description": "split: face band % of height, 20-60 (default 35)"},
                    "face_box": {"type": "string", "description": "split: manual camera box x,y,w,h in % of the source, e.g. 76,64,22,30"},
                    "filter": {"type": "string", "enum": ["none", "punch", "warm", "cool", "cinematic", "vintage", "bw", "bright"]},
                    "caption_pos": {"type": "string", "enum": ["auto", "top", "middle", "bottom"], "description": "auto keeps captions out of the platform UI zone; on split it sits on the seam"},
                    "audio": {"type": "string", "enum": ["off", "clean"], "description": "clean = denoise + loudness to -14 LUFS"},
                    "progress": {"type": "boolean", "description": "thin amber progress bar"},
                    "fixes": {"type": "string", "description": "caption word fixes: cloud=Claude, marz=Mars"},
                    "style": {"type": "string", "enum": ["pop", "impact", "clean", "glow", "neon", "boxed"]},
                    "captions": {"type": "boolean"},
                    "start": {"type": "number", "description": "New start on the source, seconds"},
                    "end": {"type": "number", "description": "New end on the source, seconds"},
                    "title": {"type": "string"},
                },
                "required": ["job", "file"],
            },
        },
        handler=lambda args, **kw: hermes_studio_restyle(**{k: v for k, v in (args or {}).items() if v is not None and k in ("job", "file", "layout", "face", "face_size", "face_box", "filter", "caption_pos", "audio", "progress", "fixes", "style", "captions", "start", "end", "title")}),
        description="Hermes Studio: restyle / re-cut one clip. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_name",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_name",
            "description": "Hermes Studio: AI-name every clip in a library run from its own words (Opus Clip-style titles, local Ollama first), or set one clip's name with file+title. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job": {"type": "string", "description": "Library run id"},
                    "file": {"type": "string", "description": "Optional: one clip file to rename"},
                    "title": {"type": "string", "description": "Title for that file"},
                },
                "required": ["job"],
            },
        },
        handler=lambda args, **kw: hermes_studio_name(job=(args or {}).get("job") or "", file=(args or {}).get("file") or "", title=(args or {}).get("title") or ""),
        description="Hermes Studio: AI clip names. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_recommend",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_recommend",
            "description": "Hermes Studio: analyze a source and return the best local job settings. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {"src": {"type": "string"}},
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_recommend(src=(args or {}).get("src") or ""),
        description="Hermes Studio: analyze a source and pick settings. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_copy",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_copy",
            "description": "Hermes Studio: local titles, description, hashtags for a job. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Job id or job directory"},
                    "clip_title": {"type": "string"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_copy(
            src=(args or {}).get("src") or "",
            clip_title=(args or {}).get("clip_title") or "",
        ),
        description="Hermes Studio: local social copy pack. Does not post.",
    )
    _register_slash(ctx)


_STUDIO_VERBS = ("clip", "captions", "reframe", "tighten", "transcribe", "desk", "open", "help", "this")


def _studio_help() -> str:
    return (
        "Hermes Studio commands (Desktop chat, Telegram, CLI):\n"
        "  /studio clip <url or file>       hook-first shorts\n"
        "  /studio captions <url or file>   captioned take (you write the lines)\n"
        "  /studio reframe <url or file>    change aspect\n"
        "  /studio tighten <url or file>    cut filler\n"
        "  /studio transcribe <url or file> draft transcript only\n"
        "  /studio this <url or file>       throw it into Studio (clip)\n"
        "  /studio desk                     open the local desk\n"
        "Never posts. Attach a video or paste a link after the command."
    )


def _studio_prompt(verb: str, src: str) -> str:
    if verb == "captions":
        job = (
            "Throw this video into Hermes Studio as captions. "
            "I write the caption lines (hermes_studio_captions with lines). "
            "A speech model is a draft ear only. Do not burn raw speech-model words. Never post."
        )
    elif verb == "reframe":
        job = "Throw this video into Hermes Studio as a reframe (hermes_studio_run mode=reframe). Never post."
    elif verb == "tighten":
        job = "Throw this video into Hermes Studio and tighten it (hermes_studio_run mode=tighten). Never post."
    elif verb == "transcribe":
        job = (
            "Throw this video into Hermes Studio for a draft transcript only "
            "(hermes_studio_transcribe). I rewrite those words before any burn. Never post."
        )
    else:
        job = (
            "Throw this video into Hermes Studio as hook-first shorts "
            "(hermes_studio_run mode=clip). Caption lines I write, not a speech model. Never post."
        )
    if src:
        return job + f"\n\nSource: {src}"
    return job + "\n\nUse the video I just attached or the last video in this chat."


def _handle_studio(raw_args: str, *, session_id: str = "", session_key: str = "", platform: str = "") -> str:
    text = (raw_args or "").strip()
    if not text or text.split()[0].lower() in {"help", "-h", "--help"}:
        return _studio_help()
    parts = text.split(None, 1)
    head = parts[0].lower().lstrip("/")
    rest = parts[1].strip() if len(parts) > 1 else ""
    if head in _STUDIO_VERBS:
        verb, src = head, rest
    else:
        verb, src = "clip", text
    if verb in {"desk", "open"}:
        return hermes_studio_desk()
    if verb == "help":
        return _studio_help()
    prompt = _studio_prompt(verb, src)
    injected = False
    try:
        fn = getattr(_handle_studio, "_inject", None)
        if callable(fn):
            injected = bool(fn(prompt, role="user", session_key=session_key or None))
    except Exception:
        injected = False
    if injected:
        return f"Studio queued ({verb}). The agent will pick it up this turn."
    return (
        "Studio command received. Paste this to the agent if it does not pick up:\n\n"
        + prompt
    )


def _register_slash(ctx) -> None:
    inject = getattr(ctx, "inject_message", None)
    _handle_studio._inject = inject if callable(inject) else None  # type: ignore[attr-defined]
    try:
        ctx.register_command(
            "studio",
            _handle_studio,
            description="Throw a video into Hermes Studio",
            args_hint="<clip|captions|reframe|tighten|this> <url or file>",
        )
    except Exception:
        pass

