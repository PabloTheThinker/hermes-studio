"""Hermes Studio over MCP (stdio). For Claude, Grok, Codex, Cursor, Hermes and any MCP client.

Speaks the standard stdio transport (one JSON-RPC message per line) and, for older
clients, Content-Length framing — whichever the client sends first. Tools call
``hermes_studio.api`` directly and return both readable text and ``structuredContent``.
Long jobs can run in the background (``detach``) and report progress when the client
sends a progressToken. Nothing here posts anywhere.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from hermes_studio import __version__
from hermes_studio.api import ASPECTS, CAPTION_POS, FILTERS, LAYOUTS, MODES, STYLES, HermesStudioError

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "Hermes Studio makes short-form clips on this computer: long video or link in, captioned 9:16 shorts out. "
    "Nothing is uploaded or posted. Typical flow: `doctor` once if unsure; `run` with src (a local file path or "
    "http(s) link); read `items` for each clip's path, title, score and length; `restyle` to change one clip's "
    "look; `copy` for titles/description/hashtags. Runs take minutes: pass detach=true to get an id back at once, "
    "then poll `show` until status is completed or failed. Local files must be under the user's home folder or a "
    "mounted drive."
)

_S = {"type": "string"}
_LOOK = {
    "layout": {"type": "string", "enum": list(LAYOUTS), "description": "auto picks from the frame; fill = speaker crop; split = facecam band + screen/game; fit = whole frame on blur"},
    "face": {"type": "string", "enum": ["top", "bottom"], "description": "split layout: face band on top or bottom"},
    "face_size": {"type": "number", "minimum": 20, "maximum": 60, "description": "split layout: face band % of height"},
    "face_box": {"type": "string", "description": "split layout: manual camera box x,y,w,h in % of the source, e.g. 76,64,22,30"},
    "filter": {"type": "string", "enum": list(FILTERS), "description": "colour look"},
    "caption_pos": {"type": "string", "enum": list(CAPTION_POS)},
    "audio": {"type": "string", "enum": ["off", "clean"], "description": "clean = denoise + loudness to -14 LUFS"},
    "progress": {"type": "boolean", "description": "thin amber progress bar on the clip"},
    "fixes": {"type": "string", "description": "caption word fixes, comma-separated: cloud=Claude,marz=Mars"},
}
_ITEM = {"type": "object", "properties": {"file": _S, "path": _S, "title": _S, "start": {"type": "number"}, "end": {"type": "number"},
                                          "seconds": {"type": ["number", "null"]}, "score": {"type": ["number", "null"]}}}
_RUN_OUT = {"type": "object", "properties": {"ok": {"type": "boolean"}, "id": _S, "status": _S, "title": {"type": ["string", "null"]},
                                             "clips": {"type": "array", "items": _S}, "items": {"type": "array", "items": _ITEM},
                                             "dir": {"type": ["string", "null"]}, "error": {"type": ["string", "null"]}}, "required": ["ok"]}
_RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
_RO_NET = {**_RO, "openWorldHint": True}
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}

TOOLS: list[dict] = [
    {
        "name": "run",
        "title": "Make clips",
        "description": "Make short clips from a video file or http(s) link (YouTube, X, Twitch, Kick…). mode=clip finds hook-first "
                       "moments and renders captioned shorts; captions captions the whole video; reframe changes aspect; tighten "
                       "cuts filler and pauses; transcript writes SRT/VTT/TXT. Returns each clip's path, title, score and length. "
                       "Takes minutes; set detach=true to get an id immediately and poll `show`. Saved to the local library. Does not post.",
        "inputSchema": {"type": "object", "properties": {
            "src": {"type": "string", "description": "local video/audio path (under the home folder) or http(s) link"},
            "mode": {"type": "string", "enum": list(MODES), "default": "clip"},
            "max_clips": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3},
            "min_sec": {"type": "number", "default": 12}, "max_sec": {"type": "number", "default": 45},
            "prompt": {"type": "string", "description": "what to hunt for, e.g. 'funny moments', 'the pricing part'"},
            "keywords": {"type": "string", "description": "words to highlight in captions, comma-separated"},
            "aspect": {"type": "string", "enum": list(ASPECTS)},
            "style": {"type": "string", "enum": list(STYLES), "default": "pop", "description": "caption style"},
            "captions": {"type": "boolean", "description": "burn captions (default on)"},
            "hook": {"type": "boolean", "description": "hook title in the first seconds (default on for clips)"},
            "whisper": {"type": "string", "enum": ["fast", "balanced", "accurate"], "default": "fast", "description": "speech quality vs speed"},
            "recommend": {"type": "boolean", "description": "analyse the source first and pick settings"},
            "out": {"type": "string", "description": "optional folder to also copy results into"},
            "detach": {"type": "boolean", "description": "return an id at once and keep working in the background; poll `show`"},
            **_LOOK,
        }, "required": ["src"], "additionalProperties": False},
        "outputSchema": _RUN_OUT,
        "annotations": {"title": "Make clips", **_WRITE},
    },
    {
        "name": "show",
        "title": "Show a run",
        "description": "One run from the library: status (queued/running/completed/failed), progress message, and each clip's path, title, score and length. Use it to poll a detached run.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "run id from `run` or `list`"}}, "required": ["id"], "additionalProperties": False},
        "annotations": {"title": "Show a run", **_RO},
    },
    {
        "name": "list",
        "title": "List runs",
        "description": "Runs in the local library, newest first, with id, title, status and clip count.",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "minimum": 0, "default": 20, "description": "0 = all"},
            "status": {"type": "string", "enum": ["completed", "failed", "running", "queued"]}}, "additionalProperties": False},
        "annotations": {"title": "List runs", **_RO},
    },
    {
        "name": "restyle",
        "title": "Restyle a clip",
        "description": "Re-render one clip from a run with a new look (layout, face band, colour filter, caption style/position, audio clean-up, progress bar, word fixes) or new start/end on the source. The old file is kept in .trash. Does not post.",
        "inputSchema": {"type": "object", "properties": {
            "id": {"type": "string", "description": "run id"}, "file": {"type": "string", "description": "clip file, e.g. clip-01.mp4"},
            "style": {"type": "string", "enum": list(STYLES)}, "captions": {"type": "boolean"}, "hook": {"type": "boolean"},
            "start": {"type": "number"}, "end": {"type": "number"}, "title": {"type": "string"}, **_LOOK,
        }, "required": ["id", "file"], "additionalProperties": False},
        "annotations": {"title": "Restyle a clip", **_WRITE, "openWorldHint": False},
    },
    {
        "name": "edit",
        "title": "Edit a clip file",
        "description": "trim (start,end), split (at), duplicate, drop (to .trash) or restore a clip file. Does not post.",
        "inputSchema": {"type": "object", "properties": {
            "src": {"type": "string", "description": "clip file path"},
            "op": {"type": "string", "enum": ["trim", "split", "duplicate", "drop", "restore"], "default": "trim"},
            "start": {"type": "number"}, "end": {"type": "number"}, "at": {"type": "number"}, "out": {"type": "string"},
        }, "required": ["src"], "additionalProperties": False},
        "annotations": {"title": "Edit a clip file", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "probe",
        "title": "Probe a source",
        "description": "Title, length, platform and live status of a file or link, without downloading it.",
        "inputSchema": {"type": "object", "properties": {"src": {"type": "string"}}, "required": ["src"], "additionalProperties": False},
        "annotations": {"title": "Probe a source", **_RO_NET},
    },
    {
        "name": "recommend",
        "title": "Recommend settings",
        "description": "Suggested run settings for a file or link (mode, clip count, layout, style, why). Pass them to `run`.",
        "inputSchema": {"type": "object", "properties": {"src": {"type": "string"}}, "required": ["src"], "additionalProperties": False},
        "annotations": {"title": "Recommend settings", **_RO_NET},
    },
    {
        "name": "copy",
        "title": "Write post copy",
        "description": "Titles, description and hashtags for a run (id, run folder or transcript.json). Text only; does not post.",
        "inputSchema": {"type": "object", "properties": {"src": {"type": "string"}, "clip_title": {"type": "string"}}, "required": ["src"], "additionalProperties": False},
        "annotations": {"title": "Write post copy", **_RO},
    },
    {
        "name": "name",
        "title": "Name clips",
        "description": "AI titles for every clip in a run from its words (local Ollama first), or rename one clip with file+title.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "file": {"type": "string"}, "title": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
        "annotations": {"title": "Name clips", **_WRITE, "openWorldHint": False},
    },
    {
        "name": "tools",
        "title": "What Studio can do",
        "description": "Modes, caption styles, colour filters, layouts and aspects Studio supports.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "What Studio can do", **_RO},
    },
    {
        "name": "doctor",
        "title": "Check setup",
        "description": "Checks FFmpeg (with caption burn-in), speech recognition, link downloads and the library folder. Each failed check has a fix.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "Check setup", **_RO},
    },
]
_BY_NAME = {t["name"]: t for t in TOOLS}
# Older names still work so existing agent configs keep running.
_ALIASES = {"captions": "run"}


def _look(args: dict) -> dict:
    lk: dict = {}
    for k in ("layout", "face", "filter", "caption_pos", "audio"):
        if args.get(k) not in (None, ""):
            lk[k] = args[k]
    if args.get("face_size") not in (None, ""):
        lk["face_ratio"] = float(args["face_size"])
    if args.get("face_box"):
        lk["face_box"] = str(args["face_box"])
    if args.get("progress"):
        lk["progress"] = True
    return lk


# --------------------------------------------------------------------------- transport


class Transport:
    """stdio JSON-RPC. Protocol output goes to a private copy of stdout; fd 1 is pointed at stderr
    so a stray print (ours, a library's or a child process's) can never corrupt the stream."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.framing = "line"
        self.inp = sys.stdin.buffer
        try:
            proto_fd = os.dup(1)
            os.dup2(2, 1)
            self.out = os.fdopen(proto_fd, "wb", buffering=0)
            sys.stdout = sys.stderr
        except OSError:
            self.out = sys.stdout.buffer

    def read(self) -> dict | None:
        while True:
            line = self.inp.readline()
            if not line:
                return None
            s = line.strip()
            if not s:
                continue
            if s.lower().startswith(b"content-length:"):
                self.framing = "lsp"
                length = int(s.split(b":", 1)[1].strip())
                while True:  # rest of the header block
                    h = self.inp.readline()
                    if not h or not h.strip():
                        break
                body = self.inp.read(length)
                return json.loads(body.decode("utf-8"))
            try:
                return json.loads(s.decode("utf-8"))
            except json.JSONDecodeError:
                self.write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})

    def write(self, msg: dict) -> None:
        raw = json.dumps(msg, ensure_ascii=False, default=str).encode("utf-8")
        with self.lock:
            if self.framing == "lsp":
                self.out.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
            else:
                self.out.write(raw + b"\n")
            try:
                self.out.flush()
            except Exception:
                pass


