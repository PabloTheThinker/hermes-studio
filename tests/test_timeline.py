"""Slice 1: hs.timeline/1 schema, validator, canonical hash and OTIO export (Prove C1)."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from hermes_studio import timeline as T

S = T.TICK_RATE  # ticks per second


def doc() -> dict:
    """A valid doc: 3 V1 clips with a gap and an xfade, text and music anchored to V1, a voice clip,
    markers and a second text track."""
    d = T.new_timeline("p-7f3a")
    d["media"] = {
        "m1": {"path": "media/talk.mp4", "dur": 1200 * S, "fps": [30000, 1001], "proxy": "cache/proxy/m1.mp4"},
        "m2": {"path": "media/song.mp3", "dur": 180 * S, "fps": None},
    }
    tracks = {t["id"]: t for t in d["tracks"]}
    tracks["V1"]["items"] = [
        {"id": "c1", "type": "clip", "media": "m1", "src": [12 * S, 20 * S], "at": 0, "fade_in": S // 2, "fade_out": 0,
         "props": {"crop": {"x": [0, 1], "y": [1, 4], "w": [1, 2], "h": [1, 2]}}},
        {"id": "c2", "type": "clip", "media": "m1", "src": [40 * S, 50 * S], "at": 8 * S - S // 4, "fade_in": 0,
         "fade_out": 0, "props": {"volume": [1, 2], "speed": [1, 1], "crop": None, "look": "warm"}},
        {"id": "x1", "type": "transition", "kind": "xfade", "between": ["c1", "c2"], "dur": S // 4},
        # a 2 s gap before c3, implied by `at`
        {"id": "c3", "type": "clip", "media": "m1", "src": [60 * S, 64 * S], "at": 20 * S - S // 4, "fade_in": 0,
         "fade_out": S, "split_from": "c0", "props": {"speed": [2, 1]}},
    ]
    tracks["T1"]["items"] = [
        {"id": "t1", "type": "text", "dur": 3 * S, "text": "Hola, café", "style": "pop", "fade_in": 0, "fade_out": 0,
         "anchor": {"to": "c2", "offset": S}},
        {"id": "t2", "type": "text", "at": 0, "dur": 2 * S, "text": "Intro", "style": "pop", "fade_in": S // 10,
         "fade_out": S // 10},
    ]
    tracks["A1"]["items"] = [
        {"id": "a1", "type": "clip", "media": "m1", "src": [12 * S, 20 * S], "at": 0, "fade_in": 0, "fade_out": 0},
    ]
    tracks["A2"]["items"] = [
        {"id": "mu1", "type": "clip", "media": "m2", "src": [0, 30 * S], "anchor": {"to": "c1", "offset": 0},
         "fade_in": 2 * S, "fade_out": 3 * S, "props": {"volume": [3, 10]}},
        {"id": "mu2", "type": "clip", "media": "m2", "src": [30 * S, 40 * S], "at": 5 * S, "fade_in": 0, "fade_out": 0},
    ]
    d["tracks"].insert(0, {"id": "T2", "role": "text", "items": []})
    d["markers"] = [{"id": "k2", "at": 9 * S, "label": "good bit"}, {"id": "k1", "at": 2 * S, "label": ""}]
    return d


def track(d: dict, tid: str) -> dict:
    return next(t for t in d["tracks"] if t["id"] == tid)


def item(d: dict, iid: str) -> dict:
    return next(i for t in d["tracks"] for i in t["items"] if i["id"] == iid)


def _resolve_pointer(d, ptr: str):
    """Follow an RFC 6901 pointer; a final missing key (missing_field) resolves to its parent."""
    o = d
    parts = [x.replace("~1", "/").replace("~0", "~") for x in ptr.split("/")[1:]] if ptr else []
    for i, k in enumerate(parts):
        if isinstance(o, list):
            o = o[int(k)]
        elif isinstance(o, dict) and k in o:
            o = o[k]
        else:
            assert i == len(parts) - 1, (ptr, k)
    return o


def _id_pointers(d) -> dict[str, list[str]]:
    """Every id in the doc -> the pointers of the objects that use it (items and markers by
    pointer; media keys and tracks too, so clashes count)."""
    out: dict[str, list[str]] = {}
    if not isinstance(d, dict):
        return out
    for k in d.get("media", {}) if isinstance(d.get("media"), dict) else {}:
        out.setdefault(k, []).append(T._j("", "media", k))
    for ti, tr in enumerate(d.get("tracks", []) if isinstance(d.get("tracks"), list) else []):
        if not isinstance(tr, dict):
            continue
        if isinstance(tr.get("id"), str):
            out.setdefault(tr["id"], []).append(T._j("", "tracks", ti))
        for ii, it in enumerate(tr.get("items", []) if isinstance(tr.get("items"), list) else []):
            if isinstance(it, dict) and isinstance(it.get("id"), str):
                out.setdefault(it["id"], []).append(T._j("", "tracks", ti, "items", ii))
    for mi, mk in enumerate(d.get("markers", []) if isinstance(d.get("markers"), list) else []):
        if isinstance(mk, dict) and isinstance(mk.get("id"), str):
            out.setdefault(mk["id"], []).append(T._j("", "markers", mi))
    return out


def V(d) -> list[dict]:
    """T.validate(d), plus the blanket id check every test goes through: a problem's id names
    exactly one valid item or marker, and its path is that item's pointer or inside it."""
    found = T.validate(d)
    ptrs = _id_pointers(d)
    for p in found:
        if "id" not in p:
            continue
        assert p["rule"] not in ("bad_id", "duplicate_id"), p
        assert T.ID_RE.fullmatch(p["id"]), p
        where = ptrs.get(p["id"], [])
        assert len(where) == 1, (p, where)
        assert re.fullmatch(r"/(tracks/\d+/items|markers)/\d+", where[0]), (p, where)
        assert p["path"] == where[0] or p["path"].startswith(where[0] + "/"), (p, where)
    return found


