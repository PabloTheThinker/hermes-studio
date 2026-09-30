"""The CLI and MCP contracts agents rely on: one JSON object, stable exit codes, standard MCP stdio."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hermesclip import api, cli, mcp

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> tuple[int, str, str]:
    p = subprocess.run([sys.executable, "-m", "hermesclip", *args], capture_output=True, text=True, cwd=ROOT, timeout=120)
    return p.returncode, p.stdout, p.stderr


def test_version_matches_package():
    code, out, _ = run_cli("--version")
    assert code == 0
    assert out.strip() == f"hermesclip {api.__version__}"


def test_no_args_prints_help_and_succeeds():
    code, out, _ = run_cli()
    assert code == 0
    assert "hermesclip mcp install claude" in out


@pytest.mark.parametrize(
    ("argv", "exit_code", "code"),
    [
        (["run", "~/definitely-not-here.mp4", "--json"], 4, "not_found"),
        (["run", "ftp://example.com/x.mp4", "--json"], 2, "bad_input"),
        (["run", "x.mp4", "--stlye", "pop", "--json"], 2, "bad_input"),
        (["run", "x.mp4", "--style", "nope", "--json"], 2, "bad_input"),
        (["show", "../etc", "--json"], 2, "bad_input"),
        (["show", "zzzzzzzzzzzz", "--json"], 4, "not_found"),
        (["rnu", "--json"], 2, "bad_input"),
    ],
)
def test_errors_are_one_json_object_with_a_stable_exit_code(argv, exit_code, code):
    rc, out, _ = run_cli(*argv)
    assert rc == exit_code
    lines = [x for x in out.splitlines() if x.strip()]
    assert len(lines) == 1, out
    obj = json.loads(lines[0])
    assert obj["ok"] is False and obj["code"] == code and obj["error"]


def test_typo_suggests_the_right_command():
    rc, _, err = run_cli("rnu")
    assert rc == 2
    assert "Did you mean 'run'?" in err


def test_bad_source_never_creates_a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    before = api.library()["total"]
    with pytest.raises(api.HermesClipError):
        api.run(str(Path.home() / "definitely-not-here.mp4"))
    assert api.library()["total"] == before


def test_non_media_file_is_refused_with_the_list(tmp_path):
    f = Path.home() / ".hermesclip-test-notes.txt"
    f.write_text("x")
    try:
        with pytest.raises(api.HermesClipError) as e:
            api.check_source(str(f))
        assert ".mp4" in e.value.hint
    finally:
        f.unlink()


def test_vocab_matches_the_engine():
    from hermesclip.captions import STYLES
    from hermesclip.look import FILTERS

    assert set(api.STYLES) == set(STYLES)
    assert set(api.FILTERS) == set(FILTERS)
    run_schema = next(t for t in mcp.TOOLS if t["name"] == "run")["inputSchema"]["properties"]
    assert set(run_schema["style"]["enum"]) == set(STYLES)
    assert set(run_schema["filter"]["enum"]) == set(FILTERS)


def test_doctor_json_shape():
    rc, out, _ = run_cli("doctor", "--json")
    obj = json.loads(out)
    assert rc in (0, 3) and (rc == 0) == obj["ok"]
    ids = {c["id"] for c in obj["checks"]}
    assert {"python", "ffmpeg", "whisper", "library"} <= ids
    assert all(c["fix"] for c in obj["checks"] if not c["ok"])


def test_parser_covers_every_command():
    p = cli.build_parser()
    sub = next(a for a in p._actions if a.dest == "cmd")
    assert set(sub.choices) <= set(cli.COMMANDS)


# --------------------------------------------------------------------------- MCP


def _mcp(frames: list[bytes]) -> list[dict]:
    p = subprocess.run([sys.executable, "-m", "hermesclip", "mcp"], input=b"".join(frames), capture_output=True, cwd=ROOT, timeout=60)
    raw = p.stdout
    msgs = []
    if raw.startswith(b"Content-Length"):
        while raw:
            head, _, rest = raw.partition(b"\r\n\r\n")
            n = int(head.split(b":")[1])
            msgs.append(json.loads(rest[:n]))
            raw = rest[n:]
    else:
        msgs = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return msgs


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}


def test_mcp_newline_stdio_handshake_and_tools():
    frames = [json.dumps(m).encode() + b"\n" for m in (
        INIT,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run", "arguments": {"src": "/nope/x.mp4"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "bogus/method"},
    )]
    msgs = {m.get("id"): m for m in _mcp(frames)}
    init = msgs[1]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["serverInfo"]["version"] == api.__version__
    assert "instructions" in init
    tools = {t["name"]: t for t in msgs[2]["result"]["tools"]}  # every call answered even though stdin closed
    assert {"run", "show", "list", "restyle", "doctor"} <= set(tools)
    assert tools["show"]["annotations"]["readOnlyHint"] is True
    err = msgs[3]["result"]
    assert err["isError"] is True
    assert json.loads(err["content"][-1]["text"])["ok"] is False
    assert msgs[4]["error"]["code"] == -32601


def test_mcp_still_speaks_content_length_framing():
    body = json.dumps(INIT).encode()
    msgs = _mcp([f"Content-Length: {len(body)}\r\n\r\n".encode() + body])
    assert msgs[0]["result"]["serverInfo"]["name"] == "hermesclip"


def test_mcp_stdout_is_protected_from_stray_prints():
    frames = [json.dumps(INIT).encode() + b"\n",
              json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "tools", "arguments": {}}}).encode() + b"\n"]
    p = subprocess.run([sys.executable, "-c", "import sys; print('noise'); from hermesclip.mcp import serve; print('more noise'); sys.exit(serve())"],
                       input=b"".join(frames), capture_output=True, cwd=ROOT, timeout=60)
    lines = [x for x in p.stdout.splitlines() if x.strip()]
    assert len(lines) == 2  # init + tools result, nothing else
    for line in lines:
        json.loads(line)  # protocol only; the prints went to stderr
    assert b"noise" in p.stderr


def test_install_dry_run_and_config():
    cfg = mcp.client_config()
    assert cfg["args"][-1] == "mcp"
    res = mcp.install("cursor", dry_run=True)
    assert res["ok"] and res["dry_run"]
