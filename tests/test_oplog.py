"""Slice 2: the op log (Prove C2-C6): ops and inverses, atomic batches, groups, append-only
undo/redo, client_op_id dedupe, actor and step from the session only, version conflicts."""

from __future__ import annotations

import copy
import json
import random
import unicodedata
from pathlib import Path

import pytest

from hermes_studio import oplog as O
from hermes_studio import timeline as T

S = T.TICK_RATE
HUMAN = O.Session(O.Actor("human", "pablo"))
HERMES_ACTOR = O.Actor("agent", "hermes")


def hermes(step: int | None = 3) -> O.Session:
    return O.Session(HERMES_ACTOR, O.PlanContext(step))


def base() -> dict:
    d = T.new_timeline("p1")
    d["media"] = {
        "m1": {"path": "media/talk.mp4", "dur": 600 * S, "fps": [30, 1]},
        "m2": {"path": "media/song.mp3", "dur": 300 * S, "fps": None},
    }
    tr = {t["id"]: t for t in d["tracks"]}
    tr["V1"]["items"] = [
        {"id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * S], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "c2", "type": "clip", "media": "m1", "src": [10 * S, 14 * S], "at": 4 * S, "fade_in": 0, "fade_out": 0},
        {"id": "c3", "type": "clip", "media": "m1", "src": [20 * S, 24 * S], "at": 10 * S, "fade_in": 0, "fade_out": 0},
    ]
    tr["T1"]["items"] = [
        {
            "id": "x1",
            "type": "text",
            "dur": S,
            "text": "Hi",
            "style": "pop",
            "fade_in": 0,
            "fade_out": 0,
            "anchor": {"to": "c2", "offset": S},
        }
    ]
    tr["A2"]["items"] = [
        {
            "id": "mu1",
            "type": "clip",
            "media": "m2",
            "src": [0, 6 * S],
            "anchor": {"to": "c1", "offset": 0},
            "fade_in": 0,
            "fade_out": 0,
        }
    ]
    d["markers"] = [{"id": "k1", "at": 2 * S, "label": "here"}]
    return d


def new_log(**kw) -> O.Oplog:
    n = iter(range(1, 10**9))
    return O.Oplog(base(), new_op_id=lambda: f"op{next(n)}", **kw)


_cid = iter(range(1, 10**9))


def apply(log: O.Oplog, session: O.Session, *ops: dict, **extra) -> dict:
    args = {"base_version": log.version, "ops": list(ops), "summary": "edit", "client_op_id": f"k{next(_cid)}", **extra}
    return log.call(session, "timeline_apply", args)


def undo(log: O.Oplog, session: O.Session, **target) -> dict:
    return log.call(session, "history_undo", {"client_op_id": f"u{next(_cid)}", **target})


def item(d: dict, iid: str) -> dict:
    return next(i for t in d["tracks"] for i in t["items"] if i["id"] == iid)


def ids(d: dict) -> set[str]:
    return {i["id"] for t in d["tracks"] for i in t["items"]}


def h(log: O.Oplog) -> str:
    return T.canonical_hash(log.doc)


# --------------------------------------------------------------------------- the log line


def test_a_line_has_exactly_the_contract_fields():
    log = new_log()
    r = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 11 * S}, group_id="g1")
    (e,) = log.history_list()
    assert list(O.LINE_FIELDS) == [
        "seq",
        "op_id",
        "client_op_id",
        "group_id",
        "actor",
        "summary",
        "base_version",
        "new_version",
        "hash",
        "ops",
        "inverse",
        "changed_ids",
        "undoes",
    ]
    assert set(e) == set(O.LINE_FIELDS)  # a human op has no step
    assert e["seq"] == 1 and e["op_id"] == r["op_id"] == "op1" and e["group_id"] == "g1"
    assert e["actor"] == {"kind": "human", "id": "pablo"}
    assert (e["base_version"], e["new_version"]) == (0, 1) and log.doc["version"] == 1
    assert e["hash"] == r["hash"] == log.doc["hash"] == T.canonical_hash(log.doc)
    assert e["ops"] == [{"op": "move_clip", "id": "c3", "at": 11 * S}]
    assert e["inverse"] == [{"op": "move_clip", "id": "c3", "at": 10 * S}]
    assert e["changed_ids"] == ["c3"] and e["undoes"] is None
    assert r["tick_rate"] == S and r["warnings"] == [] and r["before_frame"] is None and r["after_frame"] is None


def test_the_result_carries_the_write_contract():
    r = apply(new_log(), hermes(), {"op": "add_marker", "at": 211680000, "label": "x"})
    assert {
        "ok",
        "op_id",
        "group_id",
        "seq",
        "new_version",
        "hash",
        "tick_rate",
        "summary",
        "changed_ids",
        "undoes",
        "before_frame",
        "after_frame",
        "warnings",
    } == set(r)
    assert r["changed_ids"] == ["mk1"]


# --------------------------------------------------------------------------- actor and step come from the session


def test_forged_actor_in_the_args_is_ignored():
    log = new_log()
    r = log.call(
        hermes(),
        "timeline_apply",
        {
            "base_version": 0,
            "summary": "s",
            "client_op_id": "a1",
            "actor": {"kind": "human", "id": "pablo"},
            "ops": [{"op": "move_clip", "id": "c3", "at": 11 * S}],
        },
    )
    assert log.history_list()[-1]["actor"] == {"kind": "agent", "id": "hermes"}
    assert r["warnings"] == [
        {"code": "ignored_field", "path": "/actor", "message": "'actor' is ignored: it comes from the session, not the arguments"}
    ]
    # ...so the forged human identity doesn't let the agent undo a human's entry
    h1 = apply(log, HUMAN, {"op": "set_fade", "id": "c1", "fade_in": S // 2})
    with pytest.raises(O.OplogError) as e:
        log.call(hermes(), "history_undo", {"op_id": h1["op_id"], "client_op_id": "a2", "actor": "human"})
    assert e.value.code == "undo_blocked" and e.value.extra["reason"] == "actor"


def test_forged_actor_and_step_inside_an_op_are_ignored():
    log = new_log()
    r = apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "x", "actor": "hermes", "step": 7})
    e = log.history_list()[-1]
    assert e["actor"] == {"kind": "human", "id": "pablo"} and "step" not in e
    assert e["ops"] == [{"op": "add_marker", "at": 0, "label": "x", "id": "mk1"}]
    assert [w["path"] for w in r["warnings"]] == ["/ops/0/actor", "/ops/0/step"]
    assert all(m.keys() == {"id", "at", "label"} for m in log.doc["markers"])


def test_forged_step_is_ignored_and_the_plan_step_is_logged():
    log = new_log()
    plan = O.PlanContext(3)
    agent = O.Session(HERMES_ACTOR, plan)
    apply(log, agent, {"op": "move_clip", "id": "c3", "at": 11 * S}, step=99)
    assert log.history_list()[-1]["step"] == 3
    plan.step = 4  # the session layer moves the plan on
    apply(log, agent, {"op": "move_clip", "id": "c3", "at": 12 * S}, step=1)
    assert log.history_list()[-1]["step"] == 4


def test_an_agent_without_a_plan_step_gets_no_step_even_if_the_args_have_one():
    log = new_log()
    for session in (O.Session(O.Actor("agent", "claude")), hermes(None)):
        r = apply(log, session, {"op": "add_marker", "at": 0, "label": "x"}, step=2)
        assert "step" not in log.history_list()[-1]
        assert [w["path"] for w in r["warnings"]] == ["/step"]


def test_a_human_op_never_gets_a_step():
    log = new_log()
    human_with_plan = O.Session(O.Actor("human", "pablo"), O.PlanContext(5))  # a plan context is present
    apply(log, human_with_plan, {"op": "move_clip", "id": "c3", "at": 11 * S}, step=5)
    apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 12 * S})
    log.call(human_with_plan, "history_undo", {"op_id": log.history_list()[1]["op_id"], "client_op_id": "hu", "step": 2})
    assert len(log.history_list()) == 3 and all("step" not in e for e in log.history_list())


def test_forged_fields_are_ignored_on_undo_and_redo_too():
    log = new_log()
    r = apply(log, hermes(2), {"op": "move_clip", "id": "c3", "at": 11 * S})
    u = log.call(hermes(2), "history_undo", {"op_id": r["op_id"], "client_op_id": "u", "actor": "pablo", "step": 9})
    rd = log.call(hermes(2), "history_redo", {"op_id": u["op_id"], "client_op_id": "r", "actor": {"kind": "human"}, "step": 9})
    for res, e in zip((u, rd), log.history_list()[1:], strict=True):
        assert e["actor"] == {"kind": "agent", "id": "hermes"} and e["step"] == 2
        assert [w["path"] for w in res["warnings"]] == ["/actor", "/step"]


def test_call_is_the_only_way_to_write():
    public = {n for n in dir(O.Oplog) if not n.startswith("_")}
    assert public == {"call", "doc", "version", "history_list", "history_diff", "load"}
    log = new_log()
    log.doc["markers"].clear()  # doc is a copy
    assert log.doc["markers"]
    with pytest.raises(TypeError):
        log.call({"actor": {"kind": "human", "id": "pablo"}}, "timeline_apply", {})


def test_sessions_are_checked():
    with pytest.raises(ValueError):
        O.Actor("robot", "x")
    with pytest.raises(ValueError):
        O.Actor("human", "a/b")
    with pytest.raises(ValueError):
        O.PlanContext(0)
    with pytest.raises(ValueError):
        O.PlanContext(True)


# --------------------------------------------------------------------------- dedupe, conflict, atomic batches


def test_a_retry_with_the_same_client_op_id_applies_once():
    log = new_log()
    args = {"base_version": 0, "ops": [{"op": "add_marker", "at": 0, "label": "x"}], "summary": "s", "client_op_id": "same"}
    r1 = log.call(HUMAN, "timeline_apply", args)
    r2 = log.call(HUMAN, "timeline_apply", args)  # base_version is stale now: the retry still returns the original
    assert r1 == r2 and log.version == 1 and len(log.history_list()) == 1
    r3 = log.call(hermes(), "timeline_apply", {**args, "base_version": 1})  # another actor: its own key
    assert r3["op_id"] != r1["op_id"] and log.version == 2


def test_a_stale_base_version_is_a_conflict_with_a_history_diff():
    log = new_log()
    apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 11 * S})
    before, n = h(log), len(log.history_list())
    args = {"base_version": 0, "ops": [{"op": "add_marker", "at": 0, "label": "x"}], "summary": "s", "client_op_id": "c"}
    for _ in range(2):  # a stale retry is refused again
        with pytest.raises(O.OplogError) as e:
            log.call(hermes(), "timeline_apply", args)
        d = e.value.as_dict()
        assert d["code"] == "conflict" and d["current_version"] == 1
        assert [x["op_id"] for x in d["history_diff"]] == ["op1"] and d["history_diff"][0]["actor"]["kind"] == "human"
        assert h(log) == before and len(log.history_list()) == n


