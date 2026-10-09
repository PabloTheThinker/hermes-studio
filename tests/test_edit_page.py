"""The Edit page's engine side: the ui token handed over in memory, project_list / project_new
(tools and REST), and the static files the page loads."""

from __future__ import annotations

import json
import os
import time

import pytest
from s3_app import App
from test_oplog import base

from hermes_studio import http_engine
from hermes_studio import mcp_timeline as MT
from hermes_studio import project as P


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base())
    yield a
    a.close()


def test_the_desktop_ui_token_is_adopted_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    raw = "ab" * 32
    monkeypatch.setenv("HERMES_STUDIO_UI_TOKEN", raw)
    eng = http_engine.start(0)
    try:
        assert http_engine.UI_TOKEN == raw and eng.ui_token_given
        assert "HERMES_STUDIO_UI_TOKEN" not in os.environ  # taken out, so child processes never see it
        tok = eng.tokens.resolve(raw)
        assert tok.kind == "ui" and tok.session.actor.kind == "human" and tok.session.actor.id == "user"
    finally:
        http_engine.stop(eng)


def test_a_bad_environment_token_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_STUDIO_UI_TOKEN", "not-hex")
    with pytest.raises(ValueError):
        http_engine.start(0)


def test_without_one_the_engine_mints_it():
    t = P.Tokens()
    with pytest.raises(ValueError):
        t.adopt("ui", "AB" * 32)  # uppercase isn't what the app makes
    assert len(t.mint("ui")) == 64


def test_project_list_and_new_over_mcp(app):
    ok, lst = app.mcp("project_list", {})
    assert ok and [p["project_id"] for p in lst["projects"]] == ["p1"]
    row = lst["projects"][0]
    assert row["size"] == [1080, 1920] and row["media"] == 2 and row["mode"] == "auto" and row["engine"]["port"] == app.port
    ok, new = app.mcp("project_new", {"shape": "16:9", "fps": 25}, app.ui)
    assert ok and new["project_id"].startswith("p-") and new["version"] == 0 and new["mode"] == "propose"
    doc = app.eng.projects[new["project_id"]].log.doc
    assert doc["size"] == [1920, 1080] and doc["fps"] == [25, 1] and doc["media"] == {}
    ok, lst = app.mcp("project_list", {})
    assert {p["project_id"] for p in lst["projects"]} == {"p1", new["project_id"]}
    m0 = {p["project_id"]: p["modified"] for p in lst["projects"]}
    assert all(isinstance(t, float) and t > 0 for t in m0.values())
    time.sleep(0.05)
    ok, _ = app.mcp_apply({"op": "add_marker", "at": 0, "label": "x"}, token=app.ui)  # an edit moves p1's time on
    ok, lst = app.mcp("project_list", {})
    m1 = {p["project_id"]: p["modified"] for p in lst["projects"]}
    assert ok and m1["p1"] > m0["p1"] and m1[new["project_id"]] == m0[new["project_id"]]


@pytest.mark.parametrize(
    "args, want",
    [
        ({"shape": "2:1"}, ("bad_arg", "/shape")),
        ({"fps": 29}, ("bad_arg", "/fps")),
        ({"fps": True}, ("bad_arg", "/fps")),
        ({"zz": 1}, ("unknown_arg", "/zz")),
    ],
)
def test_project_new_refusals(app, args, want):
    ok, e = app.mcp("project_new", args, app.ui)
    assert not ok and (e["rule"], e["path"]) == want


def test_project_tools_scopes_and_closed_app(app, tmp_path):
    ro = app.eng.tokens.mint("mcp:ro", scopes={"read"})
    ok, e = app.mcp("project_new", {}, ro)
    assert not ok and e["code"] == "permission_denied"
    ok, e = app.mcp("project_list", {"zz": 1})
    assert not ok and e["rule"] == "unknown_arg"
    r = MT.call("project_list", {}, MT.ClosedBackend())
    assert not r["isError"] and r["structuredContent"]["projects"][0]["project_id"] == "p1"
    r = MT.call("project_new", {}, MT.ClosedBackend())
    assert json.loads(r["content"][-1]["text"])["code"] == "engine_offline"


def test_projects_rest(app):
    st, _, lst = app.req("GET", "/api/projects", token=app.ui)
    assert st == 200 and lst["projects"][0]["project_id"] == "p1"
    st, _, new = app.req("POST", "/api/projects", {"shape": "1:1"}, app.ui)
    assert st == 200 and app.eng.projects[new["project_id"]].log.doc["size"] == [1080, 1080]
    st, _, _ = app.req("GET", "/api/projects", token=None)
    assert st == 401
    st, _, e = app.req("POST", "/api/projects", {"shape": "x"}, app.ui)
    assert st == 400 and e["path"] == "/shape"


def test_the_page_files_are_served(app):
    import http.client

    for path, needle in (("/edit/edit.js", b"window.HSEdit"), ("/sw.js", b"Authorization"), ("/", b'data-page="edit"')):
        c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=10)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{app.port}"})
        r = c.getresponse()
        body = r.read()
        c.close()
        assert r.status == 200 and needle in body
        assert r.getheader("Content-Type").startswith("text/html" if path == "/" else "text/javascript")


def test_the_desk_has_the_edit_page():
    html = (P.Path(__file__).resolve().parent.parent / "hermes_studio" / "ui" / "index.html").read_text()
    assert 'data-page="edit"' in html and "/edit/edit.js" in html and 'state.page === "edit") return;' in html


def test_set_canvas_from_the_edit_page_and_undo_puts_the_old_size_back(app):
    """PR #44's canvas size, folded into the engine Edit page: one set_canvas entry, undone as one."""
    doc0 = app.proj.log.doc
    size0, hash0 = list(doc0["size"]), doc0["hash"]
    ok, r = app.mcp_apply({"op": "set_canvas", "width": 1920, "height": 1080}, token=app.ui)
    assert ok, r
    assert app.proj.log.doc["size"] == [1920, 1080]
    ok, u = app.mcp("history_undo", {"project_id": "p1", "op_id": r["op_id"], "client_op_id": "u-canvas"}, app.ui)
    assert ok, u
    doc = app.proj.log.doc
    assert doc["size"] == size0 and doc["hash"] == hash0
    ok, e = app.mcp_apply({"op": "set_canvas", "width": 0, "height": 1080}, token=app.ui)
    assert not ok and e["code"] == "invalid_op" and e["rule"] == "out_of_range"
    js = open(os.path.join(os.path.dirname(__file__), "..", "hermes_studio", "ui", "edit.js"), encoding="utf-8").read()
    assert '"set_canvas"' in js and "Phone" in js and "Desktop" in js and "Square" in js