def rules(d) -> set[str]:
    return {p["rule"] for p in V(d)}


def test_fixture_is_valid_and_every_rule_is_listed():
    assert T.validate(doc()) == []
    assert T.validate_or_raise(T.new_timeline("empty"))
    assert len(T.RULES) == len(set(T.RULES))


# --------------------------------------------------------------------------- bad docs


def _set(path: str, value):
    def f(d):
        *head, last = path.split(".")
        o = d
        for k in head:
            o = item(d, k[1:]) if k.startswith("@") else (o[int(k)] if isinstance(o, list) else o[k])
        if value is _DEL:
            del o[last]
        else:
            o[last] = value
    return f


_DEL = object()


def _clip(**kw):
    base = {"id": "z", "type": "clip", "media": "m1", "src": [0, S], "at": 100 * S, "fade_in": 0, "fade_out": 0}
    base.update(kw)
    return base


def _add(tid: str, it: dict):
    def f(d):
        track(d, tid)["items"].append(it)
    return f


def _add_track(tr: dict, at: int):
    def f(d):
        d["tracks"].insert(at, tr)
    return f


BAD = {
    "bad schema_version": (_set("schema_version", "hs.timeline/2"), "bad_schema"),
    "schema_version missing": (_set("schema_version", _DEL), "bad_schema"),
    "old field name schema": (lambda d: d.update(schema=d.pop("schema_version")), "bad_schema"),
    "tick_rate 1000": (_set("tick_rate", 1000), "bad_tick_rate"),
    "tick_rate 48000": (_set("tick_rate", 48000), "bad_tick_rate"),
    "tick_rate as float": (_set("tick_rate", 705600000.0), "bad_tick_rate"),
    "tick_rate missing": (_set("tick_rate", _DEL), "bad_tick_rate"),
    "missing markers": (_set("markers", _DEL), "missing_field"),
    "missing fade_in": (_set("@c1.fade_in", _DEL), "missing_field"),
    "missing src": (_set("@c1.src", _DEL), "missing_field"),
    "unknown top field": (_set("duration", 5), "unknown_field"),
    "unknown item field": (_set("@c1.colour", "red"), "unknown_field"),
    "actor on item (Glyph 1)": (_set("@c1.actor", "hermes"), "attribution_field"),
    "author on doc (Glyph 1)": (_set("author", "pablo"), "attribution_field"),
    "float at": (_set("@c1.at", 0.5), "not_integer_ticks"),
    "bool at": (_set("@c1.at", True), "not_integer_ticks"),
    "float text dur": (_set("@t2.dur", 2.0), "not_integer_ticks"),
    "float src": (_set("@c1.src", [12.0, 20 * S]), "not_integer_ticks"),
    "float anchor offset": (_set("@t1.anchor", {"to": "c2", "offset": 1.5}), "not_integer_ticks"),
    "float fade": (_set("@c1.fade_out", 0.0), "not_integer_ticks"),
    "float marker at": (_set("markers.0.at", 9.0), "not_integer_ticks"),
    "float media dur": (_set("media.m1.dur", 1200.0), "not_integer_ticks"),
    "negative at": (_set("@c1.at", -1), "negative_time"),
    "negative marker at": (_set("markers.0.at", -S), "negative_time"),
    "negative fade_in": (_set("@c1.fade_in", -1), "negative_time"),
    "zero text dur": (_set("@t2.dur", 0), "empty_range"),
    "negative text dur": (_set("@t2.dur", -S), "negative_time"),
    "src in == out": (_set("@c1.src", [S, S]), "empty_range"),
    "src reversed": (_set("@c1.src", [2 * S, S]), "empty_range"),
    "src past media end": (_set("@c1.src", [1199 * S, 1201 * S]), "src_out_of_media"),
    "huge at": (_set("@c1.at", 2**60), "too_large"),
    "float fps": (_set("fps", 29.97), "bad_rational"),
    "unreduced fps": (_set("fps", [60, 2]), "bad_rational"),
    "fps not tick-exact": (_set("fps", [11, 1]), "bad_fps"),
    "float volume": (_set("@c2.props.volume", 0.5), "bad_rational"),
    "speed out of range": (_set("@c2.props.speed", [20, 1]), "out_of_range"),
    "speed gives fractional ticks": (_set("@c3.props.speed", [11, 10]), "non_integer_duration"),
    "crop outside frame": (_set("@c1.props.crop", {"x": [1, 2], "y": [0, 1], "w": [3, 4], "h": [1, 2]}), "out_of_range"),
    "decomposed é in text": (_set("@t1.text", "Hola, cafe\u0301"), "not_nfc"),
    "decomposed é in label": (_set("markers.0.label", "e\u0301"), "not_nfc"),
    "bad id chars": (_set("@c1.id", "c 1"), "bad_id"),
    "duplicate item id across tracks (Glyph 2)": (_add("A1", _clip(id="c1")), "duplicate_id"),
    "marker id equals item id (Glyph 5)": (_set("markers.0.id", "c2"), "duplicate_id"),
    "duplicate marker ids (Glyph 5)": (_set("markers.1.id", "k2"), "duplicate_id"),
    "track id equals item id": (_set("@t2.id", "A1"), "duplicate_id"),
    "bad track role": (_set("tracks.0.role", "b-roll"), "bad_track_role"),
    "overlay role is not in hs.timeline/1": (_set("tracks.0.role", "overlay"), "bad_track_role"),
    "second video track": (_add_track({"id": "V2", "role": "main", "items": []}, 2), "bad_track_id"),
    "audio role on a V id": (_set("tracks.2.role", "voice"), "bad_track_id"),
    "second main track": (_add_track({"id": "V3", "role": "main", "items": []}, 2), "bad_track_id"),
    "no main track": (lambda d: d["tracks"].remove(track(d, "V1")), "missing_main_track"),
    "tracks out of role order": (lambda d: d["tracks"].reverse(), "track_order"),
    "text on V1": (_add("V1", {"id": "tx", "type": "text", "at": 0, "dur": S, "text": "", "style": "pop",
                               "fade_in": 0, "fade_out": 0}), "item_not_allowed_on_track"),
    "clip on a text track": (_add("T1", _clip()), "item_not_allowed_on_track"),
    "unknown media": (_set("@c1.media", "m9"), "unknown_media"),
    "fade_in + fade_out > dur (b)": (_set("@c1.fade_out", 8 * S), "fade_too_long"),
    "text fades > dur (b)": (_set("@t2.fade_in", 2 * S), "fade_too_long"),
    "both at and anchor": (_set("@t1.at", 0), "at_and_anchor"),
    "neither at nor anchor": (_set("@c1.at", _DEL), "at_and_anchor"),
    "anchor on a V1 video clip (a)": (_set("@c3.anchor", {"to": "c1", "offset": 0}), "at_and_anchor"),
    "anchor-only V1 video clip (a)": (lambda d: (item(d, "c3").pop("at"), item(d, "c3").update(
        anchor={"to": "c1", "offset": 0})), "anchor_not_allowed"),
    "anchor on a voice clip (a)": (lambda d: (item(d, "a1").pop("at"), item(d, "a1").update(
        anchor={"to": "c1", "offset": 0})), "anchor_not_allowed"),
    "anchor to missing id (a)": (_set("@t1.anchor", {"to": "c9", "offset": 0}), "anchor_target_missing"),
    "anchor to non-V1 clip (a)": (_set("@t1.anchor", {"to": "a1", "offset": 0}), "anchor_target_not_main"),
    "anchor to a text item (a)": (_set("@t1.anchor", {"to": "t2", "offset": 0}), "anchor_target_not_main"),
    "anchor to a transition (a)": (_set("@t1.anchor", {"to": "x1", "offset": 0}), "anchor_target_not_main"),
    "anchor before 0": (_set("@mu1.anchor", {"to": "c1", "offset": -S}), "anchor_before_zero"),
    "anchor extra key": (_set("@t1.anchor", {"to": "c2", "offset": 0, "track": "V1"}), "unknown_field"),
    "V1 overlap (c)": (_set("@c3.at", 17 * S), "overlap"),
    "V1 clip inside another (c)": (_add("V1", _clip(id="c4", at=S)), "overlap"),
    "voice overlap": (_add("A1", _clip(id="a2", at=S)), "overlap"),
    "xfade dur differs from overlap": (_set("@x1.dur", S // 5), "transition_overlap_mismatch"),
    "xfade on clips that don't touch": (_set("@x1.between", ["c2", "c3"]), "transition_overlap_mismatch"),
    "xfade backwards": (_set("@x1.between", ["c2", "c1"]), "bad_transition"),
    "xfade to another track": (_set("@x1.between", ["c1", "a1"]), "bad_transition"),
    "xfade kind": (_set("@x1.kind", "wipe"), "bad_transition"),
    "split_from itself (Glyph 2)": (_set("@c3.split_from", "c3"), "bad_split_from"),
    "split_from not an id": (_set("@c3.split_from", ""), "wrong_type"),
    "stale hash": (lambda d: d.update(hash="sha256:" + "0" * 64), "hash_mismatch"),
}


@pytest.mark.parametrize("name", list(BAD))
def test_validator_rejects(name):
    mutate, rule = BAD[name]
    d = doc()
    mutate(d)
    assert rule in rules(d), (name, V(d))
    with pytest.raises(T.TimelineError) as e:
        T.validate_or_raise(d)
    assert rule in e.value.rules
    assert e.value.code == "bad_input" and e.value.as_dict()["problems"] == V(d)
    for p in e.value.problems:
        assert p["rule"] in T.RULES and set(p) <= {"rule", "path", "message", "id"}
        assert p["path"] == "" or p["path"].startswith("/")  # RFC 6901 JSON Pointer
        _resolve_pointer(d, p["path"])  # points into the doc (or at a missing key's parent object)


def test_non_object_doc_is_rejected():
    for d in (None, [], "x", 3):
        assert rules(d) == {"not_object"}


# --------------------------------------------------------------------------- desk rulings


def test_v1_gaps_are_allowed_without_a_gap_object():
    d = doc()
    c1, c3 = item(d, "c1"), item(d, "c3")
    assert c3["at"] > T.resolve(d)["c2"][1]  # a 2 s gap before c3
    c1["at"] = 10 * S  # gap at the very start too (and c2 no longer touches c1)
    track(d, "V1")["items"] = [i for i in track(d, "V1")["items"] if i["id"] != "x1"]
    item(d, "c2")["at"] = 30 * S
    item(d, "c3")["at"] = 60 * S
    assert V(d) == []


def test_xfade_is_the_only_allowed_overlap_on_v1():
    d = doc()
    assert T.resolve(d)["c1"][1] - T.resolve(d)["c2"][0] == item(d, "x1")["dur"]
    track(d, "V1")["items"].remove(item(d, "x1"))
    assert "overlap" in rules(d)


def test_text_and_music_tracks_may_overlap():
    d = doc()
    track(d, "T1")["items"].append({"id": "t3", "type": "text", "at": S, "dur": S, "text": "x", "style": "pop",
                                   "fade_in": 0, "fade_out": 0})
    assert T.resolve(d)["mu2"][0] < T.resolve(d)["mu1"][1]
    assert V(d) == []


def test_anchored_items_follow_their_v1_clip():
    d = doc()
    before = T.resolve(d)
    assert before["t1"] == (before["c2"][0] + S, before["c2"][0] + 4 * S)
    assert before["mu1"][0] == before["c1"][0] == 0
    for c in ("c1", "c2", "c3"):  # move everything on V1 5 s later
        item(d, c)["at"] += 5 * S
    after = T.resolve(d)
    assert after["t1"][0] == before["t1"][0] + 5 * S
    assert after["mu1"][0] == before["mu1"][0] + 5 * S
    assert after["t2"] == before["t2"] and after["mu2"] == before["mu2"]  # absolute items stay
    assert V(d) == []


def test_fades_are_plain_ticks_up_to_the_duration():
    d = doc()
    item(d, "c1")["fade_in"], item(d, "c1")["fade_out"] = 4 * S, 4 * S  # == 8 s duration: allowed
    assert V(d) == []
    item(d, "c3")["fade_in"], item(d, "c3")["fade_out"] = S, S  # c3 is 4 s of source at 2x = 2 s
    assert V(d) == []
    item(d, "c3")["fade_out"] = S + 1
    assert rules(d) == {"fade_too_long"}
    item(d, "c1")["fade_in"] = {"keyframes": []}
    assert "not_integer_ticks" in rules(d)


# --------------------------------------------------------------------------- time


@pytest.mark.parametrize("rate,per", [((24000, 1001), 29429400), (24, 29400000), (25, 28224000),
                                      ((30000, 1001), 23543520), (30, 23520000), (60, 11760000), (48000, 14700)])
def test_common_rates_are_whole_ticks(rate, per):
    assert T.ticks_per_frame(rate) == per
    assert T.frames_to_ticks(1001, rate) == 1001 * per
    assert T.ticks_to_frames(T.frames_to_ticks(7, rate), rate) == 7


def test_seconds_to_ticks():
    assert T.seconds_to_ticks(1) == S
    assert T.seconds_to_ticks("19.15") == 19 * S + 105840000
    assert T.seconds_to_ticks(Decimal("0.5")) == S // 2
    assert T.seconds_to_ticks(Fraction(1001, 30000)) == 23543520
    assert T.seconds_to_ticks("1001/30000") == 23543520
    with pytest.raises(ValueError):
        T.seconds_to_ticks(Fraction(1, 7 * S))
    with pytest.raises(TypeError):
        T.seconds_to_ticks(True)
    # floats: exact binary value, rounded half to even
    assert T.seconds_to_ticks(0.1) == 70560000
    assert T.seconds_to_ticks(2.5 / S) == 2 and T.seconds_to_ticks(3.5 / S) == 4
    assert T.ticks_to_seconds(23543520) == Fraction(1001, 30000)
    assert T.seconds_to_ticks(T.ticks_to_seconds(123456789)) == 123456789


def test_frame_helpers_refuse_inexact_rates():
    with pytest.raises(ValueError):
        T.ticks_per_frame(11)


# --------------------------------------------------------------------------- hash


def test_hash_is_sha256_of_the_documented_canonical_json():
    import hashlib

    d = doc()
    body = T.canonical_json(d)
    assert T.canonical_hash(d) == "sha256:" + hashlib.sha256(body).hexdigest()
    parsed = json.loads(body)
    assert "version" not in parsed and "hash" not in parsed
    assert parsed["schema_version"] == T.SCHEMA_VERSION  # hashed (and any other value fails validation)
    assert body == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert "café".encode() in body  # UTF-8, not \u escapes


def test_equal_content_hashes_equal():
    a, b = doc(), doc()
    b = json.loads(json.dumps(b, sort_keys=True))  # every object's key order changed
    for t in b["tracks"]:
        t["items"].reverse()  # item list order is not meaningful
    b["markers"].reverse()  # nor is marker order
    item(b, "a1")["props"] = dict(T.DEFAULT_PROPS)  # explicit defaults == omitted props
    assert T.canonical_hash(a) == T.canonical_hash(b)


def test_version_and_stored_hash_are_not_hashed():
    a = doc()
    h = T.canonical_hash(a)
    b, stamped = T.stamp_hash(a)
    assert stamped == h and b["hash"] == h and "hash" not in a  # a copy; the input is untouched
    b["version"] = 9999
    assert T.canonical_hash(b) == h and V(b) == []  # version is free to move


def test_canonical_hash_refuses_a_stale_hash_and_stamp_hash_fixes_it():
    d = doc()
    d["hash"] = "sha256:" + "f" * 64  # the only problem
    assert V(d) == [{"rule": "hash_mismatch", "path": "/hash", "message": "hash does not match the content"}]
    with pytest.raises(T.TimelineError) as e:
        T.canonical_hash(d)
    assert e.value.rules == ["hash_mismatch"]
    with pytest.raises(T.TimelineError):
        T.canonical_json(d)
    fixed, h = T.stamp_hash(d)
    assert fixed["hash"] == h == T.canonical_hash(fixed) and V(fixed) == []
    item(d, "c1")["at"] = -1  # stamp_hash still refuses every other problem
    with pytest.raises(T.TimelineError) as e:
        T.stamp_hash(d)
    assert e.value.rules == ["negative_time"]


@pytest.mark.parametrize("mutate", [
    lambda d: item(d, "c3").update(at=item(d, "c3")["at"] + 1),  # one tick
    lambda d: item(d, "c1").update(fade_in=S // 2 + 1),
    lambda d: item(d, "t1").update(text="Hola, cafe"),
    lambda d: item(d, "t1")["anchor"].update(offset=S + 1),
    lambda d: item(d, "c3").pop("split_from"),
    lambda d: d["markers"][0].update(label="Good bit"),
    lambda d: d["media"]["m1"].update(proxy=None),
    lambda d: item(d, "c2")["props"].update(look=None),
    lambda d: d.update(fps=[25, 1]),
    lambda d: d.update(id="p-other"),
    lambda d: track(d, "A2")["items"].pop(),
])
def test_different_content_hashes_differ(mutate):
    a, b = doc(), doc()
    mutate(b)
    T.validate_or_raise(b)
    assert T.canonical_hash(a) != T.canonical_hash(b)


def test_track_order_is_meaningful_and_fixed_by_role():
    d = doc()
    assert [t["id"] for t in d["tracks"]] == ["T2", "T1", "V1", "A1", "A2"]
    d["tracks"][0], d["tracks"][1] = d["tracks"][1], d["tracks"][0]
    assert rules(d) == {"track_order"}


def test_canonical_hash_refuses_an_invalid_doc():
    d = doc()
    item(d, "t1")["anchor"]["to"] = "nope"
    d["tick_rate"] = 1000
    with pytest.raises(T.TimelineError) as e:
        T.canonical_hash(d)
    assert e.value.rules == ["bad_tick_rate"]
    d["tick_rate"] = T.TICK_RATE
    with pytest.raises(T.TimelineError) as e:
        T.canonical_hash(d)
    assert e.value.rules == ["anchor_target_missing"] and e.value.rule == "anchor_target_missing"


def test_undo_back_to_a_state_gives_back_its_hash():
    d = doc()
    h = T.canonical_hash(d)
    old = copy.deepcopy(item(d, "c3"))
    item(d, "c3")["at"] += S
    assert T.canonical_hash(d) != h
    item(d, "c3").update(old)
    assert T.canonical_hash(d) == h


# --------------------------------------------------------------------------- OTIO


def test_to_otio_maps_clips_gaps_transitions_and_markers():
    import opentimelineio as otio

    d = doc()
    tl = T.to_otio(d)
    v1 = next(t for t in tl.tracks if t.name == "V1")
    kinds = [type(c).__name__ for c in v1]
    assert kinds == ["Clip", "Transition", "Clip", "Gap", "Clip"]
    when = T.resolve(d)
    for c in v1.find_clips():
        s, e = when[c.name]
        r = c.range_in_parent()
        assert r.start_time.rate == T.TICK_RATE
        assert r.start_time.value == s
        trim = 0 if c.name != "c1" else item(d, "x1")["dur"]
        assert r.duration.value == e - s - trim
    gap = v1[3]
    assert gap.source_range.duration.value == item(d, "c3")["at"] - when["c2"][1]
    assert v1[1].out_offset.value == item(d, "x1")["dur"] and v1[1].in_offset.value == 0
    assert len(list(tl.find_clips())) == 8  # 3 V1 + 2 text + 1 voice + 2 music
    assert [m.name for m in tl.tracks.markers] == ["", "good bit"]
    assert [t.name for t in tl.tracks] == ["T2", "T1", "V1", "A1", "A2", "A2.1"]  # music overlaps -> 2 lanes
    assert next(t for t in tl.tracks if t.name == "A1").kind == otio.schema.TrackKind.Audio
    t1 = next(c for c in tl.find_clips() if c.name == "t1")
    assert t1.media_reference.generator_kind == T.TEXT_GENERATOR
    assert t1.range_in_parent().start_time.value == when["t1"][0]


def test_otio_round_trip_loses_nothing(tmp_path):
    import opentimelineio as otio

    d, _ = T.stamp_hash(doc())
    path = T.write_otio(d, str(tmp_path / "out.otio"))
    back = T.from_otio(otio.adapters.read_from_file(path))
    assert back == T.normalize(d)
    assert T.canonical_hash(back) == d["hash"] and back["version"] == d["version"]
    assert T.from_otio(T.to_otio(back)) == back


def test_otio_round_trip_of_an_empty_timeline():
    d = T.new_timeline("empty")
    assert T.from_otio(T.to_otio(d)) == T.normalize(d)


def _otiotool() -> str | None:
    found = shutil.which("otiotool")
    if found:
        return found
    cand = Path(sys.executable).with_name("otiotool")
    return str(cand) if cand.exists() else None


@pytest.mark.skipif(_otiotool() is None, reason="otiotool not installed")
def test_export_opens_in_otiotool(tmp_path):
    # --stats and --list-markers print SMPTE timecode, which OTIO only formats at standard frame
    # rates, not at the 705,600,000/s tick rate; every other read, inspect and verify phase works.
    d, _ = T.stamp_hash(doc())
    out = T.write_otio(d, str(tmp_path / "out.otio"))
    again = tmp_path / "again.otio"
    r = subprocess.run([_otiotool(), "-i", out, "--list-tracks", "--list-clips", "--list-media", "--verify-ranges",
                        "--inspect", "c1", "-o", str(again)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    for name in ("V1", "A2.1", "c1", "c2", "c3", "t1", "mu1", "media/talk.mp4"):
        assert name in r.stdout
    assert "OUT OF BOUNDS" not in r.stdout
    import opentimelineio as otio

    # otiotool's own re-serialization still converts back to the same document.
    assert T.from_otio(otio.adapters.read_from_file(str(again))) == T.normalize(d)


def test_every_rule_has_a_rejection_case():
    assert {r for _, r in BAD.values()} | {"not_object"} == set(T.RULES)


def test_the_documented_example_is_valid():
    import re

    text = (Path(__file__).resolve().parents[1] / "docs/timeline.md").read_text(encoding="utf-8")
    d = json.loads(re.search(r"```json\n(.*?)```", text, re.S).group(1).replace('"hash": "sha256:…",', ""))
    assert V(d) == []
    assert ", ".join(f"`{r}`" for r in T.RULES) in " ".join(text.split("## Rule ids")[1].split())


def test_public_api_is_importable():
    from hermes_studio.timeline import canonical_hash, seconds_to_ticks, to_otio, validate

    assert all(callable(f) for f in (validate, canonical_hash, to_otio, seconds_to_ticks))
    assert T.ROLE_ORDER == ("text", "main", "voice", "music")
    assert T.new_timeline("p")["schema_version"] == "hs.timeline/1" and "schema" not in T.new_timeline("p")


def test_pointer_helper_escapes_tilde_and_slash():
    assert T._j("", "media", "a~b/c", 0) == "/media/a~0b~1c/0"
    assert T._j("/tracks/1", "items", 2, "fade_in") == "/tracks/1/items/2/fade_in"
    assert T._j("") == ""


def test_problem_paths_are_json_pointers_into_the_doc():
    d = doc()
    d["media"]["m.1"] = {"path": "x.mp4", "dur": S, "fps": 29.97}  # a valid id with a dot
    item(d, "c2")["fade_in"] = -1
    found = V(d)
    by_rule = {p["rule"]: p for p in found}
    assert by_rule["bad_rational"]["path"] == "/media/m.1/fps" and "id" not in by_rule["bad_rational"]
    assert _resolve_pointer(d, "/media/m.1/fps") == 29.97
    neg = by_rule["negative_time"]
    assert neg["path"] == "/tracks/2/items/1/fade_in" and neg["id"] == "c2"
    assert _resolve_pointer(d, neg["path"]) == -1


@pytest.mark.parametrize("key,ptr", [("m/1", "/media/m~11"), ("m~1", "/media/m~01")])
def test_media_key_with_slash_or_tilde_is_a_bad_id_at_an_escaped_path(key, ptr):
    d = doc()
    d["media"][key] = {"path": "x.mp4", "dur": S, "fps": None}
    assert {"rule": "bad_id", "path": ptr} == {k: v for k, v in V(d)[0].items() if k in ("rule", "path")}
    assert _resolve_pointer(d, ptr) == d["media"][key]


@pytest.mark.parametrize("mutate,rule,path,iid", [
    (lambda d: item(d, "c3").update(at=17 * S), "overlap", "/tracks/2/items/3", "c3"),
    (lambda d: item(d, "t1")["anchor"].update(to="zz"), "anchor_target_missing", "/tracks/1/items/0/anchor/to", "t1"),
    (lambda d: item(d, "x1").update(dur=1), "transition_overlap_mismatch", "/tracks/2/items/2/dur", "x1"),
    (lambda d: item(d, "mu1").update(fade_in=40 * S), "fade_too_long", "/tracks/4/items/0", "mu1"),
    (lambda d: item(d, "a1").update(colour=1), "unknown_field", "/tracks/3/items/0/colour", "a1"),
    (lambda d: d["markers"][0].update(at=1.0), "not_integer_ticks", "/markers/0/at", "k2"),
    (lambda d: d["markers"][1].update(id="k2"), "duplicate_id", "/markers/1", None),
    (lambda d: d["media"]["m1"].update(dur=0), "empty_range", "/media/m1/dur", None),
    (lambda d: d["tracks"][0].update(role="b-roll"), "bad_track_role", "/tracks/0/role", None),
    (lambda d: d.update(fps=[11, 1]), "bad_fps", "/fps", None),
])
def test_problems_in_an_item_or_marker_carry_its_id(mutate, rule, path, iid):
    d = doc()
    mutate(d)
    p = next(p for p in V(d) if p["rule"] == rule)
    assert p["path"] == path
    assert p.get("id") == iid and (("id" in p) == (iid is not None))


def test_exactly_one_main_track_surfaces_as_three_rules():
    d = doc()
    d["tracks"].remove(track(d, "V1"))
    assert "missing_main_track" in rules(d)
    d = doc()
    d["tracks"].insert(2, {"id": "V2", "role": "main", "items": []})
    assert "bad_track_id" in rules(d)
    d = doc()
    d["tracks"].insert(2, {"id": "V1", "role": "main", "items": []})
    assert "duplicate_id" in rules(d)


def test_bad_id_never_carries_an_id():
    d = doc()
    item(d, "c2")["id"] = "c 2"
    p = next(p for p in V(d) if p["rule"] == "bad_id")
    assert p["path"] == "/tracks/2/items/1/id" and "id" not in p and "'c 2'" in p["message"]


def test_duplicate_id_has_no_id_and_points_at_the_second_copy():
    d = doc()
    track(d, "A1")["items"].append({"id": "c2", "type": "clip", "media": "m1", "src": [0, S], "at": 100 * S,
                                    "fade_in": 0, "fade_out": 0})
    dup = [p for p in V(d) if p["rule"] == "duplicate_id"]
    assert len(dup) == 1 and dup[0]["path"] == "/tracks/3/items/1" and "id" not in dup[0]
    assert "'c2'" in dup[0]["message"] and "/tracks/2/items/1" in dup[0]["message"]  # names the first copy


def test_other_problems_on_a_duplicated_or_malformed_id_carry_no_id():
    d = doc()
    track(d, "A1")["items"].append({"id": "c2", "type": "clip", "media": "m1", "src": [0, S], "at": 100 * S,
                                    "fade_in": S, "fade_out": S})  # duplicated id, and fades > 1 s
    fade = next(p for p in V(d) if p["rule"] == "fade_too_long")
    assert fade["path"] == "/tracks/3/items/1" and "id" not in fade
    d = doc()
    item(d, "a1").update(id="a 1", fade_in=9 * S)  # malformed id
    fade = next(p for p in V(d) if p["rule"] == "fade_too_long")
    assert "id" not in fade
    d = doc()
    d["media"]["a1"] = {"path": "x", "dur": S, "fps": None}  # an item id that clashes with a media key
    item(d, "a1")["fade_in"] = 9 * S
    assert "id" not in next(p for p in V(d) if p["rule"] == "fade_too_long")


def test_a_fade_error_on_a_normal_item_keeps_its_id():
    d = doc()
    item(d, "a1")["fade_in"] = 9 * S
    fade = next(p for p in V(d) if p["rule"] == "fade_too_long")
    assert fade == {"rule": "fade_too_long", "path": "/tracks/3/items/0", "id": "a1",
                    "message": "fade_in + fade_out must not exceed the item's duration"}


def test_three_copies_of_an_id_give_two_duplicate_id_errors():
    d = doc()
    for tid in ("A1", "A2"):
        track(d, tid)["items"].append({"id": "c2", "type": "clip", "media": "m1", "src": [0, S], "at": 150 * S,
                                       "fade_in": 0, "fade_out": 0})
    dup = [p for p in V(d) if p["rule"] == "duplicate_id"]
    assert [p["path"] for p in dup] == ["/tracks/3/items/1", "/tracks/4/items/2"]
    assert all("id" not in p and "/tracks/2/items/1" in p["message"] for p in dup)