def test_a_batch_that_fails_at_op_k_applies_nothing():
    log = new_log()
    before = log.doc
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 11 * S}, {"op": "move_clip", "id": "nope", "at": 0})
    assert e.value.code == "not_found" and e.value.extra["op_index"] == 1 and e.value.extra["path"] == "/ops/1/id"
    assert log.doc == before and log.history_list() == []


def test_a_batch_whose_result_is_invalid_applies_nothing_and_passes_problems_through():
    log = new_log()
    before = log.doc
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "ok"}, {"op": "move_clip", "id": "c3", "at": 7 * S})
    d = e.value.as_dict()
    assert d["code"] == "invalid_op" and d["rule"] == "overlap" and d["op_index"] == 1 and d["id"] == "c3"
    assert d["path"] == "/tracks/1/items/2" and d["problems"][0]["rule"] == "overlap"
    assert log.doc == before and log.history_list() == []


@pytest.mark.parametrize(
    "op, rule, pid",
    [
        ({"op": "set_fade", "id": "c1", "fade_in": 3 * S, "fade_out": 2 * S}, "fade_too_long", "c1"),
        ({"op": "set_anchor", "id": "x1", "anchor": {"to": "mu1", "offset": 0}}, "anchor_target_not_main", "x1"),
        ({"op": "move_clip", "id": "c2", "at": 0}, "overlap", None),
        ({"op": "add_marker", "at": 0, "label": "e\u0301"}, "not_nfc", "mk1"),
    ],
)
def test_the_validator_runs_after_the_ops(op, rule, pid):
    log = new_log()
    before = h(log)
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, op)
    assert e.value.code == "invalid_op" and e.value.extra["rule"] == rule
    assert pid is None or e.value.extra["id"] == pid
    assert h(log) == before


def test_moving_a_clip_can_push_its_anchored_item_below_zero():
    log = new_log()
    apply(log, HUMAN, {"op": "set_anchor", "id": "x1", "anchor": {"to": "c3", "offset": -10 * S}})
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 9 * S})
    assert e.value.extra["rule"] == "anchor_before_zero" and e.value.extra["id"] == "x1"  # the anchored item's id


@pytest.mark.parametrize(
    "args, rule",
    [
        ({"ops": [], "summary": "s"}, "bad_arg"),
        ({"ops": [{"op": "frobnicate"}], "summary": "s"}, "unknown_op"),
        ({"ops": [{"op": "set_fields", "id": "c1", "set": {"at": 0}}], "summary": "s"}, "unknown_op"),  # internal only
        ({"ops": [{"op": "move_clip", "id": "c3"}], "summary": "s"}, "missing_arg"),
        ({"ops": [{"op": "move_clip", "id": "c3", "at": 1.5}], "summary": "s"}, "not_integer_ticks"),
        ({"ops": [{"op": "move_clip", "id": "c3", "at": 0, "color": 1}], "summary": "s"}, "unknown_arg"),
        ({"ops": [{"op": "add_marker", "at": 0, "label": "x"}], "summary": ""}, "bad_arg"),
        ({"ops": [{"op": "add_marker", "at": 0, "label": "x"}], "summary": "s", "seq": 5}, "unknown_arg"),
        ({"ops": [{"op": "add_marker", "at": 0, "label": "x"}]}, "missing_arg"),
    ],
)
def test_bad_calls_are_invalid_op(args, rule):
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "timeline_apply", {"base_version": 0, "client_op_id": "x", **args})
    assert e.value.code == "invalid_op" and e.value.extra["rule"] == rule and log.history_list() == []


@pytest.mark.parametrize("with_file", [False, True])
def test_a_summary_with_a_lone_surrogate_is_invalid_op_not_an_encode_error(tmp_path, with_file):
    log = new_log(path=tmp_path / "oplog.jsonl") if with_file else new_log()
    bad = json.loads('"a\\ud800"')
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "x"}, summary=bad)
    assert (e.value.code, e.value.extra["rule"], e.value.extra["path"]) == ("invalid_op", "bad_arg", "/summary")
    r = apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "x"})
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "history_undo", {"op_id": r["op_id"], "client_op_id": "u-sur", "summary": bad})
    assert e.value.extra["path"] == "/summary" and log.version == 1 and len(log.history_list()) == 1
    with pytest.raises(O.OplogError) as e:  # a lone surrogate in an op is the validator's wrong_type
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": bad})
    assert e.value.extra["rule"] == "wrong_type" and log.version == 1


def test_unknown_tool_and_project():
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "publish", {})
    assert e.value.extra["rule"] == "unknown_tool"
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "x"}, project_id="other")
    assert e.value.code == "not_found" and e.value.exit_code == 4


# --------------------------------------------------------------------------- ops and inverses


def roundtrip(*ops: dict) -> tuple[O.Oplog, dict]:
    """Apply ops as one entry, check undo restores the hash and redo restores the new one."""
    log = new_log()
    h0 = h(log)
    r = apply(log, HUMAN, *ops)
    h1 = h(log)
    assert h1 != h0
    after = log.doc
    u = undo(log, HUMAN, op_id=r["op_id"])
    assert h(log) == h0 and u["undoes"] == [r["op_id"]]
    log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": f"r{next(_cid)}"})
    assert h(log) == h1
    return log, after


def test_insert_clip_gets_a_fresh_id_and_undo_deletes_it():
    log, d = roundtrip({"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S})
    assert item(d, "c4")["at"] == 20 * S and item(d, "c4")["fade_in"] == 0
    assert log.history_list()[0]["inverse"] == [{"op": "delete_item", "id": "c4"}]


def test_add_text_transition_track_and_marker():
    roundtrip({"op": "add_text", "at": 0, "dur": S, "text": "Hola", "style": "pop"})
    roundtrip(
        {"op": "move_clip", "id": "c2", "at": 4 * S - S // 2}, {"op": "add_transition", "between": ["c1", "c2"], "dur": S // 2}
    )
    _, d = roundtrip({"op": "add_track", "role": "text"}, {"op": "add_track", "role": "voice"})
    assert [t["id"] for t in d["tracks"]] == ["T2", "T1", "V1", "A1", "A3", "A2"]  # role order kept
    roundtrip({"op": "add_marker", "at": 3 * S, "label": "b"}, {"op": "remove_marker", "id": "k1"})
    roundtrip({"op": "remove_track", "id": "A2"})


def test_move_trim_props_fade_and_anchor_undo_with_old_values():
    roundtrip({"op": "move_clip", "id": "c3", "at": 12 * S})
    roundtrip({"op": "trim_clip", "id": "c3", "src_in": 21 * S})  # c3 stays put: at moves 1 s right
    roundtrip({"op": "trim_clip", "id": "c1", "src_out": 3 * S, "ripple": True})
    roundtrip({"op": "trim_clip", "id": "x1", "dur": 2 * S})
    roundtrip({"op": "set_props", "id": "c1", "props": {"volume": [1, 2], "look": "warm"}})
    roundtrip({"op": "set_fade", "id": "x1", "fade_in": S // 4})
    roundtrip({"op": "set_anchor", "id": "x1", "anchor": None, "at": 7 * S})
    roundtrip({"op": "set_anchor", "id": "mu1", "anchor": {"to": "c2", "offset": S}})


def test_trim_ripple_moves_later_items_and_undo_moves_them_back():
    log = new_log()
    apply(log, HUMAN, {"op": "trim_clip", "id": "c1", "src_out": 3 * S, "ripple": True})
    d = log.doc
    assert item(d, "c2")["at"] == 3 * S and item(d, "c3")["at"] == 9 * S
    assert log.history_list()[0]["inverse"][0] == {"op": "shift_items", "ids": ["c2", "c3"], "by": S}


def test_split_gives_two_pieces_and_undo_joins_back_to_the_old_id():
    log, d = roundtrip({"op": "split_clip", "id": "c2", "at": 5 * S})
    a, b = item(d, "c4"), item(d, "c5")
    assert "c2" not in ids(d) and a["split_from"] == b["split_from"] == "c2"
    assert (a["src"], a["at"], b["src"], b["at"]) == ([10 * S, 11 * S], 4 * S, [11 * S, 14 * S], 5 * S)
    assert item(d, "x1")["anchor"] == {"to": "c5", "offset": 0}  # x1 starts at the cut: the second piece
    e = log.history_list()[0]
    assert e["ops"][0]["ids"] == ["c4", "c5"] and e["inverse"][0]["op"] == "join_clips"
    assert e["changed_ids"] == ["c2", "c4", "c5", "x1"]
    assert item(log.doc, "c4") == a  # redo made the same pieces


def test_split_at_speed_refuses_a_non_whole_tick_point():
    log = new_log()
    apply(
        log,
        HUMAN,
        {"op": "set_props", "id": "c3", "props": {"speed": [3, 2]}},
        {"op": "trim_clip", "id": "c3", "src_out": 23 * S},
    )  # 3 s of source at 1.5x = 2 s
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "split_clip", "id": "c3", "at": 10 * S + 1})
    assert e.value.extra["rule"] == "non_integer_duration"


def test_split_moves_transitions_and_anchors_to_the_right_piece():
    log = new_log()
    apply(
        log,
        HUMAN,
        {"op": "move_clip", "id": "c2", "at": 4 * S - S // 2},
        {"op": "add_transition", "id": "tA", "between": ["c1", "c2"], "dur": S // 2},
    )
    apply(log, HUMAN, {"op": "split_clip", "id": "c2", "at": 4 * S + S // 4, "ids": ["p1", "p2"]})
    d = log.doc
    assert item(d, "tA")["between"] == ["c1", "p1"]
    assert item(d, "x1")["anchor"] == {"to": "p2", "offset": S // 4}  # the text starts after the cut
    assert T.resolve(d)["x1"][0] == 4 * S + S // 2


def test_deleting_a_clip_frees_its_anchored_items_and_undo_reanchors_them():
    log, d = roundtrip({"op": "delete_clip", "id": "c2"})
    assert "c2" not in ids(d) and item(d, "x1")["at"] == 5 * S and "anchor" not in item(d, "x1")
    assert T.validate(d) == []  # never an anchor_target_missing doc


def test_freed_anchored_items_are_in_changed_ids_of_the_delete_and_its_undo():
    log = new_log()
    apply(log, HUMAN, {"op": "add_text", "id": "x9", "dur": S, "text": "b", "style": "pop", "anchor": {"to": "c2", "offset": 0}})
    r = apply(log, HUMAN, {"op": "delete_clip", "id": "c2"})
    assert r["changed_ids"] == ["c2", "x1", "x9"] == log.history_list()[-1]["changed_ids"]
    assert {o["id"] for o in log.history_list()[-1]["inverse"] if o["op"] == "set_fields"} == {"x1", "x9"}
    u = undo(log, HUMAN, op_id=r["op_id"])
    assert u["changed_ids"] == ["c2", "x1", "x9"] == log.history_list()[-1]["changed_ids"]
    assert item(log.doc, "x1")["anchor"] == {"to": "c2", "offset": S} and "at" not in item(log.doc, "x9")
    rd = log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": "rd-del"})
    assert rd["changed_ids"] == ["c2", "x1", "x9"]


def test_re_anchored_items_are_in_changed_ids_of_the_split_and_its_undo():
    log = new_log()
    r = apply(log, HUMAN, {"op": "split_clip", "id": "c1", "at": S, "ids": ["p1", "p2"]})
    assert item(log.doc, "mu1")["anchor"] == {"to": "p1", "offset": 0}  # music anchored to c1 moved to p1
    assert r["changed_ids"] == ["c1", "mu1", "p1", "p2"] == log.history_list()[-1]["changed_ids"]
    (inv,) = log.history_list()[-1]["inverse"]
    assert inv["op"] == "join_clips" and inv["anchors"] == {"mu1": {"to": "c1", "offset": 0}}
    u = undo(log, HUMAN, op_id=r["op_id"])
    assert u["changed_ids"] == ["c1", "mu1", "p1", "p2"] and item(log.doc, "mu1")["anchor"]["to"] == "c1"
    r2 = apply(log, HUMAN, {"op": "split_clip", "id": "c2", "at": 5 * S, "ids": ["q1", "q2"]})
    assert "x1" in r2["changed_ids"] and item(log.doc, "x1")["anchor"] == {"to": "q2", "offset": 0}
    assert "x1" in undo(log, HUMAN, op_id=r2["op_id"])["changed_ids"]


def test_dependents_come_back_as_blocking_op_ids_in_seq_order():
    log = new_log()
    a = apply(log, hermes(), {"op": "move_clip", "id": "c3", "at": 12 * S})
    b = apply(log, HUMAN, {"op": "set_fade", "id": "c3", "fade_in": S})
    apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "unrelated"})
    c = apply(log, HUMAN, {"op": "add_text", "dur": S, "text": "t", "style": "pop", "anchor": {"to": "c3", "offset": 0}})
    d = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 13 * S})
    before = h(log)
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, op_id=a["op_id"])
    out = e.value.as_dict()
    assert out["code"] == "undo_blocked" and out["reason"] == "dependents"
    assert out["blocking_op_ids"] == [b["op_id"], c["op_id"], d["op_id"]]  # by seq; the marker entry doesn't block
    assert h(log) == before
    undo(log, HUMAN, op_id=d["op_id"])
    with pytest.raises(O.OplogError) as e:  # an undone blocker drops out
        undo(log, HUMAN, op_id=a["op_id"])
    assert e.value.extra["blocking_op_ids"] == [b["op_id"], c["op_id"]]


def test_an_actor_block_has_no_blocking_op_ids():
    log = new_log()
    hu = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 12 * S})
    with pytest.raises(O.OplogError) as e:
        undo(log, hermes(), op_id=hu["op_id"])
    assert e.value.extra["reason"] == "actor" and "blocking_op_ids" not in e.value.extra


def test_ripple_delete_closes_the_hole_and_takes_transitions_along():
    log = new_log()
    apply(
        log,
        HUMAN,
        {"op": "move_clip", "id": "c3", "at": 8 * S - S // 4},
        {"op": "add_transition", "id": "tB", "between": ["c2", "c3"], "dur": S // 4},
    )
    h1 = h(log)
    r = apply(log, HUMAN, {"op": "delete_clip", "id": "c2", "ripple": True})
    d = log.doc
    assert "tB" not in ids(d) and item(d, "c3")["at"] == 4 * S  # abuts c1
    undo(log, HUMAN, op_id=r["op_id"])
    assert h(log) == h1


# --------------------------------------------------------------------------- undo rules


def test_undo_is_a_new_entry_and_history_is_never_rewritten():
    log = new_log()
    r = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 12 * S})
    first = copy.deepcopy(log.history_list())
    u = undo(log, HUMAN, op_id=r["op_id"])
    hist = log.history_list()
    assert hist[:1] == first and len(hist) == 2 and hist[1]["undoes"] == [r["op_id"]] and u["new_version"] == 2
    assert hist[1]["ops"] == first[0]["inverse"] and hist[1]["summary"] == "Undo: edit"
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, op_id=r["op_id"])
    assert e.value.extra["rule"] == "already_undone"


