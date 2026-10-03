"""Replay at scale: load skips re-validating every replayed doc (each must still reproduce its
stored hash, version and inverse; the final doc is validated once), and the hash reads the doc
through a non-copying canonical view that must give the same bytes as normalize."""

from __future__ import annotations

import json
import random

import pytest
from test_oplog import HUMAN, _random_op, apply, base, new_log

from hermes_studio import oplog as O
from hermes_studio import timeline as T


def _old_bytes(doc: dict) -> bytes:
    body = {k: v for k, v in T.normalize(doc).items() if k not in T.NOT_HASHED}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def test_canonical_view_matches_normalize_over_random_edits():
    for seed in range(150):
        rng = random.Random(seed)
        log = new_log()
        for _ in range(rng.randrange(2, 8)):
            try:
                apply(log, HUMAN, *[_random_op(rng, log.doc) for _ in range(rng.randrange(1, 3))])
            except O.OplogError:
                continue
            assert T._canonical_bytes(log.doc) == _old_bytes(log.doc), seed


def _logged(tmp_path, n: int = 6):
    log = new_log()
    for i in range(n):
        apply(log, HUMAN, {"op": "add_marker", "at": i * T.TICK_RATE, "label": f"m{i}"})
    p = tmp_path / "oplog.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in log._entries))
    return log, p


def test_load_still_checks_every_line(tmp_path):
    log, p = _logged(tmp_path)
    again = O.Oplog.load(base(), p)
    assert again.doc["hash"] == log.doc["hash"] and len(again._entries) == 6
    lines = p.read_text().splitlines()
    bad = json.loads(lines[2])
    bad["ops"][0]["label"] = "tampered"  # a middle line changed: its stored hash no longer follows
    p.write_text("\n".join(lines[:2] + [json.dumps(bad)] + lines[3:]) + "\n")
    with pytest.raises(ValueError, match="line 3"):
        O.Oplog.load(base(), p)


def test_load_validates_the_final_doc(tmp_path, monkeypatch):
    log, p = _logged(tmp_path)
    real = T.validate
    monkeypatch.setattr(T, "validate", lambda d: real(d) or [{"rule": "x", "path": "/", "message": "made up"}])
    with pytest.raises(ValueError, match="not valid: made up"):
        O.Oplog.load(base(), p)
