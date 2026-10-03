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
``timeline.seconds_to_ticks_nearest`` before calling in.
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
LINE_FIELDS = (
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
)
LINE_OPTIONAL = ("step", "warnings")  # warnings: result warnings only, written only when non-empty
CONFLICT_DIFF_MAX = 200  # records in a conflict body; the rest are paged with history_diff
HISTORY_LIST_LIMIT = (50, 200)  # (default, max)
HISTORY_DIFF_LIMIT = (200, 500)
ANCHOR_OPS = ("insert_clip", "add_text", "set_anchor")  # public ops that take an anchor
ANCHOR_KEYS = frozenset({"to", "offset"})

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


CHECKPOINT_EVERY = 16  # an identical retry re-runs at most this many - 1 entries (see _same_call)


def _canon(x: Any) -> str:
    """Canonical JSON, as for the log line and ``canonical_json``: sorted keys, (',', ':'),
    UTF-8 as is, no NaN or infinity."""
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class _OpError(Exception):
    def __init__(
        self,
        rule: str,
        message: str,
        key: str | tuple | None = None,
        *,
        code: str = "invalid_op",
        ident: Any = None,
        item_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule, self.message, self.key, self.code = rule, message, key, code
        self.ident = ident  # for not_found: the id that wasn't there
        self.item_id = item_id  # the one item the problem is about, like a validator problem's id


# --------------------------------------------------------------------------- doc helpers


def _find(d: dict, iid: Any) -> tuple[dict, int, dict]:
    for tr in d["tracks"]:
        for i, it in enumerate(tr["items"]):
            if it.get("id") == iid:
                return tr, i, it
    raise _OpError("not_found", f"no item {iid!r}", "id", code="not_found", ident=iid)


def _track(d: dict, tid: Any, key: str = "track") -> tuple[int, dict]:
    for i, tr in enumerate(d["tracks"]):
        if tr["id"] == tid:
            return i, tr
    raise _OpError("not_found", f"no track {tid!r}", key, code="not_found", ident=tid)


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


def _key_parts(key: str | tuple | None) -> tuple:
    return () if key is None else key if isinstance(key, tuple) else (key,)


_ID_REFS = ("id", "track")  # public-op args that hold one id
_ID_LISTS = ("between", "ids")  # public-op args that hold a list of ids


def _check_refs(a: dict) -> None:
    """Every id a public op names must be a string before any lookup, so a wrong type is
    ``bad_arg`` at the id's own path (like ``history_undo``'s ``op_id``), never ``not_found``."""

    def bad(*key: Any) -> _OpError:
        return _OpError("bad_arg", f"'{T._j('', *key)[1:]}' must be an id string", key if len(key) > 1 else key[0])

    for k in _ID_REFS:
        if k in a and not isinstance(a[k], str):
            raise bad(k)
    for k in _ID_LISTS:
        if isinstance(a.get(k), list):
            for i, v in enumerate(a[k]):
                if not isinstance(v, str):
                    raise bad(k, i)
    anchor = a.get("anchor")
    if isinstance(anchor, dict) and "to" in anchor and not isinstance(anchor["to"], str):
        raise bad("anchor", "to")


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
        ctx.not_reused(iid, "id")
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
    m = a["media"]
    if not (isinstance(m, str) and m in ctx.doc.get("media", {})):  # the op's own arg, not the doc path
        raise _OpError("unknown_media", f"no media {m!r}", "media")
    iid = _new_id(ctx, a, "c")
    it = {
        "id": iid,
        "type": "clip",
        "media": a["media"],
        "src": copy.deepcopy(a["src"]),
        "fade_in": a.get("fade_in", 0),
        "fade_out": a.get("fade_out", 0),
    }
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
    it = {
        "id": iid,
        "type": "text",
        "dur": a["dur"],
        "text": a["text"],
        "style": a["style"],
        "fade_in": a.setdefault("fade_in", 0),
        "fade_out": a.setdefault("fade_out", 0),
    }
    _timed(a, it)
    tr["items"].append(it)
    return [{"op": "delete_item", "id": iid}]


def op_add_transition(ctx: _Ctx, a: dict) -> list[dict]:
    a.setdefault("track", T.MAIN_TRACK)
    a.setdefault("kind", "xfade")
    _, tr = _track(ctx.doc, a["track"])
    iid = _new_id(ctx, a, "tr")
    tr["items"].append(
        {"id": iid, "type": "transition", "kind": a["kind"], "between": copy.deepcopy(a["between"]), "dur": a["dur"]}
    )
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
    raise _OpError("not_found", f"no marker {a['id']!r}", "id", code="not_found", ident=a["id"])


def op_edit_marker(ctx: _Ctx, a: dict) -> list[dict]:
    """Move a marker (``at``) and/or rename it (``label``); anything not given stays. The inverse
    is the same op with the old values, so one undo puts it back."""
    mk = next((m for m in ctx.doc["markers"] if m["id"] == a["id"]), None)
    if mk is None:
        raise _OpError("not_found", f"no marker {a['id']!r}", "id", code="not_found", ident=a["id"])
    if "at" not in a and "label" not in a:
        raise _OpError("missing_arg", "edit_marker needs 'at' and/or 'label'")
    if "at" in a:
        _need_ticks(a, "at")
    if "label" in a:
        c = T._Checker()
        if not c.string(a["label"], "", empty=True):
            pr = c.problems[0]
            raise _OpError(pr.rule, f"'label' {pr.message}", "label")
    inv = {"op": "edit_marker", "id": mk["id"], **{k: mk[k] for k in ("at", "label") if k in a}}
    for k in ("at", "label"):
        if k in a:
            mk[k] = a[k]
    return [inv]


def op_insert_marker(ctx: _Ctx, a: dict) -> list[dict]:
    ctx.doc["markers"].insert(a["index"], copy.deepcopy(a["marker"]))
    return [{"op": "remove_marker", "id": a["marker"]["id"]}]


def op_add_media(ctx: _Ctx, a: dict) -> list[dict]:
    """S4: a new entry in the doc's media table. The values are checked by the validator, like
    every other field (``/media/<id>/...``); the id is the caller's or the first free ``m<n>``."""
    mid = _new_id(ctx, a, "m")
    m = {"path": a["path"], "dur": a["dur"], "fps": copy.deepcopy(a["fps"])}
    if "proxy" in a:
        m["proxy"] = a["proxy"]
    ctx.doc.setdefault("media", {})[mid] = m
    return [{"op": "delete_media", "id": mid}]


def op_delete_media(ctx: _Ctx, a: dict) -> list[dict]:
    m = ctx.doc["media"].pop(a["id"])
    return [{"op": "insert_media", "id": a["id"], "media": m}]


def op_insert_media(ctx: _Ctx, a: dict) -> list[dict]:
    ctx.doc["media"][a["id"]] = copy.deepcopy(a["media"])
    return [{"op": "delete_media", "id": a["id"]}]


BODY_KEYS = ("media", "tracks", "markers")


def op_replace_body(ctx: _Ctx, a: dict) -> list[dict]:
    """Internal (Phase 2 drafts): the doc's media, tracks and markers become ``a``'s; the inverse
    puts the old ones back. Only the engine's ``keep_body`` tool logs it."""
    old = {k: copy.deepcopy(ctx.doc[k]) for k in BODY_KEYS}
    for k in BODY_KEYS:
        ctx.doc[k] = copy.deepcopy(a[k])
    return [{"op": "replace_body", **old}]


def op_add_track(ctx: _Ctx, a: dict) -> list[dict]:
    role = a["role"]
    if not isinstance(role, str) or role not in T.ROLES:  # S1's role rule: a non-string is bad_track_role
        raise _OpError("bad_track_role", f"role must be one of {', '.join(T.ROLE_ORDER)}", "role")
    letter = T.ROLES[role][0]
    if "id" in a:
        tid = _need_id(a, "id")
        if tid in ctx.taken(ctx.doc):
            raise _OpError("duplicate_id", f"id {tid!r} is already used", "id")
        ctx.not_reused(tid, "id")
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
    i, tr = _track(ctx.doc, a["id"], "id")
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
    xin = next((x for x in tr["items"] if x["type"] == "transition" and x["between"][1] == it["id"]), None)
    xout = next((x for x in tr["items"] if x["type"] == "transition" and x["between"][0] == it["id"]), None)
    if ripple and (xin or xout):
        din, dout = (xin["dur"] if xin else 0), (xout["dur"] if xout else 0)
        # Each crossfade must fit inside the clip and leave the clips in order (longer than
        # each one), and the two must not overlap each other (at least their sum).
        # Name one crossfade: one that doesn't fit on its own (the outgoing one first); else,
        # when each fits alone but not both together, the outgoing one.
        culprit = None
        if xout and new_dur <= dout:
            culprit = xout
        elif xin and new_dur <= din:
            culprit = xin
        elif new_dur < din + dout:
            culprit = xout
        if culprit is not None:
            raise _OpError(
                "transition_too_long",
                f"the trim leaves {it['id']!r} {new_dur} ticks long, too short for crossfade "
                f"{culprit['id']!r} ({culprit['dur']} ticks); it needs more than {max(din, dout)} "
                f"and at least {din + dout}",
                item_id=culprit["id"],
            )
    if ripple and new_dur != old_dur:
        # The cut is where the next clip starts: with an outgoing crossfade that's the start of
        # the overlap, so the next clip, the crossfade (it follows that clip) and everything
        # after it shift together, and the crossfade keeps its dur on the same pair.
        cut = start + old_dur - (xout["dur"] if xout else 0)
        ids = _later(ctx.doc, tr, cut, it["id"])
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
        if not (
            isinstance(ids, list)
            and len(ids) == 2
            and all(isinstance(x, str) and T.ID_RE.fullmatch(x) for x in ids)
            and ids[0] != ids[1]
        ):
            raise _OpError("bad_id", "ids must be two different ids", "ids")
        taken = ctx.taken(ctx.doc)
        for i, x in enumerate(ids):
            if x in taken:
                raise _OpError("duplicate_id", f"piece id {x!r} is already used", ("ids", i))
        for i, x in enumerate(ids):
            ctx.not_reused(x, ("ids", i))
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
    tr["items"][idx : idx + 1] = [pa, pb]
    transitions, anchors = {}, {}
    for t2 in ctx.doc["tracks"]:
        for x in t2["items"]:
            if x["type"] == "transition" and it["id"] in x["between"]:
                transitions[x["id"]] = list(x["between"])
                x["between"] = [
                    ids[1] if x["between"][0] == it["id"] else x["between"][0],
                    ids[0] if x["between"][1] == it["id"] else x["between"][1],
                ]
            elif x.get("anchor", {}).get("to") == it["id"]:
                anchors[x["id"]] = copy.deepcopy(x["anchor"])
                o = x["anchor"]["offset"]
                x["anchor"] = {"to": ids[0], "offset": o} if o < off else {"to": ids[1], "offset": o - off}
    return [
        {"op": "join_clips", "a": ids[0], "b": ids[1], "item": it, "index": idx, "transitions": transitions, "anchors": anchors}
    ]


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
    gone = sorted(
        (
            (i, x)
            for i, x in enumerate(tr["items"])
            if x["id"] == it["id"] or (x["type"] == "transition" and it["id"] in x["between"])
        ),
        key=lambda p: p[0],
        reverse=True,
    )
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


_TEXT_FIELDS = ("text", "style")  # what edit_text may change; text may be "", style may not


def op_edit_text(ctx: _Ctx, a: dict) -> list[dict]:
    """Replace a text item's ``text`` and/or ``style`` (whole strings; anything not given stays).
    Values are checked here, at ``/ops/k/text`` / ``/ops/k/style``, with the validator's own rule
    ids (``wrong_type``, ``not_nfc``): never normalised, never at the doc path."""
    _, _, it = _find(ctx.doc, a["id"])
    if it["type"] != "text":
        raise _OpError("bad_arg", f"edit_text takes a text item id; {it['id']!r} is a {it['type']}", "id", item_id=it["id"])
    if not any(k in a for k in _TEXT_FIELDS):
        raise _OpError("missing_arg", "edit_text needs 'text' and/or 'style'")
    for k in _TEXT_FIELDS:
        if k in a:
            c = T._Checker()
            if not c.string(a[k], "", empty=k == "text"):
                pr = c.problems[0]
                raise _OpError(pr.rule, f"'{k}' {pr.message}", k, item_id=it["id"])
    return _set(ctx, it["id"], {k: a[k] for k in _TEXT_FIELDS if k in a})


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
    "insert_clip": (
        op_insert_clip,
        frozenset({"track", "media", "src"}),
        frozenset({"id", "at", "anchor", "fade_in", "fade_out", "props"}),
    ),
    "move_clip": (op_move_clip, frozenset({"id", "at"}), frozenset()),
    "trim_clip": (op_trim_clip, frozenset({"id"}), frozenset({"src_in", "src_out", "dur", "ripple"})),
    "split_clip": (op_split_clip, frozenset({"id", "at"}), frozenset({"ids"})),
    "delete_clip": (op_delete_clip, frozenset({"id"}), frozenset({"ripple"})),
    "set_props": (op_set_props, frozenset({"id", "props"}), frozenset()),
    "set_fade": (op_set_fade, frozenset({"id"}), frozenset({"fade_in", "fade_out"})),
    "set_anchor": (op_set_anchor, frozenset({"id", "anchor"}), frozenset({"at"})),
    "edit_text": (op_edit_text, frozenset({"id"}), frozenset({"text", "style"})),
    "add_text": (
        op_add_text,
        frozenset({"dur", "text", "style"}),
        frozenset({"id", "track", "at", "anchor", "fade_in", "fade_out"}),
    ),
    "add_transition": (op_add_transition, frozenset({"between", "dur"}), frozenset({"id", "track", "kind"})),
    "add_track": (op_add_track, frozenset({"role"}), frozenset({"id"})),
    "remove_track": (op_remove_track, frozenset({"id"}), frozenset()),
    "add_marker": (op_add_marker, frozenset({"at", "label"}), frozenset({"id"})),
    "remove_marker": (op_remove_marker, frozenset({"id"}), frozenset()),
    "edit_marker": (op_edit_marker, frozenset({"id"}), frozenset({"at", "label"})),
    "add_media": (op_add_media, frozenset({"path", "dur", "fps"}), frozenset({"id", "proxy"})),
}
INTERNAL_OPS: dict[str, tuple[Callable, frozenset, frozenset]] = {
    "set_fields": (op_set_fields, frozenset({"id"}), frozenset({"set", "unset"})),
    "shift_items": (op_shift_items, frozenset({"ids", "by"}), frozenset()),
    "delete_item": (op_delete_item, frozenset({"id"}), frozenset()),
    "insert_item": (op_insert_item, frozenset({"track", "index", "item"}), frozenset()),
    "insert_marker": (op_insert_marker, frozenset({"index", "marker"}), frozenset()),
    "insert_track": (op_insert_track, frozenset({"index", "track"}), frozenset()),
    "replace_body": (op_replace_body, frozenset(BODY_KEYS), frozenset()),
    "delete_media": (op_delete_media, frozenset({"id"}), frozenset()),
    "insert_media": (op_insert_media, frozenset({"id", "media"}), frozenset()),
    "join_clips": (op_join_clips, frozenset({"a", "b", "item", "index", "transitions", "anchors"}), frozenset()),
}


