"""The timeline tools at /mcp (S3 + Wire's registry): reads, ``timeline_apply`` and undo/redo.

Every tool runs the same pipeline, over HTTP /mcp (inside the engine) and stdio (attached to
the engine, or read-only with the app closed). Order (S3-SPEC §6, D21):

1. JSON-RPC parse and shape, auth (the transport);
2. the ``schema_version`` guard (D20): anything but ``hs.timeline/1`` is ``schema_mismatch``,
   a matching value is stripped;
3. ``project_id`` present (D4), else ``missing_arg`` @ /project_id;
3b. ``timeline_apply``: the engine's own envelope check (``Oplog.check_apply_envelope``);
4. per op, in op order: the check view (``oplog.check_op_args``), both-sent (D23), the ``_s``
   conversions with ``seconds_to_ticks_nearest()[0]`` (an int), the whole batch first (D31);
5. the engine, with the converted ops; 6. re-pointing (D22).

/mcp fills nothing in (D18) and passes every other field through as received (D24).
"""

from __future__ import annotations

import copy
import re
from fractions import Fraction
from typing import Any

from hermes_studio import oplog as O
from hermes_studio import project as P
from hermes_studio import timeline as T
from hermes_studio.api import HermesStudioError

READ_TOOLS = (
    "get_timeline",
    "get_hash",
    "list_markers",
    "export_otio",
    "validate_timeline",
    "history_list",
    "history_diff",
    "project_status",
)
WRITE_TOOLS = ("timeline_apply", "history_undo", "history_redo")
MEDIA_TOOLS = ("import_media", "media_status", "get_transcript")  # S4
FRAME_TOOLS = ("timeline_frames", "timeline_contact_sheet", "history_frames")  # S5
RENDER_TOOLS = ("render_timeline", "render_status")  # S6
CUT_TOOLS = ("transcript_cut",)  # S7
GATE_TOOLS = ("approval_list", "approval_status", "approval_resolve", "set_mode")  # S8
NAMES = READ_TOOLS + WRITE_TOOLS + MEDIA_TOOLS + FRAME_TOOLS + RENDER_TOOLS + CUT_TOOLS + GATE_TOOLS

_S = {"type": "string"}
_PID = {"type": "string", "description": "the project id (the timeline's id)"}
_SV = {"type": "string", "description": "optional; must be hs.timeline/1 when given"}
_RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
_W = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}


def _tool(name: str, title: str, desc: str, props: dict, ann: dict) -> dict:
    # Declared types document the args for clients; nothing here is enforced (no required list,
    # no additionalProperties:false): the engine gives every answer (§1g).
    return {
        "name": name,
        "title": title,
        "description": desc,
        "inputSchema": {"type": "object", "properties": {"project_id": _PID, **props, "schema_version": _SV}},
        "annotations": {"title": title, **ann},
    }


