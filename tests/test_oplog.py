"""Slice 2: the op log (Prove C2-C6): ops and inverses, atomic batches, groups, append-only
undo/redo, client_op_id dedupe, actor and step from the session only, version conflicts."""

from __future__ import annotations

import copy
import json

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
    d["media"] = {"m1": {"path": "media/talk.mp4", "dur": 600 * S, "fps": [30, 1]},
                  "m2": {"path": "media/song.mp3", "dur": 300 * S, "fps": None}}
    tr = {t["id"]: t for t in d["tracks"]}
    tr["V1"]["items"] = [
        {"id": "c1", "type": "clip", "media": "m1", "src": [0, 4 * S], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "c2", "type": "clip", "media": "m1", "src": [10 * S, 14 * S], "at": 4 * S, "fade_in": 0, "fade_out": 0},
        {"id": "c3", "type": "clip", "media": "m1", "src": [20 * S, 24 * S], "at": 10 * S, "fade_in": 0, "fade_out": 0},
    ]
    tr["T1"]["items"] = [{"id": "x1", "type": "text", "dur": S, "text": "Hi", "style": "pop", "fade_in": 0,
                          "fade_out": 0, "anchor": {"to": "c2", "offset": S}}]
    tr["A2"]["items"] = [{"id": "mu1", "type": "clip", "media": "m2", "src": [0, 6 * S], "anchor": {"to": "c1", "offset": 0},
                          "fade_in": 0, "fade_out": 0}]
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
    assert list(O.LINE_FIELDS) == ["seq", "op_id", "client_op_id", "group_id", "actor", "summary", "base_version",
                                   "new_version", "hash", "ops", "inverse", "changed_ids", "undoes"]
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
    assert {"ok", "op_id", "group_id", "seq", "new_version", "hash", "tick_rate", "summary", "changed_ids", "undoes",
            "before_frame", "after_frame", "warnings"} == set(r)
    assert r["changed_ids"] == ["mk1"]


# --------------------------------------------------------------------------- actor and step come from the session


def test_forged_actor_in_the_args_is_ignored():
    log = new_log()
    r = log.call(hermes(), "timeline_apply", {"base_version": 0, "summary": "s", "client_op_id": "a1",
                                              "actor": {"kind": "human", "id": "pablo"},
                                              "ops": [{"op": "move_clip", "id": "c3", "at": 11 * S}]})
    assert log.history_list()[-1]["actor"] == {"kind": "agent", "id": "hermes"}
    assert r["warnings"] == [{"code": "ignored_field", "path": "/actor",
                              "message": "'actor' is ignored: it comes from the session, not the arguments"}]
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
    rd = log.call(hermes(2), "history_redo", {"op_id": u["op_id"], "client_op_id": "r", "actor": {"kind": "human"},
                                              "step": 9})
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


@pytest.mark.parametrize("op, rule, pid", [
    ({"op": "set_fade", "id": "c1", "fade_in": 3 * S, "fade_out": 2 * S}, "fade_too_long", "c1"),
    ({"op": "set_anchor", "id": "x1", "anchor": {"to": "mu1", "offset": 0}}, "anchor_target_not_main", "x1"),
    ({"op": "move_clip", "id": "c2", "at": 0}, "overlap", None),
    ({"op": "add_marker", "at": 0, "label": "e\u0301"}, "not_nfc", "mk1"),
])
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


