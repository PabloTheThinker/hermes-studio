"""HermesClip plugin — tools other Hermes agents can call. Does not post."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__plugin_name__ = "hermesclip"
__plugin_version__ = "0.2.0"

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
) -> str:
    if not src or not str(src).strip():
        return json.dumps({"ok": False, "error": "src is required"})
    out_dir = Path(out).expanduser() if out else _out_default()
    out_dir.mkdir(parents=True, exist_ok=True)
    result = _run_mod(
        [
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
            style if style in ("pop", "impact", "clean") else "pop",
            "--plan",
            plan if plan in ("auto", "heuristic", "grok") else "heuristic",
            "--layout",
            layout if layout in ("fit", "fill") else "fit",
        ]
    )
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
    else:
        argv += ["--out", str(_out_default())]
    result = _run_mod(argv, timeout=30)
    if not result.get("ok"):
        return json.dumps(result)
    try:
        data = json.loads(result["stdout"])
        data["ok"] = True
        return json.dumps(data)
    except Exception:
        return json.dumps({"ok": True, "raw": result.get("stdout", "")[-1500:]})


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
        description="HermesClip: list rendered clips from a manifest.json directory.",
    )