def test_undoing_a_group_is_one_entry_in_reverse_order():
    log = new_log()
    h0 = h(log)
    a = apply(log, hermes(), {"op": "move_clip", "id": "c3", "at": 12 * S}, group_id="fillers")
    b = apply(log, hermes(), {"op": "move_clip", "id": "c3", "at": 13 * S}, group_id="fillers")
    apply(log, hermes(), {"op": "add_marker", "at": 0, "label": "x"})
    u = undo(log, hermes(), group_id="fillers")
    assert u["undoes"] == [b["op_id"], a["op_id"]] and h(log) != h0 and item(log.doc, "c3")["at"] == 10 * S
    assert len(log.history_list()) == 4


def test_an_agent_cannot_undo_a_humans_entry_but_a_human_can_undo_an_agents():
    log = new_log()
    hu = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 12 * S})
    ag = apply(log, hermes(), {"op": "add_marker", "at": 0, "label": "x"})
    before = h(log)
    with pytest.raises(O.OplogError) as e:
        undo(log, hermes(), op_id=hu["op_id"])
    assert e.value.as_dict()["code"] == "undo_blocked" and e.value.extra["op_ids"] == [hu["op_id"]]
    assert h(log) == before
    with pytest.raises(O.OplogError) as e:
        undo(log, O.Session(O.Actor("agent", "claude")), op_id=ag["op_id"])  # nor another agent's
    assert e.value.extra["reason"] == "actor"
    undo(log, HUMAN, op_id=ag["op_id"])
    assert "mk1" not in {m["id"] for m in log.doc["markers"]}


def test_undo_is_blocked_by_later_entries_on_the_same_ids():
    log = new_log()
    a = apply(log, hermes(), {"op": "move_clip", "id": "c3", "at": 12 * S})
    b = apply(log, HUMAN, {"op": "set_fade", "id": "c3", "fade_in": S})
    apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "unrelated"})
    before = h(log)
    with pytest.raises(O.OplogError) as e:
        undo(log, hermes(), op_id=a["op_id"])
    assert e.value.code == "undo_blocked"
    assert (e.value.extra["reason"], e.value.extra["op_ids"]) == ("dependents", [b["op_id"]])
    assert h(log) == before
    undo(log, HUMAN, op_id=b["op_id"])
    undo(log, hermes(), op_id=a["op_id"])  # the dependent and its undo cancel out
    assert item(log.doc, "c3") == item(base(), "c3")


def test_a_later_entry_that_refers_to_an_id_blocks_the_undo():
    log = new_log()
    a = apply(log, hermes(), {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S})
    b = apply(log, HUMAN, {"op": "add_text", "dur": S, "text": "t", "style": "pop", "anchor": {"to": "c4", "offset": 0}})
    with pytest.raises(O.OplogError) as e:  # b doesn't change c4, but anchors to it
        undo(log, hermes(), op_id=a["op_id"])
    assert (e.value.extra["reason"], e.value.extra["op_ids"]) == ("dependents", [b["op_id"]])


def test_redo_takes_an_undo_entry():
    log = new_log()
    r = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 12 * S})
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "history_redo", {"op_id": r["op_id"], "client_op_id": "z"})
    assert e.value.extra["rule"] == "not_an_undo"
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, op_id="op999")
    assert e.value.code == "not_found"


# --------------------------------------------------------------------------- persistence and replay


def test_the_log_file_replays_to_the_live_hash(tmp_path):
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    r = apply(log, hermes(4), {"op": "split_clip", "id": "c2", "at": 5 * S}, group_id="g")
    apply(
        log,
        HUMAN,
        {"op": "delete_clip", "id": "c3", "ripple": True},
        {"op": "add_text", "at": 0, "dur": S, "text": "café", "style": "pop"},
    )
    undo(log, HUMAN, group_id="g")
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert lines == log.history_list() and lines[0]["step"] == 4
    assert all(set(e) <= set(O.LINE_FIELDS) | {"step"} for e in lines)
    again = O.Oplog.load(base(), p)
    assert again.doc == log.doc and T.canonical_hash(O.replay(base(), lines)) == h(log)
    first = {
        "base_version": 0,
        "ops": [{"op": "split_clip", "id": "c2", "at": 5 * S}],
        "summary": "edit",
        "group_id": "g",
        "client_op_id": log.history_list()[0]["client_op_id"],
    }
    retry = again.call(hermes(4), "timeline_apply", first)
    assert retry["op_id"] == r["op_id"] and again.version == log.version  # dedupe survives a reload
    with pytest.raises(O.OplogError) as e:  # and so does the mismatch check
        again.call(hermes(4), "timeline_apply", {**first, "summary": "s"})
    assert e.value.extra["rule"] == "client_op_id_mismatch"
    lines[1]["hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        O.replay(base(), lines)


def test_a_failed_write_to_the_log_changes_nothing(tmp_path):
    log = new_log(path=tmp_path / "missing" / "oplog.jsonl")
    before = log.doc
    with pytest.raises(OSError):
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "x"})
    assert log.doc == before and log.history_list() == []


# --------------------------------------------------------------------------- C2: 1,000 seeded random runs


