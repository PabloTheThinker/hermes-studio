"""Hermes Studio plugin — tools other Hermes agents can call. Does not post."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

__plugin_name__ = "hermes-studio"
__plugin_version__ = "0.5.3"

_HERE = Path(__file__).resolve().parent


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


def _run_mod(argv: list[str], timeout: int = 3600) -> dict:
    """Run the CLI with --json: stdout is exactly one JSON object, progress goes to stderr."""
    cmd, extra_env, cwd = _command()
    if "--json" not in argv:
        argv = [*argv, "--json"]
    try:
        proc = subprocess.run([*cmd, *argv], capture_output=True, text=True,
                              env={**os.environ, **extra_env}, timeout=timeout, cwd=cwd)
    except FileNotFoundError:
        return {"ok": False, "code": "missing_dependency", "error": "Hermes Studio is not installed.",
                "hint": "uv tool install git+https://github.com/PabloTheThinker/hermes-studio"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:
        return {"ok": proc.returncode == 0, "error": (proc.stderr or proc.stdout or "")[-2000:], "exit_code": proc.returncode}


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
    argv = [
        "run",
        str(src).strip(),
        *(["--out", str(Path(out).expanduser())] if out else []),
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
    whisper: str = "tiny",
    style: str = "pop",
    layout: str = "fit",
    aspect: str = "9:16",
    hook: bool = True,
) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    argv = [
        "captions",
        str(src).strip(),
        *(["--out", str(Path(out).expanduser())] if out else []),
        "--whisper",
        whisper or "tiny",
        "--style",
        style if style in ("pop", "impact", "clean", "glow", "neon", "boxed") else "pop",
        "--layout",
        layout if layout in ("auto", "fit", "fill", "split") else "fit",
        "--aspect",
        aspect if aspect in ("9:16", "16:9", "1:1", "4:5") else "9:16",
    ]
    if not hook:
        argv.append("--no-hook")
    result = _run_mod(argv)
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
    argv = ["edit", str(Path(src).expanduser()), "--op", op if op in ("trim", "split", "duplicate", "drop", "restore") else "trim"]
    if op == "split":
        argv += ["--at", str(float(at if at is not None else 0))]
    elif op in ("duplicate", "drop", "restore"):
        if out and op == "duplicate":
            argv += ["--out", str(Path(out).expanduser())]
    else:
        argv += ["--start", str(float(start)), "--end", str(float(end))]
        if out:
            argv += ["--out", str(Path(out).expanduser())]
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
    return json.dumps(_run_mod(["recommend", str(src).strip()], timeout=120))


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
    argv = ["transcribe", str(src).strip(), "--whisper", whisper or "tiny"]
    if work:
        argv += ["--work", str(Path(work).expanduser())]
    result = _run_mod(argv)
    return json.dumps(result)


def hermes_studio_plan(transcript: str, max_clips: int = 3, plan: str = "heuristic") -> str:
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
    return json.dumps(result)


def hermes_studio_list(out: str = "") -> str:
    argv = ["list"]
    if out:
        argv += ["--out", str(Path(out).expanduser())]
    result = _run_mod(argv, timeout=30)
    return json.dumps(result)


def hermes_studio_probe(src: str) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    result = _run_mod(["probe", str(src).strip()], timeout=90)
    return json.dumps(result)


def hermes_studio_desk(host: str = "127.0.0.1", port: int = 3870) -> str:
    """Start localhost Studio if it is not already up. Loopback only. Does not post."""
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
    cmd, extra_env, cwd = _command()
    log = Path.home() / ".hermes" / "clips" / "studio.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as fh:
        subprocess.Popen(
            [*cmd, "studio", "--host", host, "--port", str(port), "--no-browser"],
            stdout=fh,
            stderr=fh,
            env={**os.environ, **extra_env},
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
            "description": "Hermes Studio: edit an image file locally. cutout = remove background (transparent PNG); enhance = light, contrast and sharpening with skin texture kept; look = bw|warm|cool|punch|fade|noir. Writes a new file next to the original.",
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
                    "out": {"type": "string", "description": "Output directory"},
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
            "description": "Hermes Studio: local Whisper transcript.json only. No render. No post.",
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
                    "host": {"type": "string", "default": "127.0.0.1"},
                    "port": {"type": "integer", "default": 3870},
                },
            },
        },
        handler=lambda args, **kw: hermes_studio_desk(
            host=(args or {}).get("host") or "127.0.0.1",
            port=int((args or {}).get("port") or 3870),
        ),
        description="Start localhost Hermes Studio (Create / Library / Jobs) on loopback. Does not post.",
    )
    ctx.register_tool(
        name="hermes_studio_captions",
        toolset="hermes-studio",
        schema={
            "name": "hermes_studio_captions",
            "description": "Hermes Studio: burn captions on the full video (no clip planner). Local only. Does not post.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "out": {"type": "string"},
                    "whisper": {"type": "string", "default": "tiny"},
                    "style": {"type": "string", "default": "pop"},
                    "layout": {"type": "string", "enum": ["auto", "fit", "fill", "split"], "default": "fit"},
                    "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1", "4:5"], "default": "9:16"},
                    "hook": {"type": "boolean", "default": True},
                },
                "required": ["src"],
            },
        },
        handler=lambda args, **kw: hermes_studio_captions(
            src=(args or {}).get("src") or "",
            out=(args or {}).get("out") or "",
            whisper=(args or {}).get("whisper") or "tiny",
            style=(args or {}).get("style") or "pop",
            layout=(args or {}).get("layout") or "fit",
            aspect=(args or {}).get("aspect") or "9:16",
            hook=(args or {}).get("hook", True) is not False,
        ),
        description="Hermes Studio: burn captions on the full video. Does not post.",
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
