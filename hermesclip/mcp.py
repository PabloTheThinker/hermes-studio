"""Local stdio MCP for HermesClip. Same jobs as native hermesclip_* tools. Never posts. Not Opus cloud."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = [
    {
        "name": "run",
        "description": "Hermes Studio tools: clip, captions, reframe, tighten, transcript. Local Whisper + FFmpeg. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string"},
                "out": {"type": "string"},
                "max_clips": {"type": "integer", "default": 3},
                "prompt": {"type": "string"},
                "keywords": {"type": "string"},
                "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1", "4:5", "source"]},
                "layout": {"type": "string", "enum": ["auto", "fit", "fill", "split"], "description": "auto picks from the frame; split = facecam band + screen/game"},
                "face": {"type": "string", "enum": ["top", "bottom"], "description": "split: face band on top or bottom"},
                "face_size": {"type": "number", "description": "split: face band % of height (20-60)"},
                "face_box": {"type": "string", "description": "split: manual camera box x,y,w,h in % of source"},
                "filter": {"type": "string", "enum": ["none", "punch", "warm", "cool", "cinematic", "vintage", "bw", "bright"]},
                "caption_pos": {"type": "string", "enum": ["auto", "top", "middle", "bottom"]},
                "audio": {"type": "string", "enum": ["off", "clean"]},
                "progress": {"type": "boolean"},
                "fixes": {"type": "string", "description": "word fixes: cloud=Claude, marz=Mars"},
                "mode": {"type": "string", "enum": ["clip", "captions", "reframe", "tighten", "transcript"]},
                "whisper": {"type": "string", "description": "fast | balanced | accurate"},
            },
            "required": ["src"],
        },
    },
    {
        "name": "restyle",
        "description": "Edit one library clip: new layout (auto/fit/fill/split), face top/bottom, band size, colour filter, caption spot/style, audio clean-up, progress bar, word fixes, or new start/end on the source. Old file goes to .trash. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job": {"type": "string"},
                "file": {"type": "string"},
                "layout": {"type": "string", "enum": ["auto", "fit", "fill", "split"], "description": "auto picks from the frame; split = facecam band + screen/game"},
                "face": {"type": "string", "enum": ["top", "bottom"], "description": "split: face band on top or bottom"},
                "face_size": {"type": "number", "description": "split: face band % of height (20-60)"},
                "face_box": {"type": "string", "description": "split: manual camera box x,y,w,h in % of source"},
                "filter": {"type": "string", "enum": ["none", "punch", "warm", "cool", "cinematic", "vintage", "bw", "bright"]},
                "caption_pos": {"type": "string", "enum": ["auto", "top", "middle", "bottom"]},
                "audio": {"type": "string", "enum": ["off", "clean"]},
                "progress": {"type": "boolean"},
                "fixes": {"type": "string", "description": "word fixes: cloud=Claude, marz=Mars"},
                "style": {"type": "string", "enum": ["pop", "impact", "clean", "glow", "neon", "boxed"]},
                "captions": {"type": "boolean"},
                "start": {"type": "number"},
                "end": {"type": "number"},
                "title": {"type": "string"},
            },
            "required": ["job", "file"],
        },
    },
    {
        "name": "captions",
        "description": "Burn captions on the full video. No clip planner. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {"src": {"type": "string"}, "out": {"type": "string"}},
            "required": ["src"],
        },
    },
    {
        "name": "probe",
        "description": "Title and live flag for a URL or file.",
        "inputSchema": {
            "type": "object",
            "properties": {"src": {"type": "string"}},
            "required": ["src"],
        },
    },
    {
        "name": "list",
        "description": "List the local clip library.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "edit",
        "description": "Trim an existing clip file (start/end seconds). Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string"},
                "start": {"type": "number"},
                "end": {"type": "number"},
                "out": {"type": "string"},
            },
            "required": ["src", "start", "end"],
        },
    },
    {
        "name": "recommend",
        "description": "Analyze a source and return best local job settings. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {"src": {"type": "string"}},
            "required": ["src"],
        },
    },
    {
        "name": "copy",
        "description": "Local titles, description, hashtags for a job. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {"src": {"type": "string"}, "clip_title": {"type": "string"}},
            "required": ["src"],
        },
    },
    {
        "name": "name",
        "description": "AI-name every clip in a library run from its words (Opus Clip-style). Or rename one clip with file+title. Local Ollama first. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {"job": {"type": "string"}, "file": {"type": "string"}, "title": {"type": "string"}},
            "required": ["job"],
        },
    },
]


def _read() -> dict | None:
    header = b""
    while not header.endswith(b"\r\n\r\n"):
        ch = sys.stdin.buffer.read(1)
        if not ch:
            return None
        header += ch
    length = 0
    for line in header.decode("utf-8", "replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def _write(msg: dict) -> None:
    raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    sys.stdout.buffer.flush()


def _cli(argv: list[str]) -> str:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    from hermesclip.cli import main as cli_main

    buf = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        code = cli_main(argv)
    text = (buf.getvalue() or "") + (err.getvalue() or "")
    if code:
        return json.dumps({"ok": False, "error": text[-2000:], "code": code})
    return text[-8000:] or json.dumps({"ok": True})


def _look_argv(args: dict) -> list[str]:
    argv: list[str] = []
    for k, flag in (("layout", "--layout"), ("face", "--face"), ("face_size", "--face-size"), ("face_box", "--face-box"),
                    ("filter", "--filter"), ("caption_pos", "--caption-pos"), ("audio", "--audio")):
        if args.get(k) not in (None, ""):
            argv += [flag, str(args[k])]
    if args.get("progress"):
        argv.append("--progress")
    for part in str(args.get("fixes") or "").split(","):
        if "=" in part:
            argv += ["--fix", part.strip()]
    return argv


def _call(name: str, args: dict) -> str:
    args = args or {}
    if name == "restyle":
        argv = ["restyle", str(args.get("job") or ""), str(args.get("file") or "")] + _look_argv(args)
        if args.get("style"):
            argv += ["--style", str(args["style"])]
        if args.get("captions") is False:
            argv.append("--no-captions")
        for k in ("start", "end"):
            if args.get(k) not in (None, ""):
                argv += ["--" + k, str(float(args[k]))]
        if args.get("title"):
            argv += ["--title", str(args["title"])]
        return _cli(argv)
    if name == "run":
        argv = ["run", str(args.get("src") or ""), "--out", str(args.get("out") or str(Path.home() / ".hermes" / "clips"))]
        if args.get("max_clips"):
            argv += ["--max-clips", str(int(args["max_clips"]))]
        if args.get("prompt"):
            argv += ["--prompt", str(args["prompt"])]
        if args.get("keywords"):
            argv += ["--keywords", str(args["keywords"])]
        if args.get("aspect"):
            argv += ["--aspect", str(args["aspect"])]
        argv += _look_argv(args)
        if args.get("mode"):
            argv += ["--mode", str(args["mode"])]
        if args.get("whisper"):
            argv += ["--whisper", str(args["whisper"])]
        return _cli(argv)
    if name == "captions":
        return _cli(["captions", str(args.get("src") or ""), "--out", str(args.get("out") or str(Path.home() / ".hermes" / "clips"))])
    if name == "probe":
        return _cli(["probe", str(args.get("src") or "")])
    if name == "name":
        argv = ["name", str(args.get("job") or "")]
        if args.get("file"):
            argv += ["--file", str(args["file"]), "--title", str(args.get("title") or "")]
        return _cli(argv)
    if name == "list":
        return _cli(["list"])
    if name == "edit":
        op = str(args.get("op") or "trim")
        argv = ["edit", str(args.get("src") or ""), "--op", op]
        if op == "split":
            argv += ["--at", str(args.get("at") or 0)]
        elif op == "trim":
            argv += ["--start", str(args.get("start") or 0), "--end", str(args.get("end") or 0)]
            if args.get("out"):
                argv += ["--out", str(args["out"])]
        elif op == "duplicate" and args.get("out"):
            argv += ["--out", str(args["out"])]
        return _cli(argv)
    if name == "recommend":
        env = __import__("os").environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        import subprocess

        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,sys; from hermesclip.recommend import recommend_for; i,r=recommend_for(sys.argv[1]); print(json.dumps({'ok':True,'title':i.title,'recommendation':r.as_job()}))",
                str(args.get("src") or ""),
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=40,
        )
        return (proc.stdout or proc.stderr or "")[-8000:]
    if name == "copy":
        argv = ["copy", str(args.get("src") or "")]
        if args.get("clip_title"):
            argv += ["--clip-title", str(args["clip_title"])]
        return _cli(argv)
    return json.dumps({"ok": False, "error": f"unknown tool {name}"})


def serve() -> int:
    while True:
        msg = _read()
        if msg is None:
            return 0
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "hermesclip", "version": "0.3.1"},
                    },
                }
            )
            continue
        if method == "notifications/initialized" or method == "initialized":
            continue
        if method == "ping":
            _write({"jsonrpc": "2.0", "id": mid, "result": {}})
            continue
        if method == "tools/list":
            _write({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
            continue
        if method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name") or ""
            arguments = params.get("arguments") or {}
            try:
                text = _call(name, arguments)
            except Exception as exc:
                text = json.dumps({"ok": False, "error": str(exc)[-1500:]})
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {"content": [{"type": "text", "text": text}]},
                }
            )
            continue
        if mid is not None:
            _write({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": str(method)}})


if __name__ == "__main__":
    raise SystemExit(serve())
