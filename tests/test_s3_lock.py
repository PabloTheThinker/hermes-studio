"""D5/D6/D14: the project lock is exclusive across processes, and .lock stays readable while held.

This file runs in the windows desktop job too (.github/workflows/desktop.yml, "Project lock
test"), where the lock is a Windows byte-range lock (msvcrt.locking) that is mandatory: a
locked byte can't be read by another process. The code relies on reading .lock while another
process holds it (the D6 refusal message and the stdio proxy's attach), so the lock byte sits
past the JSON body (project.LOCK_BYTE). Nothing here is skipped on any OS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_oplog import base

from hermes_studio import project as P

ROOT = Path(__file__).resolve().parent.parent

HOLDER = """
import sys
from hermes_studio import project as P
eng = P.Engine(port=4242)
p = eng.open("p1")
print("ready", flush=True)
sys.stdin.readline()
if sys.argv[1] == "clean":
    eng.close()
    print("closed", flush=True)
    sys.stdin.readline()
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    for var in ("HOME", "USERPROFILE"):  # Path.home() reads USERPROFILE on Windows
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    assert Path.home() == tmp_path
    P.create_project(base())
    return tmp_path


def holder(home: Path, mode: str) -> subprocess.Popen:
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "PYTHONPATH": str(ROOT)}
    p = subprocess.Popen([sys.executable, "-c", HOLDER, mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, text=True)
    line = p.stdout.readline()
    assert line.strip() == "ready", (line, p.stderr.read() if p.poll() is not None else "")
    return p


def open_eventually(timeout: float = 10) -> P.Engine:
    """The OS releases a dead process's lock promptly, but not always instantly on Windows."""
    end = time.monotonic() + timeout
    while True:
        eng = P.Engine(port=6000)
        try:
            eng.open("p1")
            return eng
        except Exception:
            if time.monotonic() > end:
                raise
            time.sleep(0.2)


def test_lock_byte_is_past_any_lock_file_body():
    assert P.LOCK_BYTE >= 1 << 20


def test_lock_is_exclusive_across_processes_and_lock_file_stays_readable(home):
    d = P.project_dir("p1")
    h = holder(home, "clean")
    try:
        # exclusive: a second engine in another process is refused (D6) ...
        with pytest.raises(Exception) as e:
            P.Engine(port=5555).open("p1")
        assert getattr(e.value, "code", None) == "failed" and e.value.hint == P.LOCKED_HINT
        # ... and the refusal names the holder, which means .lock was read while it was locked
        assert f"pid {h.pid}" in e.value.message and "port 4242" in e.value.message
        # a raw exclusive or shared lock attempt from this process fails too
        fd = os.open(str(d / ".lock"), os.O_RDWR)
        try:
            assert not P._try_lock(fd, exclusive=True)
        finally:
            os.close(fd)
        # the stdio proxy's attach path: engine_holding reads .lock under the holder's lock
        info = P.engine_holding(d)
        assert info is not None and info["pid"] == h.pid and info["port"] == 4242
        assert len(info["attach_token_sha256"]) == 64
        raw = (d / ".lock").read_bytes()  # a plain read of the whole file works
        assert json.loads(raw)["pid"] == h.pid
        attach = (d / ".attach").read_text()
        assert P._sha(attach) == info["attach_token_sha256"]
        # closed-app reads still work while the engine holds the project (D28)
        c = P.ClosedProject("p1")
        st = c.status()
        assert st["version"] == 0 and st["engine"]["pid"] == h.pid
        # the holder releases cleanly: .attach goes, and the next engine opens it
        h.stdin.write("\n")
        h.stdin.flush()
        assert h.stdout.readline().strip() == "closed"
        assert not (d / ".attach").exists() and P.engine_holding(d) is None
        eng = open_eventually()
        try:
            assert json.loads((d / ".lock").read_bytes())["port"] == 6000
        finally:
            eng.close()
    finally:
        h.kill()
        h.wait()


def test_a_killed_engine_leaves_a_stale_lock_file_that_does_not_block(home):
    d = P.project_dir("p1")
    h = holder(home, "kill")
    with pytest.raises(Exception):
        P.Engine(port=5555).open("p1")
    h.kill()  # no clean exit: .lock and .attach stay on disk
    h.wait()
    assert (d / ".lock").exists()
    eng = open_eventually()
    try:
        assert eng.projects["p1"].log.version == 0
        assert json.loads((d / ".lock").read_bytes())["pid"] == os.getpid()
    finally:
        eng.close()


def test_two_engines_in_one_process_also_exclude(home):
    a = P.Engine(port=1)
    a.open("p1")
    try:
        with pytest.raises(Exception) as e:
            P.Engine(port=2).open("p1")
        assert e.value.code == "failed" and "port 1" in e.value.message
    finally:
        a.close()
    b = P.Engine(port=2)
    b.open("p1")
    b.close()