class _Ctx:
    def __init__(self, doc: dict, retired: set[str], *, public: bool = False) -> None:
        self.doc = doc
        self.retired = retired  # ids used earlier in the log: never handed out again
        self.public = public  # a caller's batch (not an inverse, load or replay)
        self._handed: set[str] = set()
        self.seen: set[str] = set(T._all_ids(doc))  # every id present at any point in the batch

    def taken(self, d: dict) -> set[str]:
        return set(T._all_ids(d))

    def not_reused(self, iid: str, key: str | tuple) -> None:
        """A caller may not name an id that existed earlier in the log or earlier in this batch.
        Inverses (undo/redo, load, replay) restore old ids on purpose and skip this."""
        if self.public and iid in (self.retired | self.seen | self._handed):
            raise _OpError("id_reused", f"id {iid!r} existed earlier in this log and can't be used again", key)

    def fresh(self, prefix: str, also: tuple[str, ...] = ()) -> str:
        used = self.taken(self.doc) | self.retired | self._handed | set(also)
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        self._handed.add(f"{prefix}{n}")
        return f"{prefix}{n}"


def _op_arg_error(op: Any, internal: bool) -> _OpError | None:
    """The op's name and argument-name checks, in the engine's order (values are never read)."""
    if not isinstance(op, dict) or not isinstance(op.get("op"), str):
        return _OpError("bad_arg", "an op is an object with an 'op' name")
    table = {**PUBLIC_OPS, **INTERNAL_OPS} if internal else PUBLIC_OPS
    if op["op"] not in table:
        return _OpError("unknown_op", f"unknown op {op['op']!r}", "op")
    _, req, opt = table[op["op"]]
    for k in sorted(set(op) - req - opt - {"op"}, key=repr):  # keys may not be strings
        return _OpError("unknown_arg", f"{op['op']} takes no {k!r}", (k,))
    for k in sorted(req - set(op), key=repr):
        return _OpError("missing_arg", f"{op['op']} needs '{k}'", k)
    anchor = op.get("anchor")
    if not internal and op["op"] in ANCHOR_OPS and isinstance(anchor, dict):
        # keys inside anchor are checked by name too, before any lookup or value check
        for k in sorted(set(anchor) - ANCHOR_KEYS, key=repr):
            return _OpError("unknown_arg", f"{op['op']} anchor takes no {k!r}", ("anchor", k))
        for k in sorted(ANCHOR_KEYS - set(anchor)):
            return _OpError("missing_arg", f"{op['op']} anchor needs '{k}'", ("anchor", k))
    return None


