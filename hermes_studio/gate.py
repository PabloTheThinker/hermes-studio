"""S8 engine mode gate: Ask / Propose / Auto, with parked writes.

The mode lives in the engine (PLAN-MERGED §4.6) because plain MCP clients never pass through
ACP. It applies to **agent** writes only: a person is the one who approves, so a human token's
writes always apply.

- **Ask:** an agent write is ``permission_denied``.
- **Propose (the default):** an agent write is checked like a real one (envelope, conflict, ops
  and validator, on a scratch copy), then **parked**: nothing is logged, the call returns
  ``needs_approval`` with a ``pending_id``, and ``approval.pending`` goes to the project's SSE
  clients. A person resolves it with ``approval_resolve`` (apply / skip; ``rest`` applies every
  write that agent has parked). It never times out and never resolves itself (Ada's rule,
  PLAN-MERGED Decisions 1). A resolution happens exactly once; asking again returns the outcome.
- **Auto:** agent writes apply at once (and can be undone like any entry).

Parked writes live in ``<project>/pending/<id>.json`` (0600), so they survive an engine restart.
A retry of a parked call (same actor and ``client_op_id``) returns the same ``pending_id``.
"""

from __future__ import annotations

import contextlib
import copy
import os
import secrets
import time
from pathlib import Path
from typing import Any

from hermes_studio import media as M
from hermes_studio import oplog as O
from hermes_studio import project as P

MODES = ("ask", "propose", "auto")
DEFAULT_MODE = "propose"
GATED_TOOLS = ("timeline_apply", "history_undo", "history_redo")


def _bad(path: str, rule: str, msg: str) -> O.OplogError:
    return O.OplogError("invalid_op", msg, rule=rule, path=path)


def mode_of(d: Path) -> str:
    data = M.read_json(d / "mode.json")
    m = data.get("mode") if isinstance(data, dict) else None
    return m if m in MODES else DEFAULT_MODE


def _pending_dir(proj: Any) -> Path:
    return proj.dir / "pending"


def _save(proj: Any, rec: dict) -> None:
    M._write_json(_pending_dir(proj) / f"{rec['pending_id']}.json", rec)


def _load_all(proj: Any) -> list[dict]:
    out = []
    try:
        names = sorted(os.listdir(_pending_dir(proj)))
    except OSError:
        return out
    for n in names:
        if n.endswith(".json") and not n.startswith("."):
            rec = M.read_json(_pending_dir(proj) / n)
            if isinstance(rec, dict) and "pending_id" in rec:
                out.append(rec)
    return sorted(out, key=lambda r: (r["created"], r["pending_id"]))


def _load(proj: Any, pid: str) -> dict | None:
    if not (isinstance(pid, str) and pid.startswith("pend-") and pid[5:].isalnum() and len(pid) <= 40):
        return None
    rec = M.read_json(_pending_dir(proj) / f"{pid}.json")
    return rec if isinstance(rec, dict) else None


def _public(rec: dict) -> dict:
    return {k: copy.deepcopy(v) for k, v in rec.items() if k not in ("args", "after")}


def needs_approval(rec: dict) -> P.ToolError:
    return P.ToolError(
        "needs_approval",
        f"waiting for a person to approve: {rec['summary']}",
        hint="Propose mode: the edit is parked until the person applies or skips it. Watch approval.pending / op.applied "
        "events or poll approval_status with this pending_id; don't resend it with a new client_op_id.",
        pending_id=rec["pending_id"],
    )


def _dry_run(log: O.Oplog, session: O.Session, tool: str, args: dict) -> tuple[dict, dict]:
    """The engine's own answers for this call (same actor), on a scratch copy: nothing is logged.
    Returns the result and the doc it would leave (``timeline_check`` shows both)."""
    shadow = copy.copy(log)
    shadow._entries, shadow._results, shadow._tools = list(log._entries), dict(log._results), dict(log._tools)
    shadow._retired, shadow._batch_ids, shadow._checkpoints = set(log._retired), set(), dict(log._checkpoints)
    shadow._path = None
    res = shadow.call(session, tool, copy.deepcopy(args))
    return res, shadow.doc