TOOLS: list[dict] = [
    _tool(
        "get_timeline",
        "Get the timeline",
        "The project's timeline document, raw, in integer ticks (tick_rate 705600000/s), with version and hash.",
        {},
        _RO,
    ),
    _tool(
        "get_hash",
        "Get the timeline hash",
        "{project_id, schema_version, version, hash, seq} of the timeline, read in one go.",
        {},
        _RO,
    ),
    _tool("list_markers", "List markers", "The timeline's markers sorted by time, each time as {ticks, seconds}.", {}, _RO),
    _tool(
        "export_otio",
        "Export OTIO",
        "Write the timeline as an .otio file in the project's exports/ folder and return {path, timeline_hash}. Needs the app running.",
        {},
        {**_W, "idempotentHint": True},
    ),
    {
        "name": "validate_timeline",
        "title": "Validate a timeline document",
        "description": "Dry-run the validator on a document: {ok:true, hash} or invalid_doc / schema_mismatch.",
        "inputSchema": {"type": "object", "properties": {"doc": {"type": "object"}, "schema_version": _SV}},
        "annotations": {"title": "Validate a timeline document", **_RO},
    },
    _tool(
        "history_list",
        "List history",
        "Full op-log lines after since_version (default 0), oldest first, at most limit (default 50, 1-200): {entries, next_since_version, head_version}. Ticks are raw.",
        {"since_version": {"type": "integer"}, "limit": {"type": "integer"}},
        _RO,
    ),
    _tool(
        "history_diff",
        "What changed",
        "One short record per entry after since_version, oldest first, at most limit (default 200, 1-500): {records, next_since_version, head_version}.",
        {"since_version": {"type": "integer"}, "limit": {"type": "integer"}},
        _RO,
    ),
    _tool(
        "project_status",
        "Project status",
        "{project_id, schema_version, version, hash, seq, engine:{pid, port, started_at}|null, mode}. Works with the app closed.",
        {},
        _RO,
    ),
    _tool(
        "timeline_apply",
        "Edit the timeline",
        "Apply ops as one atomic batch (all or nothing) and log one entry. Times: integer ticks, or seconds through _s args "
        "(at_s, src_s, src_in_s, src_out_s, dur_s, fade_in_s, fade_out_s, anchor.offset_s). Needs base_version, summary and "
        "a fresh client_op_id; resend the exact same call to retry. Ops: insert_clip, move_clip, trim_clip, split_clip, "
        "delete_clip, set_props, set_fade, set_anchor, edit_text, add_text, add_transition, add_track, remove_track, add_marker, "
        "remove_marker, add_media (import_media is easier: it probes the file for you).",
        {
            "base_version": {"type": "integer"},
            "ops": {"type": "array", "items": {"type": "object"}},
            "summary": _S,
            "client_op_id": _S,
            "group_id": _S,
        },
        _W,
    ),
    _tool(
        "history_undo",
        "Undo",
        "Undo one entry (op_id) or a group (group_id) as a new entry. base_version is optional.",
        {"client_op_id": _S, "op_id": _S, "group_id": _S, "summary": _S, "base_version": {"type": "integer"}},
        _W,
    ),
    _tool(
        "history_redo",
        "Redo",
        "Redo an undo entry (its op_id) as a new entry.",
        {"client_op_id": _S, "op_id": _S, "summary": _S, "base_version": {"type": "integer"}},
        _W,
    ),
    _tool(
        "import_media",
        "Import media",
        "Add a local video or audio file to the project: probes it, logs one add_media entry (undoable) and returns "
        "{media_id, probe, status, op_id, new_version}. Then builds, in the background, a 540p proxy, a thumbnail strip, "
        "a waveform and (with 'words' in stages) Whisper words. Poll media_status or watch the project's events for "
        "media.progress / media.ready. Needs the app running. The file is read where it is, never copied or uploaded.",
        {
            "path": _S,
            "client_op_id": _S,
            "id": _S,
            "summary": _S,
            "stages": {"type": "array", "items": {"type": "string", "enum": ["proxy", "thumbs", "wave", "words"]}},
            "whisper": {"type": "string", "enum": ["tiny", "base", "small", "medium"]},
        },
        _W,
    ),
    _tool(
        "media_status",
        "Media status",
        "Progress and files of one media's background work: {state: queued|running|ready|failed|cancelled|interrupted|none, "
        "progress 0-1, stage, stages:{proxy|thumbs|wave|words: {state, ...}}, probe}.",
        {"media_id": _S},
        _RO,
    ),
    _tool(
        "get_transcript",
        "Get the transcript",
        "Words on the timeline: each {w, at, end, at_s, end_s, clip, media, src_in, src_out}, sorted by time, mapped through "
        "every clip that shows them. Only media imported with 'words' have any.",
        {"media_id": _S},
        _RO,
    ),
    _tool(
        "timeline_frames",
        "Look at the timeline",
        "Still frames of the edit at given times (at_s: up to 12 seconds values, or at: ticks), as JPEG images plus "
        "refs {at, key, cached}. width 32-1080 (default 320). images:false returns refs only. Frames are cached by what is "
        "visible at that time, so unchanged moments come back instantly. Needs the app running and the render scope.",
        {
            "at_s": {"type": "array", "items": {"type": "number"}},
            "at": {"type": "array", "items": {"type": "integer"}},
            "width": {"type": "integer"},
            "images": {"type": "boolean"},
        },
        _RO,
    ),
    _tool(
        "timeline_contact_sheet",
        "Contact sheet",
        "One image of count frames (default 12, up to 48) spread over from_s..to_s (default the whole timeline), tiled cols "
        "across (default 4) with each frame's time. The cheapest way to see a whole edit.",
        {
            "count": {"type": "integer"},
            "from_s": {"type": "number"},
            "to_s": {"type": "number"},
            "cols": {"type": "integer"},
            "width": {"type": "integer"},
            "images": {"type": "boolean"},
        },
        _RO,
    ),
    _tool(
        "history_frames",
        "Before and after",
        "The frame just before and just after one history entry (op_id), at the first time it changed: "
        "{at, at_s, before:{key}, after:{key}, before_version, after_version} plus the two images.",
        {"op_id": _S, "width": {"type": "integer"}, "images": {"type": "boolean"}},
        _RO,
    ),
    _tool(
        "render_timeline",
        "Render the video",
        "Render the current version to an MP4 (H.264 + AAC) in the project's exports/ folder, in the background: "
        "{render_id, state, progress, path, version}. width/height default to the timeline's size (even, 16-3840). "
        "captions (default true) burns in the words from get_transcript when there are any. The same version, size and "
        "captions return the existing render. Poll render_status or watch render.progress / render.ready events. "
        "Needs the app running and the render scope. Never uploads or posts.",
        {"width": {"type": "integer"}, "height": {"type": "integer"}, "captions": {"type": "boolean"}},
        {**_W, "idempotentHint": True},
    ),
    _tool(
        "render_status",
        "Render status",
        "{render_id, state: queued|running|ready|failed|cancelled|interrupted|missing, progress, path, version, size, "
        "seconds, bytes, error}. Works with the app closed.",
        {"render_id": _S},
        _RO,
    ),
    _tool(
        "transcript_cut",
        "Cut by transcript",
        "Remove filler words (fillers:true: um, uh, erm...), long pauses (pauses:true: gaps over 0.7 s cut to 0.26 s) and/or "
        "ranges [{from_s, to_s}] in timeline seconds from the main track, as ONE history entry (one undo). Uses the words "
        "from get_transcript (import with 'words'). Needs base_version and client_op_id like timeline_apply; summary is "
        "optional. preview:true returns the cuts and ops without changing anything. Returns {cuts, skipped, removed_s, "
        "op_id, new_version, ...}.",
        {
            "base_version": {"type": "integer"},
            "client_op_id": _S,
            "summary": _S,
            "group_id": _S,
            "fillers": {"type": "boolean"},
            "pauses": {"type": "boolean"},
            "ranges": {"type": "array", "items": {"type": "object"}},
            "preview": {"type": "boolean"},
        },
        _W,
    ),
    _tool(
        "approval_list",
        "Waiting edits",
        "The project's mode (ask | propose | auto) and the agent edits parked for approval (all:true includes resolved ones): "
        "{mode, pending:[{pending_id, state, actor, step, tool, summary, n_ops, base_version, created, result, error}]}.",
        {"all": {"type": "boolean"}},
        _RO,
    ),
    _tool(
        "approval_status",
        "Waiting edit status",
        "One parked edit: state pending | applied | skipped | failed, with result {op_id, new_version, ...} or error. "
        "In Propose mode an agent's write returns needs_approval with a pending_id; poll this (or watch events) until it "
        "isn't pending. Don't resend the write with a new client_op_id.",
        {"pending_id": _S},
        _RO,
    ),
    _tool(
        "approval_resolve",
        "Apply or skip",
        "A person applies or skips a parked agent edit (decision: apply | skip). rest:true does the same to every edit that "
        "agent has parked. Each edit resolves once; a second answer returns the outcome. Agents can't call this.",
        {"pending_id": _S, "decision": {"type": "string", "enum": ["apply", "skip"]}, "rest": {"type": "boolean"}},
        _W,
    ),
    _tool(
        "set_mode",
        "Set the edit mode",
        "A person sets how agent edits land: ask (agents only read), propose (each edit waits for Apply/Skip; the default) "
        "or auto (edits apply at once, undo after). Agents can't call this.",
        {"mode": {"type": "string", "enum": ["ask", "propose", "auto"]}},
        _W,
    ),
]
BY_NAME = {t["name"]: t for t in TOOLS}

