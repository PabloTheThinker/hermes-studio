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
