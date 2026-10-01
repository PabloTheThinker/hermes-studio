"""Op log: the only way a timeline changes (docs/oplog.md has the full spec).

Every write goes through :meth:`Oplog.call` with a :class:`Session`. MCP, HTTP and ACP all resolve
their token to a Session and call it; nothing else in the engine writes the timeline. One call
is one atomic batch: every op applies and the result validates (``hermes_studio.timeline``), or
nothing changes and nothing is logged. Each applied batch appends one line to ``oplog.jsonl``::

    seq, op_id, client_op_id, group_id, actor, summary, base_version, new_version, hash,
    ops, inverse, changed_ids, undoes  (+ step, on agent ops whose session has a plan step)

``actor`` comes from the Session (the token), and ``step`` from the session's plan context, only
for agent sessions. An ``actor`` or ``step`` passed in the call's args, or in any op, is dropped
and reported as an ``ignored_field`` warning. The engine computes every inverse when it applies
an op. Undo and redo append a new entry (``undoes``); history is never rewritten.

Times are integer ticks (``timeline.TICK_RATE``); the tool layer converts seconds once with
``timeline.seconds_to_ticks`` before calling in.
"""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from hermes_studio import timeline as T
from hermes_studio.api import EXIT, HermesStudioError

ACTOR_KINDS = ("human", "agent")
FORGED_FIELDS = ("actor", "step")  # never taken from args: the session decides both
MAX_OPS = 500
SUMMARY_MAX = 200
CLIENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
LINE_FIELDS = ("seq", "op_id", "client_op_id", "group_id", "actor", "summary", "base_version", "new_version",
               "hash", "ops", "inverse", "changed_ids", "undoes")
LINE_OPTIONAL = ("step",)

# --------------------------------------------------------------------------- sessions


@dataclass(frozen=True)
class Actor:
    """Who a session acts for: ``kind`` is human or agent, ``id`` names them (e.g. ``hermes``)."""

    kind: str
    id: str

    def __post_init__(self) -> None:
        if self.kind not in ACTOR_KINDS:
            raise ValueError(f"actor kind must be one of {ACTOR_KINDS}")
        if not (isinstance(self.id, str) and T.ID_RE.fullmatch(self.id)):
            raise ValueError(f"actor id must match {T.ID_RE.pattern}")

    def as_dict(self) -> dict:
        return {"kind": self.kind, "id": self.id}


class PlanContext:
    """The plan an agent session is working through. The session layer (ACP, for Hermes) sets
    ``step`` as the agent moves through its plan; the engine reads it when it logs an agent op."""

    def __init__(self, step: int | None = None) -> None:
        self.step = step

    @property
    def step(self) -> int | None:
        return self._step

    @step.setter
    def step(self, v: int | None) -> None:
        if v is not None and not (T._is_int(v) and v >= 1):
            raise ValueError("a plan step is an integer >= 1, or None")
        self._step = v


@dataclass(frozen=True)
class Session:
    """The engine-side context a token resolves to. Only this decides ``actor`` and ``step``."""

    actor: Actor
    plan: PlanContext | None = None

    def step(self) -> int | None:
        """The plan step to log: only for agents, and only from the plan context."""
        if self.actor.kind != "agent" or self.plan is None:
            return None
        return self.plan.step


# --------------------------------------------------------------------------- errors

_EXIT_AS = {"invalid_op": "bad_input", "not_found": "not_found", "conflict": "failed", "undo_blocked": "failed"}


class OplogError(HermesStudioError):
    """A refused write. ``code`` is invalid_op, not_found, conflict or undo_blocked; the extra
    fields (op_index, rule, path, id, problems, current_version, history_diff, op_ids, reason)
    are in :meth:`as_dict`. Nothing was applied or logged."""

    def __init__(self, code: str, message: str, *, hint: str = "", **extra: Any) -> None:
        super().__init__(message, code=_EXIT_AS[code], hint=hint)
        self.code = code
        self.extra = extra

    @property
    def exit_code(self) -> int:
        return EXIT[_EXIT_AS[self.code]]

    def as_dict(self) -> dict:
        d = super().as_dict()
        d.update(self.extra)
        return d


class _OpError(Exception):
    def __init__(self, rule: str, message: str, key: str | None = None, *, code: str = "invalid_op") -> None:
        super().__init__(message)
        self.rule, self.message, self.key, self.code = rule, message, key, code


# --------------------------------------------------------------------------- doc helpers


def _find(d: dict, iid: Any) -> tuple[dict, int, dict]:
    for tr in d["tracks"]:
        for i, it in enumerate(tr["items"]):
            if it.get("id") == iid:
                return tr, i, it
    raise _OpError("not_found", f"no item {iid!r}", "id", code="not_found")


def _track(d: dict, tid: Any) -> tuple[int, dict]:
    for i, tr in enumerate(d["tracks"]):
        if tr["id"] == tid:
            return i, tr
    raise _OpError("not_found", f"no track {tid!r}", "track", code="not_found")


def _start(d: dict, it: dict) -> int:
    if "at" in it:
        return it["at"]
    _, _, tgt = _find(d, it["anchor"]["to"])
    return tgt["at"] + it["anchor"]["offset"]


def _dur(it: dict) -> int:
    try:
        return T.item_duration(it)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError) as e:
        raise _OpError("bad_arg", f"{it.get('id')!r} has no usable duration") from e


def _speed(it: dict) -> Fraction:
    sp = it.get("props", {}).get("speed", [1, 1])
    return Fraction(sp[0], sp[1])


def _whole(x: Fraction, what: str) -> int:
    if x.denominator != 1:
        raise _OpError("non_integer_duration", f"{what} is not a whole number of ticks at this speed")
    return int(x)


