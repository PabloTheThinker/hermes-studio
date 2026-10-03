"""Markers you can move and rename: ``edit_marker`` is one op, one entry and one undo, from the
engine, /mcp (with ``at_s``) and the Edit page alike."""

from __future__ import annotations

import pytest
from s3_app import App
from test_oplog import HUMAN, S, apply, base, new_log, roundtrip

from hermes_studio import oplog as O


def marker(d: dict, mid: str = "k1") -> dict:
    return next(m for m in d["markers"] if m["id"] == mid)


def test_edit_marker_moves_renames_and_undoes():
    _, d = roundtrip({"op": "edit_marker", "id": "k1", "at": 5 * S})
    assert marker(d) == {"id": "k1", "at": 5 * S, "label": "here"}
    _, d = roundtrip({"op": "edit_marker", "id": "k1", "label": "hook"})
    assert marker(d) == {"id": "k1", "at": 2 * S, "label": "hook"}
    log, d = roundtrip({"op": "edit_marker", "id": "k1", "at": 0, "label": ""})
    assert marker(d) == {"id": "k1", "at": 0, "label": ""}
    line = log._entries[0]
    assert line["inverse"] == [{"op": "edit_marker", "id": "k1", "at": 2 * S, "label": "here"}]
    assert line["changed_ids"] == ["k1"]


@pytest.mark.parametrize(
    "op, want",
    [
        ({"op": "edit_marker", "id": "k1"}, ("missing_arg", "/ops/0")),
        ({"op": "edit_marker", "id": "k9", "at": 0}, ("not_found", "/ops/0/id")),
        ({"op": "edit_marker", "id": "k1", "at": -1}, ("negative_time", "/ops/0/at")),
        ({"op": "edit_marker", "id": "k1", "at": 1.5}, ("not_integer_ticks", "/ops/0/at")),
        ({"op": "edit_marker", "id": "k1", "label": 3}, ("wrong_type", "/ops/0/label")),
        ({"op": "edit_marker", "id": "k1", "zz": 1}, ("unknown_arg", "/ops/0/zz")),
    ],
)
def test_edit_marker_refusals_leave_the_doc_alone(op, want):
    log = new_log()
    before = log.doc
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, op)
    d = e.value.as_dict()
    assert (d["rule"], d["path"]) == want, d
    assert log.doc == before and log._entries == []


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def test_edit_marker_over_mcp_takes_seconds(app):
    ok, r = app.mcp_apply({"op": "edit_marker", "id": "k1", "at_s": 4.5, "label": "hook"})
    assert ok, r
    assert marker(app.proj.log.doc) == {"id": "k1", "at": 9 * S // 2, "label": "hook"}
    ok, u = app.mcp("history_undo", {"project_id": "p1", "client_op_id": "u", "op_id": r["op_id"]})
    assert ok and marker(app.proj.log.doc)["at"] == 2 * S