def _as_oplog_error(e: _OpError, k: int) -> OplogError:
    """The OplogError a batch reports for op ``k``'s _OpError (``op_index`` k, path /ops/k/...)."""
    found_id = {"id": e.ident} if e.code == "not_found" and isinstance(e.ident, str) else {}
    if e.item_id is not None:
        found_id = {"id": e.item_id}
    return OplogError(
        e.code,
        f"op {k}: {e.message}",
        rule=e.rule,
        op_index=k,
        path=T._j("", "ops", k, *_key_parts(e.key)),
        **found_id,
    )


def check_op_args(op: Any, k: int, *, internal: bool = False) -> OplogError | None:
    """The engine's own per-op name check for op ``k`` of a batch, or None when it passes:
    (1) not an object / no string ``op`` -> ``bad_arg`` @ /ops/k; (2) ``unknown_op`` @ /ops/k/op;
    (3) ``unknown_arg`` @ /ops/k/<key> (sorted with ``key=repr``); (4) ``missing_arg`` (sorted);
    (5) for a public ``insert_clip``/``add_text``/``set_anchor`` with a dict ``anchor``: a key
    other than to/offset -> ``unknown_arg`` @ /ops/k/anchor/<key>, then a missing offset or to ->
    ``missing_arg``. It reads names only, never values. ``_run`` and /mcp both call it."""
    e = _op_arg_error(op, internal)
    return None if e is None else _as_oplog_error(e, k)