def _shift(d: dict, ids: list[str], by: int) -> None:
    for iid in ids:
        _, _, it = _find(d, iid)
        if "at" not in it:
            raise _OpError("bad_arg", f"{iid!r} is anchored and can't be shifted")
        it["at"] += by


def _later(d: dict, tr: dict, after: int, skip: str) -> list[str]:
    """Ids of the items on ``tr`` with their own ``at`` at or after ``after`` (ripple targets)."""
    return sorted(it["id"] for it in tr["items"] if it["id"] != skip and "at" in it and it["at"] >= after)


def _id_map(d: dict) -> dict[tuple[str, str], str]:
    """Everything with an id, as canonical JSON, for working out changed_ids. An item's entry
    holds its track, its stored JSON and its RESOLVED (start, end), so an anchored item whose
    target moved, or whose end moved with it, counts as changed even though its JSON didn't."""
    out: dict[tuple[str, str], str] = {}

    def j(v: Any) -> str:
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    try:
        spans = T.resolve(d)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError):
        spans = {}  # only a valid doc resolves; both sides of a commit are valid
    for k, m in d.get("media", {}).items():
        out[("media", k)] = j(m)
    for tr in d["tracks"]:
        out[("track", tr["id"])] = j({k: v for k, v in tr.items() if k != "items"})
        for it in tr["items"]:
            out[("item", it["id"])] = j([tr["id"], it, spans.get(it["id"])])
    for mk in d["markers"]:
        out[("marker", mk["id"])] = j(mk)
    return out


def changed_ids(before: dict, after: dict) -> list[str]:
    """Ids added, removed or changed between two docs (media, tracks, items, markers), sorted.
    Items are compared by stored state AND resolved start/end, so items that move because their
    anchor target moved are included. Undo's dependents check uses this same set."""
    a, b = _id_map(before), _id_map(after)
    return sorted({k[1] for k in a.keys() | b.keys() if a.get(k) != b.get(k)})


# --------------------------------------------------------------------------- ops
#
# Each op mutates the working doc and returns its inverse as a list of ops (applied in order).
# Public ops are what callers send; internal ops only appear in inverses (and so in undo entries).


def _need_ticks(a: dict, k: str, *, signed: bool = False) -> int:
    v = a[k]
    if not T._is_int(v):
        raise _OpError("not_integer_ticks", f"'{k}' must be integer ticks", k)
    if not signed and v < 0:
        raise _OpError("negative_time", f"'{k}' must not be negative", k)
    return v


def _need_id(a: dict, k: str) -> str:
    v = a[k]
    if not (isinstance(v, str) and T.ID_RE.fullmatch(v)):
        raise _OpError("bad_id", f"'{k}' must be an id matching {T.ID_RE.pattern}", k)
    return v


def _need_bool(a: dict, k: str) -> bool:
    v = a.get(k, False)
    if not isinstance(v, bool):
        raise _OpError("bad_arg", f"'{k}' must be true or false", k)
    return v


def _new_id(ctx: _Ctx, a: dict, prefix: str) -> str:
    if "id" in a:
        iid = _need_id(a, "id")
        if iid in ctx.taken(ctx.doc):
            raise _OpError("duplicate_id", f"id {iid!r} is already used", "id")
        return iid
    a["id"] = ctx.fresh(prefix)
    return a["id"]


def _timed(a: dict, item: dict) -> None:
    if "anchor" in a:
        item["anchor"] = copy.deepcopy(a["anchor"])
    if "at" in a:
        item["at"] = _need_ticks(a, "at")


def op_insert_clip(ctx: _Ctx, a: dict) -> list[dict]:
    _, tr = _track(ctx.doc, a["track"])
    iid = _new_id(ctx, a, "c")
    it = {"id": iid, "type": "clip", "media": a["media"], "src": copy.deepcopy(a["src"]),
          "fade_in": a.get("fade_in", 0), "fade_out": a.get("fade_out", 0)}
    _timed(a, it)
    if "props" in a:
        it["props"] = copy.deepcopy(a["props"])
    a.setdefault("fade_in", 0)
    a.setdefault("fade_out", 0)
    tr["items"].append(it)
    return [{"op": "delete_item", "id": iid}]


def op_add_text(ctx: _Ctx, a: dict) -> list[dict]:
    a.setdefault("track", next((t["id"] for t in ctx.doc["tracks"] if t["role"] == "text"), "T1"))
    _, tr = _track(ctx.doc, a["track"])
    iid = _new_id(ctx, a, "x")
    it = {"id": iid, "type": "text", "dur": a["dur"], "text": a["text"], "style": a["style"],
          "fade_in": a.setdefault("fade_in", 0), "fade_out": a.setdefault("fade_out", 0)}
    _timed(a, it)
    tr["items"].append(it)
    return [{"op": "delete_item", "id": iid}]


def op_add_transition(ctx: _Ctx, a: dict) -> list[dict]:
    a.setdefault("track", T.MAIN_TRACK)
    a.setdefault("kind", "xfade")
    _, tr = _track(ctx.doc, a["track"])
    iid = _new_id(ctx, a, "tr")
    tr["items"].append({"id": iid, "type": "transition", "kind": a["kind"], "between": copy.deepcopy(a["between"]),
                        "dur": a["dur"]})
    return [{"op": "delete_item", "id": iid}]


def op_add_marker(ctx: _Ctx, a: dict) -> list[dict]:
    iid = _new_id(ctx, a, "mk")
    ctx.doc["markers"].append({"id": iid, "at": a["at"], "label": a["label"]})
    return [{"op": "remove_marker", "id": iid}]


