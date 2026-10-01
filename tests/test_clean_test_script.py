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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "clean-test-linux.sh"
pytestmark = pytest.mark.skipif(not (shutil.which("sh") and shutil.which("curl")), reason="needs sh and curl")


def _block(name: str) -> str:
    text = SCRIPT.read_text()
    start = text.index(f"# >>> {name}")
    end = text.index(f"# <<< {name} <<<")
    return text[start:end]


def _helpers() -> str:
    return _block("job helpers")


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
                if status == "hang":  # a wedged engine: answer far later than curl's --max-time
                    time.sleep(error)
                    status, error = "running", None
                job = {"id": job_id, "status": status, "live_status": None, "error": error, "clips": []}
                return self._send(200, {"ok": True, "job": job})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _run(engine, tmp_path, max_polls=20, **env_extra):
    script = (
        "set -e\n" + _helpers() + 'submit_job "{\\"src\\":\\"/s.mp4\\",\\"mode\\":\\"clip\\"}" clip\n'
        f'wait_job "$JOB_ID" {max_polls} clip\n'
        'echo "WAITED FOR $JOB_ID"\n'
    )
    env = {**os.environ, "PORT": str(engine.port), "HOME": str(tmp_path), "POLL_SLEEP": "0", **env_extra}
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


def test_cancelled_job_fails_fast(tmp_path):
    eng = Engine("cancel000005", {"cancel000005": [("running", None), ("cancelled", "cancelled by user")]})
    r = _run(eng, tmp_path, max_polls=50)
    assert r.returncode == 1
    assert 'FAIL: clip job cancel000005 cancelled: "error": "cancelled by user"' in r.stdout
    assert eng.gets == {"cancel000005": 2}, "stops at the first cancelled poll, not at the poll limit"
    assert "WAITED FOR" not in r.stdout


def test_a_wedged_engine_costs_one_bounded_poll(tmp_path):
    eng = Engine("wedged000006", {"wedged000006": [("hang", 5)]})
    t0 = time.monotonic()
    r = _run(eng, tmp_path, max_polls=2, CURL_MAX_TIME="1")
    assert time.monotonic() - t0 < 5, "curl --max-time bounds each poll"
    assert r.returncode == 1
    assert "FAIL: clip job wedged000006 did not finish after 2 polls (last status: none, last HTTP: 000)" in r.stdout


def test_every_curl_in_the_clean_tests_is_bounded():
    for name in ("clean-test-linux.sh", "clean-test-installer.sh"):
        text = (SCRIPT.parent / name).read_text()
        calls = [line for line in text.splitlines() if "curl " in line and not line.lstrip().startswith("#")]
        calls = [c for c in calls if "apt-get" not in c and "ca-certificates" not in c]
        assert calls and all("--max-time" in c for c in calls), (name, calls)


def test_apt_get_is_timestamped():
    for name in ("clean-test-linux.sh", "clean-test-installer.sh"):
        lines = (SCRIPT.parent / name).read_text().splitlines()
        start = next(i for i, x in enumerate(lines) if x.startswith('echo "apt-get start: $(date -u'))
        done = next(i for i, x in enumerate(lines) if x.startswith('echo "apt-get done: $(date -u'))
        apt = [i for i, x in enumerate(lines) if x.startswith("apt-get ")]
        assert apt and start < min(apt) and max(apt) < done, name


def test_poll_limits_and_pace():
    text = SCRIPT.read_text()
    assert 'POLL_SLEEP="${POLL_SLEEP:-2}"' in text
    assert 'CURL_MAX_TIME="${CURL_MAX_TIME:-10}"' in text
    assert 'wait_job "$JOB_ID" 240 captions' in text
    assert 'wait_job "$JOB_ID" 300 clip' in text


def test_poll_limit_is_exact(tmp_path):
    eng = Engine("limit0000007", {"limit0000007": [("running", None)] * 7 + [("completed", None)]})
    r = _run(eng, tmp_path, max_polls=8)
    assert r.returncode == 0, r.stdout + r.stderr
    assert eng.gets == {"limit0000007": 8}, "the 8th poll of 8 still counts"


def _outputs(tmp_path, files):
    lib = tmp_path / ".hermes" / "clips" / "library"
    for f in files:
        (lib / f).parent.mkdir(parents=True, exist_ok=True)
        (lib / f).write_bytes(b"")
    script = "set -e\n" + _block("output check")
    return subprocess.run(
        ["sh", "-c", script], env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=30
    )


@pytest.mark.parametrize(
    "files, ok",
    [
        ([], False),
        (["src/sample.mp4", "captions-sample.mp4"], False),  # other mp4s don't count
        (["clip-notes.txt"], False),
        (["run1/clip-01.mp4"], True),
        (["run1/clip-01.mp4", "run1/clip-02.mp4", "src/sample.mp4"], True),
    ],
)
def test_output_check_needs_a_real_clip_mp4(tmp_path, files, ok):
    r = _outputs(tmp_path, files)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
        assert f"clips written: {sum(f.split('/')[-1].startswith('clip-') for f in files)}" in r.stdout
    else:
        assert r.returncode == 1
        assert "FAIL: no clips written" in r.stdout
