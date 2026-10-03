"""Phase 2 Q3 presets: named edits that compile to ONE ``timeline_apply`` entry (one card, one
undo). They are plain op batches on the current doc, so they go through the engine's checks and
the S8 mode gate like any other write.

``apply_preset {preset, base_version, client_op_id, summary?, text?, seconds?, preview?}``:
- ``fade_in_out``: every V1 clip fades in and out (``seconds``, default 0.3).
- ``title_card``: ``text`` as a big title over the first ``seconds`` (default 2.5).
- ``end_card``: ``text`` over the last ``seconds`` (default 2.5).
- ``duck_music``: every clip on a music track at 15% volume.
- ``crossfade_all``: a crossfade (``seconds``, default 0.3) between every two touching V1
  clips, pulling the later clips in by the overlap.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

from hermes_studio import oplog as O
from hermes_studio import timeline as T

PRESETS = {
    "fade_in_out": "Fade every clip in and out",
    "title_card": "A title at the start",
    "end_card": "A card at the end",
    "duck_music": "Music at 15% under the voice",
    "crossfade_all": "Crossfade every cut",
}
DEFAULT_SECONDS = {"fade_in_out": 0.3, "title_card": 2.5, "end_card": 2.5, "crossfade_all": 0.3}


def _bad(path: str, rule: str, msg: str) -> O.OplogError:
    return O.OplogError("invalid_op", msg, rule=rule, path=path)


def _snap(t: int, doc: dict) -> int:
    fr = Fraction(T.TICK_RATE) / Fraction(*doc["fps"])
    return int(round(round(Fraction(t) / fr) * fr))


def _v1_clips(doc: dict, spans: dict) -> list[dict]:
    v1 = next((tr for tr in doc["tracks"] if tr["id"] == T.MAIN_TRACK), {"items": []})
    return sorted((it for it in v1["items"] if it["type"] == "clip"), key=lambda it: spans[it["id"]][0])


def compile_preset(doc: dict, name: str, args: dict) -> list[dict]:
    spans = T.resolve(doc)
    secs = args.get("seconds", DEFAULT_SECONDS.get(name))
    d = _snap(int(Fraction(secs) * T.TICK_RATE), doc) if secs is not None else 0
    end = max((e for _, e in spans.values()), default=0)
    text_track = next((tr["id"] for tr in doc["tracks"] if tr["role"] == "text"), None)
    if name == "fade_in_out":
        return [
            {
                "op": "set_fade",
                "id": it["id"],
                "fade_in": min(d, (spans[it["id"]][1] - spans[it["id"]][0]) // 2),
                "fade_out": min(d, (spans[it["id"]][1] - spans[it["id"]][0]) // 2),
            }
            for it in _v1_clips(doc, spans)
        ]
    if name in ("title_card", "end_card"):
        if text_track is None:
            raise _bad("/preset", "bad_arg", "this project has no text track")
        if end <= 0:
            raise _bad("/preset", "bad_arg", "the timeline is empty")
        dur = min(d, end)
        at = 0 if name == "title_card" else end - dur
        return [
            {
                "op": "add_text",
                "track": text_track,
                "text": args["text"],
                "style": "impact" if name == "title_card" else "pop",
                "at": at,
                "dur": dur,
                "fade_in": min(_snap(T.TICK_RATE // 5, doc), dur // 4),
                "fade_out": min(_snap(T.TICK_RATE // 5, doc), dur // 4),
            }
        ]
    if name == "duck_music":
        return [
            {"op": "set_props", "id": it["id"], "props": {"volume": [3, 20]}}
            for tr in doc["tracks"]
            if tr["role"] == "music"
            for it in tr["items"]
            if it["type"] == "clip"
        ]
    # crossfade_all: every touching pair without one, the later clips pulled in by d each time
    clips = _v1_clips(doc, spans)
    v1 = next(tr for tr in doc["tracks"] if tr["id"] == T.MAIN_TRACK)
    faded = {tuple(x["between"]) for x in v1["items"] if x["type"] == "transition"}
    ops: list[dict] = []
    shift = 0
    moved: dict[str, int] = {}
    for a, b in zip(clips, clips[1:], strict=False):
        touching = spans[a["id"]][1] == spans[b["id"]][0]
        la, lb = spans[a["id"]][1] - spans[a["id"]][0], spans[b["id"]][1] - spans[b["id"]][0]
        if touching and (a["id"], b["id"]) not in faded and d * 2 < min(la, lb) and "at" in b:
            shift += d
            ops.append({"op": "add_transition", "between": [a["id"], b["id"]], "dur": d})
        if shift and "at" in b:
            moved[b["id"]] = b["at"] - shift
    return [{"op": "move_clip", "id": i, "at": at} for i, at in moved.items()] + ops


def apply_preset(proj: Any, session: O.Session, args: Any) -> dict:
    from hermes_studio import gate

    gate.refuse_in_ask(proj, session)
    if not isinstance(args, dict):
        raise _bad("", "bad_arg", "arguments must be an object")
    allowed = {"preset", "base_version", "client_op_id", "summary", "group_id", "text", "seconds", "preview"}
    for k in sorted(args, key=repr):
        if k not in allowed:
            raise _bad(f"/{k}", "unknown_arg", f"unknown argument '{k}'")
    name = args.get("preset")
    if name not in PRESETS:
        raise _bad("/preset", "missing_arg" if "preset" not in args else "bad_arg", "preset is one of " + ", ".join(PRESETS))
    if "seconds" in args:
        v = args["seconds"]
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or not 0 < v <= 30:
            raise _bad("/seconds", "bad_arg", "'seconds' must be a number of seconds, more than 0 and at most 30")
    if name in ("title_card", "end_card"):
        t = args.get("text")
        if not isinstance(t, str) or not t.strip():
            raise _bad("/text", "missing_arg" if "text" not in args else "bad_arg", "this preset needs a 'text'")
    preview = args.get("preview", False)
    if not isinstance(preview, bool):
        raise _bad("/preview", "bad_arg", "'preview' must be true or false")
    from hermes_studio import frames as F

    with proj.mutex:
        log = proj.oplog()
        cid = args.get("client_op_id")
        actor = (session.actor.kind, session.actor.id)
        prior = next(
            (e for e in log._entries if (e["actor"]["kind"], e["actor"]["id"]) == actor and e["client_op_id"] == cid), None
        )
        doc = F.doc_at(log, prior["base_version"]) if prior is not None else log.doc  # a retry compiles what it first saw
        ops = compile_preset(doc, name, args)
        if preview or not ops:
            return {"applied": False, "preset": name, "ops": ops, "version": log.version}
        call = {k: args[k] for k in ("base_version", "client_op_id", "group_id") if k in args}
        call["summary"] = args.get("summary") or PRESETS[name]
        call["ops"] = ops
        res = proj.write_locked(session, "timeline_apply", call)
    return {**res, "preset": name, "applied": True}