def op_remove_marker(ctx: _Ctx, a: dict) -> list[dict]:
    ms = ctx.doc["markers"]
    for i, mk in enumerate(ms):
        if mk["id"] == a["id"]:
            del ms[i]
            return [{"op": "insert_marker", "index": i, "marker": mk}]
    raise _OpError("not_found", f"no marker {a['id']!r}", "id", code="not_found")


def op_insert_marker(ctx: _Ctx, a: dict) -> list[dict]:
    ctx.doc["markers"].insert(a["index"], copy.deepcopy(a["marker"]))
    return [{"op": "remove_marker", "id": a["marker"]["id"]}]


def op_add_track(ctx: _Ctx, a: dict) -> list[dict]:
    role = a["role"]
    if not isinstance(role, str) or role not in T.ROLES:  # S1's role rule: a non-string is bad_track_role
        raise _OpError("bad_track_role", f"role must be one of {', '.join(T.ROLE_ORDER)}", "role")
    letter = T.ROLES[role][0]
    if "id" in a:
        tid = _need_id(a, "id")
        if tid in ctx.taken(ctx.doc):
            raise _OpError("duplicate_id", f"id {tid!r} is already used", "id")
    else:
        tid = a["id"] = ctx.fresh(letter)  # first free, never an id that ever existed in the log
    ts = ctx.doc["tracks"]
    new = {"id": tid, "role": role, "items": []}
    try:
        key = T._track_key((role, tid))
        at = next((i for i, t in enumerate(ts) if T._track_key((t["role"], t["id"])) > key), len(ts))
    except (ValueError, KeyError):
        at = len(ts)  # an invalid id; the validator reports it
    ts.insert(at, new)
    return [{"op": "remove_track", "id": tid}]


def op_remove_track(ctx: _Ctx, a: dict) -> list[dict]:
    i, tr = _track(ctx.doc, a["id"])
    del ctx.doc["tracks"][i]
    return [{"op": "insert_track", "index": i, "track": tr}]


def op_insert_track(ctx: _Ctx, a: dict) -> list[dict]:
    ctx.doc["tracks"].insert(a["index"], copy.deepcopy(a["track"]))
    return [{"op": "remove_track", "id": a["track"]["id"]}]


def op_delete_item(ctx: _Ctx, a: dict) -> list[dict]:
    tr, i, it = _find(ctx.doc, a["id"])
    del tr["items"][i]
    return [{"op": "insert_item", "track": tr["id"], "index": i, "item": it}]


def op_insert_item(ctx: _Ctx, a: dict) -> list[dict]:
    _, tr = _track(ctx.doc, a["track"])
    tr["items"].insert(a["index"], copy.deepcopy(a["item"]))
    return [{"op": "delete_item", "id": a["item"]["id"]}]


_SETTABLE = ("at", "anchor", "src", "dur", "fade_in", "fade_out", "props", "text", "style", "split_from")


def op_set_fields(ctx: _Ctx, a: dict) -> list[dict]:
    _, _, it = _find(ctx.doc, a["id"])
    sets, unset = a.get("set", {}), a.get("unset", [])
    if not set(sets) | set(unset) <= set(_SETTABLE):
        raise _OpError("bad_arg", "set_fields only changes item fields", "set")
    old_set = {k: copy.deepcopy(it[k]) for k in list(sets) + list(unset) if k in it}
    old_unset = sorted(k for k in list(sets) + list(unset) if k not in it)
    for k in unset:
        it.pop(k, None)
    for k, v in sets.items():
        it[k] = copy.deepcopy(v)
    return [{"op": "set_fields", "id": a["id"], "set": old_set, "unset": old_unset}]


def _set(ctx: _Ctx, iid: str, sets: dict, unset: list[str] = ()) -> list[dict]:
    return op_set_fields(ctx, {"id": iid, "set": sets, "unset": list(unset)})


def op_shift_items(ctx: _Ctx, a: dict) -> list[dict]:
    _shift(ctx.doc, a["ids"], a["by"])
    return [{"op": "shift_items", "ids": list(a["ids"]), "by": -a["by"]}]


def op_move_clip(ctx: _Ctx, a: dict) -> list[dict]:
    _, _, it = _find(ctx.doc, a["id"])
    if "at" not in it:
        raise _OpError("bad_arg", f"{a['id']!r} has no 'at' (anchored or a transition); use set_anchor", "id")
    old = it["at"]
    it["at"] = _need_ticks(a, "at")
    return [{"op": "move_clip", "id": a["id"], "at": old}]


def op_trim_clip(ctx: _Ctx, a: dict) -> list[dict]:
    tr, _, it = _find(ctx.doc, a["id"])
    ripple = _need_bool(a, "ripple")
    keys = {"src_in", "src_out"} if it["type"] == "clip" else {"dur"} if it["type"] == "text" else set()
    given = {k for k in ("src_in", "src_out", "dur") if k in a}
    if not given or not given <= keys:
        raise _OpError("bad_arg", f"trim a {it['type']} with {' / '.join(sorted(keys)) or 'nothing'}", "id")
    start, old_dur = _start(ctx.doc, it), _dur(it)
    sets: dict[str, Any] = {}
    move = 0
    if it["type"] == "clip":
        i0, o0 = it["src"]
        i1 = _need_ticks(a, "src_in") if "src_in" in a else i0
        o1 = _need_ticks(a, "src_out") if "src_out" in a else o0
        sp = _speed(it)
        new_dur = _whole(Fraction(o1 - i1) / sp, "the trimmed duration")
        sets["src"] = [i1, o1]
        if not ripple:
            move = _whole(Fraction(i1 - i0) / sp, "the trim at the start")
    else:
        new_dur = sets["dur"] = _need_ticks(a, "dur")
    if move and "at" in it:
        sets["at"] = it["at"] + move
    elif move:
        sets["anchor"] = {**it["anchor"], "offset": it["anchor"]["offset"] + move}
    inv: list[dict] = []
    if ripple and new_dur != old_dur:
        ids = _later(ctx.doc, tr, start + old_dur, it["id"])
        if ids:
            _shift(ctx.doc, ids, new_dur - old_dur)
            inv.append({"op": "shift_items", "ids": ids, "by": old_dur - new_dur})
    return inv + _set(ctx, it["id"], sets)