def refuse_in_ask(proj: Any, session: O.Session) -> None:
    """Ask mode refuses an agent's write tool before it does any work (S7 cut, S4 import)."""
    if session.actor.kind == "agent" and proj.mode == "ask":
        raise P.ToolError(
            "permission_denied",
            "Ask mode: agents can read and look, not edit",
            hint="The person can switch to Propose or Auto in the Edit page.",
        )


def gate(proj: Any, session: O.Session, tool: str, args: Any, *, after: dict | None = None) -> dict | None:
    """Called by ``Project.write_locked`` (mutex held) before a write. Returns None to go on, or
    raises ``permission_denied`` (Ask) / ``needs_approval`` (Propose). ``after`` is a follow-up
    the engine runs once the write applies (S4's media job for an import)."""
    if session.actor.kind != "agent" or tool not in GATED_TOOLS:
        return None
    mode = proj.mode
    if mode == "auto":
        return None
    if mode == "ask":
        refuse_in_ask(proj, session)
    log = proj.oplog()
    stripped, _ = O.strip_forged(args) if isinstance(args, dict) else (args, [])
    cid = stripped.get("client_op_id") if isinstance(stripped, dict) else None
    key = (session.actor.kind, session.actor.id)
    if isinstance(cid, str):
        if (key[0], key[1], cid) in log._results:
            return None  # already applied: the engine's dedupe answers the retry
        for rec in _load_all(proj):
            if (rec["actor"]["kind"], rec["actor"]["id"]) == key and rec["client_op_id"] == cid:
                if rec["state"] == "pending":
                    raise needs_approval(rec)
                if rec["state"] == "skipped":
                    return {"skipped": rec}
                break  # failed earlier: a fresh attempt is allowed
    _dry_run(log, session, tool, stripped)  # an invalid or stale write is refused now, never parked
    rec = {
        "pending_id": f"pend-{secrets.token_hex(8)}",
        "state": "pending",
        "created": time.time(),
        "actor": {"kind": key[0], "id": key[1]},
        "step": session.plan.step if session.plan else None,
        "tool": tool,
        "client_op_id": cid,
        "summary": (stripped.get("summary") if isinstance(stripped, dict) else None)
        or {"history_undo": "Undo", "history_redo": "Redo"}.get(tool, "Edit"),
        "base_version": stripped.get("base_version") if isinstance(stripped, dict) else None,
        "n_ops": len(stripped.get("ops", [])) if isinstance(stripped, dict) and isinstance(stripped.get("ops"), list) else 0,
        "args": stripped,
        "after": after,
        "result": None,
        "error": None,
    }
    _save(proj, rec)
    proj.notify({"type": "approval.pending", "project_id": proj.id, **_public(rec)})
    raise needs_approval(rec)


def _run_after(proj: Any, after: dict | None) -> None:
    if not after:
        return
    if after.get("kind") == "media":
        from hermes_studio import media_jobs as MJ

        MJ.after_import(proj, after)


def resolve(proj: Any, session: O.Session | None, args: Any) -> dict:
    """``approval_resolve {pending_id, decision: apply|skip, rest?}`` by a person."""
    if session is None or session.actor.kind != "human":
        raise P.ToolError("permission_denied", "only a person can apply or skip a parked edit")
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    for k in sorted(args, key=repr):
        if k not in ("pending_id", "decision", "rest"):
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    if args.get("decision") not in ("apply", "skip"):
        raise _bad("/decision", "missing_arg" if "decision" not in args else "bad_arg", "'decision' is apply or skip")
    rest = args.get("rest", False)
    if not isinstance(rest, bool):
        raise _bad("/rest", "bad_arg", "'rest' must be true or false")
    pid = args.get("pending_id")
    if not isinstance(pid, str):
        raise _bad("/pending_id", "missing_arg" if "pending_id" not in args else "bad_arg", "'pending_id' must be a string")
    with proj.mutex:
        rec = _load(proj, pid)
        if rec is None:
            raise O.OplogError("not_found", f"no parked edit {pid!r}", rule="not_found", path="/pending_id", id=pid)
        todo = [rec]
        if rest and rec["state"] == "pending":
            todo += [
                r for r in _load_all(proj) if r["state"] == "pending" and r["actor"] == rec["actor"] and r["pending_id"] != pid
            ]
        out = [_resolve_one(proj, r, args["decision"]) for r in todo]
    return {"resolved": out[0], "also": out[1:]}