# --------------------------------------------------------------------------- tools


def call_tool(name: str, args: dict, progress=None) -> dict:
    """Run one tool. Returns the tool's JSON result; raises HermesStudioError for caller mistakes."""
    from hermes_studio import api

    name = _ALIASES.get(name, name)
    a = dict(args or {})
    if name == "run":
        detach = bool(a.pop("detach", False))
        kw: dict[str, Any] = dict(
            mode=a.get("mode") or "clip", out=a.get("out") or None, max_clips=int(a.get("max_clips") or 3),
            min_sec=float(a.get("min_sec") or 12), max_sec=float(a.get("max_sec") or 45), whisper=a.get("whisper") or "fast",
            style=a.get("style") or "pop", aspect=a.get("aspect"), layout=a.get("layout"), captions=a.get("captions"),
            hook=a.get("hook"), prompt=a.get("prompt") or "", keywords=a.get("keywords") or "", look=_look(a),
            fixes=a.get("fixes") or "", recommend=bool(a.get("recommend")),
        )
        if not detach:
            return api.run(str(a.get("src") or ""), on_progress=progress, **kw)
        api.check_source(str(a.get("src") or ""))
        api.require_ffmpeg()
        created = threading.Event()
        box: dict = {}

        def on_created(job) -> None:
            box["id"] = job.id
            created.set()

        def work() -> None:
            try:
                api.run(str(a.get("src") or ""), on_created=on_created, **kw)
            except Exception as exc:  # surfaced through `show`; keep the server alive
                box["error"] = str(exc)
                created.set()

        threading.Thread(target=work, name="hermes-studio-run", daemon=True).start()
        created.wait(120)
        if not box.get("id"):
            raise HermesStudioError(box.get("error") or "The run did not start.", code="failed")
        return {"ok": True, "id": box["id"], "status": "running", "detached": True,
                "next": f"Poll the `show` tool with id={box['id']} until status is completed or failed."}
    if name == "show":
        return api.show(str(a.get("id") or a.get("job") or ""))
    if name == "list":
        return api.library(limit=int(a["limit"]) if a.get("limit") not in (None, "") else 20, status=a.get("status"))
    if name == "restyle":
        return api.restyle(str(a.get("id") or a.get("job") or ""), str(a.get("file") or ""), look=_look(a), style=a.get("style"),
                           captions=a.get("captions"), hook=a.get("hook"), start=a.get("start"), end=a.get("end"),
                           fixes=a.get("fixes") or "", title=a.get("title"))
    if name == "edit":
        return api.edit(str(a.get("src") or ""), str(a.get("op") or "trim"), start=a.get("start"), end=a.get("end"),
                        at=a.get("at"), out=a.get("out"))
    if name == "probe":
        return api.probe_source(str(a.get("src") or ""))
    if name == "recommend":
        return api.recommend(str(a.get("src") or ""))
    if name == "copy":
        return api.copy(str(a.get("src") or ""), str(a.get("clip_title") or ""))
    if name == "name":
        return api.name(str(a.get("id") or a.get("job") or ""), str(a.get("file") or ""), str(a.get("title") or ""))
    if name == "tools":
        return api.tools()
    if name == "doctor":
        return api.doctor()
    raise HermesStudioError(f"Unknown tool: {name}", code="not_found", hint="Call tools/list for the tool names.")