def op_split_clip(ctx: _Ctx, a: dict) -> list[dict]:
    tr, idx, it = _find(ctx.doc, a["id"])
    if it["type"] == "transition" or "at" not in it:
        raise _OpError("bad_arg", f"split a clip or text item with its own 'at', not {a['id']!r}", "id")
    cut = _need_ticks(a, "at")
    start, dur = it["at"], _dur(it)
    if not start < cut < start + dur:
        raise _OpError("bad_arg", "the split point must be strictly inside the item", "at")
    off = cut - start
    if "ids" in a:
        ids = a["ids"]
        if not (isinstance(ids, list) and len(ids) == 2 and all(isinstance(x, str) and T.ID_RE.fullmatch(x) for x in ids)
                and ids[0] != ids[1]):
            raise _OpError("bad_id", "ids must be two different ids", "ids")
        taken = ctx.taken(ctx.doc)
        if any(x in taken for x in ids):
            raise _OpError("duplicate_id", "a piece id is already used", "ids")
    else:
        ida = ctx.fresh("c" if it["type"] == "clip" else "x")
        ids = a["ids"] = [ida, ctx.fresh("c" if it["type"] == "clip" else "x", also=(ida,))]
    pa, pb = copy.deepcopy(it), copy.deepcopy(it)
    pa["id"], pb["id"] = ids
    pa["split_from"] = pb["split_from"] = it["id"]
    pb["at"] = cut
    if it["type"] == "clip":
        mid = it["src"][0] + _whole(off * _speed(it), "the split point")
        pa["src"], pb["src"] = [it["src"][0], mid], [mid, it["src"][1]]
    else:
        pa["dur"], pb["dur"] = off, dur - off
    pa["fade_out"], pb["fade_in"] = 0, 0
    pa["fade_in"], pb["fade_out"] = min(it["fade_in"], off), min(it["fade_out"], dur - off)
    tr["items"][idx:idx + 1] = [pa, pb]
    transitions, anchors = {}, {}
    for t2 in ctx.doc["tracks"]:
        for x in t2["items"]:
            if x["type"] == "transition" and it["id"] in x["between"]:
                transitions[x["id"]] = list(x["between"])
                x["between"] = [ids[1] if x["between"][0] == it["id"] else x["between"][0],
                                ids[0] if x["between"][1] == it["id"] else x["between"][1]]
            elif x.get("anchor", {}).get("to") == it["id"]:
                anchors[x["id"]] = copy.deepcopy(x["anchor"])
                o = x["anchor"]["offset"]
                x["anchor"] = {"to": ids[0], "offset": o} if o < off else {"to": ids[1], "offset": o - off}
    return [{"op": "join_clips", "a": ids[0], "b": ids[1], "item": it, "index": idx,
             "transitions": transitions, "anchors": anchors}]


def op_join_clips(ctx: _Ctx, a: dict) -> list[dict]:
    """Inverse of split_clip: put the original item (old id) back where it was."""
    tr, _, pa = _find(ctx.doc, a["a"])
    tr_b, _, pb = _find(ctx.doc, a["b"])
    if tr is not tr_b or pa.get("split_from") != a["item"]["id"] or pb.get("split_from") != a["item"]["id"]:
        raise _OpError("bad_arg", "join_clips needs the two pieces of one split")
    tr["items"] = [x for x in tr["items"] if x["id"] not in (a["a"], a["b"])]
    tr["items"].insert(a["index"], copy.deepcopy(a["item"]))
    for t2 in ctx.doc["tracks"]:
        for x in t2["items"]:
            if x["id"] in a["transitions"]:
                x["between"] = list(a["transitions"][x["id"]])
            elif x["id"] in a["anchors"]:
                x["anchor"] = copy.deepcopy(a["anchors"][x["id"]])
    return [{"op": "split_clip", "id": a["item"]["id"], "at": pb["at"], "ids": [a["a"], a["b"]]}]


def op_delete_clip(ctx: _Ctx, a: dict) -> list[dict]:
    """Delete an item. Transitions that touch it go with it; items anchored to it keep their place
    as an absolute ``at``. With ``ripple``, later items on its track close the hole."""
    tr, _, it = _find(ctx.doc, a["id"])
    ripple = _need_bool(a, "ripple")
    if it["type"] == "transition":
        if ripple:
            raise _OpError("bad_arg", "a transition can't be ripple-deleted", "ripple")
        return op_delete_item(ctx, {"id": it["id"]})
    start, dur = _start(ctx.doc, it), _dur(it)
    inv_anchor: list[dict] = []
    for t2 in ctx.doc["tracks"]:
        for x in t2["items"]:
            if x.get("anchor", {}).get("to") == it["id"]:
                inv_anchor += _set(ctx, x["id"], {"at": start + x["anchor"]["offset"]}, ["anchor"])
    gone = sorted(((i, x) for i, x in enumerate(tr["items"])
                   if x["id"] == it["id"] or (x["type"] == "transition" and it["id"] in x["between"])),
                  key=lambda p: p[0], reverse=True)
    for i, _ in gone:
        del tr["items"][i]
    inv_insert = [{"op": "insert_item", "track": tr["id"], "index": i, "item": x} for i, x in reversed(gone)]
    inv_shift: list[dict] = []
    if ripple:
        d_in = sum(x["dur"] for _, x in gone if x["type"] == "transition" and x["between"][1] == it["id"])
        d_out = sum(x["dur"] for _, x in gone if x["type"] == "transition" and x["between"][0] == it["id"])
        ids = _later(ctx.doc, tr, start + dur - d_out, it["id"])
        by = dur - d_in - d_out
        if ids and by:
            _shift(ctx.doc, ids, -by)
            inv_shift = [{"op": "shift_items", "ids": ids, "by": by}]
    return inv_shift + inv_insert + list(reversed(inv_anchor))