# --------------------------------------------------------------------------- the _s registry (D22)
#
# op -> [(s_arg, engine field, landing op paths, doc suffixes that are re-pointed, rules)]
# Paths are relative: "at" is /ops/k/at; a doc suffix "at" matches <item pointer>/at.
_TICK_RULES = ("too_large", "negative_time")
_TOO_LARGE = ("too_large",)
S_ARGS: dict[str, list[tuple[str, str, tuple, tuple, tuple]]] = {
    "add_marker": [("at_s", "at", ("at",), ("at",), _TICK_RULES)],
    "move_clip": [("at_s", "at", ("at",), ("at",), _TICK_RULES)],
    "split_clip": [("at_s", "at", ("at",), (), _TICK_RULES)],
    "trim_clip": [
        ("src_in_s", "src_in", ("src_in",), (), _TICK_RULES),
        ("src_out_s", "src_out", ("src_out",), ("src/1",), _TICK_RULES),
        ("dur_s", "dur", ("dur",), ("dur",), _TICK_RULES),
    ],
    "set_fade": [
        ("fade_in_s", "fade_in", ("fade_in",), ("fade_in",), _TICK_RULES),
        ("fade_out_s", "fade_out", ("fade_out",), ("fade_out",), _TICK_RULES),
    ],
    "set_anchor": [
        ("at_s", "at", ("at",), ("at",), _TICK_RULES),
        ("anchor.offset_s", "anchor.offset", ("anchor/offset",), ("anchor/offset",), _TOO_LARGE),
    ],
    "insert_clip": [
        ("at_s", "at", ("at",), ("at",), _TICK_RULES),
        ("src_s", "src", (), ("src/0", "src/1"), _TICK_RULES),
        ("fade_in_s", "fade_in", (), ("fade_in",), _TICK_RULES),
        ("fade_out_s", "fade_out", (), ("fade_out",), _TICK_RULES),
        ("anchor.offset_s", "anchor.offset", (), ("anchor/offset",), _TOO_LARGE),
    ],
    "add_text": [
        ("at_s", "at", ("at",), ("at",), _TICK_RULES),
        ("dur_s", "dur", (), ("dur",), _TICK_RULES),
        ("fade_in_s", "fade_in", (), ("fade_in",), _TICK_RULES),
        ("fade_out_s", "fade_out", (), ("fade_out",), _TICK_RULES),
        ("anchor.offset_s", "anchor.offset", (), ("anchor/offset",), _TOO_LARGE),
    ],
    "add_transition": [("dur_s", "dur", (), ("dur",), _TICK_RULES)],
}
_ITEM_PTR = re.compile(r"\A(/tracks/[0-9]+/items/[0-9]+|/markers/[0-9]+)/(.+)\Z")