def _summary(name: str, res: dict) -> str:
    """A short readable line for the model, ahead of the full JSON."""
    if name == "run" and res.get("detached"):
        return f"Started run {res['id']} in the background. Poll `show` with this id."
    if name == "run":
        items = res.get("items") or []
        if not res.get("ok"):
            return f"Run {res.get('id')} failed: {res.get('error') or res.get('message')}"
        lines = [f"Made {len(items) or len(res.get('clips') or [])} file(s) from '{res.get('title')}' in {res.get('seconds')}s (run {res.get('id')})."]
        lines += [f"- {it.get('title') or it.get('file')} · {it.get('seconds')}s · score {it.get('score')} · {it.get('path')}" for it in items]
        return "\n".join(lines)
    if name == "show":
        return f"Run {res.get('id')} · {res.get('status')} · {res.get('clips')} clip(s) · {res.get('message') or ''}".strip()
    if name == "doctor":
        bad = [c["name"] for c in res.get("checks", []) if not c["ok"] and c["required"]]
        return "Ready." if res.get("ok") else "Not ready: " + ", ".join(bad)
    return ""


def serve() -> int:
    t = Transport()
    calls: list[threading.Thread] = []
    while True:
        msg = t.read()
        if msg is None:  # client closed stdin: finish what it asked for, then exit
            for th in calls:
                th.join()
            return 0
        if not isinstance(msg, dict):
            continue
        mid, method = msg.get("id"), msg.get("method")
        params = msg.get("params") or {}
        if method == "initialize":
            asked = str(params.get("protocolVersion") or "")
            t.write({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "hermes-studio", "title": "Hermes Studio", "version": __version__},
                "instructions": INSTRUCTIONS,
            }})
        elif method in ("notifications/initialized", "initialized") or (method or "").startswith("notifications/"):
            continue
        elif method == "ping":
            t.write({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            t.write({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            th = threading.Thread(target=_handle_call, args=(t, mid, params), daemon=True)
            th.start()
            calls[:] = [c for c in calls if c.is_alive()] + [th]
        elif method in ("resources/list", "prompts/list"):
            t.write({"jsonrpc": "2.0", "id": mid, "result": {method.split("/")[0]: []}})
        elif mid is not None:
            t.write({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}})


def _handle_call(t: Transport, mid, params: dict) -> None:
    name = str(params.get("name") or "")
    args = params.get("arguments") or {}
    if name == "captions":  # legacy tool name
        args = {**args, "mode": "captions"}
    token = (params.get("_meta") or {}).get("progressToken")

    def progress(stage: str, pct: float, message: str) -> None:
        if token is not None:
            t.write({"jsonrpc": "2.0", "method": "notifications/progress",
                     "params": {"progressToken": token, "progress": round(pct * 100, 1), "total": 100, "message": f"{stage}: {message}"}})

    real = _ALIASES.get(name, name)
    if real not in _BY_NAME:
        t.write({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}})
        return
    try:
        res = call_tool(name, args, progress=progress)
        is_error = res.get("ok") is False
    except HermesStudioError as e:
        res, is_error = e.as_dict(), True
    except Exception as e:  # never kill the server on one bad call
        res, is_error = {"ok": False, "error": f"{type(e).__name__}: {str(e)[-800:]}", "code": "failed"}, True
    text = json.dumps(res, ensure_ascii=False, default=str)
    head = _summary(real, res) if not is_error else f"Error: {res.get('error')}" + (f"\nHint: {res['hint']}" if res.get("hint") else "")
    content = ([{"type": "text", "text": head}] if head else []) + [{"type": "text", "text": text}]
    result = {"content": content, "isError": is_error}
    if not is_error:
        result["structuredContent"] = json.loads(text)
    t.write({"jsonrpc": "2.0", "id": mid, "result": result})


# --------------------------------------------------------------------------- client wiring


def _temporary_mount(exe: str) -> bool:
    """A Linux AppImage runs from a fresh /tmp/.mount_* folder each launch, so its path can't go in a config."""
    appdir = os.environ.get("APPDIR", "")
    return "/.mount_" in exe or bool(appdir and exe.startswith(appdir))


def client_config() -> dict:
    """The stdio command that starts this server with the Python that is running now."""
    bindir = Path(sys.executable).parent  # the venv's bin/Scripts (not resolved: venv pythons are symlinks)
    for name in ("hermes_studio.exe", "hermes-studio") if os.name == "nt" else ("hermes-studio",):
        exe = bindir / name
        if exe.is_file() and not _temporary_mount(str(exe)):
            return {"command": str(exe), "args": ["mcp"]}
    exe_on_path = shutil.which("hermes-studio")
    if exe_on_path and Path(exe_on_path).parent == bindir:
        return {"command": exe_on_path, "args": ["mcp"]}
    if _temporary_mount(sys.executable):
        return {"command": "hermes-studio", "args": ["mcp"],
                "note": "The Linux AppImage moves on every launch. Install the command line once "
                        "(uv tool install git+https://github.com/PabloTheThinker/hermes-studio), then use this."}
    return {"command": sys.executable, "args": ["-m", "hermes_studio", "mcp"]}


def install(client: str, scope: str = "user", dry_run: bool = False) -> dict:
    cfg = client_config()
    if cfg.get("note") and not shutil.which("hermes-studio"):
        raise HermesStudioError("This copy runs from a temporary folder, so an AI app can't start it later.",
                              code="missing_dependency", hint=cfg["note"])
    cfg = {"command": cfg["command"], "args": cfg["args"]}
    cmd, args = cfg["command"], cfg["args"]
    if client in ("claude", "grok"):
        tool = client
        argv = [tool, "mcp", "add", "--scope", scope, "hermes-studio", "--", cmd, *args]
    elif client == "codex":
        argv = ["codex", "mcp", "add", "hermes-studio", "--", cmd, *args]
    elif client in ("cursor", "hermes"):
        return _install_json(client, cfg, scope, dry_run)
    else:
        raise HermesStudioError(f"Unknown client: {client}")
    if not shutil.which(argv[0]):
        raise HermesStudioError(f"The `{argv[0]}` command is not installed or not on PATH.", code="missing_dependency",
                              hint="Install it, or paste the block from `hermes-studio mcp config` into its settings.")
    shown = " ".join(argv)
    if dry_run:
        return {"ok": True, "dry_run": True, "command": shown}
    if client == "claude":  # re-install cleanly if it is already there
        subprocess.run([argv[0], "mcp", "remove", "--scope", scope, "hermes-studio"], capture_output=True, text=True, timeout=60)  # noqa: S603
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)  # noqa: S603
    if proc.returncode != 0:
        raise HermesStudioError(f"`{shown}` failed: {(proc.stderr or proc.stdout).strip()[-400:]}", code="failed")
    nxt = {"claude": "Restart Claude Code, then ask: \"make 3 shorts from ~/Videos/talk.mp4\".",
           "grok": "Restart grok, then ask it to make shorts from a video.",
           "codex": "Restart codex, then ask it to make shorts from a video."}[client]
    return {"ok": True, "client": client, "command": shown, "next": nxt}


def _install_json(client: str, cfg: dict, scope: str, dry_run: bool) -> dict:
    if client == "cursor":
        path = (Path.cwd() / ".cursor" / "mcp.json") if scope == "project" else (Path.home() / ".cursor" / "mcp.json")
        if dry_run:
            return {"ok": True, "dry_run": True, "command": f"add mcpServers.hermes-studio to {path}"}
        data = json.loads(path.read_text()) if path.is_file() else {}
        data.setdefault("mcpServers", {})["hermes-studio"] = cfg
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
        return {"ok": True, "client": client, "where": str(path), "next": "Reload Cursor; hermes-studio appears under MCP tools."}
    # hermes: config.yaml mcp_servers block
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    path = home / "config.yaml"
    block = f"  hermes-studio:\n    command: {json.dumps(cfg['command'])}\n    args: {json.dumps(cfg['args'])}\n"
    if dry_run:
        return {"ok": True, "dry_run": True, "command": f"add mcp_servers.hermes-studio to {path}"}
    text = path.read_text() if path.is_file() else ""
    if "\n  hermes-studio:\n" in text or text.startswith("  hermes-studio:"):
        return {"ok": True, "client": client, "where": str(path), "next": "Already configured."}
    if "\nmcp_servers:\n" in "\n" + text:
        text = text.replace("mcp_servers:\n", "mcp_servers:\n" + block, 1)
    else:
        text = text.rstrip("\n") + ("\n" if text else "") + "mcp_servers:\n" + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return {"ok": True, "client": client, "where": str(path), "next": "Restart Hermes to load the tools."}


if __name__ == "__main__":
    raise SystemExit(serve())