def _random_op(rng: random.Random, d: dict) -> dict:
    clips = [i for i in T.normalize(d)["tracks"][1]["items"] if i["type"] == "clip"]
    texts = [i for t in d["tracks"] if t["role"] == "text" for i in t["items"]]
    c = rng.choice(clips) if clips else None
    k = rng.randrange(12)
    sec = lambda lo, hi: rng.randrange(lo, hi) * S // 4  # noqa: E731
    if k == 0 or c is None:
        return {"op": "insert_clip", "track": "V1", "media": "m1", "src": [sec(0, 40), sec(41, 60)], "at": sec(0, 200)}
    if k == 1:
        return {"op": "move_clip", "id": c["id"], "at": sec(0, 200)}
    if k == 2:
        return {"op": "trim_clip", "id": c["id"], "src_out": c["src"][1] - S // 4, "ripple": rng.random() < 0.5}
    if k == 3:
        return {"op": "split_clip", "id": c["id"], "at": c["at"] + S // 4}
    if k == 4:
        return {"op": "delete_clip", "id": c["id"], "ripple": rng.random() < 0.5}
    if k == 5:
        return {"op": "set_props", "id": c["id"], "props": {"volume": [rng.randrange(1, 4), 2]}}
    if k == 6:
        return {"op": "set_fade", "id": c["id"], "fade_in": sec(0, 3)}
    if k == 7:
        return {"op": "add_text", "dur": S, "text": "t", "style": "pop", "anchor": {"to": c["id"], "offset": 0}}
    if k == 8 and texts:
        return {"op": "set_anchor", "id": rng.choice(texts)["id"], "anchor": None, "at": sec(0, 40)}
    if k == 9:
        return {"op": "add_marker", "at": sec(0, 100), "label": "m"}
    if k == 10 and d["markers"]:
        return {"op": "remove_marker", "id": rng.choice(d["markers"])["id"]}
    return {"op": "add_track", "role": rng.choice(["text", "voice", "music"])}


def test_c2_undo_restores_the_hash_over_1000_seeded_runs():
    applied = undone_groups = 0
    for seed in range(1000):
        rng = random.Random(seed)
        log = new_log()
        hashes = [h(log)]
        for _ in range(rng.randrange(2, 7)):
            ops = [_random_op(rng, log.doc) for _ in range(rng.randrange(1, 3))]
            try:
                apply(log, rng.choice([HUMAN, hermes()]), *ops, **({"group_id": "g"} if rng.random() < 0.3 else {}))
            except O.OplogError as e:
                assert e.code in ("invalid_op", "not_found") and h(log) == hashes[-1]
                continue
            hashes.append(h(log))
            applied += 1
        n = len(log.history_list())
        assert len(hashes) == n + 1
        if n and rng.random() < 0.3 and any(e["group_id"] == "g" for e in log.history_list()):
            # a group undo is one entry
            try:
                undo(log, HUMAN, group_id="g")
                undone_groups += 1
                assert len(log.history_list()) == n + 1
                undo(log, HUMAN, op_id=log.history_list()[-1]["op_id"])  # undo the undo
                assert h(log) == hashes[-1]
            except O.OplogError as e:
                assert e.code == "undo_blocked" and e.extra["reason"] == "dependents"
                blockers = e.extra["blocking_op_ids"]
                seqs = {x["op_id"]: x["seq"] for x in log.history_list()}
                assert blockers and [seqs[b] for b in blockers] == sorted(seqs[b] for b in blockers)
        # undo-all, newest first, as a human: every step lands on the previous hash
        live = [e for e in log.history_list() if not e["undoes"]]
        for e, want in zip(reversed(live), reversed(hashes[:-1]), strict=True):
            undo(log, HUMAN, op_id=e["op_id"])
            assert h(log) == want
        assert h(log) == hashes[0]
        assert T.canonical_hash(O.replay(base(), log.history_list())) == hashes[0]
    assert applied > 2000 and undone_groups > 50


# --------------------------------------------------------------------------- changed_ids follow resolved positions


def _spans_changed(before: dict, after: dict) -> set[str]:
    a, b = T.resolve(before), T.resolve(after)
    return {i for i in a.keys() & b.keys() if a[i] != b[i]}


@pytest.mark.parametrize(
    "op, want",
    [
        ({"op": "move_clip", "id": "c2", "at": 5 * S}, ["c2", "x1"]),
        ({"op": "trim_clip", "id": "c2", "src_in": 11 * S}, ["c2", "x1"]),  # trim-start keeps the rest in place
        ({"op": "trim_clip", "id": "c1", "src_out": 3 * S, "ripple": True}, ["c1", "c2", "c3", "x1"]),  # ripple shift
    ],
)
def test_items_that_move_with_their_anchor_are_in_changed_ids(op, want):
    log = new_log()
    before = log.doc
    r = apply(log, HUMAN, op)
    assert r["changed_ids"] == want == log.history_list()[-1]["changed_ids"]
    assert "x1" in _spans_changed(before, log.doc)
    u = undo(log, HUMAN, op_id=r["op_id"])
    assert u["changed_ids"] == want  # the undo moves them back
    redo = log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": f"r{next(_cid)}"})
    assert redo["changed_ids"] == want


def test_a_later_edit_to_an_item_that_moved_with_its_anchor_blocks_undoing_the_move():
    log = new_log()
    mv = apply(log, HUMAN, {"op": "move_clip", "id": "c2", "at": 5 * S})
    fx = apply(log, HUMAN, {"op": "set_fade", "id": "x1", "fade_in": S // 4})
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, op_id=mv["op_id"])
    assert e.value.extra["reason"] == "dependents" and e.value.extra["blocking_op_ids"] == [fx["op_id"]]


def test_an_unmoved_anchored_item_is_not_in_changed_ids():
    log = new_log()
    r = apply(log, HUMAN, {"op": "trim_clip", "id": "c2", "src_out": 13 * S})  # c2's start stays; x1 stays
    assert r["changed_ids"] == ["c2"]


def test_changed_ids_cover_every_item_whose_resolved_span_changed_over_300_seeded_runs():
    checked = 0
    for seed in range(300):
        rng = random.Random(10_000 + seed)
        log = new_log()
        for _ in range(rng.randrange(2, 6)):
            before = log.doc
            try:
                r = apply(log, rng.choice([HUMAN, hermes()]), *[_random_op(rng, before) for _ in range(rng.randrange(1, 3))])
            except O.OplogError:
                continue
            assert _spans_changed(before, log.doc) <= set(r["changed_ids"])
            checked += 1
        for e in reversed([e for e in log.history_list() if not e["undoes"]]):
            before = log.doc
            u = undo(log, HUMAN, op_id=e["op_id"])
            assert _spans_changed(before, log.doc) <= set(u["changed_ids"])
    assert checked > 500


# --------------------------------------------------------------------------- add_track ids and roles


def test_add_track_never_reuses_a_track_id_that_existed_in_the_log(tmp_path):
    p = tmp_path / "oplog.jsonl"
    n = iter(range(1, 10**9))
    log = O.Oplog(base(), path=p, new_op_id=lambda: f"op{next(n)}")
    a = apply(log, HUMAN, {"op": "add_track", "role": "music"})
    assert "A3" in a["changed_ids"] and log.history_list()[-1]["ops"][0]["id"] == "A3"  # picked id is logged
    apply(log, HUMAN, {"op": "remove_track", "id": "A3"})
    b = apply(log, HUMAN, {"op": "add_track", "role": "music"})
    assert "A4" in b["changed_ids"] and "A3" not in b["changed_ids"]
    assert log.history_list()[-1]["ops"][0]["id"] == "A4"
    apply(log, HUMAN, {"op": "remove_track", "id": "A4"})
    again = O.Oplog.load(base(), p, new_op_id=lambda: f"op{next(n)}")
    assert T.canonical_hash(again.doc) == h(log)
    c = apply(again, HUMAN, {"op": "add_track", "role": "voice"})
    assert "A5" in c["changed_ids"]  # A3 and A4 are retired after load too
    assert again.history_list()[-1]["ops"][0]["id"] == "A5"


def test_add_track_takes_the_first_free_id_never_seen():
    log = new_log()
    apply(log, HUMAN, {"op": "remove_track", "id": "A1"})  # A1 existed: retired, not handed out
    r = apply(log, HUMAN, {"op": "add_track", "role": "voice"})
    assert "A3" in r["changed_ids"]


@pytest.mark.parametrize("role", [[], {}, ["main"], 1, None, True])
def test_add_track_with_a_non_string_role_is_bad_track_role(role):
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "add_track", "role": role})
    x = e.value.extra
    assert e.value.code == "invalid_op" and x["rule"] == "bad_track_role" and x["path"] == "/ops/0/role"
    assert log.version == 0 and log.history_list() == []


# --------------------------------------------------------------------------- undo_blocked shapes


def test_inverse_invalid_carries_the_target_op_ids_path_and_id():
    log = new_log()
    mv = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 20 * S})
    apply(log, HUMAN, {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, 4 * S], "at": 10 * S})  # not a dependent
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, op_id=mv["op_id"])  # c3 back to 10 s would overlap the new clip
    x = e.value.extra
    assert e.value.code == "undo_blocked" and x["reason"] == "inverse_invalid"
    assert x["op_ids"] == [mv["op_id"]] and x["path"] == "/op_id" and x["id"] == mv["op_id"]
    assert x["rule"] == "overlap" and x["problems"] and "blocking_op_ids" not in x
    assert len(log.history_list()) == 2


def test_inverse_invalid_on_a_group_lists_its_entries_by_seq():
    log = new_log()
    a = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 20 * S}, group_id="g")
    b = apply(log, HUMAN, {"op": "add_marker", "at": S, "label": "x"}, group_id="g")
    apply(log, HUMAN, {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, 4 * S], "at": 10 * S})
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, group_id="g")
    x = e.value.extra
    assert x["reason"] == "inverse_invalid" and x["op_ids"] == [a["op_id"], b["op_id"]]
    assert x["path"] == "/group_id" and x["id"] == "g"


def test_actor_and_dependents_blocks_carry_path_and_id_too():
    log = new_log()
    r = apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 11 * S})
    with pytest.raises(O.OplogError) as e:
        undo(log, hermes(), op_id=r["op_id"])
    assert e.value.extra["reason"] == "actor" and e.value.extra["path"] == "/op_id" and e.value.extra["id"] == r["op_id"]
    apply(log, HUMAN, {"op": "set_fade", "id": "c3", "fade_in": S // 4})
    with pytest.raises(O.OplogError) as e:
        undo(log, HUMAN, op_id=r["op_id"])
    assert e.value.extra["reason"] == "dependents" and e.value.extra["path"] == "/op_id" and e.value.extra["id"] == r["op_id"]


@pytest.mark.parametrize(
    "op, path, missing",
    [
        ({"op": "move_clip", "id": "nope", "at": 0}, "/ops/1/id", "nope"),
        ({"op": "add_text", "track": "T9", "at": 0, "dur": S, "text": "a", "style": "pop"}, "/ops/1/track", "T9"),
        ({"op": "remove_marker", "id": "k9"}, "/ops/1/id", "k9"),
        ({"op": "remove_track", "id": "A9"}, "/ops/1/id", "A9"),
    ],
)
def test_an_op_level_not_found_carries_the_missing_id(op, path, missing):
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "set_fade", "id": "c1", "fade_in": 0}, op)
    x = e.value.extra
    assert e.value.code == "not_found" and x["rule"] == "not_found" and x["op_index"] == 1
    assert x["path"] == path and x["id"] == missing and log.history_list() == []


# --------------------------------------------------------------------------- ids that existed only inside a batch (Prove F1)


def _picked(log: O.Oplog, k: int = 0) -> str:
    return log.history_list()[-1]["ops"][k]["id"]


@pytest.mark.parametrize(
    "make, remove, again",
    [
        (
            {"op": "add_marker", "at": 0, "label": "t"},
            lambda i: {"op": "remove_marker", "id": i},
            {"op": "add_marker", "at": S, "label": "u"},
        ),
        (
            {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S},
            lambda i: {"op": "delete_clip", "id": i},
            {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 30 * S},
        ),
        ({"op": "add_track", "role": "music"}, lambda i: {"op": "remove_track", "id": i}, {"op": "add_track", "role": "music"}),
    ],
)
def test_an_id_created_and_removed_in_one_batch_is_never_handed_out_again(tmp_path, make, remove, again):
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    probe = new_log()  # what the first op alone would pick
    apply(probe, HUMAN, make)
    gone = _picked(probe)
    apply(log, HUMAN, make, remove(gone))
    assert log.history_list()[-1]["ops"][0]["id"] == gone and gone not in T._all_ids(log.doc)
    lines = log.history_list()
    p2 = tmp_path / "after-batch.jsonl"
    p2.write_bytes(p.read_bytes())
    apply(log, HUMAN, again)
    assert _picked(log) != gone
    loaded = O.Oplog.load(base(), p2)  # after load: the same
    apply(loaded, HUMAN, again)
    assert _picked(loaded) != gone
    # replay retires the same way (it shares _retire with _commit and load) and reproduces the hash
    assert T.canonical_hash(O.replay(base(), lines)) == T.canonical_hash(O.replay(base(), loaded.history_list()[:1]))