def _resolve_one(proj: Any, rec: dict, decision: str) -> dict:
    if rec["state"] != "pending":
        return _public(rec)  # exactly once: a second answer changes nothing
    if decision == "skip":
        rec["state"] = "skipped"
    else:
        sess = O.Session(
            O.Actor(rec["actor"]["kind"], rec["actor"]["id"]), O.PlanContext(rec["step"]) if rec.get("step") is not None else None
        )
        try:
            res = proj.write_locked(sess, rec["tool"], rec["args"], gated=False)
            rec.update(state="applied", result={k: res.get(k) for k in ("op_id", "seq", "new_version", "hash", "summary")})
        except P.HermesStudioError as e:
            rec.update(state="failed", error=e.as_dict())
    rec["resolved"] = time.time()
    _save(proj, rec)
    if rec["state"] == "applied":
        with contextlib.suppress(Exception):
            _run_after(proj, rec.get("after"))
    proj.notify({"type": "approval.resolved", "project_id": proj.id, **_public(rec)})
    return _public(rec)


def status(proj: Any, args: Any) -> dict:
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    pid = args.get("pending_id")
    if not isinstance(pid, str):
        raise _bad("/pending_id", "missing_arg" if "pending_id" not in args else "bad_arg", "'pending_id' must be a string")
    preview = args.get("preview", False)
    if not isinstance(preview, bool):
        raise _bad("/preview", "bad_arg", "'preview' must be true or false")
    rec = _load(proj, pid)
    if rec is None:
        raise O.OplogError("not_found", f"no parked edit {pid!r}", rule="not_found", path="/pending_id", id=pid)
    out = _public(rec)
    if preview and rec["state"] == "pending":
        out["preview"] = _preview(proj, rec)
    return out


def _preview(proj: Any, rec: dict) -> dict:
    """What Apply would do now: the parked call dry-run as its agent on a scratch log, with the
    items it would change and an outline of the result, or the refusal Apply would meet."""
    import contextlib

    from hermes_studio.outline import outline

    session = O.Session(O.Actor(rec["actor"]["kind"], rec["actor"]["id"]))
    with proj.mutex if hasattr(proj, "mutex") else contextlib.nullcontext():
        try:
            res, doc = _dry_run(proj.oplog(), session, rec["tool"], rec["args"])
        except O.OplogError as e:
            return {"would_apply": False, "error": e.as_dict()}
    o = outline(doc)
    return {"would_apply": True, "changed_ids": res["changed_ids"], "length_s": o["length_s"], "outline": o["text"]}


def listing(proj: Any, args: Any) -> dict:
    if isinstance(args, dict):
        for k in sorted(args, key=repr):
            if k != "all":
                raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    every = isinstance(args, dict) and args.get("all") is True
    recs = [_public(r) for r in _load_all(proj) if every or r["state"] == "pending"]
    return {"mode": getattr(proj, "mode", None) or mode_of(proj.dir), "pending": recs}


def set_mode(proj: Any, session: O.Session | None, args: Any) -> dict:
    if session is None or session.actor.kind != "human":
        raise P.ToolError("permission_denied", "only a person can change the mode")
    if not isinstance(args, dict) or set(args) - {"mode"}:
        k = sorted(set(args) - {"mode"}, key=repr)[0] if isinstance(args, dict) else ""
        raise _bad(f"/{k}" if k else "", "unknown_arg" if k else "bad_arg", f"unknown argument '{k}'")
    m = args.get("mode")
    if m not in MODES:
        raise _bad("/mode", "missing_arg" if "mode" not in args else "bad_arg", "mode is ask, propose or auto")
    with proj.mutex:
        old = proj.mode
        M._write_json(proj.dir / "mode.json", {"mode": m})
        proj._mode = m
    if old != m:
        proj.notify({"type": "mode.changed", "project_id": proj.id, "mode": m, "was": old})
    return {"mode": m, "was": old}