def op_set_props(ctx: _Ctx, a: dict) -> list[dict]:
    _, _, it = _find(ctx.doc, a["id"])
    if it["type"] != "clip" or not isinstance(a["props"], dict):
        raise _OpError("bad_arg", "set_props takes a clip id and a props object", "props")
    return _set(ctx, it["id"], {"props": {**it.get("props", {}), **copy.deepcopy(a["props"])}})


def op_set_fade(ctx: _Ctx, a: dict) -> list[dict]:
    _, _, it = _find(ctx.doc, a["id"])
    sets = {k: _need_ticks(a, k) for k in ("fade_in", "fade_out") if k in a}
    if it["type"] == "transition" or not sets:
        raise _OpError("bad_arg", "set_fade takes a clip or text id and fade_in and/or fade_out", "id")
    return _set(ctx, it["id"], sets)


def op_set_anchor(ctx: _Ctx, a: dict) -> list[dict]:
    _, _, it = _find(ctx.doc, a["id"])
    if a["anchor"] is None:
        if "at" not in a:
            raise _OpError("missing_arg", "clearing an anchor needs 'at'", "at")
        return _set(ctx, it["id"], {"at": _need_ticks(a, "at")}, ["anchor"])
    if "at" in a:
        raise _OpError("bad_arg", "give 'anchor' or 'at', not both", "at")
    return _set(ctx, it["id"], {"anchor": copy.deepcopy(a["anchor"])}, ["at"])


# name -> (handler, required args, optional args)
PUBLIC_OPS: dict[str, tuple[Callable, frozenset, frozenset]] = {
    "insert_clip": (op_insert_clip, frozenset({"track", "media", "src"}),
                    frozenset({"id", "at", "anchor", "fade_in", "fade_out", "props"})),
    "move_clip": (op_move_clip, frozenset({"id", "at"}), frozenset()),
    "trim_clip": (op_trim_clip, frozenset({"id"}), frozenset({"src_in", "src_out", "dur", "ripple"})),
    "split_clip": (op_split_clip, frozenset({"id", "at"}), frozenset({"ids"})),
    "delete_clip": (op_delete_clip, frozenset({"id"}), frozenset({"ripple"})),
    "set_props": (op_set_props, frozenset({"id", "props"}), frozenset()),
    "set_fade": (op_set_fade, frozenset({"id"}), frozenset({"fade_in", "fade_out"})),
    "set_anchor": (op_set_anchor, frozenset({"id", "anchor"}), frozenset({"at"})),
    "add_text": (op_add_text, frozenset({"dur", "text", "style"}),
                 frozenset({"id", "track", "at", "anchor", "fade_in", "fade_out"})),
    "add_transition": (op_add_transition, frozenset({"between", "dur"}), frozenset({"id", "track", "kind"})),
    "add_track": (op_add_track, frozenset({"role"}), frozenset({"id"})),
    "remove_track": (op_remove_track, frozenset({"id"}), frozenset()),
    "add_marker": (op_add_marker, frozenset({"at", "label"}), frozenset({"id"})),
    "remove_marker": (op_remove_marker, frozenset({"id"}), frozenset()),
}
INTERNAL_OPS: dict[str, tuple[Callable, frozenset, frozenset]] = {
    "set_fields": (op_set_fields, frozenset({"id"}), frozenset({"set", "unset"})),
    "shift_items": (op_shift_items, frozenset({"ids", "by"}), frozenset()),
    "delete_item": (op_delete_item, frozenset({"id"}), frozenset()),
    "insert_item": (op_insert_item, frozenset({"track", "index", "item"}), frozenset()),
    "insert_marker": (op_insert_marker, frozenset({"index", "marker"}), frozenset()),
    "insert_track": (op_insert_track, frozenset({"index", "track"}), frozenset()),
    "join_clips": (op_join_clips, frozenset({"a", "b", "item", "index", "transitions", "anchors"}), frozenset()),
}


class _Ctx:
    def __init__(self, doc: dict, retired: set[str]) -> None:
        self.doc = doc
        self.retired = retired  # ids used earlier in the log: never handed out again
        self._handed: set[str] = set()

    def taken(self, d: dict) -> set[str]:
        return set(T._all_ids(d))

    def fresh(self, prefix: str, also: tuple[str, ...] = ()) -> str:
        used = self.taken(self.doc) | self.retired | self._handed | set(also)
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        self._handed.add(f"{prefix}{n}")
        return f"{prefix}{n}"