# --------------------------------------------------------------------------- id types are checked up front (Prove F2)

_REF_CASES = [
    ({"op": "move_clip", "id": "@", "at": 0}, "/ops/0/id"),
    ({"op": "delete_clip", "id": "@"}, "/ops/0/id"),
    ({"op": "set_fade", "id": "@", "fade_in": 0}, "/ops/0/id"),
    ({"op": "set_props", "id": "@", "props": {}}, "/ops/0/id"),
    ({"op": "trim_clip", "id": "@", "dur": S}, "/ops/0/id"),
    ({"op": "split_clip", "id": "@", "at": 5 * S}, "/ops/0/id"),
    ({"op": "split_clip", "id": "c2", "at": 5 * S, "ids": ["n1", "@"]}, "/ops/0/ids/1"),
    ({"op": "set_anchor", "id": "@", "anchor": None, "at": 0}, "/ops/0/id"),
    ({"op": "set_anchor", "id": "x1", "anchor": {"to": "@", "offset": 0}}, "/ops/0/anchor/to"),
    ({"op": "remove_marker", "id": "@"}, "/ops/0/id"),
    ({"op": "remove_track", "id": "@"}, "/ops/0/id"),
    ({"op": "insert_clip", "track": "@", "media": "m1", "src": [0, S], "at": 20 * S}, "/ops/0/track"),
    ({"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S, "id": "@"}, "/ops/0/id"),
    ({"op": "add_text", "track": "@", "at": 0, "dur": S, "text": "a", "style": "pop"}, "/ops/0/track"),
    ({"op": "add_text", "dur": S, "text": "a", "style": "pop", "anchor": {"to": "@", "offset": 0}}, "/ops/0/anchor/to"),
    ({"op": "add_text", "at": 0, "dur": S, "text": "a", "style": "pop", "id": "@"}, "/ops/0/id"),
    ({"op": "add_transition", "between": ["c1", "@"], "dur": S // 2}, "/ops/0/between/1"),
    ({"op": "add_transition", "between": ["c1", "c2"], "dur": S // 2, "track": "@"}, "/ops/0/track"),
    ({"op": "add_marker", "at": 0, "label": "m", "id": "@"}, "/ops/0/id"),
    ({"op": "add_track", "role": "voice", "id": "@"}, "/ops/0/id"),
]


def _put(op: object, v: object) -> object:
    if op == "@":
        return v
    if isinstance(op, dict):
        return {k: _put(x, v) for k, x in op.items()}
    if isinstance(op, list):
        return [_put(x, v) for x in op]
    return op


@pytest.mark.parametrize("bad", [7, None, [], {}, True], ids=["int", "None", "list", "dict", "bool"])
@pytest.mark.parametrize("op, path", _REF_CASES, ids=[f"{c[0]['op']}{c[1]}" for c in _REF_CASES])
def test_a_non_string_id_is_bad_arg_at_its_path_not_not_found(op, path, bad):
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, _put(op, bad))
    x = e.value.extra
    assert (e.value.code, x["rule"], x["path"], x["op_index"]) == ("invalid_op", "bad_arg", path, 0)
    assert log.history_list() == [] and log.version == 0


# --------------------------------------------------------------------------- id_reused (Ada)


def _reused(log: O.Oplog, *ops: dict, path: str) -> None:
    v, n = log.version, len(log.history_list())
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, *ops)
    assert (e.value.code, e.value.extra["rule"], e.value.extra["path"]) == ("invalid_op", "id_reused", path)
    assert log.version == v and len(log.history_list()) == n


def test_an_explicit_retired_marker_clip_or_track_id_is_id_reused():
    log = new_log()
    apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "t"})
    mk = _picked(log)
    apply(log, HUMAN, {"op": "remove_marker", "id": mk})
    _reused(log, {"op": "add_marker", "at": 0, "label": "t", "id": mk}, path="/ops/0/id")
    apply(log, HUMAN, {"op": "delete_clip", "id": "c3"})
    _reused(log, {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S, "id": "c3"}, path="/ops/0/id")
    _reused(log, {"op": "split_clip", "id": "c2", "at": 5 * S, "ids": ["n1", "c3"]}, path="/ops/0/ids/1")
    apply(log, HUMAN, {"op": "remove_track", "id": "A1"})
    _reused(log, {"op": "set_fade", "id": "c1", "fade_in": 0}, {"op": "add_track", "role": "voice", "id": "A1"}, path="/ops/1/id")
    # an id that's in the doc now is still duplicate_id
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "t", "id": "k1"})
    assert e.value.extra["rule"] == "duplicate_id"


def test_an_id_from_earlier_in_the_same_batch_is_id_reused():
    log = new_log()
    _reused(
        log,
        {"op": "add_marker", "at": 0, "label": "a", "id": "z1"},
        {"op": "remove_marker", "id": "z1"},
        {"op": "add_marker", "at": 0, "label": "b", "id": "z1"},
        path="/ops/2/id",
    )
    probe = new_log()
    apply(probe, HUMAN, {"op": "add_marker", "at": 0, "label": "a"})
    handed = _picked(probe)  # handed out by the engine, then removed, in one batch
    _reused(
        log,
        {"op": "add_marker", "at": 0, "label": "a"},
        {"op": "remove_marker", "id": handed},
        {"op": "add_marker", "at": 0, "label": "b", "id": handed},
        path="/ops/2/id",
    )


def test_id_reused_holds_after_load_and_undo_redo_still_restore_old_ids(tmp_path):
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "a", "id": "z1"}, {"op": "remove_marker", "id": "z1"})
    d = apply(log, HUMAN, {"op": "delete_clip", "id": "c3"})
    u = undo(log, HUMAN, op_id=d["op_id"])  # an inverse restores c3: allowed
    log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": "redo-1"})
    assert "c3" not in ids(log.doc)
    again = O.Oplog.load(base(), p)
    assert T.canonical_hash(O.replay(base(), log.history_list())) == h(log) == h(again)
    _reused(again, {"op": "add_marker", "at": 0, "label": "b", "id": "z1"}, path="/ops/0/id")
    _reused(again, {"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S, "id": "c3"}, path="/ops/0/id")


# --------------------------------------------------------------------------- client_op_id_mismatch (Ada)


def _mismatch(log: O.Oplog, session: O.Session, tool: str, args: dict) -> None:
    v, n = log.version, len(log.history_list())
    with pytest.raises(O.OplogError) as e:
        log.call(session, tool, args)
    assert (e.value.code, e.value.extra["rule"], e.value.extra["path"]) == (
        "invalid_op",
        "client_op_id_mismatch",
        "/client_op_id",
    )
    assert log.version == v and len(log.history_list()) == n


APPLY = {
    "base_version": 0,
    "ops": [{"op": "add_marker", "at": 0, "label": "x"}],
    "summary": "s",
    "client_op_id": "same",
    "group_id": "g",
}


@pytest.mark.parametrize(
    "change",
    [
        {"ops": [{"op": "add_marker", "at": S, "label": "x"}]},
        {"ops": [{"op": "add_marker", "at": 0, "label": "x"}, {"op": "set_fade", "id": "c1", "fade_in": 0}]},
        {"ops": [{"op": "add_marker", "at": 0, "label": "x", "id": "z9"}]},
        {"summary": "other"},
        {"group_id": "h"},
        {"base_version": 1},
    ],
    ids=["op-arg", "extra-op", "other-explicit-id", "summary", "group", "base_version"],
)
def test_a_retry_with_different_args_is_client_op_id_mismatch(change):
    log = new_log()
    log.call(HUMAN, "timeline_apply", APPLY)
    _mismatch(log, HUMAN, "timeline_apply", {**APPLY, **change})


def test_an_identical_retry_still_returns_the_cached_result_even_with_forged_fields():
    log = new_log()
    r = log.call(hermes(2), "timeline_apply", APPLY)
    forged = {
        **APPLY,
        "actor": {"kind": "human", "id": "pablo"},
        "step": 9,
        "ops": [{**APPLY["ops"][0], "step": 1, "actor": "x"}],
    }
    again = log.call(hermes(2), "timeline_apply", forged)
    assert again["op_id"] == r["op_id"] and len(log.history_list()) == 1
    picked = {**APPLY, "ops": [{**APPLY["ops"][0], "id": _picked(log)}]}  # naming the id the engine picked
    assert log.call(hermes(2), "timeline_apply", picked)["op_id"] == r["op_id"]


def test_undo_or_redo_reusing_an_apply_client_op_id_is_a_mismatch_and_vice_versa():
    log = new_log()
    a = log.call(HUMAN, "timeline_apply", APPLY)
    _mismatch(log, HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "same"})
    _mismatch(log, HUMAN, "history_redo", {"op_id": a["op_id"], "client_op_id": "same"})
    u = log.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "u1"})
    assert log.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "u1"})["op_id"] == u["op_id"]
    _mismatch(log, HUMAN, "timeline_apply", {**APPLY, "base_version": log.version, "client_op_id": "u1"})
    _mismatch(log, HUMAN, "history_undo", {"group_id": "g", "client_op_id": "u1"})
    _mismatch(log, HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "u1", "summary": "other"})
    _mismatch(log, HUMAN, "history_redo", {"op_id": a["op_id"], "client_op_id": "u1"})
    r = log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": "r1"})
    assert log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": "r1", "step": 3})["op_id"] == r["op_id"]
    _mismatch(log, HUMAN, "history_undo", {"op_id": u["op_id"], "client_op_id": "r1"})  # undo vs redo: other summary


def test_the_mismatch_check_survives_load(tmp_path):
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    a = log.call(
        HUMAN,
        "timeline_apply",
        {**APPLY, "ops": [{"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S}]},
    )
    u = log.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "u1"})
    again = O.Oplog.load(base(), p)
    first = {**APPLY, "ops": [{"op": "insert_clip", "track": "V1", "media": "m1", "src": [0, S], "at": 20 * S}]}
    assert again.call(HUMAN, "timeline_apply", first)["op_id"] == a["op_id"]
    assert again.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "u1"})["op_id"] == u["op_id"]
    _mismatch(again, HUMAN, "timeline_apply", {**first, "summary": "t"})
    _mismatch(again, HUMAN, "timeline_apply", {**APPLY})  # other ops
    _mismatch(again, HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": "same"})
    _mismatch(again, HUMAN, "history_undo", {"group_id": "g", "client_op_id": "u1"})
    assert T.canonical_hash(O.replay(base(), again.history_list())) == h(again)


# --------------------------------------------------------------------------- junk retries on a cached key (Wire)


def _cached() -> tuple[O.Oplog, dict, dict]:
    log = new_log()
    a = log.call(HUMAN, "timeline_apply", APPLY)
    u = log.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "u1"})
    return log, a, u