def _apply_one(ctx: _Ctx, op: Any, internal: bool, k: int = 0) -> tuple[dict, list[dict]]:
    err = check_op_args(op, k, internal=internal)
    if err is not None:
        raise err
    fn, _, _ = ({**PUBLIC_OPS, **INTERNAL_OPS} if internal else PUBLIC_OPS)[op["op"]]
    a = copy.deepcopy(op)
    if op["op"] in PUBLIC_OPS:
        _check_refs(a)
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
    if "warnings" in e and not _result_warnings_ok(e["warnings"]):
        raise ValueError("not an oplog line")
    return e


def _result_warnings_ok(w: Any) -> bool:
    """A stored ``warnings`` value: a non-empty list of {code, path, message} strings, never
    ``ignored_field`` (that one belongs to the call, not to the result)."""
    return (
        isinstance(w, list)
        and len(w) > 0
        and all(
            isinstance(x, dict)
            and set(x) == {"code", "path", "message"}
            and all(isinstance(v, str) for v in x.values())
            and x["code"] != "ignored_field"
            for x in w
        )
    )


_UNSET: Any = object()


def _int_arg(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


class Oplog:
    """The op log of one timeline, and the one way to change it: :meth:`call`.

    ``base`` is the version the log starts from (a valid doc, normally ``version`` 0). With
    ``path``, every entry is appended to that ``oplog.jsonl`` (flushed and fsynced) before it
    takes effect; a failed write leaves the timeline and the log unchanged."""

    def __init__(self, base: dict, *, path: str | os.PathLike | None = None, new_op_id: Callable[[], str] | None = None) -> None:
        self._base, _ = T.stamp_hash(base)
        self._doc = copy.deepcopy(self._base)
        self._entries: list[dict] = []
        self._results: dict[tuple[str, str, str], dict] = {}
        # which tool made each cached result; None after load when the line can't tell
        # history_undo of an undo entry from history_redo of it
        self._tools: dict[tuple[str, str, str], str | None] = {}
        self._retired: set[str] = set(T._all_ids(self._doc))
        self._batch_ids: set[str] = set()
        # (doc, retired ids) after every CHECKPOINT_EVERY-th entry, so _same_call re-runs at most
        # CHECKPOINT_EVERY - 1 entries instead of the whole log. Docs are never changed in place
        # (_run works on a deep copy), so holding a reference is enough.
        self._checkpoints: dict[int, tuple[dict, frozenset[str]]] = {0: (self._base, frozenset(self._retired))}
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

    def head(self) -> dict:
        """The current ``{project_id, schema_version, version, hash, seq}`` in one read."""
        return {
            "project_id": self._doc["id"],
            "schema_version": self._doc["schema_version"],
            "version": self._doc["version"],
            "hash": self._doc["hash"],
            "seq": len(self._entries),
        }

    def history_list(self, /, **args: Any) -> dict:
        """``history_list{since_version?=0, limit?=50}``: copies of the full log lines with
        ``new_version`` > ``since_version``, oldest first, at most ``limit`` (1-200), as
        ``{entries, next_since_version, head_version}``. Bad args are ``invalid_op``."""
        since, limit = self._history_args(args, required=False, limits=HISTORY_LIST_LIMIT)
        page, nxt = self._page([e for e in self._entries if e["new_version"] > since], limit)
        return {"entries": [copy.deepcopy(e) for e in page], "next_since_version": nxt, "head_version": self.version}

    def history_diff(self, /, **args: Any) -> dict:
        """``history_diff{since_version, limit?=200}``: one short record per entry after
        ``since_version`` (no ops), at most ``limit`` (1-500), as ``{records, next_since_version,
        head_version}``."""
        since, limit = self._history_args(args, required=True, limits=HISTORY_DIFF_LIMIT)
        page, nxt = self._page([e for e in self._entries if e["new_version"] > since], limit)
        return {"records": [_diff_record(e) for e in page], "next_since_version": nxt, "head_version": self.version}

    @staticmethod
    def _page(items: list[dict], limit: int) -> tuple[list[dict], int | None]:
        page = items[:limit]
        return page, (page[-1]["new_version"] if len(items) > limit else None)

    def _history_args(self, args: dict, *, required: bool, limits: tuple[int, int]) -> tuple[int, int]:
        """Order: unknown arg, missing arg, project_id, since_version, limit."""
        need = {"since_version"} if required else set()
        for k in sorted(set(args) - {"since_version", "limit", "project_id"}, key=repr):
            raise OplogError("invalid_op", f"unknown argument '{k}'", rule="unknown_arg", path=T._j("", k))
        for k in sorted(need - set(args), key=repr):
            raise OplogError("invalid_op", f"'{k}' is required", rule="missing_arg", path=T._j("", k))
        self._check_project_id(args)
        since = args.get("since_version", 0)
        if not (_int_arg(since) and since >= 0):
            raise OplogError("invalid_op", "since_version must be an integer >= 0", rule="bad_arg", path="/since_version")
        limit = args.get("limit", limits[0])
        if not (_int_arg(limit) and 1 <= limit <= limits[1]):
            raise OplogError("invalid_op", f"limit must be an integer from 1 to {limits[1]}", rule="bad_arg", path="/limit")
        return since, limit

    def _diff_since(self, since_version: int) -> list[dict]:
        return [_diff_record(e) for e in self._entries if e["new_version"] > since_version]

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
        args, warnings = _strip_forged(args)  # this call's own ignored_field warnings
        if tool == "timeline_apply":
            return self._apply(session, args, warnings)
        if tool in ("history_undo", "history_redo"):
            return self._undo(session, args, warnings, redo=tool == "history_redo")
        if tool == "keep_body":  # Phase 2 drafts: the engine's own tool, never sent by an agent
            return self._keep_body(session, args)
        raise OplogError("invalid_op", f"unknown write tool {tool!r}", rule="unknown_tool", path="")

    # ---- internals

    def _check_args(self, args: dict, required: set[str], optional: set[str]) -> None:
        for k in sorted(set(args) - required - optional, key=repr):
            raise OplogError("invalid_op", f"unknown argument '{k}'", rule="unknown_arg", path=T._j("", k))
        for k in sorted(required - set(args), key=repr):
            raise OplogError("invalid_op", f"'{k}' is required", rule="missing_arg", path=T._j("", k))
        cid = args["client_op_id"]
        if not (isinstance(cid, str) and CLIENT_ID_RE.fullmatch(cid)):
            raise OplogError(
                "invalid_op", f"client_op_id must match {CLIENT_ID_RE.pattern}", rule="bad_arg", path="/client_op_id"
            )
        for k in ("group_id", "op_id"):
            if args.get(k) is not None and not (isinstance(args[k], str) and CLIENT_ID_RE.fullmatch(args[k])):
                raise OplogError("invalid_op", f"{k} must match {CLIENT_ID_RE.pattern}", rule="bad_arg", path=T._j("", k))
        if "summary" in args:
            s = args["summary"]
            if not (
                isinstance(s, str) and s.strip() and len(s) <= SUMMARY_MAX and _utf8(s) and unicodedata.normalize("NFC", s) == s
            ):
                raise OplogError(
                    "invalid_op",
                    f"summary must be a non-empty NFC string of at most {SUMMARY_MAX} chars",
                    rule="bad_arg",
                    path="/summary",
                )
        self._check_project_id(args)

    def _check_project_id(self, args: dict) -> None:
        if "project_id" not in args:
            return
        if not isinstance(args["project_id"], str):
            raise OplogError("invalid_op", "project_id must be a string", rule="bad_arg", path="/project_id")
        if args["project_id"] != self._doc["id"]:
            raise OplogError(
                "not_found",
                f"no project {args['project_id']!r} here",
                rule="not_found",
                path="/project_id",
                id=args["project_id"],
            )

    @staticmethod
    def _base_version_type(args: dict) -> None:
        if "base_version" in args and not (T._is_int(args["base_version"]) and args["base_version"] >= 0):
            raise OplogError("invalid_op", "base_version must be an integer >= 0", rule="bad_arg", path="/base_version")

    @staticmethod
    def _ops_shape(ops: Any) -> None:
        """The shape of ``ops``, checked before dedupe so a junk retry is bad_arg, never a crash."""
        if not (isinstance(ops, list) and 0 < len(ops) <= MAX_OPS):
            raise OplogError("invalid_op", f"ops must be a list of 1-{MAX_OPS} ops", rule="bad_arg", path="/ops")
        for k, op in enumerate(ops):
            if not isinstance(op, dict) or not isinstance(op.get("op"), str):
                raise OplogError(
                    "invalid_op",
                    f"op {k}: an op is an object with an 'op' name",
                    rule="bad_arg",
                    op_index=k,
                    path=T._j("", "ops", k),
                )

    @staticmethod
    def _undo_shape(args: dict, redo: bool) -> None:
        """The shape of undo/redo args, checked before dedupe (same reason as _ops_shape)."""
        for k in ("op_id", "group_id"):
            if k in args and not isinstance(args[k], str):
                raise OplogError("invalid_op", f"{k} must be a string", rule="bad_arg", path=T._j("", k))
        if ("op_id" in args) == ("group_id" in args) or (redo and "group_id" in args):
            raise OplogError("invalid_op", "give exactly one of op_id or group_id (redo takes op_id)", rule="bad_arg", path="")

    def _base_version(self, args: dict, *, required: bool) -> None:
        if "base_version" not in args and not required:
            return
        self._base_version_type(args)
        bv = args["base_version"]
        if bv != self.version:
            diff = self._diff_since(min(bv, self.version))
            raise OplogError(
                "conflict",
                f"the timeline is at version {self.version}, not {bv}",
                hint="Read the history_diff, then retry against current_version.",
                current_version=self.version,
                history_diff=diff[:CONFLICT_DIFF_MAX],
                history_diff_truncated=len(diff) > CONFLICT_DIFF_MAX,
            )

    def _replayed(self, session: Session, tool: str, args: dict, warnings: list[dict]) -> dict | None:
        """The cached result of an identical earlier call with this (actor, client_op_id), or
        None. A different call under the same key is ``client_op_id_mismatch``. The cache holds
        result warnings only; this call's own strip ``warnings`` are added after them."""
        key = (session.actor.kind, session.actor.id, args["client_op_id"])
        r = self._results.get(key)
        if r is None:
            return None
        entry = next(e for e in self._entries if e["op_id"] == r["op_id"])
        known = self._tools.get(key)
        if (known is not None and known != tool) or not self._same_call(tool, args, entry):
            raise OplogError(
                "invalid_op",
                "this client_op_id was already used for a different call",
                rule="client_op_id_mismatch",
                path="/client_op_id",
                op_ids=[entry["op_id"]],
                hint="Use a new client_op_id for a new call.",
            )
        out = copy.deepcopy(r)
        out["warnings"] = out["warnings"] + copy.deepcopy(warnings)
        return out

    def _same_call(self, tool: str, args: dict, e: dict) -> bool:
        """Whether ``args`` (forged fields already stripped) is the call that made entry ``e``.
        Everything is derived from the log line, so the check is the same after ``load``.
        timeline_apply: same base_version, summary and group_id, and the ops give exactly the
        logged ops when re-run on the doc and retired ids as they were before ``e`` (so an id the
        engine picked matches an omitted id). history_undo/redo: same target, same summary (or
        the default one for that tool), and base_version, if given, equal to the line's."""

        def same(x: Any, y: Any) -> bool:
            # Byte-for-byte canonical JSON, the encoding the hash and the log line use: no numeric
            # or Unicode folding, so 1 != 1.0 != true and NFC != NFD. Anything canonical JSON
            # can't encode (NaN, a non-string key, an object) is never the same as anything.
            try:
                return _canon(x) == _canon(y)
            except (TypeError, ValueError):
                return False

        if tool == "timeline_apply":
            if e["undoes"] is not None or not all(same(args.get(k), e[k]) for k in ("base_version", "summary", "group_id")):
                return False
            then = Oplog(self._base)
            n = e["seq"] - 1
            done = max(k for k in self._checkpoints if k <= n)
            then._doc, retired = self._checkpoints[done]
            then._retired = set(retired)
            for prev in self._entries[done:n]:
                new, _, _ = then._run(prev["ops"], internal=True)
                then._retire(new)
                then._doc = new
            try:
                _, logged, _ = then._run(args["ops"], internal=False)
            except OplogError:
                return False
            return same(logged, e["ops"])
        if e["undoes"] is None:
            return False
        by_id = {x["op_id"]: x for x in self._entries}
        if tool == "history_redo" and not all(by_id[t]["undoes"] for t in e["undoes"]):
            return False  # it was an undo of a normal entry, so not a redo
        if "base_version" in args and not same(args["base_version"], e["base_version"]):
            return False
        if "group_id" in args:
            if tool != "history_undo" or not same(args["group_id"], e["group_id"]):
                return False
        elif e["group_id"] is not None or e["undoes"] != [args.get("op_id")]:
            return False
        if "summary" in args:
            return same(args["summary"], e["summary"])
        last = max((by_id[t] for t in e["undoes"]), key=lambda x: x["seq"])
        return e["summary"] == ((("Redo: " if tool == "history_redo" else "Undo: ") + last["summary"])[:SUMMARY_MAX])

    def _run(self, ops: list, *, internal: bool, base: dict | None = None) -> tuple[dict, list[dict], list[dict]]:
        """Apply ``ops`` to a copy of the doc; return (new doc, logged ops, inverse) or raise."""
        start = base if base is not None else self._doc
        ctx = _Ctx(copy.deepcopy(start), self._retired, public=not internal)
        logged: list[dict] = []
        inverse: list[dict] = []
        for k, op in enumerate(ops):
            try:
                a, inv = _apply_one(ctx, op, internal, k)
            except _OpError as e:
                raise _as_oplog_error(e, k) from None
            logged.append(a)
            inverse = inv + inverse
            ctx.seen |= set(T._all_ids(ctx.doc))
        self._batch_ids = ctx.seen | ctx._handed  # retired by whoever commits this batch
        new = ctx.doc
        new["version"] = start["version"] + 1
        new.pop("hash", None)
        found = T.validate(new)
        if found:
            raise OplogError(
                "invalid_op",
                f"the timeline after these ops is invalid: {found[0]['message']}",
                hint=T._HINTS.get(found[0]["rule"], ""),
                op_index=self._first_bad(ops, internal, start),
                rule=found[0]["rule"],
                path=found[0]["path"],
                **({"id": found[0]["id"]} if "id" in found[0] else {}),
                problems=found,
            )
        new, _ = T.stamp_hash(new)
        return new, logged, inverse

    def _checkpoint(self) -> None:
        n = len(self._entries)
        if n % CHECKPOINT_EVERY == 0:
            self._checkpoints[n] = (self._doc, frozenset(self._retired))

    def _retire(self, new: dict) -> None:
        """An id that existed at any point (or was handed out) in the last batch is never handed
        out again, even if the batch removed it. _commit, load and replay all call this."""
        self._retired |= set(T._all_ids(new)) | self._batch_ids
        self._batch_ids = set()

    def _first_bad(self, ops: list, internal: bool, start: dict) -> int:
        """The first op after which the doc stops validating (only worked out on failure)."""
        ctx = _Ctx(copy.deepcopy(start), self._retired, public=not internal)
        for k, op in enumerate(ops):
            _apply_one(ctx, op, internal, k)
            d = dict(ctx.doc)
            d.pop("hash", None)
            if T.validate(d):
                return k
        return len(ops) - 1

    def _commit(
        self,
        session: Session,
        args: dict,
        new: dict,
        logged: list,
        inverse: list,
        undoes: list[str] | None,
        summary: str,
        warnings: list[dict],
        tool: str,
    ) -> dict:
        """``warnings`` are this call's strip warnings: returned, never stored. Result warnings
        (none exist yet) would go in the line's ``warnings`` key and the cache."""
        stored: list[dict] = []
        entry: dict[str, Any] = {
            "seq": len(self._entries) + 1,
            "op_id": self._new_op_id(),
            "client_op_id": args["client_op_id"],
            "group_id": args.get("group_id"),
            "actor": session.actor.as_dict(),
            "summary": summary,
            "base_version": self.version,
            "new_version": new["version"],
            "hash": new["hash"],
            "ops": logged,
            "inverse": inverse,
            "changed_ids": changed_ids(self._doc, new),
            "undoes": undoes,
        }
        step = session.step()
        if step is not None:
            entry["step"] = step
        if stored:
            entry["warnings"] = stored
        if self._path is not None:
            line = _canon(entry)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        self._entries.append(entry)
        self._retire(new)
        self._doc = new
        self._checkpoint()
        result = _result(entry, entry.get("warnings", []))
        self._results[(session.actor.kind, session.actor.id, args["client_op_id"])] = result
        self._tools[(session.actor.kind, session.actor.id, args["client_op_id"])] = tool
        out = copy.deepcopy(result)
        out["warnings"] = out["warnings"] + copy.deepcopy(warnings)
        return out

    def check_apply_envelope(self, args: dict) -> None:
        """``timeline_apply``'s envelope checks, in order: tool args (unknown, missing,
        client_op_id, group_id, summary, project_id), ``group_id: null``, the ``base_version``
        type, the ``ops`` shape. ``args`` must already have actor/step stripped. /mcp runs this
        same check before its op stage."""
        self._check_args(args, {"base_version", "ops", "summary", "client_op_id"}, {"project_id", "group_id"})
        if "group_id" in args and args["group_id"] is None:  # Ada: omit it for no group; null is junk
            raise OplogError("invalid_op", "group_id must be a string; omit it for no group", rule="bad_arg", path="/group_id")
        self._base_version_type(args)  # every shape check runs before dedupe
        self._ops_shape(args["ops"])

    def _keep_body(self, session: Session, args: dict) -> dict:
        """``call(session, "keep_body", ...)`` (Phase 2 drafts): make this doc's media, tracks and markers ``body``'s as ONE entry (one
        ``replace_body`` op; its inverse restores the old body, so undo works as for any entry).
        ``args``: ``client_op_id``, ``summary``, ``base_version``, ``body``, ``group_id?``. A retry
        with the same ``client_op_id`` returns the first result."""
        self._check_args(args, {"client_op_id", "summary", "base_version", "body"}, {"group_id"})
        body = args["body"]
        if not (isinstance(body, dict) and all(k in body for k in BODY_KEYS)):
            raise OplogError("invalid_op", "body must hold media, tracks and markers", rule="bad_arg", path="/body")
        if "group_id" in args and args["group_id"] is None:
            raise OplogError("invalid_op", "group_id must be a string; omit it for no group", rule="bad_arg", path="/group_id")
        self._base_version_type(args)
        key = (session.actor.kind, session.actor.id, args["client_op_id"])
        if key in self._results:
            out = copy.deepcopy(self._results[key])
            out["warnings"] = []
            return out
        self._base_version(args, required=True)
        new, logged, inverse = self._run([{"op": "replace_body", **{k: body[k] for k in BODY_KEYS}}], internal=True)
        return self._commit(session, args, new, logged, inverse, None, args["summary"], [], "timeline_apply")

    def _apply(self, session: Session, args: dict, warnings: list[dict]) -> dict:
        self.check_apply_envelope(args)
        done = self._replayed(session, "timeline_apply", args, warnings)
        if done is not None:
            return done
        self._base_version(args, required=True)
        ops = args["ops"]
        new, logged, inverse = self._run(ops, internal=False)
        return self._commit(session, args, new, logged, inverse, None, args["summary"], warnings, "timeline_apply")

    def _cancelled(self) -> set[str]:
        """Entries whose effect a live undo entry has reversed (walking back, an undone undo
        cancels nothing)."""
        out: set[str] = set()
        for e in reversed(self._entries):
            if e["op_id"] not in out:
                out.update(e["undoes"] or [])
        return out

    def check_undo_envelope(self, args: dict, *, redo: bool) -> None:
        """``history_undo``/``history_redo``'s arg checks, in order (``args`` already stripped)."""
        self._check_args(args, {"client_op_id"}, {"project_id", "op_id", "group_id", "summary", "base_version"})
        self._base_version_type(args)  # every shape check runs before dedupe
        self._undo_shape(args, redo)

    @classmethod
    def precheck(cls, tool: str, args: dict) -> OplogError:
        """The error the engine gives ``tool`` with these ``args`` when there is no such project:
        the same checks in the same order, with any string ``project_id`` ``not_found`` and any
        other one ``bad_arg``. For a caller (/mcp) that can't pick the project, so it answers
        exactly as the engine would."""
        shadow = cls.__new__(cls)
        shadow._doc = {"id": None, "version": 0}
        shadow._entries = []
        args, _ = _strip_forged(args)
        try:
            if tool == "timeline_apply":
                shadow.check_apply_envelope(args)
            elif tool in ("history_undo", "history_redo"):
                shadow.check_undo_envelope(args, redo=tool == "history_redo")
            elif tool == "history_list":
                shadow.history_list(**args)
            elif tool == "history_diff":
                shadow.history_diff(**args)
            else:
                shadow._check_project_id(args)
        except OplogError as e:
            return e
        raise AssertionError("precheck needs a project_id")  # pragma: no cover

    def _undo(self, session: Session, args: dict, warnings: list[dict], *, redo: bool) -> dict:
        self.check_undo_envelope(args, redo=redo)
        done = self._replayed(session, "history_redo" if redo else "history_undo", args, warnings)
        if done is not None:
            return done
        self._base_version(args, required=False)
        cancelled = self._cancelled()
        if "op_id" in args:
            hit = [e for e in self._entries if e["op_id"] == args["op_id"]]
            if not hit:
                raise OplogError("not_found", f"no entry {args['op_id']!r}", rule="not_found", path="/op_id", id=args["op_id"])
            if redo and not hit[0]["undoes"]:
                raise OplogError("invalid_op", "history_redo takes the op_id of an undo entry", rule="not_an_undo", path="/op_id")
            group = [e for e in hit if e["op_id"] not in cancelled]
        else:
            gid = args["group_id"]  # a null group never matches the ungrouped entries
            hit = [e for e in self._entries if gid is not None and e["group_id"] == gid]
            if not hit:
                raise OplogError(
                    "not_found", f"no group {args['group_id']!r}", rule="not_found", path="/group_id", id=args["group_id"]
                )
            group = [e for e in hit if e["op_id"] not in cancelled]
        if not group:
            raise OplogError(
                "invalid_op", "already undone", rule="already_undone", path="/op_id" if "op_id" in args else "/group_id"
            )
        # every undo_blocked result points at the target the caller named
        where = {"path": "/op_id", "id": args["op_id"]} if "op_id" in args else {"path": "/group_id", "id": args["group_id"]}
        target_ids = [e["op_id"] for e in sorted(group, key=lambda e: e["seq"])]
        if session.actor.kind == "agent":
            others = [e["op_id"] for e in group if e["actor"] != session.actor.as_dict()]
            if others:
                raise OplogError(
                    "undo_blocked",
                    "an agent can only undo its own entries",
                    reason="actor",
                    op_ids=others,
                    **where,
                    hint="Ask the person to undo it.",
                )
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
            raise OplogError(
                "undo_blocked",
                "later entries changed the same items",
                reason="dependents",
                blocking_op_ids=dependents,
                op_ids=dependents,
                **where,
                hint="Undo those first, or restore to before this step.",
            )
        ops = [op for e in sorted(group, key=lambda e: -e["seq"]) for op in e["inverse"]]
        try:
            new, logged, inverse = self._run(ops, internal=True)
        except OplogError as e:
            raise OplogError(
                "undo_blocked",
                "the inverse no longer applies",
                reason="inverse_invalid",
                op_ids=target_ids,
                **where,
                problems=e.extra.get("problems", []),
                rule=e.extra.get("rule"),
            ) from None
        last = max(group, key=lambda e: e["seq"])
        summary = args.get("summary") or (("Redo: " if redo else "Undo: ") + last["summary"])[:SUMMARY_MAX]
        undoes = [e["op_id"] for e in sorted(group, key=lambda e: -e["seq"])]
        tool = "history_redo" if redo else "history_undo"
        return self._commit(session, args, new, logged, inverse, undoes, summary, warnings, tool)

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
            log._retire(new)
            log._doc = new
            log._checkpoint()
            key = (e["actor"]["kind"], e["actor"]["id"], e["client_op_id"])
            log._results[key] = _result(e, e.get("warnings", []))
            log._tools[key] = _tool_of(e, log._entries)
        log._path = os.fspath(path)
        return log


def _tool_of(e: dict, entries: list[dict]) -> str | None:
    """The tool that wrote line ``e``, as far as the line tells: an apply has no ``undoes``; an
    undo of a group, or of a normal entry, is history_undo; an undo of an undo entry could be
    either history_undo or history_redo (None)."""
    if e["undoes"] is None:
        return "timeline_apply"
    by_id = {x["op_id"]: x for x in entries}
    if e["group_id"] is not None or not all(by_id[t]["undoes"] for t in e["undoes"]):
        return "history_undo"
    return None


def replay(base: dict, entries: list[dict]) -> dict:
    """The timeline after applying ``entries`` (oplog lines) to ``base``; checks every hash."""
    log = Oplog(base)
    for e in entries:
        new, _, _ = log._run(_check_line(e)["ops"], internal=True)
        if new["hash"] != e["hash"]:
            raise ValueError(f"oplog line {e['seq']}: replay gives {new['hash']}, the log says {e['hash']}")
        log._entries.append(e)
        log._retire(new)
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
            if k in _REF_KEYS and (
                v in ids if isinstance(v, str) else isinstance(v, list) and any(isinstance(x, str) and x in ids for x in v)
            ):
                return True
            if isinstance(v, (dict, list)) and _mentions(v, ids):
                return True
    return False


_DIFF_KEYS = (
    "seq",
    "op_id",
    "group_id",
    "actor",
    "step",
    "summary",
    "base_version",
    "new_version",
    "hash",
    "changed_ids",
    "undoes",
)


def _diff_record(e: dict) -> dict:
    """The short record of one entry (history_diff, conflict bodies, events): no ops."""
    return {k: copy.deepcopy(e[k]) for k in _DIFF_KEYS if k in e}


def strip_forged(args: dict) -> tuple[dict, list[dict]]:
    """Public name for the engine's actor/step strip (what :meth:`Oplog.call` does first)."""
    return _strip_forged(args)


def _result(entry: dict, warnings: list[dict]) -> dict:
    r = {
        "ok": True,
        "op_id": entry["op_id"],
        "group_id": entry["group_id"],
        "seq": entry["seq"],
        "new_version": entry["new_version"],
        "hash": entry["hash"],
        "tick_rate": T.TICK_RATE,
        "summary": entry["summary"],
        "changed_ids": list(entry["changed_ids"]),
        "undoes": entry["undoes"],
        "before_frame": None,
        "after_frame": None,
        "warnings": copy.deepcopy(warnings),
    }
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
                warnings.append(
                    {
                        "code": "ignored_field",
                        "path": T._j(base, k),
                        "message": f"'{k}' is ignored: it comes from the session, not the arguments",
                    }
                )
        return obj

    args = drop(args, "")
    if isinstance(args.get("ops"), list):
        args["ops"] = [drop(op, T._j("", "ops", i)) if isinstance(op, dict) else op for i, op in enumerate(args["ops"])]
    return args, warnings