def _get(op: dict, dotted: str) -> tuple[bool, Any]:
    if "." in dotted:
        outer, inner = dotted.split(".")
        sub = op.get(outer)
        if isinstance(sub, dict) and inner in sub:
            return True, sub[inner]
        return False, None
    return (dotted in op), op.get(dotted)


def _ptr(k: int, dotted: str, *more: Any) -> str:
    return T._j("", "ops", k, *dotted.split("."), *more)


def _bad(k: int, msg: str, path: str) -> O.OplogError:
    return O.OplogError("invalid_op", f"op {k}: {msg}", rule="bad_arg", op_index=k, path=path)


def _check_view(op: dict) -> dict:
    """Prove's ordering rule: drop each _s arg and add its field with a placeholder 0 only when
    the caller didn't send that field (never overwrite a raw value). Same inside ``anchor``."""
    view = dict(op)
    for s_arg, fld, *_ in S_ARGS.get(op["op"], []):
        if "." in s_arg:
            outer, inner = s_arg.split(".")
            fouter, finner = fld.split(".")
            sub = view.get(outer)
            if isinstance(sub, dict) and inner in sub:
                sub = dict(sub)
                del sub[inner]
                if finner not in sub:
                    sub[finner] = 0
                view[outer] = sub
        elif s_arg in view:
            del view[s_arg]
            if fld not in view:
                view[fld] = 0
    return view


