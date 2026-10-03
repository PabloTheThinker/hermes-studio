"""Slip and roll: two trims that leave the rest of the timeline where it was. Each is one op,
one entry and one undo that restores the hash.

The fixture (test_oplog.base): c1 0-4 s (source 0-4), c2 4-8 s (source 10-14), c3 10-14 s,
all m1 (600 s); x1 anchored 1 s into c2."""

from __future__ import annotations

import pytest
from s3_app import App
from test_oplog import HUMAN, S, apply, base, item, new_log, roundtrip

from hermes_studio import oplog as O
from hermes_studio import timeline as T


def spans(d: dict) -> dict:
    return T.resolve(d)


def test_slip_moves_the_source_and_nothing_else():
    log0 = new_log()
    before = spans(log0.doc)
    _, d = roundtrip({"op": "slip_clip", "id": "c2", "by": S})
    assert item(d, "c2")["src"] == [11 * S, 15 * S] and spans(d) == before
    _, d = roundtrip({"op": "slip_clip", "id": "c2", "by": -10 * S})
    assert item(d, "c2")["src"] == [0, 4 * S]


@pytest.mark.parametrize("by", [S, -S])
def test_roll_moves_the_cut_and_keeps_the_length(by):
    log0 = new_log()
    before = spans(log0.doc)
    log, d = roundtrip({"op": "roll_edit", "id": "c1", "by": by})
    after = spans(d)
    assert item(d, "c1")["src"] == [0, 4 * S + by] and item(d, "c2")["src"] == [10 * S + by, 14 * S]
    assert after["c1"] == (0, 4 * S + by) and after["c2"] == (4 * S + by, 8 * S)
    assert after["c3"] == before["c3"] and after["x1"][0] == before["x1"][0] + by  # x1 rides on c2's start
    assert log._entries[0]["changed_ids"] == ["c1", "c2", "x1"]


def test_roll_through_a_crossfade():
    log = new_log()
    apply(
        log,
        HUMAN,
        {"op": "move_clip", "id": "c2", "at": 4 * S - S // 2},
        {"op": "add_transition", "between": ["c1", "c2"], "dur": S // 2},
    )
    apply(log, HUMAN, {"op": "roll_edit", "id": "c1", "by": S})
    sp = spans(log.doc)
    assert sp["c1"] == (0, 5 * S) and sp["c2"] == (5 * S - S // 2, 8 * S - S // 2)
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "roll_edit", "id": "c1", "by": -5 * S + S // 4})
    assert e.value.as_dict()["rule"] == "transition_too_long"


def test_roll_at_speed_needs_whole_ticks():
    log = new_log()
    apply(log, HUMAN, {"op": "set_props", "id": "c2", "props": {"speed": [3, 2]}})
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "roll_edit", "id": "c1", "by": 1})
    assert e.value.as_dict()["rule"] == "non_integer_duration"
    apply(log, HUMAN, {"op": "roll_edit", "id": "c1", "by": 2})
    assert item(log.doc, "c2")["src"][0] == 10 * S + 3


@pytest.mark.parametrize(
    "op, want",
    [
        ({"op": "slip_clip", "id": "c1", "by": -1}, ("out_of_range", "/ops/0/by")),
        ({"op": "slip_clip", "id": "c1", "by": 597 * S}, ("out_of_range", "/ops/0/by")),
        ({"op": "slip_clip", "id": "x1", "by": S}, ("bad_arg", "/ops/0/id")),
        ({"op": "slip_clip", "id": "c1", "by": 0}, ("bad_arg", "/ops/0/by")),
        ({"op": "slip_clip", "id": "c1", "by": 0.5}, ("not_integer_ticks", "/ops/0/by")),
        ({"op": "slip_clip", "id": "zz", "by": S}, ("not_found", "/ops/0/id")),
        ({"op": "roll_edit", "id": "c2", "by": S}, ("bad_arg", "/ops/0/id")),  # c3 starts 2 s after c2 ends
        ({"op": "roll_edit", "id": "c3", "by": S}, ("bad_arg", "/ops/0/id")),  # the last clip
        ({"op": "roll_edit", "id": "c1", "by": -4 * S}, ("bad_arg", "/ops/0/by")),
        ({"op": "roll_edit", "id": "c1", "by": 4 * S}, ("bad_arg", "/ops/0/by")),
        ({"op": "roll_edit", "id": "c1", "by": -11 * S}, ("out_of_range", "/ops/0/by")),
        ({"op": "roll_edit", "id": "c1", "by": 0}, ("bad_arg", "/ops/0/by")),
        ({"op": "roll_edit", "id": "c1"}, ("missing_arg", "/ops/0/by")),
    ],
)
def test_refusals_leave_the_doc_alone(op, want):
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


def test_mcp_takes_seconds(app):
    ok, r = app.mcp_apply({"op": "roll_edit", "id": "c1", "by_s": -1.5}, {"op": "slip_clip", "id": "c3", "by_s": 2})
    assert ok, r
    d = app.proj.log.doc
    assert item(d, "c1")["src"] == [0, 5 * S // 2] and item(d, "c3")["src"] == [22 * S, 26 * S]
    ok, e = app.mcp_apply({"op": "slip_clip", "id": "c3", "by_s": -1000})
    assert not ok and (e["rule"], e["path"]) == ("out_of_range", "/ops/0/by"), e
