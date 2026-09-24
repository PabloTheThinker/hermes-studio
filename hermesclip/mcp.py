"""Local stdio MCP for HermesClip. Same jobs as native hermesclip_* tools. Never posts. Not Opus cloud."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = [
    {
        "name": "run",
        "description": "Clip a local file or URL into shorts. Local Whisper + FFmpeg. Does not post.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string"},
                "out": {"type": "string"},
                "max_clips": {"type": "integer", "default": 3},
                "prompt": {"type": "string"},
                "aspect": {"type": "string", "enum": ["9:16", "16:9", "1:1"]},
                "layout": {"type": "string", "enum": ["fit", "fill"]},
            },
            "required": ["src"],
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
    from hermesclip.cli import main as cli_main
    import io
    from contextlib import redirect_stdout, redirect_stderr

    buf = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        code = cli_main(argv)
    text = (buf.getvalue() or "") + (err.getvalue() or "")
    if code:
        return json.dumps({"ok": False, "error": text[-2000:], "code": code})
    return text[-8000:] or json.dumps({"ok": True})


def _call(name: str, args: dict) -> str:
    args = args or {}
    if name == "run":
        argv = ["run", str(args.get("src") or ""), "--out", str(args.get("out") or str(Path.home() / ".hermes" / "clips"))]
        if args.get("max_clips"):
            argv += ["--max-clips", str(int(args["max_clips"]))]
        if args.get("prompt"):
            argv += ["--prompt", str(args["prompt"])]
        if args.get("aspect"):
            argv += ["--aspect", str(args["aspect"])]
        if args.get("layout"):
            argv += ["--layout", str(args["layout"])]
        return _cli(argv)
    if name == "captions":
        return _cli(["captions", str(args.get("src") or ""), "--out", str(args.get("out") or str(Path.home() / ".hermes" / "clips"))])
    if name == "probe":
        return _cli(["probe", str(args.get("src") or "")])
    if name == "list":
        return _cli(["list"])
    if name == "edit":
        return _cli(
            [
                "edit",
                str(args.get("src") or ""),
                "--start",
                str(args.get("start") or 0),
                "--end",
                str(args.get("end") or 0),
                "--out",
                str(args.get("out") or ""),
            ]
        )
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