def _apply_one(ctx: _Ctx, op: Any, internal: bool) -> tuple[dict, list[dict]]:
    if not isinstance(op, dict) or not isinstance(op.get("op"), str):
        raise _OpError("bad_arg", "an op is an object with an 'op' name")
    table = {**PUBLIC_OPS, **INTERNAL_OPS} if internal else PUBLIC_OPS
    if op["op"] not in table:
        raise _OpError("unknown_op", f"unknown op {op['op']!r}", "op")
    fn, req, opt = table[op["op"]]
    a = copy.deepcopy(op)
    for k in sorted(set(a) - req - opt - {"op"}):
        raise _OpError("unknown_arg", f"{op['op']} takes no '{k}'", k)
    for k in sorted(req - set(a)):
        raise _OpError("missing_arg", f"{op['op']} needs '{k}'", k)
    try:
        inv = fn(ctx, a)
    except _OpError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, ZeroDivisionError) as e:
        raise _OpError("bad_arg", f"{op['op']}: malformed arguments ({type(e).__name__})") from e
    return a, inv


# --------------------------------------------------------------------------- the log


def _check_line(e: Any) -> dict:
    if not (isinstance(e, dict) and set(LINE_FIELDS) <= set(e) <= set(LINE_FIELDS) | set(LINE_OPTIONAL)):
        raise ValueError("not an oplog line")
    return e


