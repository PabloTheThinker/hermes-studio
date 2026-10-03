"""Phase 2 Q2 draft branches: an agent (or a person) edits a copy; a person keeps or discards it.

- ``draft_new {project_id}`` copies the main timeline at its head into a new project
  ``<main>.d<hex>`` (mode Auto: edits in a draft apply at once, it's a sandbox) and records
  ``draft.json`` ``{main, from_version, from_hash}``. Refused in Ask mode for agents.
- Edits go to the draft's own ``project_id`` with every normal tool, with their own log and undo.
- ``draft_keep {project_id: <draft>, summary?}`` (a person): the main timeline's media, tracks and
  markers become the draft's as **one** entry (``Oplog.call(..., "keep_body")``, one undo). If the main moved
  since the draft was made it's ``conflict`` (re-draft or discard). The draft is marked kept.
- ``draft_discard {project_id: <draft>}`` (a person): the draft folder is deleted; the main is
  untouched, so its hash is exactly what it was.
- ``draft_list {project_id: <main>}``: the main's drafts and their state.
"""

from __future__ import annotations

import secrets
import shutil
import time
from typing import Any

from hermes_studio import media as M
from hermes_studio import oplog as O
from hermes_studio import project as P
from hermes_studio import timeline as T


def _bad(path: str, rule: str, msg: str) -> O.OplogError:
    return O.OplogError("invalid_op", msg, rule=rule, path=path)


def _human(session: O.Session | None, what: str) -> None:
    if session is None or session.actor.kind != "human":
        raise P.ToolError("permission_denied", f"only a person can {what} a draft")


def info(proj: Any) -> dict | None:
    data = M.read_json(proj.dir / "draft.json")
    return data if isinstance(data, dict) and "main" in data else None


def _need_draft(proj: Any) -> dict:
    d = info(proj)
    if d is None:
        raise _bad("/project_id", "bad_arg", f"{proj.id!r} is not a draft")
    if d.get("state") != "open":
        raise _bad("/project_id", "bad_arg", f"draft {proj.id!r} was already {d.get('state')}")
    return d


def draft_new(engine: P.Engine, session: O.Session, main: P.Project, args: Any) -> dict:
    from hermes_studio import gate

    gate.refuse_in_ask(main, session)
    if not isinstance(args, dict) or args:
        k = sorted(args, key=repr)[0] if isinstance(args, dict) else ""
        raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    if info(main) is not None:
        raise _bad("/project_id", "bad_arg", "a draft can't have drafts; keep or discard it first")
    with main.mutex:
        doc = main.oplog().doc
    did = f"{main.id[:48]}.d{secrets.token_hex(3)}"
    base = {**doc, "id": did, "version": 0}
    base.pop("hash", None)
    d = P.create_project(base)
    M._write_json(d / "mode.json", {"mode": "auto"})
    M._write_json(
        d / "draft.json",
        {
            "main": main.id,
            "from_version": doc["version"],
            "from_hash": doc["hash"],
            "created": time.time(),
            "by": session.actor.as_dict(),
            "state": "open",
        },
    )
    return {**engine.get(did).status(), "draft_of": main.id, "from_version": doc["version"]}


def draft_list(engine: P.Engine | None, main: Any) -> dict:
    out = []
    for row in P.list_projects(engine)["projects"]:
        pid = row.get("project_id", "")
        if not pid.startswith(main.id + ".d"):
            continue
        d = M.read_json(P.project_dir(pid) / "draft.json") if P.project_dir(pid) else None
        if isinstance(d, dict) and d.get("main") == main.id:
            out.append({**row, "draft": d})
    return {"project_id": main.id, "drafts": out}


def draft_keep(engine: P.Engine, session: O.Session | None, draft: P.Project, args: Any) -> dict:
    _human(session, "keep")
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    for k in sorted(args, key=repr):
        if k not in ("summary", "client_op_id"):
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    d = _need_draft(draft)
    main = engine.get(d["main"])
    with draft.mutex:
        body = draft.oplog().doc
        n_edits = len(draft.oplog()._entries)
    call = {
        "client_op_id": args.get("client_op_id") or f"keep-{draft.id[-16:]}",
        "base_version": d["from_version"],
        "summary": args.get("summary") or f"Keep draft ({n_edits} edit{'s' * (n_edits != 1)})",
    }
    with main.mutex:
        res = main.keep_locked(session, call, {k: body[k] for k in O.BODY_KEYS})
    M._write_json(draft.dir / "draft.json", {**d, "state": "kept", "op_id": res["op_id"], "resolved": time.time()})
    return {**res, "draft": draft.id, "main": main.id}


def draft_discard(engine: P.Engine, session: O.Session | None, draft: P.Project, args: Any) -> dict:
    _human(session, "discard")
    if isinstance(args, dict) and args:
        raise _bad(f"/{sorted(args, key=repr)[0]}", "unknown_arg", "draft_discard takes only the draft's project_id")
    d = info(draft)
    if d is None:
        raise _bad("/project_id", "bad_arg", f"{draft.id!r} is not a draft")
    with engine._lock:
        p = engine.projects.pop(draft.id, None)
    if p is not None:
        if engine._media is not None:
            engine._media.cancel_project(p.id)
        p.close()
    shutil.rmtree(draft.dir, ignore_errors=True)
    return {"discarded": draft.id, "main": d["main"]}


def body_equal(a: dict, b: dict) -> bool:
    """Keep's promise, for tests and checks: the two docs show the same media, tracks and markers."""

    def norm(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "hash"} | {"id": "x", "version": 0}

    return T.canonical_hash(norm(a)) == T.canonical_hash(norm(b))
