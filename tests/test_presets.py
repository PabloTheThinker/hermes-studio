"""Phase 2 Q3 presets: each is ONE entry and one undo restores the hash."""

from __future__ import annotations

import pytest
from s3_app import App

from hermes_studio import presets as PR
from hermes_studio import timeline as T

S = T.TICK_RATE


def doc0() -> dict:
    d = T.new_timeline("p1")
    d["media"] = {
        "m1": {"path": "/media/talk.mp4", "dur": 300 * S, "fps": [30, 1]},
        "m2": {"path": "/media/song.mp3", "dur": 300 * S, "fps": None},
    }
    tr = {t["id"]: t for t in d["tracks"]}
    tr["V1"]["items"] = [
        {
            "id": f"c{i}",
            "type": "clip",
            "media": "m1",
            "src": [i * 10 * S, (i * 10 + 4) * S],
            "at": i * 4 * S,
            "fade_in": 0,
            "fade_out": 0,
        }
        for i in range(3)
    ]
    tr["A2"]["items"] = [{"id": "mu", "type": "clip", "media": "m2", "src": [0, 12 * S], "at": 0, "fade_in": 0, "fade_out": 0}]
    return d


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(doc0())
    yield a
    a.close()


def preset(app: App, name: str, **args) -> tuple[bool, dict]:
    return app.mcp(
        "apply_preset",
        {
            "project_id": "p1",
            "preset": name,
            "base_version": app.proj.log.version,
            "client_op_id": f"p{app.proj.log.version}",
            **args,
        },
    )


@pytest.mark.parametrize(
    "name, args, n_ops",
    [
        ("fade_in_out", {}, 3),
        ("title_card", {"text": "HERMES"}, 1),
        ("end_card", {"text": "Follow for more"}, 1),
        ("duck_music", {}, 1),
        ("crossfade_all", {}, 4),
    ],
)
def test_q3_one_entry_and_one_undo(app, name, args, n_ops):
    h0 = app.head()
    ok, r = preset(app, name, **args)
    assert ok and r["applied"] and r["preset"] == name, r
    assert len(app.proj.log._entries) == 1 and len(app.proj.log._entries[0]["ops"]) == n_ops
    assert app.proj.log._entries[0]["summary"] == PR.PRESETS[name]
    ok, u = app.mcp("history_undo", {"project_id": "p1", "client_op_id": "u", "op_id": r["op_id"]})
    assert ok and app.head()["hash"] == h0["hash"]


def test_what_each_preset_does(app):
    preset(app, "fade_in_out", seconds=0.5)
    clips = {it["id"]: it for it in app.proj.log.doc["tracks"][1]["items"]}
    assert all(c["fade_in"] == c["fade_out"] == S // 2 for c in clips.values())
    preset(app, "duck_music")
    mu = next(t for t in app.proj.log.doc["tracks"] if t["role"] == "music")["items"][0]
    assert mu["props"]["volume"] == [3, 20]
    preset(app, "end_card", text="Bye")
    x = next(t for t in app.proj.log.doc["tracks"] if t["role"] == "text")["items"][-1]
    spans = T.resolve(app.proj.log.doc)
    assert spans[x["id"]][1] == 12 * S and x["text"] == "Bye"
    preset(app, "crossfade_all")
    doc = app.proj.log.doc
    spans = T.resolve(doc)
    trans = [it for it in doc["tracks"][1]["items"] if it["type"] == "transition"]
    assert len(trans) == 2 and max(e for _, e in spans.values()) == 12 * S  # the music still runs to 12 s
    v1_end = max(spans[c][1] for c in ("c0", "c1", "c2"))
    assert v1_end == 12 * S - 2 * 9 * (S // 30)  # 0.3 s snapped to 9 frames, twice


def test_preview_and_retry(app):
    h0 = app.head()
    ok, p = preset(app, "fade_in_out", preview=True)
    assert ok and not p["applied"] and len(p["ops"]) == 3 and app.head() == h0
    args = {"project_id": "p1", "preset": "title_card", "text": "Hi", "base_version": 0, "client_op_id": "same"}
    ok, a = app.mcp("apply_preset", args)
    ok2, b = app.mcp("apply_preset", args)
    assert ok and ok2 and a["op_id"] == b["op_id"] and len(app.proj.log._entries) == 1


@pytest.mark.parametrize(
    "args, want",
    [
        ({}, ("missing_arg", "/preset")),
        ({"preset": "sparkle"}, ("bad_arg", "/preset")),
        ({"preset": "title_card"}, ("missing_arg", "/text")),
        ({"preset": "title_card", "text": " "}, ("bad_arg", "/text")),
        ({"preset": "fade_in_out", "seconds": 0}, ("bad_arg", "/seconds")),
        ({"preset": "fade_in_out", "seconds": True}, ("bad_arg", "/seconds")),
        ({"preset": "fade_in_out", "zz": 1}, ("unknown_arg", "/zz")),
    ],
)
def test_preset_refusals(app, args, want):
    ok, e = app.mcp("apply_preset", {"project_id": "p1", "base_version": 0, "client_op_id": "x", **args})
    assert not ok and (e["rule"], e["path"]) == want, e
    assert app.proj.log._entries == []


def test_presets_obey_the_mode_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    a = App(doc0(), mode="ask")
    try:
        ok, e = a.mcp("apply_preset", {"project_id": "p1", "preset": "fade_in_out", "base_version": 0, "client_op_id": "x"})
        assert not ok and e["code"] == "permission_denied"
        ok, _ = a.mcp("set_mode", {"project_id": "p1", "mode": "propose"}, a.ui)
        ok, e = a.mcp("apply_preset", {"project_id": "p1", "preset": "fade_in_out", "base_version": 0, "client_op_id": "x"})
        assert not ok and e["code"] == "needs_approval"
        st, _, r = a.req(
            "POST", "/api/projects/p1/apply_preset", {"preset": "duck_music", "base_version": 0, "client_op_id": "h"}, a.ui
        )
        assert st == 200 and r["applied"], r  # a person's preset applies at once
    finally:
        a.close()
