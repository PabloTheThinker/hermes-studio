"""S7 transcript cuts: remove fillers, long pauses or given ranges as ONE log entry.

``transcript_cut`` compiles the cuts into one ordinary ``timeline_apply`` batch of
``split_clip`` + ``delete_clip{ripple}`` ops on V1, so the whole cut is one entry, one card and
one undo (Prove C12), and it goes through the same engine path (and, from S8, the same mode
gate) as any other write.

Cuts are found on the words ``get_transcript`` maps onto the timeline (S4), snapped to the
timeline's frame grid, and applied from the end of the timeline backwards, so a ripple never
moves a cut still to come. Piece ids are derived from the ``client_op_id``, so a retry compiles
to the same ops and the engine's dedupe returns the first result.
"""

from __future__ import annotations

import hashlib
from fractions import Fraction
from typing import Any

from hermes_studio import oplog as O
from hermes_studio import pacing
from hermes_studio import timeline as T

PAD = T.TICK_RATE // 20  # 50 ms of the silence around a filler goes with it
MAX_PAUSE = int(pacing.MAX_PAUSE * T.TICK_RATE)  # a pause longer than this is cut ...
KEEP_PAUSE = int(pacing.KEEP_PAUSE * T.TICK_RATE)  # ... down to this
MAX_RANGES = 500


def _bad(path: str, rule: str, msg: str) -> O.OplogError:
    return O.OplogError("invalid_op", msg, rule=rule, path=path)


def _frame(doc: dict) -> Fraction:
    return Fraction(T.TICK_RATE) / Fraction(*doc["fps"])


def _snap(t: int, frame: Fraction) -> int:
    """The nearest frame boundary, in whole ticks."""
    return int(round(round(Fraction(t) / frame) * frame))


def merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(r for r in ranges if r[1] > r[0]):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def filler_ranges(words: list[dict], *, fillers: bool, pauses: bool) -> list[dict]:
    """Ranges to cut from timeline words (sorted, each with the clip that shows it)."""
    out: list[dict] = []
    by_clip: dict[str, list[dict]] = {}
    for w in words:
        by_clip.setdefault(w["clip"], []).append(w)
    for clip, ws in by_clip.items():
        ws = sorted(ws, key=lambda w: w["at"])
        for i, w in enumerate(ws):
            prev_end = ws[i - 1]["end"] if i else None
            nxt = ws[i + 1]["at"] if i + 1 < len(ws) else None
            if fillers and pacing.is_filler(w["w"]):
                a = w["at"] - PAD if prev_end is None else max(prev_end, w["at"] - PAD)
                b = w["end"] + PAD if nxt is None else min(nxt, w["end"] + PAD)
                out.append({"from": max(0, a), "to": b, "why": "filler", "word": w["w"], "clip": clip})
        if pauses:
            spoken = [w for w in ws if not (fillers and pacing.is_filler(w["w"]))]
            for x, y in zip(spoken, spoken[1:], strict=False):
                gap = y["at"] - x["end"]
                if gap > MAX_PAUSE:
                    out.append(
                        {"from": x["end"] + KEEP_PAUSE // 2, "to": y["at"] - KEEP_PAUSE // 2, "why": "pause", "clip": clip}
                    )
    return sorted(out, key=lambda r: (r["from"], r["to"]))


def compile_cuts(doc: dict, ranges: list[tuple[int, int]], key: str) -> tuple[list[dict], list[dict], list[dict]]:
    """(ops, applied, skipped) cutting ``ranges`` (timeline ticks) out of V1 with ripple.

    A range is clipped to each V1 clip it crosses and snapped to the frame grid. Skipped: a range
    inside a transition's overlap, on a clip whose speed isn't 1, or shorter than one frame."""
    frame = _frame(doc)
    spans = T.resolve(doc)
    v1 = next((tr for tr in doc["tracks"] if tr["id"] == T.MAIN_TRACK), {"items": []})
    clips = sorted((it for it in v1["items"] if it["type"] == "clip"), key=lambda it: spans[it["id"]][0])
    busy = [spans[it["id"]] for it in v1["items"] if it["type"] == "transition"]
    salt = hashlib.sha256(key.encode()).hexdigest()[:6]
    n = [0]

    def fresh(base: str) -> str:
        n[0] += 1
        return f"{base[:40]}.{salt}{n[0]}"

    per_clip: dict[str, list[tuple[int, int]]] = {}
    applied, skipped = [], []
    for a0, b0 in merge(ranges):
        for it in clips:
            s, e = spans[it["id"]]
            a, b = max(a0, s), min(b0, e)
            if b <= a:
                continue
            a, b = _snap(a, frame), _snap(b, frame)
            if a - s < frame:
                a = s
            if e - b < frame:
                b = e
            why = None
            if b - a < frame:
                why = "shorter than one frame"
            elif any(x < b and a < y for x, y in busy):
                why = "inside a transition"
            elif Fraction(*{**T.DEFAULT_PROPS, **(it.get("props") or {})}["speed"]) != 1:
                why = "the clip's speed isn't 1"
            if why:
                skipped.append({"from": a, "to": b, "clip": it["id"], "why": why})
                continue
            per_clip.setdefault(it["id"], []).append((a, b))
            applied.append({"from": a, "to": b, "clip": it["id"]})
    ops: list[dict] = []
    for it in reversed(clips):  # last clip first: a ripple never moves a cut still to come
        cuts = sorted(per_clip.get(it["id"], []), reverse=True)
        if not cuts:
            continue
        s, e = spans[it["id"]]
        cur, cur_end = it["id"], e
        for a, b in cuts:
            if b < cur_end:
                left, right = fresh(it["id"]), fresh(it["id"])
                ops.append({"op": "split_clip", "id": cur, "at": b, "ids": [left, right]})
                cur, cur_end = left, b
            if a > s:
                left, mid = fresh(it["id"]), fresh(it["id"])
                ops.append({"op": "split_clip", "id": cur, "at": a, "ids": [left, mid]})
                ops.append({"op": "delete_clip", "id": mid, "ripple": True})
                cur, cur_end = left, a
            else:
                ops.append({"op": "delete_clip", "id": cur, "ripple": True})
                break  # the whole rest of the clip is gone; this was its first cut
    return ops, applied, skipped


def _seconds_range(r: Any, i: int) -> tuple[int, int]:
    if not isinstance(r, dict) or set(r) - {"from_s", "to_s"} or not {"from_s", "to_s"} <= set(r):
        raise _bad(f"/ranges/{i}", "bad_arg", "each range is {from_s, to_s} in timeline seconds")
    out = []
    for k in ("from_s", "to_s"):
        v = r[k]
        if isinstance(v, bool) or not isinstance(v, int | float) or v != v or v in (float("inf"), float("-inf")) or v < 0:
            raise _bad(f"/ranges/{i}/{k}", "bad_arg", "a time must be a number of seconds, 0 or more")
        out.append(int(Fraction(v) * T.TICK_RATE))
    if out[1] <= out[0]:
        raise _bad(f"/ranges/{i}/to_s", "bad_arg", "to_s must be after from_s")
    return out[0], out[1]


def plan_cut(doc: dict, words: list[dict], args: dict, key: str) -> dict:
    """Validate ``args`` and compile the cut against ``doc``: ``{ops, cuts, skipped, removed}``."""
    fillers = args.get("fillers", False)
    pauses = args.get("pauses", False)
    for k, v in (("fillers", fillers), ("pauses", pauses)):
        if not isinstance(v, bool):
            raise _bad(f"/{k}", "bad_arg", f"'{k}' must be true or false")
    raw = args.get("ranges", [])
    if not isinstance(raw, list) or len(raw) > MAX_RANGES:
        raise _bad("/ranges", "bad_arg", f"'ranges' must be a list of at most {MAX_RANGES} {{from_s, to_s}}")
    explicit = [_seconds_range(r, i) for i, r in enumerate(raw)]
    if not (fillers or pauses or explicit):
        raise _bad("/fillers", "missing_arg", "say what to cut: fillers, pauses and/or ranges")
    found = filler_ranges(words, fillers=fillers, pauses=pauses)
    ranges = explicit + [(r["from"], r["to"]) for r in found]
    ops, applied, skipped = compile_cuts(doc, ranges, key)
    return {"ops": ops, "cuts": applied, "skipped": skipped, "found": found, "removed": sum(c["to"] - c["from"] for c in applied)}


def _words_for(proj: Any, doc: dict) -> list[dict]:
    from hermes_studio import media as M

    words: dict[str, list[dict]] = {}
    for mid in doc["media"]:
        data = M.read_json(M.cache_paths(proj.dir, mid)["words"])
        if isinstance(data, dict) and isinstance(data.get("words"), list):
            words[mid] = data["words"]
    return M.timeline_words(doc, words)


def transcript_cut(proj: Any, session: O.Session, args: Any) -> dict:
    """The ``transcript_cut`` tool: ``{base_version, client_op_id, summary?, group_id?, fillers?,
    pauses?, ranges?, preview?}``. With ``preview`` nothing is written."""
    from hermes_studio import frames as F

    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    allowed = {"base_version", "client_op_id", "summary", "group_id", "fillers", "pauses", "ranges", "preview"}
    for k in sorted(args, key=repr):
        if k not in allowed:
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    preview = args.get("preview", False)
    if not isinstance(preview, bool):
        raise _bad("/preview", "bad_arg", "'preview' must be true or false")
    with proj.mutex:
        log = proj.oplog()
        if not preview:  # the engine's own envelope answers, in its order (the summary is ours when not given)
            env = {k: args[k] for k in ("base_version", "client_op_id", "summary", "group_id") if k in args}
            log.check_apply_envelope({"summary": "cut", **env, "ops": [{"op": "split_clip"}]})  # ops: ours, checked later
        cid = args.get("client_op_id", "preview")
        actor = (session.actor.kind, session.actor.id)
        prior = next(
            (e for e in log._entries if (e["actor"]["kind"], e["actor"]["id"]) == actor and e["client_op_id"] == cid), None
        )
        if prior is None and not preview:
            log._base_version({"summary": "cut", **env, "ops": [{"op": "split_clip"}]}, required=True)  # conflict first
        bv = args.get("base_version", log.version)
        at = prior["base_version"] if prior is not None else bv if O._int_arg(bv) and 0 <= bv <= log.version else log.version
        doc = F.doc_at(log, at) if at != log.version else log.doc
        plan = plan_cut(doc, _words_for(proj, doc), args, str(cid))
        out = {k: plan[k] for k in ("cuts", "skipped", "removed")}
        out["removed_s"] = plan["removed"] / T.TICK_RATE
        if len(plan["ops"]) > O.MAX_OPS and not preview:
            raise _bad(
                "/fillers",
                "bad_arg",
                f"{len(plan['cuts'])} cuts need {len(plan['ops'])} ops, over the {O.MAX_OPS} "
                "one entry can hold; cut part of the timeline with ranges, then the rest",
            )
        if preview or not plan["ops"]:
            return {**out, "applied": False, "ops": plan["ops"], "version": log.version}
        n_fill = sum(1 for f in plan["found"] if f["why"] == "filler")
        n_pause = sum(1 for f in plan["found"] if f["why"] == "pause")
        bits = [f"{n_fill} filler{'s' * (n_fill != 1)}"] * bool(n_fill) + [f"{n_pause} pause{'s' * (n_pause != 1)}"] * bool(
            n_pause
        )
        bits += [f"{len(args.get('ranges', []))} range{'s' * (len(args.get('ranges', [])) != 1)}"] * bool(args.get("ranges"))
        call = {k: args[k] for k in ("base_version", "client_op_id", "group_id") if k in args}
        call["summary"] = args.get("summary") or f"Cut {', '.join(bits)} ({out['removed_s']:.1f} s)"
        call["ops"] = plan["ops"]
        res = proj.write_locked(session, "timeline_apply", call)
    return {**res, **out, "applied": True}