def convert_ops(ops: list, stripped_ops: list) -> tuple[list, dict]:
    """The /mcp op stage for the whole batch (D21, D23, D31): per op in order, the check view,
    then both-sent, then the conversions. Returns (converted ops, used) or raises the first
    error. ``ops`` are the caller's (forged fields kept, so the engine warns); ``stripped_ops``
    the same with actor/step removed, which the name check sees."""
    out: list = []
    used: dict = {}
    for k, (op, sop) in enumerate(zip(ops, stripped_ops, strict=True)):
        err = O.check_op_args(_check_view(sop), k)
        if err is not None:
            raise err
        table = S_ARGS.get(op["op"], [])
        for s_arg, fld, *_ in table:  # both-sent
            has_s, _ = _get(sop, s_arg)
            has_raw, _ = _get(sop, fld)
            if has_s and has_raw:
                f, s = fld.split(".")[-1], s_arg.split(".")[-1]
                raise _bad(k, f"give '{f}' or '{s}', not both", _ptr(k, s_arg))
        new = copy.deepcopy(op)
        for s_arg, fld, *_ in table:  # conversions
            has_s, v = _get(op, s_arg)
            if not has_s:
                continue
            if s_arg == "src_s":
                del new["src_s"]
                if isinstance(v, list) and len(v) == 2:
                    ticks = []
                    for i, x in enumerate(v):
                        try:
                            ticks.append(T.seconds_to_ticks_nearest(x)[0])
                        except (TypeError, ValueError):
                            raise _bad(k, f"'src_s[{i}]' must be a number of seconds", _ptr(k, "src_s", i)) from None
                    new["src"] = ticks
                    used["src_s"] = [{"ticks": t, "seconds": float(Fraction(t, T.TICK_RATE))} for t in ticks]
                else:
                    new["src"] = v  # not a conversion: the engine answers for src
                continue
            try:
                t = T.seconds_to_ticks_nearest(v)[0]
            except (TypeError, ValueError):
                raise _bad(k, f"'{s_arg.split('.')[-1]}' must be a number of seconds", _ptr(k, s_arg)) from None
            if "." in s_arg:
                outer, inner = s_arg.split(".")
                fin = fld.split(".")[1]
                sub = dict(new[outer])
                del sub[inner]
                sub[fin] = t
                new[outer] = sub
            else:
                del new[s_arg]
                new[fld] = t
            used[s_arg.split(".")[-1]] = {"ticks": t, "seconds": float(Fraction(t, T.TICK_RATE))}
        out.append(new)
    return out, used


def repoint(e: O.OplogError, ops: list, pre_ids: set[str]) -> O.OplogError:
    """D22: a ``too_large``/``negative_time`` at op k's converted field gets the ``_s`` path.
    ``code``, ``rule``, ``id``, ``op_index`` and ``problems`` are kept; anything else is verbatim."""
    x = e.extra
    k = x.get("op_index")
    rule, path = x.get("rule"), x.get("path")
    if rule not in _TICK_RULES or not isinstance(k, int) or not (0 <= k < len(ops)) or not isinstance(path, str):
        return e
    op = ops[k]
    for s_arg, _fld, op_paths, doc_suffixes, rules in S_ARGS.get(op.get("op"), []):
        sent, _ = _get(op, s_arg)
        if not sent or rule not in rules:
            continue
        new_path = None
        for rel in op_paths:
            if path == T._j("", "ops", k, *rel.split("/")):
                new_path = _ptr(k, s_arg)
        m = _ITEM_PTR.match(path)
        if new_path is None and m and m.group(2) in doc_suffixes:
            iid = x.get("id")
            if isinstance(iid, str) and (iid == op.get("id") or iid not in pre_ids):
                new_path = _ptr(k, s_arg, m.group(2)[-1]) if s_arg == "src_s" else _ptr(k, s_arg)
        if new_path is not None:
            extra = dict(x)
            extra["path"] = new_path
            out = O.OplogError(e.code, e.message, hint=e.hint, **extra)
            return out
    return e


# --------------------------------------------------------------------------- the pipeline