def _bad_arg(log: O.Oplog, tool: str, args: dict, path: str) -> None:
    v, n = log.version, len(log.history_list())
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, tool, args)
    assert (e.value.code, e.value.extra["rule"], e.value.extra["path"]) == ("invalid_op", "bad_arg", path)
    assert log.version == v and len(log.history_list()) == n


@pytest.mark.parametrize(
    "ops, path",
    [
        (5, "/ops"),
        (None, "/ops"),
        ("x", "/ops"),
        ({}, "/ops"),
        ([], "/ops"),
        ([5], "/ops/0"),
        ([None], "/ops/0"),
        ([{"op": "add_marker", "at": 0, "label": "x"}, "y"], "/ops/1"),
        ([{"op": 3}], "/ops/0"),
        ([{}], "/ops/0"),
    ],
    ids=["int", "None", "str", "dict", "empty", "[5]", "[None]", "[op,str]", "op-not-str", "[{}]"],
)
def test_a_cached_key_with_junk_ops_is_bad_arg_like_a_fresh_call(ops, path):
    log, _, _ = _cached()
    _bad_arg(log, "timeline_apply", {**APPLY, "ops": ops}, path)  # cached key "same"
    _bad_arg(log, "timeline_apply", {**APPLY, "ops": ops, "client_op_id": "fresh"}, path)


@pytest.mark.parametrize(
    "tool, change, path",
    [
        ("timeline_apply", {"base_version": "0"}, "/base_version"),
        ("timeline_apply", {"base_version": True}, "/base_version"),
        ("timeline_apply", {"base_version": None}, "/base_version"),
        ("timeline_apply", {"base_version": -1}, "/base_version"),
        ("timeline_apply", {"base_version": 1.5}, "/base_version"),
        ("timeline_apply", {"summary": 5}, "/summary"),
        ("timeline_apply", {"summary": None}, "/summary"),
        ("timeline_apply", {"group_id": 7}, "/group_id"),
        ("timeline_apply", {"group_id": []}, "/group_id"),
        ("history_undo", {"op_id": 7}, "/op_id"),
        ("history_undo", {"op_id": None}, "/op_id"),
        ("history_undo", {"op_id": []}, "/op_id"),
        ("history_undo", {"op_id": {}}, "/op_id"),
        ("history_undo", {"group_id": None}, "/group_id"),
        ("history_undo", {"group_id": 7}, "/group_id"),
        ("history_undo", {"summary": 5}, "/summary"),
        ("history_undo", {"summary": ["s"]}, "/summary"),
        ("history_undo", {"base_version": "1"}, "/base_version"),
        ("history_undo", {"base_version": False}, "/base_version"),
        ("history_undo", {"base_version": None}, "/base_version"),
        ("history_redo", {"op_id": 7}, "/op_id"),
        ("history_redo", {"op_id": None}, "/op_id"),
        ("history_redo", {"summary": {}}, "/summary"),
        ("history_redo", {"base_version": 2.0}, "/base_version"),
    ],
)
def test_wrong_typed_fields_on_a_cached_key_are_bad_arg(tool, change, path):
    log, a, u = _cached()
    if tool == "timeline_apply":
        base_args = dict(APPLY)
    else:
        base_args = {"op_id": a["op_id"] if tool == "history_undo" else u["op_id"], "client_op_id": "u1"}
        if "group_id" in change:
            base_args.pop("op_id")
    for key in (base_args["client_op_id"], "same", "u1", "fresh"):  # cached under each tool, and fresh
        _bad_arg(log, tool, {**base_args, **change, "client_op_id": key}, path)


def test_an_undo_with_both_or_neither_target_is_bad_arg_on_a_cached_key():
    log, a, _ = _cached()
    _bad_arg(log, "history_undo", {"client_op_id": "u1"}, "")
    _bad_arg(log, "history_undo", {"op_id": a["op_id"], "group_id": "g", "client_op_id": "u1"}, "")
    _bad_arg(log, "history_redo", {"group_id": "g", "client_op_id": "u1"}, "")


_JUNK = [
    5,
    None,
    "x",
    {},
    [],
    [5],
    [None],
    True,
    -1,
    1.5,
    "c1",
    {"op": 3},
    [{"op": "move_clip"}],
    "Ω",
    10**30,
    [{"op": "add_marker", "at": 0, "label": "x"}],
    "op1",
    "g",
    0,
    "s",
]


def test_junk_args_on_a_cached_key_never_crash_over_3000_seeded_runs():
    log, a, u = _cached()
    v, n = log.version, len(log.history_list())
    good = {  # the cached calls; each run mutates one to three fields with junk
        "timeline_apply": {k: v for k, v in APPLY.items() if k != "client_op_id"},
        "history_undo": {"op_id": a["op_id"]},
        "history_redo": {"op_id": u["op_id"]},
    }
    fields = ["base_version", "ops", "summary", "group_id", "op_id", "project_id", "junk_key"]
    seen: dict[str, int] = {}
    for seed in range(3000):
        rng = random.Random(seed)
        tool = rng.choice(list(good))
        args = dict(good[tool])
        for k in rng.sample(fields, rng.randrange(1, 4)):
            if rng.random() < 0.15:
                args.pop(k, None)
            else:
                args[k] = rng.choice(_JUNK + [a["op_id"], u["op_id"]])
        args["client_op_id"] = rng.choice(["same", "u1"])
        try:
            r = log.call(HUMAN, tool, args)
            assert r["op_id"] in (a["op_id"], u["op_id"])  # only ever the cached result
            out = "cached"
        except O.OplogError as e:
            out = f"{e.code}/{e.extra.get('rule')}"
        seen[out] = seen.get(out, 0) + 1
        assert log.version == v and len(log.history_list()) == n
    assert {"invalid_op/bad_arg", "invalid_op/client_op_id_mismatch", "invalid_op/unknown_arg"} <= set(seen)


@pytest.mark.parametrize("ids, path", [(["n1", "c1"], "/ops/0/ids/1"), (["c1", "n1"], "/ops/0/ids/0")])
def test_split_duplicate_piece_id_points_at_that_entry(ids, path):
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "split_clip", "id": "c2", "at": 5 * S, "ids": ids})
    assert (e.value.extra["rule"], e.value.extra["path"]) == ("duplicate_id", path)


# --------------------------------------------------------------------------- Prove C2 retry/target checks (R1-R4)


@pytest.mark.parametrize("ops", [5, None, 1.5, True, -1], ids=["5", "null", "1.5", "True", "-1"])
def test_r1_scalar_ops_on_a_cached_key_are_bad_arg(ops):
    log, _, _ = _cached()
    _bad_arg(log, "timeline_apply", {**APPLY, "ops": ops}, "/ops")


@pytest.mark.parametrize("n", [0, O.MAX_OPS + 1])
def test_the_ops_length_cap_runs_before_dedupe_and_any_replay(monkeypatch, n):
    log, _, _ = _cached()
    ops = [{"op": "add_marker", "at": 0, "label": "x"}] * n

    def no_replay(*a, **k):
        raise AssertionError("the log was replayed")

    monkeypatch.setattr(O.Oplog, "_run", no_replay)
    for key in ("same", "fresh"):  # cached and fresh: the same invalid_op
        _bad_arg(log, "timeline_apply", {**APPLY, "ops": ops, "client_op_id": key}, "/ops")


def test_r2_redo_reusing_an_undo_key_with_the_same_summary_and_op_id_is_a_mismatch(tmp_path):
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    a = log.call(HUMAN, "timeline_apply", APPLY)
    u = log.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "k", "summary": "S"})
    _mismatch(log, HUMAN, "history_redo", {"op_id": a["op_id"], "client_op_id": "k", "summary": "S"})
    assert log.call(HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "k", "summary": "S"})["op_id"] == u["op_id"]
    # an undo of an undo entry vs a redo of it, same explicit summary: told apart by the tool
    uu = log.call(HUMAN, "history_undo", {"op_id": u["op_id"], "client_op_id": "k2", "summary": "S2"})
    _mismatch(log, HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": "k2", "summary": "S2"})
    assert log.call(HUMAN, "history_undo", {"op_id": u["op_id"], "client_op_id": "k2", "summary": "S2"})["op_id"] == uu["op_id"]
    again = O.Oplog.load(base(), p)  # after load, the undo of a normal entry is still not a redo
    _mismatch(again, HUMAN, "history_redo", {"op_id": a["op_id"], "client_op_id": "k", "summary": "S"})
    _mismatch(again, HUMAN, "timeline_apply", {**APPLY, "client_op_id": "k"})


def test_r2_an_apply_key_reused_by_undo_with_a_summary_is_a_mismatch():
    log = new_log()
    a = log.call(HUMAN, "timeline_apply", APPLY)
    _mismatch(log, HUMAN, "history_undo", {"op_id": a["op_id"], "client_op_id": "same", "summary": "s"})


@pytest.mark.parametrize(
    "tool, args, path",
    [
        ("history_undo", {"op_id": None}, "/op_id"),
        ("history_redo", {"op_id": None}, "/op_id"),
        ("history_undo", {"group_id": None}, "/group_id"),
        ("history_redo", {"group_id": None}, "/group_id"),
        ("history_undo", {"op_id": "@a", "group_id": None}, "/group_id"),
        ("history_redo", {"op_id": "@u", "group_id": None}, "/group_id"),
        ("history_undo", {"op_id": None, "group_id": "g"}, "/op_id"),
        ("history_undo", {}, ""),
        ("history_redo", {}, ""),
        ("history_undo", {"op_id": "@a", "group_id": "g"}, ""),
    ],
)
def test_r3_null_or_missing_undo_redo_targets_are_bad_arg_before_dedupe(tool, args, path):
    log, a, u = _cached()
    args = {k: {"@a": a["op_id"], "@u": u["op_id"]}.get(v, v) for k, v in args.items()}
    for key in ("u1", "same", "fresh"):  # the cached undo key, the cached apply key, a fresh key
        _bad_arg(log, tool, {**args, "client_op_id": key}, path)


def test_r4_undo_with_a_null_group_is_bad_arg_and_undoes_nothing(monkeypatch):
    log = new_log()
    apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "A"})
    apply(log, HUMAN, {"op": "add_marker", "at": S, "label": "B"})
    apply(log, HUMAN, {"op": "add_marker", "at": 2 * S, "label": "C"}, group_id="g1")
    before = h(log)
    _bad_arg(log, "history_undo", {"group_id": None, "client_op_id": "gnull"}, "/group_id")
    assert h(log) == before and len(log.history_list()) == 3 and all(not e["undoes"] for e in log.history_list())
    # with the shape check out of the way, the group match itself still never takes null as "ungrouped"
    monkeypatch.setattr(O.Oplog, "_undo_shape", staticmethod(lambda args, redo: None))
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "history_undo", {"group_id": None, "client_op_id": "gnull2"})
    assert e.value.code == "not_found" and h(log) == before and len(log.history_list()) == 3


# --------------------------------------------------------------------------- ripple trim with crossfades (Glyph/Ada: the crossfade stays with the cut)

