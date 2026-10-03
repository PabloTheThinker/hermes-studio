"""Opening a project replays its log; a long one must not block the engine: other projects open
meanwhile, and two opens of the same project get the same Project."""

from __future__ import annotations

import threading
import time

from test_oplog import base

from hermes_studio import project as P


def test_a_slow_open_blocks_only_itself(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for pid in ("slow", "quick"):
        P.create_project({**base(), "id": pid})
    real = P.Project.load

    def load(self):
        if self.id == "slow":
            time.sleep(1.0)
        return real(self)

    monkeypatch.setattr(P.Project, "load", load)
    eng = P.Engine(port=0)
    got: list = []
    try:
        ts = [threading.Thread(target=lambda: got.append(eng.open("slow"))) for _ in range(2)]
        for t in ts:
            t.start()
        time.sleep(0.15)
        t0 = time.monotonic()
        q = eng.open("quick")
        assert time.monotonic() - t0 < 0.5 and q.id == "quick"  # not behind the slow replay
        for t in ts:
            t.join()
        assert len(got) == 2 and got[0] is got[1] is eng.projects["slow"]
        assert set(eng.projects) == {"slow", "quick"} and eng._opening == {}
    finally:
        eng.close()