def _schema_guard(args: dict) -> dict:
    if "schema_version" not in args:
        return args
    v = args["schema_version"]
    if not (isinstance(v, str) and v == T.SCHEMA_VERSION):
        raise P.ToolError(
            "schema_mismatch",
            f"schema_version must be {T.SCHEMA_VERSION!r}",
            rule="bad_schema",
            path="/schema_version",
            expected=T.SCHEMA_VERSION,
            got=v,
        )
    return {k: w for k, w in args.items() if k != "schema_version"}


def _no_unknown(args: dict, allowed: set[str]) -> None:
    for k in sorted(set(args) - allowed, key=repr):
        raise O.OplogError("invalid_op", f"unknown argument '{k}'", rule="unknown_arg", path=T._j("", k))


class Backend:
    """Where a project comes from: the engine (writes allowed) or the closed app (reads only)."""

    writable = False

    def project(self, project_id: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError


class EngineBackend(Backend):
    writable = True

    def __init__(self, engine: P.Engine, session: O.Session, scopes: frozenset) -> None:
        self.engine, self.session, self.scopes = engine, session, scopes

    def project(self, project_id: Any) -> P.Project:
        return self.engine.get(project_id)


class ClosedBackend(Backend):
    def project(self, project_id: Any) -> P.ClosedProject:
        return P.ClosedProject(project_id)


def _need_scope(backend: Backend, scope: str) -> None:
    if isinstance(backend, EngineBackend) and scope not in backend.scopes:
        raise P.ToolError("permission_denied", f"this token has no '{scope}' scope")


def run_tool(name: str, args: dict, backend: Backend) -> dict:
    """One /mcp timeline tool call. Returns the result or raises the error to report."""
    args = _schema_guard(args)
    if name == "validate_timeline":
        _need_scope(backend, "read")
        _no_unknown(args, {"doc"})
        if "doc" not in args:
            raise O.OplogError("invalid_op", "'doc' is required", rule="missing_arg", path="/doc")
        err = P.doc_error(args["doc"])
        if err is not None:
            raise err
        return {"ok": True, "hash": T.canonical_hash(args["doc"])}
    if "project_id" not in args:  # D4, §11 row G: before any other tool-level check
        raise O.OplogError("invalid_op", "'project_id' is required", rule="missing_arg", path="/project_id")
    writes = name in WRITE_TOOLS or name in ("export_otio", "import_media", "transcript_cut", "approval_resolve", "set_mode")
    _need_scope(backend, "write" if writes else "render" if name in FRAME_TOOLS or name == "render_timeline" else "read")
    pid = args["project_id"]
    if name in ("get_timeline", "get_hash", "list_markers", "export_otio", "project_status"):
        _no_unknown(args, {"project_id"})
    if name in ("media_status", "get_transcript"):
        _no_unknown(args, {"project_id", "media_id"})
    if name == "render_status":
        _no_unknown(args, {"project_id", "render_id"})
    try:
        proj = backend.project(pid) if isinstance(pid, str) else None
    except O.OplogError as e:
        if e.code != "not_found":
            raise
        proj = None
    extra = MEDIA_TOOLS + FRAME_TOOLS + RENDER_TOOLS + CUT_TOOLS + GATE_TOOLS
    if proj is None:  # the engine's own answer, in the engine's order, for a project that isn't here
        raise O.Oplog.precheck(name if name not in extra else "get_hash", args if name not in extra else {"project_id": pid})
    if name in GATE_TOOLS:
        from hermes_studio import gate as G

        rest = {k: v for k, v in args.items() if k != "project_id"}
        if name == "approval_list":
            return G.listing(proj, rest)
        if name == "approval_status":
            _no_unknown(rest, {"pending_id"})
            return G.status(proj, rest)
        if not backend.writable:
            raise P.offline()
        if name == "set_mode":
            return G.set_mode(proj, backend.session, rest)
        return G.resolve(proj, backend.session, rest)
    if name == "transcript_cut":
        from hermes_studio import cuts as CU

        if not backend.writable:
            raise P.offline()
        stripped, _ = O.strip_forged({k: v for k, v in args.items() if k != "project_id"})
        return CU.transcript_cut(proj, backend.session, stripped)
    if name in RENDER_TOOLS:
        from hermes_studio import render_jobs as RJ

        rest = {k: v for k, v in args.items() if k != "project_id"}
        if name == "render_status":
            return RJ.render_status(proj, rest, backend.engine.renders if isinstance(backend, EngineBackend) else None)
        if not backend.writable:
            raise P.offline()
        return RJ.render_timeline(proj, rest, backend.engine.renders)
    if name in FRAME_TOOLS:
        from hermes_studio import frame_tools as FT

        if not backend.writable:
            raise P.offline()  # making a frame writes the cache; a closed-app read never writes
        return FT.TOOLS[name](proj, {k: v for k, v in args.items() if k != "project_id"})
    if name in MEDIA_TOOLS:
        return _media(name, args, proj, backend)
    if writes:
        if not backend.writable:
            raise P.offline()
        return _write(name, args, proj, backend) if name != "export_otio" else proj.export_otio()
    return _read(name, args, proj)


def _media(name: str, args: dict, proj: Any, backend: Backend) -> dict:
    from hermes_studio import media_jobs as MJ

    rest = {k: v for k, v in args.items() if k != "project_id"}
    if name == "get_transcript":
        return MJ.get_transcript(proj, rest)
    if name == "media_status":
        live = backend.engine.media.live_for(proj.id) if isinstance(backend, EngineBackend) else set()
        return MJ.media_status(proj, rest, live)
    if not backend.writable:
        raise P.offline()
    stripped, _ = O.strip_forged(rest)  # the actor is the token's, as on every write
    return MJ.import_media(proj, backend.session, stripped, backend.engine.media)


def _locked(proj: Any):
    import contextlib

    return proj.mutex if hasattr(proj, "mutex") else contextlib.nullcontext()


def _read(name: str, args: dict, proj: Any) -> dict:
    if name == "project_status":
        return proj.status()
    with _locked(proj):
        log = proj.oplog()
        if name == "history_list":
            return log.history_list(**args)
        if name == "history_diff":
            return log.history_diff(**args)
        if name == "get_hash":
            return log.head()
        doc = log.doc
    if name == "get_timeline":
        return doc
    return P.list_markers(doc)


def _write(name: str, args: dict, proj: P.Project, backend: EngineBackend) -> dict:
    with proj.mutex:
        log = proj.oplog()
        if name != "timeline_apply":
            return proj.write_locked(backend.session, name, args)
        stripped, _ = O.strip_forged(args)
        log.check_apply_envelope(stripped)  # 3b: the engine's own envelope check
        ops, used = convert_ops(args["ops"], stripped["ops"])
        pre_ids = set(T._all_ids(log._doc))
        call = dict(args)
        call["ops"] = ops
        try:
            res = proj.write_locked(backend.session, name, call)
        except O.OplogError as e:
            raise repoint(e, args["ops"], pre_ids) from None
    if used:
        res["used"] = used
    return res


def as_result(res: dict | None, err: HermesStudioError | None) -> dict:
    """The MCP tools/call result: readable text + JSON; errors are isError with the body."""
    import json

    if err is not None:
        body = err.as_dict()
        head = f"Error: {body.get('error')}" + (f"\nHint: {body['hint']}" if body.get("hint") else "")
        return {
            "content": [{"type": "text", "text": head}, {"type": "text", "text": json.dumps(body, ensure_ascii=True)}],
            "isError": True,
        }
    images = res.pop("_images", []) if isinstance(res, dict) else []  # S5: pixels only as image content
    text = json.dumps(res, ensure_ascii=True)
    content: list[dict] = [{"type": "text", "text": text}]
    if images:
        import base64

        content += [{"type": "image", "mimeType": mime, "data": base64.b64encode(b).decode("ascii")} for mime, b in images]
    return {"content": content, "isError": False, "structuredContent": json.loads(text)}


def call(name: str, args: dict, backend: Backend) -> dict:
    try:
        return as_result(run_tool(name, args, backend), None)
    except HermesStudioError as e:
        return as_result(None, e)
    except Exception as e:  # never kill the server on one bad call
        return as_result(None, HermesStudioError(f"{type(e).__name__}: {str(e)[-800:]}", code="failed"))
