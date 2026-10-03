"""Run the Phase 2 Q1 eval set.

    python -m evals.run --reference            # the reference solutions (must score 20/20)
    python -m evals.run --check t02-remove-fillers --project <id>   # score a project an agent edited

Scoring (per model and build, PLAN-MERGED Phase 2): correct (the check passes), steps (log
entries the agent wrote), undo rate (its entries that are undos). Results are one JSON object
on stdout; save it as evals/results/<model>-<build>.json to compare runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from evals.tasks import TASKS, fixture_doc, fixture_words


def _engine(home: Path):
    os.environ["HOME"] = str(home)
    from hermes_studio import media as M
    from hermes_studio import project as P

    d = P.create_project(fixture_doc())
    (d / "mode.json").write_text('{"mode": "auto"}')
    M._write_json(M.cache_paths(d, "m1")["words"], {"words": fixture_words()})
    eng = P.Engine(port=0)
    return eng, eng.open("eval")


def _call(backend, proj, tool: str, args: dict, n: int) -> dict:
    from hermes_studio import mcp_timeline as MT

    a = {"project_id": "eval", **args}
    if tool in ("timeline_apply", "transcript_cut", "apply_preset", "history_undo"):
        a.setdefault("client_op_id", f"eval-{n}")
    if tool in ("timeline_apply", "transcript_cut", "apply_preset"):
        a.setdefault("base_version", proj.log.version)
    r = MT.call(tool, a, backend)
    if r["isError"]:
        raise RuntimeError(f"{tool}: {r['content'][-1]['text'][:300]}")
    return r["structuredContent"]


def score(task, proj) -> dict:
    from hermes_studio import media_jobs as MJ

    doc = proj.log.doc
    log = [e for e in proj.log._entries if e["actor"]["kind"] == "agent"]
    words = MJ.get_transcript(proj, {})["words"]
    try:
        ok = bool(task.check(doc, log, words))
    except Exception:  # a check that can't read the doc is a fail, not a crash
        ok = False
    undos = sum(1 for e in log if e["undoes"])
    return {"id": task.id, "pass": ok, "writes": len(log), "undos": undos}


def run_reference() -> dict:
    from hermes_studio import mcp_timeline as MT
    from hermes_studio import oplog as O

    rows = []
    for task in TASKS:
        with tempfile.TemporaryDirectory() as tmp:
            eng, proj = _engine(Path(tmp))
            backend = MT.EngineBackend(eng, O.Session(O.Actor("agent", "reference")), frozenset({"read", "write", "render"}))
            try:
                for n, (tool, args) in enumerate(task.solution):
                    if tool == "undo_last":
                        _call(backend, proj, "history_undo", {"op_id": proj.log._entries[-1]["op_id"]}, n)
                    elif tool == "compose":  # a transcript cut's ops plus more ops, as one entry
                        cut = _call(backend, proj, "transcript_cut", {**args["cut"], "preview": True}, n)
                        _call(backend, proj, "timeline_apply", {"summary": "Compose", "ops": cut["ops"] + args["ops"]}, n)
                    else:
                        _call(backend, proj, tool, args, n)
                rows.append(score(task, proj))
            except RuntimeError as e:
                rows.append({"id": task.id, "pass": False, "error": str(e)})
            finally:
                eng.close()
    return summary(rows, model="reference")


def summary(rows: list[dict], model: str) -> dict:
    from hermes_studio import __version__

    writes = sum(r.get("writes", 0) for r in rows)
    return {
        "model": model,
        "build": __version__,
        "correct": sum(r["pass"] for r in rows),
        "total": len(rows),
        "steps": writes,
        "undo_rate": round(sum(r.get("undos", 0) for r in rows) / writes, 3) if writes else 0.0,
        "tasks": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", action="store_true")
    ap.add_argument("--check", metavar="TASK")
    ap.add_argument("--project", metavar="ID")
    ap.add_argument("--model", default="unknown")
    a = ap.parse_args(argv)
    if a.reference:
        out = run_reference()
    elif a.check and a.project:
        from hermes_studio import project as P

        task = next((t for t in TASKS if t.id == a.check), None)
        if task is None:
            ap.error(f"no task {a.check}")
        out = summary([score(task, P.ClosedProject(a.project))], model=a.model)
    else:
        ap.error("--reference, or --check TASK --project ID")
    print(json.dumps(out, indent=1))
    return 0 if out["correct"] == out["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