class Oplog:
    """The op log of one timeline, and the one way to change it: :meth:`call`.

    ``base`` is the version the log starts from (a valid doc, normally ``version`` 0). With
    ``path``, every entry is appended to that ``oplog.jsonl`` (flushed and fsynced) before it
    takes effect; a failed write leaves the timeline and the log unchanged."""

    def __init__(self, base: dict, *, path: str | os.PathLike | None = None,
                 new_op_id: Callable[[], str] | None = None) -> None:
        self._base, _ = T.stamp_hash(base)
        self._doc = copy.deepcopy(self._base)
        self._entries: list[dict] = []
        self._results: dict[tuple[str, str, str], dict] = {}
        self._retired: set[str] = set(T._all_ids(self._doc))
        self._path = os.fspath(path) if path is not None else None
        self._new_op_id = new_op_id or (lambda: "op-" + secrets.token_hex(8))

    # ---- reads

    @property
    def doc(self) -> dict:
        """A copy of the current timeline (valid, with ``version`` and ``hash``)."""
        return copy.deepcopy(self._doc)

    @property
    def version(self) -> int:
        return self._doc["version"]

    def history_list(self, since_version: int = 0) -> list[dict]:
        """Copies of the entries with ``new_version`` > ``since_version``, oldest first."""
        return [copy.deepcopy(e) for e in self._entries if e["new_version"] > since_version]

    def history_diff(self, since_version: int) -> list[dict]:
        """What changed after ``since_version``: one short record per entry (no ops)."""
        keep = ("seq", "op_id", "group_id", "actor", "step", "summary", "base_version", "new_version", "changed_ids",
                "undoes")
        return [{k: copy.deepcopy(e[k]) for k in keep if k in e} for e in self._entries
                if e["new_version"] > since_version]

    # ---- the single entry point

    def call(self, session: Session, tool: str, args: Any) -> dict:
        """Run one write tool for ``session``: ``timeline_apply``, ``history_undo`` or
        ``history_redo``. MCP, HTTP and ACP all come in here. Returns the write result, or raises
        OplogError with nothing applied. ``actor`` and ``step`` in ``args`` (or in any op) are
        ignored: they come from ``session`` alone."""
        if not isinstance(session, Session):
            raise TypeError("call() needs the Session the caller's token resolves to")
        if not isinstance(args, dict):
            raise OplogError("invalid_op", "args must be an object", rule="bad_arg", path="")
        args, warnings = _strip_forged(args)
        if tool == "timeline_apply":
            return self._apply(session, args, warnings)
        if tool in ("history_undo", "history_redo"):
            return self._undo(session, args, warnings, redo=tool == "history_redo")
        raise OplogError("invalid_op", f"unknown write tool {tool!r}", rule="unknown_tool", path="")

    # ---- internals

    def _check_args(self, args: dict, required: set[str], optional: set[str]) -> None:
        for k in sorted(set(args) - required - optional):
            raise OplogError("invalid_op", f"unknown argument '{k}'", rule="unknown_arg", path=T._j("", k))
        for k in sorted(required - set(args)):
            raise OplogError("invalid_op", f"'{k}' is required", rule="missing_arg", path=T._j("", k))
        cid = args["client_op_id"]
        if not (isinstance(cid, str) and CLIENT_ID_RE.fullmatch(cid)):
            raise OplogError("invalid_op", f"client_op_id must match {CLIENT_ID_RE.pattern}", rule="bad_arg",
                             path="/client_op_id")
        for k in ("group_id", "op_id"):
            if args.get(k) is not None and not (isinstance(args[k], str) and CLIENT_ID_RE.fullmatch(args[k])):
                raise OplogError("invalid_op", f"{k} must match {CLIENT_ID_RE.pattern}", rule="bad_arg",
                                 path=T._j("", k))
        if "summary" in args:
            s = args["summary"]
            if not (isinstance(s, str) and s.strip() and len(s) <= SUMMARY_MAX and _utf8(s)
                    and unicodedata.normalize("NFC", s) == s):
                raise OplogError("invalid_op", f"summary must be a non-empty NFC string of at most {SUMMARY_MAX} chars",
                                 rule="bad_arg", path="/summary")
        if "project_id" in args and args["project_id"] != self._doc["id"]:
            raise OplogError("not_found", f"no project {args['project_id']!r} here", rule="not_found",
                             path="/project_id", id=str(args["project_id"]))

    def _base_version(self, args: dict, *, required: bool) -> None:
        if "base_version" not in args and not required:
            return
        bv = args["base_version"]
        if not (T._is_int(bv) and bv >= 0):
            raise OplogError("invalid_op", "base_version must be an integer >= 0", rule="bad_arg", path="/base_version")
        if bv != self.version:
            raise OplogError("conflict", f"the timeline is at version {self.version}, not {bv}",
                             hint="Read the history_diff, then retry against current_version.",
                             current_version=self.version, history_diff=self.history_diff(min(bv, self.version)))

    def _replayed(self, session: Session, args: dict) -> dict | None:
        r = self._results.get((session.actor.kind, session.actor.id, args["client_op_id"]))
        return copy.deepcopy(r) if r is not None else None

    def _run(self, ops: list, *, internal: bool, base: dict | None = None) -> tuple[dict, list[dict], list[dict]]:
        """Apply ``ops`` to a copy of the doc; return (new doc, logged ops, inverse) or raise."""
        start = base if base is not None else self._doc
        ctx = _Ctx(copy.deepcopy(start), self._retired)
        logged: list[dict] = []
        inverse: list[dict] = []
        for k, op in enumerate(ops):
            try:
                a, inv = _apply_one(ctx, op, internal)
            except _OpError as e:
                raise OplogError(e.code, f"op {k}: {e.message}", rule=e.rule, op_index=k,
                                 path=T._j("", "ops", k, *([e.key] if e.key else []))) from None
            logged.append(a)
            inverse = inv + inverse
        new = ctx.doc
        new["version"] = start["version"] + 1
        new.pop("hash", None)
        found = T.validate(new)
        if found:
            raise OplogError("invalid_op", f"the timeline after these ops is invalid: {found[0]['message']}",
                             hint=T._HINTS.get(found[0]["rule"], ""), op_index=self._first_bad(ops, internal, start),
                             rule=found[0]["rule"], path=found[0]["path"],
                             **({"id": found[0]["id"]} if "id" in found[0] else {}), problems=found)
        new, _ = T.stamp_hash(new)
        return new, logged, inverse

    def _first_bad(self, ops: list, internal: bool, start: dict) -> int:
        """The first op after which the doc stops validating (only worked out on failure)."""
        ctx = _Ctx(copy.deepcopy(start), self._retired)
        for k, op in enumerate(ops):
            _apply_one(ctx, op, internal)
            d = dict(ctx.doc)
            d.pop("hash", None)
            if T.validate(d):
                return k
        return len(ops) - 1

    def _commit(self, session: Session, args: dict, new: dict, logged: list, inverse: list,
                undoes: list[str] | None, summary: str, warnings: list[dict]) -> dict:
        entry: dict[str, Any] = {
            "seq": len(self._entries) + 1, "op_id": self._new_op_id(), "client_op_id": args["client_op_id"],
            "group_id": args.get("group_id"), "actor": session.actor.as_dict(), "summary": summary,
            "base_version": self.version, "new_version": new["version"], "hash": new["hash"], "ops": logged,
            "inverse": inverse, "changed_ids": changed_ids(self._doc, new), "undoes": undoes,
        }
        step = session.step()
        if step is not None:
            entry["step"] = step
        if self._path is not None:
            line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        self._entries.append(entry)
        self._retired |= set(T._all_ids(new))
        self._doc = new
        result = _result(entry, warnings)
        self._results[(session.actor.kind, session.actor.id, args["client_op_id"])] = result
        return copy.deepcopy(result)

    def _apply(self, session: Session, args: dict, warnings: list[dict]) -> dict:
        self._check_args(args, {"base_version", "ops", "summary", "client_op_id"}, {"project_id", "group_id"})
        done = self._replayed(session, args)
        if done is not None:
            return done
        self._base_version(args, required=True)
        ops = args["ops"]
        if not (isinstance(ops, list) and 0 < len(ops) <= MAX_OPS):
            raise OplogError("invalid_op", f"ops must be a list of 1-{MAX_OPS} ops", rule="bad_arg", path="/ops")
        new, logged, inverse = self._run(ops, internal=False)
        return self._commit(session, args, new, logged, inverse, None, args["summary"], warnings)

    def _cancelled(self) -> set[str]:
        """Entries whose effect a live undo entry has reversed (walking back, an undone undo
        cancels nothing)."""
        out: set[str] = set()
        for e in reversed(self._entries):
            if e["op_id"] not in out:
                out.update(e["undoes"] or [])
        return out

    def _undo(self, session: Session, args: dict, warnings: list[dict], *, redo: bool) -> dict:
        self._check_args(args, {"client_op_id"}, {"project_id", "op_id", "group_id", "summary", "base_version"})
        done = self._replayed(session, args)
        if done is not None:
            return done
        if ("op_id" in args) == ("group_id" in args) or (redo and "group_id" in args):
            raise OplogError("invalid_op", "give exactly one of op_id or group_id (redo takes op_id)",
                             rule="bad_arg", path="")
        self._base_version(args, required=False)
        cancelled = self._cancelled()
        if "op_id" in args:
            hit = [e for e in self._entries if e["op_id"] == args["op_id"]]
            if not hit:
                raise OplogError("not_found", f"no entry {args['op_id']!r}", rule="not_found", path="/op_id",
                                 id=args["op_id"])
            if redo and not hit[0]["undoes"]:
                raise OplogError("invalid_op", "history_redo takes the op_id of an undo entry", rule="not_an_undo",
                                 path="/op_id")
            group = [e for e in hit if e["op_id"] not in cancelled]
        else:
            hit = [e for e in self._entries if e["group_id"] == args["group_id"]]
            if not hit:
                raise OplogError("not_found", f"no group {args['group_id']!r}", rule="not_found", path="/group_id",
                                 id=args["group_id"])
            group = [e for e in hit if e["op_id"] not in cancelled]
        if not group:
            raise OplogError("invalid_op", "already undone", rule="already_undone",
                             path="/op_id" if "op_id" in args else "/group_id")
        if session.actor.kind == "agent":
            others = [e["op_id"] for e in group if e["actor"] != session.actor.as_dict()]
            if others:
                raise OplogError("undo_blocked", "an agent can only undo its own entries", reason="actor",
                                 op_ids=others, hint="Ask the person to undo it.")
        ids = {e["op_id"] for e in group}
        first = min(e["seq"] for e in group)
        seq_of = {e["op_id"]: e["seq"] for e in self._entries}
        touched = {i for e in group for i in e["changed_ids"]}
        dependents = []
        for e in self._entries:
            if e["seq"] <= first or e["op_id"] in ids or e["op_id"] in cancelled:
                continue
            if e["undoes"] and all(seq_of[t] > first for t in e["undoes"]):
                continue  # it cancels a later entry: the pair has no net effect
            if touched & set(e["changed_ids"]) or _mentions(e["ops"], touched):
                dependents.append(e["op_id"])
        if dependents:
            raise OplogError("undo_blocked", "later entries changed the same items", reason="dependents",
                             blocking_op_ids=dependents, op_ids=dependents, hint="Undo those first, or restore to before this step.")
        ops = [op for e in sorted(group, key=lambda e: -e["seq"]) for op in e["inverse"]]
        try:
            new, logged, inverse = self._run(ops, internal=True)
        except OplogError as e:
            raise OplogError("undo_blocked", "the inverse no longer applies", reason="inverse_invalid", op_ids=[],
                             problems=e.extra.get("problems", []), rule=e.extra.get("rule")) from None
        last = max(group, key=lambda e: e["seq"])
        summary = args.get("summary") or (("Redo: " if redo else "Undo: ") + last["summary"])[:SUMMARY_MAX]
        undoes = [e["op_id"] for e in sorted(group, key=lambda e: -e["seq"])]
        return self._commit(session, args, new, logged, inverse, undoes, summary, warnings)

    # ---- persistence

    @classmethod
    def load(cls, base: dict, path: str | os.PathLike, **kw: Any) -> Oplog:
        """Rebuild from ``base`` and the ``oplog.jsonl`` at ``path`` (which stays the log file).
        Every entry is replayed and must reproduce its stored ``hash`` and versions."""
        log = cls(base, **kw)
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        for e in lines:
            _check_line(e)
            if e["seq"] != len(log._entries) + 1 or e["base_version"] != log.version:
                raise ValueError(f"oplog line {e.get('seq')}: out of sequence")
            new, logged, inverse = log._run(e["ops"], internal=True)
            if new["hash"] != e["hash"] or new["version"] != e["new_version"] or inverse != e["inverse"]:
                raise ValueError(f"oplog line {e['seq']}: replay does not reproduce the entry")
            log._entries.append(e)
            log._retired |= set(T._all_ids(new))
            log._doc = new
            log._results[(e["actor"]["kind"], e["actor"]["id"], e["client_op_id"])] = _result(e, [])
        log._path = os.fspath(path)
        return log


