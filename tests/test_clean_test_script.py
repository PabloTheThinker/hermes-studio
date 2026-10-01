"""scripts/clean-test-linux.sh tracks each job by the id its own submit returned.

It used to read the first "status" in GET /api/jobs (`head -1`), so a stale or
reordered list could hand it another job's "completed" (desktop run 36857864110).
These tests run the script's real helper block under /bin/sh against a fake engine.
"""

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "clean-test-linux.sh"
pytestmark = pytest.mark.skipif(not (shutil.which("sh") and shutil.which("curl")), reason="needs sh and curl")


def _helpers() -> str:
    text = SCRIPT.read_text()
    start = text.index("# >>> job helpers")
    end = text.index("# <<< job helpers <<<")
    return text[start:end]


class Engine:
    """POST /api/jobs returns `new_id`; GET /api/jobs/<id> walks `states[id]`; GET /api/jobs lists a decoy first."""

    def __init__(self, new_id, states, submit_body=None):
        self.new_id, self.states, self.submit_body = new_id, states, submit_body
        self.gets: dict[str, int] = {}
        engine = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                body = (obj if isinstance(obj, str) else json.dumps(obj)).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if engine.submit_body is not None:
                    return self._send(202, engine.submit_body)
                job = {"id": engine.new_id, "src": "/s.mp4", "title": "sample", "status": "queued", "live_status": None}
                return self._send(202, {"ok": True, "job": job})

            def do_GET(self):
                if self.path == "/api/jobs":  # the old head -1 trap: an older finished job first
                    decoy = {"id": "olddecoy0001", "status": "completed"}
                    return self._send(200, {"ok": True, "jobs": [decoy, {"id": engine.new_id, "status": "running"}]})
                job_id = self.path.rsplit("/", 1)[-1]
                seq = engine.states.get(job_id)
                if seq is None:
                    return self._send(404, {"ok": False, "error": "not found"})
                n = engine.gets.get(job_id, 0)
                engine.gets[job_id] = n + 1
                status, error = seq[min(n, len(seq) - 1)]
                job = {"id": job_id, "status": status, "live_status": None, "error": error, "clips": []}
                return self._send(200, {"ok": True, "job": job})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _run(engine, tmp_path, max_polls=20):
    script = (
        "set -e\n" + _helpers() + 'submit_job "{\\"src\\":\\"/s.mp4\\",\\"mode\\":\\"clip\\"}" clip\n'
        f'wait_job "$JOB_ID" {max_polls} clip\n'
        'echo "WAITED FOR $JOB_ID"\n'
    )
    env = {**os.environ, "PORT": str(engine.port), "HOME": str(tmp_path), "POLL_SLEEP": "0"}
    try:
        return subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    finally:
        engine.close()


def test_waits_for_its_own_job_not_the_first_in_the_list(tmp_path):
    states = {"newclip00001": [("queued", None), ("running", None), ("running", None), ("completed", None)]}
    eng = Engine("newclip00001", states)
    r = _run(eng, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "clip job id: newclip00001" in r.stdout
    assert "clip job newclip00001: completed" in r.stdout
    assert "WAITED FOR newclip00001" in r.stdout
    assert eng.gets == {"newclip00001": 4}, "polled only its own job, until it completed"


def test_failed_job_fails_clearly_with_its_error(tmp_path):
    eng = Engine("newclip00002", {"newclip00002": [("running", None), ("failed", "ffmpeg exploded")]})
    r = _run(eng, tmp_path)
    assert r.returncode == 1
    assert 'FAIL: clip job newclip00002 failed: "error": "ffmpeg exploded"' in r.stdout
    assert "WAITED FOR" not in r.stdout


def test_missing_job_fails_clearly(tmp_path):
    eng = Engine("ghostjob0003", {})  # submit says ok, but GET /api/jobs/<id> is 404
    r = _run(eng, tmp_path)
    assert r.returncode == 1
    assert "FAIL: clip job ghostjob0003 is missing (GET /api/jobs/ghostjob0003 returned 404)" in r.stdout
    assert "WAITED FOR" not in r.stdout


def test_timeout_fails_clearly_with_the_last_status(tmp_path):
    eng = Engine("slowjob00004", {"slowjob00004": [("running", None)]})
    r = _run(eng, tmp_path, max_polls=3)
    assert r.returncode == 1
    assert "FAIL: clip job slowjob00004 did not finish after 3 polls (last status: running, last HTTP: 200)" in r.stdout
    assert eng.gets == {"slowjob00004": 3}


def test_submit_without_a_job_id_fails_clearly(tmp_path):
    eng = Engine("unused", {}, submit_body={"ok": False, "error": "src required"})
    r = _run(eng, tmp_path)
    assert r.returncode == 1
    assert "FAIL: clip job: submit returned no job id" in r.stdout


def test_old_list_order_polling_is_gone():
    text = SCRIPT.read_text()
    assert '/api/jobs" | grep' not in text
    assert text.count('wait_job "$JOB_ID"') == 2
