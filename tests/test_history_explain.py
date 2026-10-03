"""history_explain: one history entry in plain words (outline lines removed and added)."""

from __future__ import annotations

import pytest
from s3_app import App
from test_oplog import S, base


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def test_explain_a_trim_a_marker_and_an_undo(app):
    ok, r = app.mcp_apply(
        {"op": "trim_clip", "id": "c2", "src_out": 12 * S, "ripple": True}, {"op": "add_marker", "at": S, "label": "hook"}
    )
    assert ok, r
    ok, x = app.mcp("history_explain", {"project_id": "p1", "op_id": r["op_id"]})
    assert ok, x
    assert x["before_version"] == 0 and x["after_version"] == 1 and x["length_s"] == [14.0, 12.0]
    assert "c2 4.00-8.00 m1[10.00-14.00]" in x["removed"] and "c2 4.00-6.00 m1[10.00-12.00]" in x["added"]
    assert "c3 8.00-12.00 m1[20.00-24.00]" in x["added"] and "gap 8.00-10.00" in x["removed"]
    assert x["removed"][-1] == 'markers: k1 2.00 "here"' and x["added"][-1].startswith("markers: ")
    assert x["added"][-1].endswith('1.00 "hook", k1 2.00 "here"')
    assert "c1 0.00-4.00 m1[0.00-4.00]" not in x["removed"] + x["added"]  # unchanged lines are left out
    ok, u = app.mcp("history_undo", {"project_id": "p1", "client_op_id": "u", "op_id": r["op_id"]})
    ok, y = app.mcp("history_explain", {"project_id": "p1", "op_id": u["op_id"]})
    assert (
        ok
        and y["undoes"] == [r["op_id"]]
        and sorted(y["added"]) == sorted(x["removed"])
        and sorted(y["removed"]) == sorted(x["added"])
    )


def test_explain_refusals(app):
    ok, e = app.mcp("history_explain", {"project_id": "p1"})
    assert not ok and (e["rule"], e["path"]) == ("missing_arg", "/op_id")
    ok, e = app.mcp("history_explain", {"project_id": "p1", "op_id": 5})
    assert not ok and (e["rule"], e["path"]) == ("bad_arg", "/op_id")
    ok, e = app.mcp("history_explain", {"project_id": "p1", "op_id": "op-nope"})
    assert not ok and e["code"] == "not_found"
    ok, e = app.mcp("history_explain", {"project_id": "p1", "op_id": "x", "zz": 1})
    assert not ok and (e["rule"], e["path"]) == ("unknown_arg", "/zz")
