"""Phase 2 Q2 draft branches: Discard returns the main hash exactly; Keep makes the main equal
to the draft (as replaying the branch would) in one entry that one undo reverses."""

from __future__ import annotations

import json

import pytest
from s3_app import App
from test_oplog import S, base

from hermes_studio import drafts as DR
from hermes_studio import oplog as O
from hermes_studio import project as P


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(base(), mode="propose")
    yield a
    a.close()


def draft_with_edits(app: App) -> str:
    ok, d = app.mcp("draft_new", {"project_id": "p1"})
    assert ok, d
    did = d["project_id"]
    assert did.startswith("p1.d") and d["from_version"] == 0 and d["mode"] == "auto"
    for i, ops in enumerate(
        (
            [{"op": "add_marker", "at": S, "label": "draft"}],
            [{"op": "delete_clip", "id": "c3", "ripple": True}],
            [{"op": "add_text", "text": "Hi", "style": "pop", "at": 0, "dur": S}],
        )
    ):
        dp = app.eng.projects[did]
        ok, r = app.mcp(
            "timeline_apply",
            {"project_id": did, "base_version": dp.log.version, "summary": f"e{i}", "client_op_id": f"e{i}", "ops": ops},
        )
        assert ok, r  # the agent edits the draft freely (Auto), even though the main is in Propose
    return did


def test_q2_discard_returns_the_main_hash_exactly(app):
    h0 = app.head()
    did = draft_with_edits(app)
    assert app.head() == h0  # the main never moved
    ok, r = app.mcp("draft_discard", {"project_id": did}, app.ui)
    assert ok and r == {"discarded": did, "main": "p1"}
    assert app.head() == h0 and not P.project_dir(did).exists() and did not in app.eng.projects


def test_q2_keep_equals_the_branch_in_one_entry_and_one_undo(app):
    h0 = app.head()
    did = draft_with_edits(app)
    branch = app.eng.projects[did].log.doc
    ok, r = app.mcp("draft_keep", {"project_id": did}, app.ui)
    assert ok, r
    main = app.proj.log
    assert len(main._entries) == 1 and main._entries[0]["summary"] == "Keep draft (3 edits)"
    assert main._entries[0]["actor"] == {"kind": "human", "id": "user"}
    assert DR.body_equal(main.doc, branch)
    # replaying the branch's own ops on the main gives the same doc
    replay = O.Oplog(base())
    for e in app.eng.projects[did].log._entries:
        replay._doc = replay._run(e["ops"], internal=True)[0]
    assert DR.body_equal(replay._doc, main.doc)
    # the reload replays it too
    assert O.Oplog.load(base(), app.proj.dir / "oplog.jsonl").doc["hash"] == main.doc["hash"]
    ok, u = app.mcp("history_undo", {"project_id": "p1", "client_op_id": "u", "op_id": r["op_id"]}, app.ui)
    assert ok and app.head()["hash"] == h0["hash"]
    st = json.loads((P.project_dir(did) / "draft.json").read_text())
    assert st["state"] == "kept" and st["op_id"] == r["op_id"]
    ok, e = app.mcp("draft_keep", {"project_id": did}, app.ui)
    assert not ok and "already kept" in e["error"]


def test_keep_after_the_main_moved_is_conflict(app):
    did = draft_with_edits(app)
    ok, _ = app.mcp_apply({"op": "add_marker", "at": 2 * S, "label": "human"}, token=app.ui)
    assert ok
    ok, e = app.mcp("draft_keep", {"project_id": did}, app.ui)
    assert not ok and e["code"] == "conflict"
    assert [x["summary"] for x in app.proj.log._entries] == ["edit"]


def test_only_a_person_keeps_or_discards(app):
    did = draft_with_edits(app)
    for tool in ("draft_keep", "draft_discard"):
        ok, e = app.mcp(tool, {"project_id": did})
        assert not ok and e["code"] == "permission_denied"
    assert P.project_dir(did).exists()


def test_listing_ask_mode_and_drafts_of_drafts(app):
    did = draft_with_edits(app)
    ok, lst = app.mcp("draft_list", {"project_id": "p1"})
    assert ok and [d["project_id"] for d in lst["drafts"]] == [did] and lst["drafts"][0]["draft"]["state"] == "open"
    ok, e = app.mcp("draft_new", {"project_id": did})
    assert not ok and e["rule"] == "bad_arg"
    ok, e = app.mcp("draft_keep", {"project_id": "p1"}, app.ui)
    assert not ok and "not a draft" in e["error"]
    app.mcp("set_mode", {"project_id": "p1", "mode": "ask"}, app.ui)
    ok, e = app.mcp("draft_new", {"project_id": "p1"})
    assert not ok and e["code"] == "permission_denied"
    ok, e = app.mcp("draft_new", {"project_id": "p1", "zz": 1}, app.ui)
    assert not ok and e["rule"] == "unknown_arg"


def test_keep_body_retry_and_bad_args():
    ses = O.Session(O.Actor("human", "user"))
    log = O.Oplog(base())
    body = {**log.doc, "markers": []}
    args = {"client_op_id": "k", "summary": "Keep", "base_version": 0}
    a = log.call(ses, "keep_body", {**args, "body": body})
    b = log.call(ses, "keep_body", {**args, "body": body})
    assert a["op_id"] == b["op_id"] and len(log._entries) == 1
    with pytest.raises(O.OplogError) as e:
        log.call(ses, "keep_body", {"client_op_id": "k2", "summary": "Keep", "body": body})
    assert e.value.as_dict()["rule"] == "missing_arg"
    with pytest.raises(O.OplogError) as e:
        log.call(ses, "keep_body", {**args, "client_op_id": "k3", "zz": 1, "body": body})
    assert e.value.as_dict()["rule"] == "unknown_arg"