H = S // 2  # half a second


def xfade_log(*, d12: int | None = H, d23: int | None = None, **kw) -> O.Oplog:
    """The base doc with c2 pulled back under c1 by d12 (crossfade tr c1->c2) and, optionally,
    c3 pulled under c2 by d23 (crossfade c2->c3). c2 = [4S-d12, 8S-d12), c3 after it."""
    log = new_log(**kw)
    ops: list[dict] = []
    c2_at = 4 * S - (d12 or 0)
    if d12:
        ops += [
            {"op": "move_clip", "id": "c2", "at": c2_at},
            {"op": "add_transition", "between": ["c1", "c2"], "dur": d12, "id": "t12"},
        ]
    if d23:
        ops += [
            {"op": "move_clip", "id": "c3", "at": c2_at + 4 * S - d23},
            {"op": "add_transition", "between": ["c2", "c3"], "dur": d23, "id": "t23"},
        ]
    if ops:
        apply(log, HUMAN, *ops)
    return log


def spans(log: O.Oplog) -> dict[str, tuple[int, int]]:
    return T.resolve(log.doc)


def _trim_roundtrip(log: O.Oplog, op: dict) -> dict:
    """Apply a trim; changed_ids covers every moved span on apply, undo and redo; hashes round-trip."""
    h0, s0 = h(log), spans(log)
    r = apply(log, HUMAN, op)
    h1, s1 = h(log), spans(log)
    moved = {i for i in s0.keys() & s1.keys() if s0[i] != s1[i]}
    assert moved <= set(r["changed_ids"])
    u = undo(log, HUMAN, op_id=r["op_id"])
    assert h(log) == h0 and spans(log) == s0 and u["changed_ids"] == r["changed_ids"]
    rd = log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": f"r{next(_cid)}"})
    assert h(log) == h1 and rd["changed_ids"] == r["changed_ids"]
    return r


def test_ripple_end_trim_with_an_outgoing_crossfade_is_no_longer_rejected():
    # regression: this used to be invalid_op / transition_overlap_mismatch
    log = xfade_log()
    r = apply(log, HUMAN, {"op": "trim_clip", "id": "c1", "src_out": 3 * S, "ripple": True})
    assert r["ok"] and item(log.doc, "t12")["between"] == ["c1", "c2"] and item(log.doc, "t12")["dur"] == H


