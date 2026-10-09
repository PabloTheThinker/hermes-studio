"""``timeline_check``: timeline_apply's answer without the write, in every mode."""

from __future__ import annotations

import pytest
from s3_app import App
from test_oplog import S, base


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base(), mode="ask")
    yield a
    a.close()


def test_check_says_what_would_change_and_writes_nothing(app):
    h0 = app.head()
    ok, r = app.mcp("timeline_check", {"project_id": "p1", "ops": [{"op": "delete_clip", "id": "c2", "ripple": True}]})
    assert ok, r  # an agent in Ask mode can still plan
    assert r["would_apply"] and r["version"] == 0 and "c2" in r["changed_ids"] and r["length_s"] == 10.0
    assert "  c2 " not in r["outline"] and "  c3 6.00-10.00 m1[20.00-24.00]" in r["outline"].splitlines()
    assert app.head() == h0 and app.proj.log._entries == []
    assert not (app.proj.dir / "pending").exists() or not list((app.proj.dir / "pending").iterdir())


def test_check_takes_seconds_and_refuses_like_apply(app):
    ok, r = app.mcp("timeline_check", {"project_id": "p1", "ops": [{"op": "move_clip", "id": "c3", "at_s": 20}]})
    assert ok and r["used"] and r["length_s"] == 24.0, r
    bad = [{"op": "move_clip", "id": "c3", "at_s": 5}]  # onto c2
    ok, e = app.mcp("timeline_check", {"project_id": "p1", "ops": bad})
    assert not ok
    app.mcp("set_mode", {"project_id": "p1", "mode": "auto"}, app.ui)
    ok2, e2 = app.mcp_apply(*bad)
    assert not ok2 and {k: e[k] for k in ("code", "rule", "path")} == {k: e2[k] for k in ("code", "rule", "path")}, (e, e2)


def test_check_stale_base_and_bad_args(app):
    app.mcp("set_mode", {"project_id": "p1", "mode": "auto"}, app.ui)
    ok, _ = app.mcp_apply({"op": "add_marker", "at": S, "label": "x"})
    assert ok
    ok, e = app.mcp(
        "timeline_check", {"project_id": "p1", "base_version": 0, "ops": [{"op": "add_marker", "at": 0, "label": "y"}]}
    )
    assert not ok and e["code"] == "conflict"
    ok, e = app.mcp("timeline_check", {"project_id": "p1"})
    assert not ok and (e["rule"], e["path"]) == ("missing_arg", "/ops")
    ok, e = app.mcp("timeline_check", {"project_id": "p1", "ops": [], "summary": "s"})
    assert not ok and (e["rule"], e["path"]) == ("unknown_arg", "/summary")