@pytest.mark.parametrize("args, rule", [
    ({"ops": [], "summary": "s"}, "bad_arg"),
    ({"ops": [{"op": "frobnicate"}], "summary": "s"}, "unknown_op"),
    ({"ops": [{"op": "set_fields", "id": "c1", "set": {"at": 0}}], "summary": "s"}, "unknown_op"),  # internal only
    ({"ops": [{"op": "move_clip", "id": "c3"}], "summary": "s"}, "missing_arg"),
    ({"ops": [{"op": "move_clip", "id": "c3", "at": 1.5}], "summary": "s"}, "not_integer_ticks"),
    ({"ops": [{"op": "move_clip", "id": "c3", "at": 0, "color": 1}], "summary": "s"}, "unknown_arg"),
    ({"ops": [{"op": "add_marker", "at": 0, "label": "x"}], "summary": ""}, "bad_arg"),
    ({"ops": [{"op": "add_marker", "at": 0, "label": "x"}], "summary": "s", "seq": 5}, "unknown_arg"),
    ({"ops": [{"op": "add_marker", "at": 0, "label": "x"}]}, "missing_arg"),
])
def test_bad_calls_are_invalid_op(args, rule):
    log = new_log()
    with pytest.raises(O.OplogError) as e:
        log.call(HUMAN, "timeline_apply", {"base_version": 0, "client_op_id": "x", **args})
    assert e.value.code == "invalid_op" and e.value.extra["rule"] == rule and log.history_list() == []


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
    roundtrip({"op": "move_clip", "id": "c2", "at": 4 * S - S // 2},
              {"op": "add_transition", "between": ["c1", "c2"], "dur": S // 2})
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
    apply(log, HUMAN, {"op": "set_props", "id": "c3", "props": {"speed": [3, 2]}},
          {"op": "trim_clip", "id": "c3", "src_out": 23 * S})  # 3 s of source at 1.5x = 2 s
    with pytest.raises(O.OplogError) as e:
        apply(log, HUMAN, {"op": "split_clip", "id": "c3", "at": 10 * S + 1})
    assert e.value.extra["rule"] == "non_integer_duration"


def test_split_moves_transitions_and_anchors_to_the_right_piece():
    log = new_log()
    apply(log, HUMAN, {"op": "move_clip", "id": "c2", "at": 4 * S - S // 2},
          {"op": "add_transition", "id": "tA", "between": ["c1", "c2"], "dur": S // 2})
    apply(log, HUMAN, {"op": "split_clip", "id": "c2", "at": 4 * S + S // 4, "ids": ["p1", "p2"]})
    d = log.doc
    assert item(d, "tA")["between"] == ["c1", "p1"]
    assert item(d, "x1")["anchor"] == {"to": "p2", "offset": S // 4}  # the text starts after the cut
    assert T.resolve(d)["x1"][0] == 4 * S + S // 2


def test_deleting_a_clip_frees_its_anchored_items_and_undo_reanchors_them():
    log, d = roundtrip({"op": "delete_clip", "id": "c2"})
    assert "c2" not in ids(d) and item(d, "x1")["at"] == 5 * S and "anchor" not in item(d, "x1")
    assert T.validate(d) == []  # never an anchor_target_missing doc


def test_ripple_delete_closes_the_hole_and_takes_transitions_along():
    log = new_log()
    apply(log, HUMAN, {"op": "move_clip", "id": "c3", "at": 8 * S - S // 4},
          {"op": "add_transition", "id": "tB", "between": ["c2", "c3"], "dur": S // 4})
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
    apply(log, HUMAN, {"op": "delete_clip", "id": "c3", "ripple": True}, {"op": "add_text", "at": 0, "dur": S,
                                                                          "text": "café", "style": "pop"})
    undo(log, HUMAN, group_id="g")
    lines = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert lines == log.history_list() and lines[0]["step"] == 4
    assert all(set(e) <= set(O.LINE_FIELDS) | {"step"} for e in lines)
    again = O.Oplog.load(base(), p)
    assert again.doc == log.doc and T.canonical_hash(O.replay(base(), lines)) == h(log)
    retry = again.call(hermes(4), "timeline_apply", {"base_version": 0, "ops": [], "summary": "s",
                                                     "client_op_id": log.history_list()[0]["client_op_id"]})
    assert retry["op_id"] == r["op_id"] and again.version == log.version  # dedupe survives a reload
    lines[1]["hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        O.replay(base(), lines)


def test_a_failed_write_to_the_log_changes_nothing(tmp_path):
    log = new_log(path=tmp_path / "missing" / "oplog.jsonl")
    before = log.doc
    with pytest.raises(OSError):
        apply(log, HUMAN, {"op": "add_marker", "at": 0, "label": "x"})
    assert log.doc == before and log.history_list() == []