def replay(base: dict, entries: list[dict]) -> dict:
    """The timeline after applying ``entries`` (oplog lines) to ``base``; checks every hash."""
    log = Oplog(base)
    for e in entries:
        new, _, _ = log._run(_check_line(e)["ops"], internal=True)
        if new["hash"] != e["hash"]:
            raise ValueError(f"oplog line {e['seq']}: replay gives {new['hash']}, the log says {e['hash']}")
        log._entries.append(e)
        log._retired |= set(T._all_ids(new))
        log._doc = new
    return log.doc


def _utf8(s: str) -> bool:
    """False for a string UTF-8 can't encode (a lone surrogate), which the log line can't hold."""
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


_REF_KEYS = ("id", "to", "between", "ids", "a", "b")


def _mentions(obj: Any, ids: set[str]) -> bool:
    """Does an op list refer to any of ``ids`` (as a target, anchor, transition end or piece)?"""
    if isinstance(obj, list):
        return any(_mentions(x, ids) for x in obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _REF_KEYS and (v in ids if isinstance(v, str) else
                                   isinstance(v, list) and any(isinstance(x, str) and x in ids for x in v)):
                return True
            if isinstance(v, (dict, list)) and _mentions(v, ids):
                return True
    return False


def _result(entry: dict, warnings: list[dict]) -> dict:
    r = {"ok": True, "op_id": entry["op_id"], "group_id": entry["group_id"], "seq": entry["seq"],
         "new_version": entry["new_version"], "hash": entry["hash"], "tick_rate": T.TICK_RATE,
         "summary": entry["summary"], "changed_ids": list(entry["changed_ids"]), "undoes": entry["undoes"],
         "before_frame": None, "after_frame": None, "warnings": copy.deepcopy(warnings)}
    return r


def _strip_forged(args: dict) -> tuple[dict, list[dict]]:
    """Drop ``actor``/``step`` from the args and from every op; one warning per dropped field."""
    args = dict(args)
    warnings: list[dict] = []

    def drop(obj: dict, base: str) -> dict:
        obj = dict(obj)
        for k in FORGED_FIELDS:
            if k in obj:
                del obj[k]
                warnings.append({"code": "ignored_field", "path": T._j(base, k),
                                 "message": f"'{k}' is ignored: it comes from the session, not the arguments"})
        return obj

    args = drop(args, "")
    if isinstance(args.get("ops"), list):
        args["ops"] = [drop(op, T._j("", "ops", i)) if isinstance(op, dict) else op for i, op in enumerate(args["ops"])]
    return args, warnings
