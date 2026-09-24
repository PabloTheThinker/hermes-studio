"""HermesClip plugin — tools other Hermes agents can call. Does not post."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__plugin_name__ = "hermesclip"
__plugin_version__ = "0.3.0"

_HERE = Path(__file__).resolve().parent
_PROJECT = Path.home() / "projects" / "hermesclip"
_PY_CANDIDATES = [
    _PROJECT / ".venv" / "bin" / "python",
    Path.home() / "projects" / "ilo-clip" / ".venv" / "bin" / "python",
]


def _python() -> str:
    for py in _PY_CANDIDATES:
        if not py.is_file():
            continue
        probe = subprocess.run(
            [str(py), "-c", "import hermesclip"],
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(_PROJECT)},
            timeout=20,
        )
        if probe.returncode == 0:
            return str(py)
    return sys.executable


def _out_default() -> Path:
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    p = Path(home) / "clips"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _run_mod(argv: list[str], timeout: int = 3600) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_PROJECT)
    try:
        proc = subprocess.run(
            [_python(), "-m", "hermesclip", *argv],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            cwd=str(_PROJECT),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout or "")[-2000:], "code": proc.returncode}
    return {"ok": True, "stdout": proc.stdout or ""}


def hermesclip_run(
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
) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    out_dir = Path(out).expanduser() if out else _out_default()
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        "run",
        str(src).strip(),
        "--out",
        str(out_dir),
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
        layout if layout in ("fit", "fill") else "fit",
        "--live-seconds",
        str(int(live_seconds) or 1200),
        "--aspect",
        aspect if aspect in ("9:16", "16:9", "1:1") else "9:16",
        "--mode",
        mode if mode in ("clip", "captions") else "clip",
        "--min-sec",
        str(float(min_sec) or 12),
        "--max-sec",
        str(float(max_sec) or 45),
    ]
    if prompt:
        argv += ["--prompt", str(prompt)]
    if not hook:
        argv.append("--no-hook")
    if live_from_start:
        argv.append("--live-from-start")
    result = _run_mod(argv)
    if not result.get("ok"):
        return json.dumps(result)
    clips = []
    manifest = out_dir / "manifest.json"
    if manifest.is_file():
        try:
            clips = json.loads(manifest.read_text()).get("clips") or []
        except Exception:
            clips = []
    return json.dumps({"ok": True, "out": str(out_dir), "clips": clips, "log": (result.get("stdout") or "")[-1500:]})


def hermesclip_captions(
    src: str,
    out: str = "",
    whisper: str = "tiny",
    style: str = "pop",
    layout: str = "fit",
    aspect: str = "9:16",
    hook: bool = True,
) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    out_dir = Path(out).expanduser() if out else _out_default()
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        "captions",
        str(src).strip(),
        "--out",
        str(out_dir),
        "--whisper",
        whisper or "tiny",
        "--style",
        style if style in ("pop", "impact", "clean", "glow", "neon", "boxed") else "pop",
        "--layout",
        layout if layout in ("fit", "fill") else "fit",
        "--aspect",
        aspect if aspect in ("9:16", "16:9", "1:1") else "9:16",
    ]
    if not hook:
        argv.append("--no-hook")
    result = _run_mod(argv)
    if not result.get("ok"):
        return json.dumps(result)
    return json.dumps({"ok": True, "out": str(out_dir), "log": (result.get("stdout") or "")[-1500:]})


def hermesclip_edit(
    src: str,
    start: float = 0,
    end: float = 0,
    out: str = "",
    op: str = "trim",
    at: float | None = None,
) -> str:
    if not src:
        return json.dumps({"ok": False, "error": "src is required"})
    argv = ["edit", str(Path(src).expanduser()), "--op", op if op in ("trim", "split", "duplicate", "drop") else "trim"]
    if op == "split":
        argv += ["--at", str(float(at if at is not None else 0))]
    elif op in ("duplicate", "drop"):
        if out and op == "duplicate":
            argv += ["--out", str(Path(out).expanduser())]
    else:
        argv += ["--start", str(float(start)), "--end", str(float(end))]
        if out:
            argv += ["--out", str(Path(out).expanduser())]
    result = _run_mod(argv, timeout=600)
    if not result.get("ok"):
        return json.dumps(result)
    try:
        return json.dumps(json.loads(result["stdout"].strip().splitlines()[-1]))
    except Exception:
        return json.dumps({"ok": True, "log": result.get("stdout", "")[-1500:]})


def hermesclip_recommend(src: str) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_PROJECT)
    try:
        proc = subprocess.run(
            [
                _python(),
                "-c",
                "import json,sys; from hermesclip.recommend import recommend_for; i,r=recommend_for(sys.argv[1]); print(json.dumps({'ok':True,'title':i.title,'is_live':i.is_live,'duration':i.duration,'recommendation':r.as_job()}))",
                str(src).strip(),
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=40,
            cwd=str(_PROJECT),
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    if proc.returncode != 0:
        return json.dumps({"ok": False, "error": (proc.stderr or proc.stdout or "")[-2000:]})
    try:
        return json.dumps(json.loads(proc.stdout.strip().splitlines()[-1]))
    except Exception:
        return json.dumps({"ok": True, "log": proc.stdout[-1500:]})


def hermesclip_copy(src: str, clip_title: str = "") -> str:
    if not src:
        return json.dumps({"ok": False, "error": "src is required"})
    argv = ["copy", str(src)]
    if clip_title:
        argv += ["--clip-title", clip_title]
    result = _run_mod(argv, timeout=60)
    if not result.get("ok"):
        return json.dumps(result)
    try:
        return json.dumps(json.loads(result["stdout"].strip().splitlines()[-1]))
    except Exception:
        return json.dumps({"ok": True, "log": result.get("stdout", "")[-1500:]})


def hermesclip_transcribe(src: str, work: str = "", whisper: str = "tiny") -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    argv = ["transcribe", str(src).strip(), "--whisper", whisper or "tiny"]
    if work:
        argv += ["--work", str(Path(work).expanduser())]
    result = _run_mod(argv)
    if not result.get("ok"):
        return json.dumps(result)
    try:
        return json.dumps(json.loads(result["stdout"].strip().splitlines()[-1]))
    except Exception:
        return json.dumps({"ok": True, "log": result.get("stdout", "")[-1500:]})


def hermesclip_plan(transcript: str, max_clips: int = 3, plan: str = "heuristic") -> str:
    if not transcript:
        return json.dumps({"ok": False, "error": "transcript path is required"})
    result = _run_mod(
        [
            "plan",
            str(Path(transcript).expanduser()),
            "--max-clips",
            str(int(max_clips) or 3),
            "--plan",
            plan if plan in ("auto", "heuristic", "grok") else "heuristic",
        ]
    )
    if not result.get("ok"):
        return json.dumps(result)
    try:
        return result["stdout"]
    except Exception:
        return json.dumps({"ok": False, "error": "plan produced no JSON"})


def hermesclip_list(out: str = "") -> str:
    argv = ["list"]
    if out:
        argv += ["--out", str(Path(out).expanduser())]
    result = _run_mod(argv, timeout=30)
    if not result.get("ok"):
        return json.dumps(result)
    try:
        data = json.loads(result["stdout"])
        data["ok"] = True
        return json.dumps(data)
    except Exception:
        return json.dumps({"ok": True, "raw": result.get("stdout", "")[-1500:]})


def hermesclip_probe(src: str) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    result = _run_mod(["probe", str(src).strip()], timeout=90)
    if not result.get("ok"):
        return json.dumps(result)
    try:
        return result["stdout"].strip().splitlines()[-1]
    except Exception:
        return json.dumps({"ok": True, "raw": result.get("stdout", "")[-1500:]})


def hermesclip_studio(host: str = "127.0.0.1", port: int = 3870) -> str:
    """Start localhost Studio if it is not already up. Loopback only. Does not post."""
    import socket
    import time
    import urllib.request

    host = host or "127.0.0.1"
    port = int(port or 3870)
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            if r.status == 200:
                return json.dumps({"ok": True, "url": url, "already": True})
    except Exception:
        pass
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_PROJECT)
    log = Path.home() / ".hermes" / "clips" / "studio.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as fh:
        subprocess.Popen(
            [_python(), "-m", "hermesclip", "studio", "--host", host, "--port", str(port)],
            stdout=fh,
            stderr=fh,
            env=env,
            cwd=str(_PROJECT),
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


def register(ctx) -> None:
    ctx.register_tool(
        name="hermesclip_run",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_run",
            "description": "HermesClip: cut a local video or URL into captioned 9:16 shorts. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Local video path or http(s) URL"},
                    "out": {"type": "string", "description": "Output directory"},
                    "max_clips": {"type": "integer", "default": 3},
                    "whisper": {"type": "string", "default": "tiny"},
                    "pacing": {"type": "string", "enum": ["tight", "natural"], "default": "tight"},
                    "style": {"type": "string", "enum": ["pop", "impact", "clean"], "default": "pop"},
                    "plan": {"type": "string", "enum": ["heuristic", "grok", "auto"], "default": "heuristic"},
                    "layout": {"type": "string", "enum": ["fit", "fill"], "default": "fit"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermesclip_run(**{k: (args or {}).get(k) for k in ("src", "out", "max_clips", "whisper", "pacing", "style", "plan", "layout") if (args or {}).get(k) is not None} | {"src": (args or {}).get("src") or ""}),
        description="HermesClip: cut a local video or URL into captioned 9:16 shorts. Does not post.",
    )
    ctx.register_tool(
        name="hermesclip_transcribe",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_transcribe",
            "description": "HermesClip: local Whisper transcript.json only. No render. No post.",
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
        handler=lambda args, **kw: hermesclip_transcribe(
            src=(args or {}).get("src") or "",
            work=(args or {}).get("work") or "",
            whisper=(args or {}).get("whisper") or "tiny",
        ),
        description="HermesClip: local Whisper transcript.json only. No render. No post.",
    )
    ctx.register_tool(
        name="hermesclip_plan",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_plan",
            "description": "HermesClip: score hook-first clip windows from a transcript.json. No render.",
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
        handler=lambda args, **kw: hermesclip_plan(
            transcript=(args or {}).get("transcript") or "",
            max_clips=int((args or {}).get("max_clips") or 3),
            plan=(args or {}).get("plan") or "heuristic",
        ),
        description="HermesClip: score hook-first clip windows from a transcript.json. No render.",
    )
    ctx.register_tool(
        name="hermesclip_list",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_list",
            "description": "HermesClip: list rendered clips from a manifest.json directory.",
            "parameters": {
                "type": "object",
                "properties": {"out": {"type": "string", "description": "Directory with manifest.json"}},
            },
        },
        handler=lambda args, **kw: hermesclip_list(out=(args or {}).get("out") or ""),
        description="HermesClip: list the local clip library (or a manifest folder). Does not post.",
    )
    ctx.register_tool(
        name="hermesclip_probe",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_probe",
            "description": "HermesClip: probe a URL or file for title and live status. No download.",
            "parameters": {
                "type": "object",
                "properties": {"src": {"type": "string"}},
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermesclip_probe(src=(args or {}).get("src") or ""),
        description="HermesClip: probe a URL or file for title and live status. No download.",
    )
    ctx.register_tool(
        name="hermesclip_studio",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_studio",
            "description": "Start localhost Hermes Studio (Create / Library / Jobs) on loopback. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": "127.0.0.1"},
                    "port": {"type": "integer", "default": 3870},
                },
            },
        },
        handler=lambda args, **kw: hermesclip_studio(
            host=(args or {}).get("host") or "127.0.0.1",
            port=int((args or {}).get("port") or 3870),
        ),
        description="Start localhost Hermes Studio (Create / Library / Jobs) on loopback. Does not post.",
    )
    ctx.register_tool(
        name="hermesclip_captions",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_captions",
            "description": "HermesClip: burn captions on the full video (no clip planner). Local only. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "out": {"type": "string"},
                    "whisper": {"type": "string", "default": "tiny"},
                    "style": {"type": "string", "default": "pop"},
                    "layout": {"type": "string", "enum": ["fit", "fill"], "default": "fit"},
                    "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1"], "default": "9:16"},
                    "hook": {"type": "boolean", "default": True},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermesclip_captions(
            src=(args or {}).get("src") or "",
            out=(args or {}).get("out") or "",
            whisper=(args or {}).get("whisper") or "tiny",
            style=(args or {}).get("style") or "pop",
            layout=(args or {}).get("layout") or "fit",
            aspect=(args or {}).get("aspect") or "9:16",
            hook=(args or {}).get("hook", True) is not False,
        ),
        description="HermesClip: burn captions on the full video. Does not post.",
    )
    ctx.register_tool(
        name="hermesclip_edit",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_edit",
            "description": "HermesClip: trim or split an existing clip. Local FFmpeg. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "op": {"type": "string", "enum": ["trim", "split", "duplicate", "drop"], "default": "trim"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "at": {"type": "number", "description": "Split point in seconds"},
                    "out": {"type": "string"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermesclip_edit(
            src=(args or {}).get("src") or "",
            start=float((args or {}).get("start") or 0),
            end=float((args or {}).get("end") or 0),
            out=(args or {}).get("out") or "",
            op=(args or {}).get("op") or "trim",
            at=(args or {}).get("at"),
        ),
        description="HermesClip: trim or split a clip. Does not post.",
    )
    ctx.register_tool(
        name="hermesclip_recommend",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_recommend",
            "description": "HermesClip: analyze a source and return the best local job settings. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {"src": {"type": "string"}},
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermesclip_recommend(src=(args or {}).get("src") or ""),
        description="HermesClip: analyze a source and pick settings. Does not post.",
    )
    ctx.register_tool(
        name="hermesclip_copy",
        toolset="hermesclip",
        schema={
            "name": "hermesclip_copy",
            "description": "HermesClip: local titles, description, hashtags for a job. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Job id or job directory"},
                    "clip_title": {"type": "string"},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermesclip_copy(
            src=(args or {}).get("src") or "",
            clip_title=(args or {}).get("clip_title") or "",
        ),
        description="HermesClip: local social copy pack. Does not post.",
    )
