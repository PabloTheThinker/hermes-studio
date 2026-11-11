"""A JSON POST against a desk on a loopback port, shared by the editor and grade
suites."""

import http.client
import json


def post(port, path, body):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", path, body=json.dumps(body).encode(),
              headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def wait_editor_render(port, pid, timeout=180.0):
    """Poll the desk Edit-page export job until it settles."""
    import time

    last = {"state": "unknown"}
    end = time.time() + timeout
    while time.time() < end:
        st, res = post(port, f"/api/editor/{pid}", {"op": "render_status"})
        if st != 200:
            raise RuntimeError(f"render_status HTTP {st}: {res}")
        last = res.get("render") or last
        if last.get("state") in ("ready", "failed", "cancelled"):
            return last
        time.sleep(0.1)
    raise TimeoutError(f"render did not finish: {last}")