@pytest.mark.parametrize(
    "src_out, delta", [(3 * S, -S), (5 * S, S), (4 * S - S // 4, -S // 4)], ids=["shorter", "longer", "quarter"]
)
def test_ripple_end_trim_moves_the_crossfade_with_the_cut(src_out, delta):
    log = xfade_log()
    s0 = spans(log)
    r = _trim_roundtrip(log, {"op": "trim_clip", "id": "c1", "src_out": src_out, "ripple": True})
    s1 = spans(log)
    assert s1["c1"] == (0, s0["c1"][1] + delta)  # the start stays
    assert s1["t12"] == (s1["c1"][1] - H, s1["c1"][1])  # same dur, at the new cut, same pair
    for i in ("c2", "t12", "c3", "x1"):  # the next clip, the crossfade, later items and x1 (anchored to c2)
        assert s1[i] == (s0[i][0] + delta, s0[i][1] + delta)
    assert s1["mu1"] == s0["mu1"] and log.doc["markers"] == base()["markers"]  # anchored to c1 (start kept); markers stay
    assert r["changed_ids"] == ["c1", "c2", "c3", "t12", "x1"]


def test_ripple_start_trim_with_an_outgoing_crossfade_moves_it_too():
    log = xfade_log()
    s0 = spans(log)
    _trim_roundtrip(log, {"op": "trim_clip", "id": "c1", "src_in": S, "ripple": True})
    s1 = spans(log)
    assert s1["c1"] == (0, 3 * S) and s1["t12"] == (3 * S - H, 3 * S) and s1["c2"][0] == s0["c2"][0] - S


def test_ripple_start_trim_with_an_incoming_crossfade_keeps_it_at_the_clip_start():
    log = xfade_log()
    s0 = spans(log)
    r = _trim_roundtrip(log, {"op": "trim_clip", "id": "c2", "src_in": 11 * S, "ripple": True})
    s1 = spans(log)
    assert s1["t12"] == s0["t12"] and s1["c1"] == s0["c1"]  # the incoming crossfade doesn't move
    assert s1["c2"] == (s0["c2"][0], s0["c2"][1] - S) and s1["c3"] == (s0["c3"][0] - S, s0["c3"][1] - S)
    assert "t12" not in r["changed_ids"] and r["changed_ids"] == ["c2", "c3"]


def test_ripple_trim_of_a_clip_with_both_crossfades():
    log = xfade_log(d23=H)
    s0 = spans(log)
    _trim_roundtrip(log, {"op": "trim_clip", "id": "c2", "src_out": 13 * S, "ripple": True})
    s1 = spans(log)
    assert s1["t12"] == s0["t12"] and s1["t23"] == (s1["c2"][1] - H, s1["c2"][1])
    assert s1["c3"][0] == s0["c3"][0] - S


@pytest.mark.parametrize(
    "d23, op, xid",
    [
        # one crossfade doesn't fit on its own: that crossfade
        (None, {"op": "trim_clip", "id": "c1", "src_out": S // 4, "ripple": True}, "t12"),  # out xfade H
        (None, {"op": "trim_clip", "id": "c1", "src_in": 4 * S - S // 4, "ripple": True}, "t12"),
        (None, {"op": "trim_clip", "id": "c1", "src_out": H, "ripple": True}, "t12"),  # exactly the out xfade
        (None, {"op": "trim_clip", "id": "c2", "src_out": 10 * S + H, "ripple": True}, "t12"),  # exactly the in xfade
        # each fits alone, not both together (in + out = S, c2 = 3/4 s): the outgoing one
        (H, {"op": "trim_clip", "id": "c2", "src_out": 10 * S + 3 * S // 4, "ripple": True}, "t23"),
        # neither fits alone (c2 = 1/4 s): the outgoing one
        (H, {"op": "trim_clip", "id": "c2", "src_out": 10 * S + S // 4, "ripple": True}, "t23"),
    ],
)
@pytest.mark.parametrize("k", [0, 1])
def test_a_ripple_trim_shorter_than_its_crossfades_need_is_transition_too_long(d23, op, xid, k):
    log = xfade_log(d23=d23)
    v, h0 = log.version, h(log)
    ops = [{"op": "set_fade", "id": "c3", "fade_in": 0}] * k + [op]
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, *ops)
    x = e.value.extra
    assert (e.value.code, x["rule"], x["path"], x["id"], x["op_index"]) == (
        "invalid_op",
        "transition_too_long",
        f"/ops/{k}",
        xid,
        k,
    )
    assert log.version == v and h(log) == h0 and item(log.doc, xid)["type"] == "transition"


def test_a_ripple_trim_exactly_as_long_as_both_crossfades_is_allowed():
    log = xfade_log(d23=H)
    _trim_roundtrip(log, {"op": "trim_clip", "id": "c2", "src_out": 11 * S, "ripple": True})  # c2 = 1 s = H + H
    s1 = spans(log)
    assert s1["c1"][1] == s1["c3"][0]  # c1 and c3 abut, no overlap


def test_a_non_ripple_end_trim_with_an_outgoing_crossfade_is_still_rejected():
    log = xfade_log()
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "trim_clip", "id": "c1", "src_out": 3 * S})
    assert e.value.extra["rule"] == "transition_overlap_mismatch"


def test_crossfade_ripple_trims_survive_load_and_replay(tmp_path):
    p = tmp_path / "oplog.jsonl"
    log = xfade_log(d23=H, path=p)
    a = apply(log, HUMAN, {"op": "trim_clip", "id": "c1", "src_out": 3 * S, "ripple": True})
    apply(log, HUMAN, {"op": "trim_clip", "id": "c2", "src_in": 11 * S, "ripple": True})
    u = undo(log, HUMAN, op_id=log.history_list()[-1]["op_id"])
    log.call(HUMAN, "history_redo", {"op_id": u["op_id"], "client_op_id": f"r{next(_cid)}"})
    again = O.Oplog.load(base(), p)
    assert h(again) == h(log) and T.canonical_hash(O.replay(base(), log.history_list())) == h(log)
    assert again.history_list()[1]["changed_ids"] == a["changed_ids"]


def test_random_ripple_trims_with_crossfades_cover_changed_ids_and_round_trip_over_300_seeds():
    done = rejected = 0
    rules: dict[str, int] = {}
    for seed in range(300):
        rng = random.Random(50_000 + seed)
        log = xfade_log(d12=rng.choice([None, S // 4, H, S]), d23=rng.choice([None, S // 4, H]))
        for _ in range(rng.randrange(1, 4)):
            c = rng.choice([i for i in log.doc["tracks"][1]["items"] if i["type"] == "clip"])
            i0, o0 = c["src"]
            k = rng.choice(["src_in", "src_out"])
            step = rng.randrange(-12, 13) * S // 4
            v = i0 + step if k == "src_in" else o0 + step
            if not (0 <= v and (i0 + S // 4 <= v if k == "src_out" else v <= o0 - S // 4)):
                continue
            try:
                _trim_roundtrip(log, {"op": "trim_clip", "id": c["id"], k: v, "ripple": True})
                done += 1
            except O.OplogError as e:
                rules[e.extra["rule"]] = rules.get(e.extra["rule"], 0) + 1
                rejected += 1
    # a too-short trim is refused before validation; a clip that grows into the next one on a
    # crossfade-free join is the usual overlap
    assert set(rules) <= {"transition_too_long", "overlap"}, rules
    assert done > 300 and rules.get("transition_too_long", 0) >= 5


# --------------------------------------------------------------------------- follow-ups after S2


@pytest.mark.parametrize("junk", [7, None, 1.5, (1, 2), True, frozenset({1})], ids=repr)
def test_a_non_string_arg_name_is_unknown_arg_not_a_crash(junk):
    log = new_log()
    op = {"op": "set_fade", "id": "c1", "fade_in": 0, junk: 1}
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, op)
    assert (e.value.code, e.value.extra["rule"], e.value.extra["path"]) == ("invalid_op", "unknown_arg", f"/ops/0/{junk}")
    mixed = {"op": "set_fade", "id": "c1", "fade_in": 0, junk: 1, "zz": 2}  # mixed key types sort without TypeError
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, mixed)
    assert e.value.extra["rule"] == "unknown_arg"
    for tool in ("timeline_apply", "history_undo", "history_redo"):
        with pytest.raises(O.OplogError) as e:
            log.call(
                HUMAN,
                tool,
                {
                    "client_op_id": "k1",
                    junk: 1,
                    "zz": 2,
                    "base_version": 0,
                    "summary": "s",
                    "ops": [{"op": "add_marker", "at": 0, "label": "x"}],
                },
            )
        assert (e.value.code, e.value.extra["rule"]) == ("invalid_op", "unknown_arg")
    assert log.history_list() == [] and log.version == 0


_NFC = "caf\u00e9"
_NFD = "cafe\u0301"


@pytest.mark.parametrize(
    "first, retry",
    [
        (S, float(S)),
        (S, S + 0.0),
        (1, True),
        (0, False),
    ],
    ids=["ticks-vs-float", "ticks-vs-float-sum", "1-vs-true", "0-vs-false"],
)
def test_same_call_does_not_fold_numbers(first, retry):
    log = new_log()
    ok = {**APPLY, "ops": [{"op": "add_marker", "at": first, "label": "x"}]}
    r = log.call(HUMAN, "timeline_apply", ok)
    assert log.call(HUMAN, "timeline_apply", ok)["op_id"] == r["op_id"]
    _mismatch(log, HUMAN, "timeline_apply", {**ok, "ops": [{"op": "add_marker", "at": retry, "label": "x"}]})
    _mismatch(log, HUMAN, "timeline_apply", {**ok, "ops": [{"op": "add_marker", "at": float("nan"), "label": "x"}]})


def test_same_call_does_not_fold_unicode():
    assert _NFC != _NFD and unicodedata.normalize("NFC", _NFD) == _NFC
    log = new_log()
    ok = {**APPLY, "ops": [{"op": "add_marker", "at": 0, "label": _NFC}], "summary": _NFC}
    r = log.call(HUMAN, "timeline_apply", ok)
    assert log.call(HUMAN, "timeline_apply", ok)["op_id"] == r["op_id"]
    _mismatch(log, HUMAN, "timeline_apply", {**ok, "ops": [{"op": "add_marker", "at": 0, "label": _NFD}]})
    _bad_arg(log, "timeline_apply", {**ok, "summary": _NFD}, "/summary")  # shape check first, as for a fresh call
    _bad_arg(log, "timeline_apply", {**ok, "base_version": 0.0}, "/base_version")
    # a fresh call carrying the NFD form is rejected outright, so it can never be logged
    fresh = {**ok, "client_op_id": "fresh", "base_version": log.version, "ops": [{"op": "add_marker", "at": S, "label": _NFD}]}
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "timeline_apply", fresh)
    assert e.value.extra["rule"] == "not_nfc"


def test_the_log_line_and_same_call_share_one_encoding(tmp_path):
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    log.call(HUMAN, "timeline_apply", {**APPLY, "summary": _NFC})
    line = p.read_text(encoding="utf-8").splitlines()[0]
    assert line == O._canon(json.loads(line)) and _NFC in line


def _replayed_states(entries: list[dict]) -> list[tuple[str, set[str]]]:
    """(hash, retired ids) after each prefix of ``entries``, from base, the way load and the old
    same-call check worked them out."""
    then = O.Oplog(base())
    out = [(then.doc["hash"], set(then._retired))]
    for e in entries:
        new, _, _ = then._run(e["ops"], internal=True)
        then._retire(new)
        then._doc = new
        out.append((new["hash"], set(then._retired)))
    return out


def _busy_log(seed: int, n: int, **kw) -> O.Oplog:
    rng = random.Random(seed)
    log = new_log(**kw)
    k = 0
    while len(log.history_list()) < n:
        k += 1
        entries = log.history_list()
        if entries and rng.random() < 0.15:
            try:
                tool = rng.choice(["history_undo", "history_redo"])
                log.call(HUMAN, tool, {"op_id": rng.choice(entries)["op_id"], "client_op_id": f"u{k}"})
            except O.OplogError:
                pass
            continue
        ops = [_random_op(rng, log.doc) for _ in range(rng.randrange(1, 3))]
        try:
            log.call(HUMAN, "timeline_apply", {"base_version": log.version, "ops": ops, "summary": "s", "client_op_id": f"k{k}"})
        except O.OplogError:
            pass
    return log


@pytest.mark.parametrize("seed", range(12))
def test_same_call_checkpoints_equal_a_full_replay(seed, monkeypatch, tmp_path):
    monkeypatch.setattr(O, "CHECKPOINT_EVERY", 3)
    p = tmp_path / "oplog.jsonl"
    log = _busy_log(seed, 30, path=p)
    states = _replayed_states(log.history_list())
    assert sorted(log._checkpoints) == list(range(0, 31, 3))
    for again in (log, O.Oplog.load(base(), p)):
        assert sorted(again._checkpoints) == sorted(log._checkpoints)
        for n, (doc, retired) in again._checkpoints.items():
            assert (doc["hash"], set(retired)) == states[n], n


def test_an_identical_retry_reruns_at_most_one_checkpoint_span(monkeypatch):
    log = new_log()
    for i in range(3 * O.CHECKPOINT_EVERY + 5):
        log.call(
            HUMAN,
            "timeline_apply",
            {**APPLY, "base_version": log.version, "client_op_id": f"k{i}", "ops": [{"op": "add_marker", "at": i, "label": "x"}]},
        )
    runs = []
    real = O.Oplog._run
    monkeypatch.setattr(O.Oplog, "_run", lambda self, *a, **kw: runs.append(1) or real(self, *a, **kw))
    for i, e in enumerate(log.history_list()):
        runs.clear()
        retry = {
            **APPLY,
            "base_version": e["base_version"],
            "client_op_id": f"k{i}",
            "ops": [{"op": "add_marker", "at": i, "label": "x"}],
        }
        assert log.call(HUMAN, "timeline_apply", retry)["op_id"] == e["op_id"]
        assert len(runs) == (e["seq"] - 1) % O.CHECKPOINT_EVERY + 1  # the entries since the checkpoint, plus the retry itself
        _mismatch(log, HUMAN, "timeline_apply", {**retry, "ops": [{"op": "add_marker", "at": i + 1, "label": "x"}]})


def test_retries_at_every_seq_still_match_after_load_with_engine_picked_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "CHECKPOINT_EVERY", 4)
    p = tmp_path / "oplog.jsonl"
    log = new_log(path=p)
    for i in range(11):  # every call lets the engine pick the marker id
        log.call(
            HUMAN,
            "timeline_apply",
            {**APPLY, "base_version": log.version, "client_op_id": f"k{i}", "ops": [{"op": "add_marker", "at": i, "label": "x"}]},
        )
    again = O.Oplog.load(base(), p)
    for i, e in enumerate(log.history_list()):
        omitted = {
            **APPLY,
            "base_version": e["base_version"],
            "client_op_id": f"k{i}",
            "ops": [{"op": "add_marker", "at": i, "label": "x"}],
        }
        named = {**omitted, "ops": [{**omitted["ops"][0], "id": e["ops"][0]["id"]}]}
        for which in (log, again):
            assert which.call(HUMAN, "timeline_apply", omitted)["op_id"] == e["op_id"]
            assert which.call(HUMAN, "timeline_apply", named)["op_id"] == e["op_id"]
            _mismatch(which, HUMAN, "timeline_apply", {**omitted, "ops": [{**omitted["ops"][0], "id": "zz9"}]})


@pytest.mark.parametrize("media", ["nope", "", 7, None, ["m1"], {"id": "m1"}, True, "M1", "m1 "], ids=repr)
def test_insert_clip_with_junk_media_is_unknown_media_at_the_op_arg(media):
    log = new_log()
    ops = [
        {"op": "add_marker", "at": 0, "label": "x"},
        {"op": "insert_clip", "track": "V1", "media": media, "src": [0, S], "at": 20 * S},
    ]
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, *ops)
    x = e.value.extra
    assert (e.value.code, x["rule"], x["path"], x["op_index"]) == ("invalid_op", "unknown_media", "/ops/1/media", 1)
    assert "id" not in x and log.version == 0 and log.history_list() == []
    assert apply(log, HUMAN, {**ops[1], "media": "m1"})["new_version"] == 1  # a real media id still works


def test_timeline_apply_with_a_null_group_id_is_bad_arg_and_omitting_it_is_no_group():
    log = new_log()
    _bad_arg(log, "timeline_apply", {**APPLY, "group_id": None}, "/group_id")  # fresh
    ungrouped = {k: v for k, v in APPLY.items() if k != "group_id"}
    r = log.call(HUMAN, "timeline_apply", ungrouped)
    assert r["group_id"] is None and log.history_list()[0]["group_id"] is None
    _bad_arg(log, "timeline_apply", {**ungrouped, "group_id": None}, "/group_id")  # a cached key: shape first
    assert log.call(HUMAN, "timeline_apply", ungrouped)["op_id"] == r["op_id"]
    _bad_arg(log, "timeline_apply", {**ungrouped, "client_op_id": "n2", "base_version": 1, "group_id": None}, "/group_id")


# --------------------------------------------------------------------------- Ada's doc-only rulings, pinned


@pytest.mark.parametrize("op", [{"src_out": 0}, {"src_in": 4 * S}], ids=["src_out-0", "src_in-at-end"])
def test_transition_too_long_is_checked_before_empty_range(op):
    op = {"op": "trim_clip", "id": "c1", "ripple": True, **op}
    log = xfade_log()
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, op)
    assert (e.value.extra["rule"], e.value.extra["path"], e.value.extra["id"]) == ("transition_too_long", "/ops/0", "t12")
    plain = new_log()  # no crossfade: the validator's empty_range, as before
    with pytest.raises(O.OplogError) as e:
        apply(plain, HUMAN, op)
    assert (e.value.extra["rule"], e.value.extra["id"]) == ("empty_range", "c1")


def test_a_ripple_trim_never_moves_a_neighbour_that_only_overlaps_the_clip():
    d = base()
    music = next(t for t in d["tracks"] if t["role"] == "music")
    music["items"] += [
        {"id": "ma", "type": "clip", "media": "m2", "src": [0, 8 * S], "at": 40 * S, "fade_in": 0, "fade_out": 0},
        {"id": "m0", "type": "clip", "media": "m2", "src": [0, S], "at": 40 * S, "fade_in": 0, "fade_out": 0},  # only overlaps ma
        {"id": "mb", "type": "clip", "media": "m2", "src": [10 * S, 16 * S], "at": 47 * S, "fade_in": 0, "fade_out": 0},
        {"id": "tab", "type": "transition", "kind": "xfade", "between": ["ma", "mb"], "dur": S},
    ]
    assert T.validate(d) == []
    log = O.Oplog(d)
    h0 = h(log)
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "trim_clip", "id": "m0", "src_out": S // 2, "ripple": True})
    x = e.value.extra
    assert (e.value.code, x["rule"], x["id"]) == ("invalid_op", "transition_overlap_mismatch", "tab")  # the existing rule
    assert h(log) == h0 and log.history_list() == []
    apply(log, HUMAN, {"op": "trim_clip", "id": "m0", "src_out": S // 2})  # without ripple it's fine


def test_rule_counts_stay_17_op_level_and_36_validator():
    text = (Path(__file__).resolve().parent.parent / "docs" / "oplog.md").read_text(encoding="utf-8")
    listed = text.split("Op-level `rule`s (17):")[1].split("plus every timeline rule")[0]
    assert len(listed.split("`")[1::2]) == 17
    assert len(T.RULES) == 36 and "transition_too_long" not in T.RULES
