"""Phase 2 Q1 eval set: 20 pinned editing tasks for agents.

Each task has the prompt a person would give, a check on the final timeline (and, where it
matters, the log), and a reference solution (the tool calls a good agent makes). The fixture is
the same for every task: a 60 s talk (m1, 30 fps) placed as three clips on V1 with words that
include fillers, plus a song (m2) on the music track. ``run.py`` scores an agent's attempt for
correctness, steps (tool calls that wrote) and undo rate, per model and build.

The words file is written into the project's cache, so no Whisper model is needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

S = 705600000
FPS_FRAME = S // 30


def fixture_doc(project_id: str = "eval") -> dict:
    from hermes_studio import timeline as T

    d = T.new_timeline(project_id)
    d["media"] = {
        "m1": {"path": "/eval/talk.mp4", "dur": 60 * S, "fps": [30, 1]},
        "m2": {"path": "/eval/song.mp3", "dur": 90 * S, "fps": None},
    }
    tr = {t["id"]: t for t in d["tracks"]}
    tr["V1"]["items"] = [
        {"id": "c1", "type": "clip", "media": "m1", "src": [0, 10 * S], "at": 0, "fade_in": 0, "fade_out": 0},
        {"id": "c2", "type": "clip", "media": "m1", "src": [20 * S, 30 * S], "at": 10 * S, "fade_in": 0, "fade_out": 0},
        {"id": "c3", "type": "clip", "media": "m1", "src": [40 * S, 50 * S], "at": 20 * S, "fade_in": 0, "fade_out": 0},
    ]
    tr["A2"]["items"] = [{"id": "mu", "type": "clip", "media": "m2", "src": [0, 30 * S], "at": 0, "fade_in": 0, "fade_out": 0}]
    return d


def fixture_words() -> list[dict]:
    """A word every 0.5 s through the whole talk; every 7th is a filler."""
    fill = ("um", "uh", "erm")
    return [
        {"w": fill[i // 7 % 3] if i % 7 == 6 else f"w{i}", "in": i * S // 2, "out": i * S // 2 + 3 * S // 10} for i in range(120)
    ]


def _spans(doc: dict) -> dict:
    from hermes_studio import timeline as T

    return T.resolve(doc)


def _end(doc: dict) -> int:
    return max((e for _, e in _spans(doc).values()), default=0)


def _v1(doc: dict) -> list[dict]:
    v1 = next(t for t in doc["tracks"] if t["id"] == "V1")
    sp = _spans(doc)
    return sorted((it for it in v1["items"] if it["type"] == "clip"), key=lambda it: sp[it["id"]][0])


def _texts(doc: dict) -> list[dict]:
    return [it for t in doc["tracks"] if t["role"] == "text" for it in t["items"]]


def _music(doc: dict) -> list[dict]:
    return [it for t in doc["tracks"] if t["role"] == "music" for it in t["items"] if it["type"] == "clip"]


def _frac(v: Any) -> float:
    return v[0] / v[1] if isinstance(v, list) else float(v)


@dataclass
class Task:
    id: str
    prompt: str
    check: Callable[[dict, list[dict], list[dict]], bool]  # (final doc, log entries, timeline words) -> pass
    solution: list[tuple[str, dict]] = field(default_factory=list)  # (tool, args without project_id/base_version/client_op_id)


def _no_fillers(doc: dict, log: list[dict], words: list[dict]) -> bool:
    from hermes_studio import pacing

    return bool(words) and not any(pacing.is_filler(w["w"]) for w in words)


TASKS: list[Task] = [
    Task(
        "t01-title",
        'Add the title "HERMES" over the first 2 seconds.',
        lambda d, log, w: any(x["text"] == "HERMES" and _spans(d)[x["id"]] == (0, 2 * S) for x in _texts(d)),
        [
            (
                "timeline_apply",
                {"summary": "Title", "ops": [{"op": "add_text", "text": "HERMES", "style": "impact", "at_s": 0, "dur_s": 2}]},
            )
        ],
    ),
    Task("t02-remove-fillers", "Remove every filler word (um, uh, erm).", _no_fillers, [("transcript_cut", {"fillers": True})]),
    Task(
        "t03-delete-middle",
        "Delete the middle clip and close the gap.",
        lambda d, log, w: [c["id"] for c in _v1(d)] == ["c1", "c3"] and _end_v1(d) == 20 * S,
        [("timeline_apply", {"summary": "Delete c2", "ops": [{"op": "delete_clip", "id": "c2", "ripple": True}]})],
    ),
    Task(
        "t04-trim-first",
        "Make the first clip 6 seconds long, keeping its start, and pull the rest in.",
        lambda d, log, w: _spans(d)["c1"] == (0, 6 * S) and _spans(d)["c2"][0] == 6 * S,
        [("timeline_apply", {"summary": "Trim c1", "ops": [{"op": "trim_clip", "id": "c1", "src_out_s": 6, "ripple": True}]})],
    ),
    Task(
        "t05-duck-music",
        "Turn the music down to 15%.",
        lambda d, log, w: (
            bool(_music(d)) and all(abs(_frac((m.get("props") or {}).get("volume", [1, 1])) - 0.15) < 1e-9 for m in _music(d))
        ),
        [("apply_preset", {"preset": "duck_music"})],
    ),
    Task(
        "t06-fade-all",
        "Fade every clip in and out by about 0.3 s.",
        lambda d, log, w: all(0 < c["fade_in"] <= S // 2 and 0 < c["fade_out"] <= S // 2 for c in _v1(d)),
        [("apply_preset", {"preset": "fade_in_out"})],
    ),
    Task(
        "t07-crossfades",
        "Crossfade every cut between clips.",
        lambda d, log, w: sum(1 for t in d["tracks"] if t["id"] == "V1" for it in t["items"] if it["type"] == "transition") == 2,
        [("apply_preset", {"preset": "crossfade_all"})],
    ),
    Task(
        "t08-end-card",
        'End with "Follow for more" over the last 2.5 seconds.',
        lambda d, log, w: any(x["text"] == "Follow for more" and _spans(d)[x["id"]][1] == _end(d) for x in _texts(d)),
        [("apply_preset", {"preset": "end_card", "text": "Follow for more"})],
    ),
    Task(
        "t09-split",
        "Split the second clip at 15 s.",
        lambda d, log, w: len(_v1(d)) == 4 and any(_spans(d)[c["id"]][0] == 15 * S for c in _v1(d)),
        [("timeline_apply", {"summary": "Split c2", "ops": [{"op": "split_clip", "id": "c2", "at_s": 15}]})],
    ),
    Task(
        "t10-marker",
        'Put a marker called "hook" at 4 s.',
        lambda d, log, w: any(m["label"] == "hook" and m["at"] == 4 * S for m in d["markers"]),
        [("timeline_apply", {"summary": "Marker", "ops": [{"op": "add_marker", "at_s": 4, "label": "hook"}]})],
    ),
    Task(
        "t11-speed",
        "Play the last clip at double speed.",
        lambda d, log, w: _frac((_v1(d)[-1].get("props") or {}).get("speed", [1, 1])) == 2,
        [("timeline_apply", {"summary": "2x", "ops": [{"op": "set_props", "id": "c3", "props": {"speed": [2, 1]}}]})],
    ),
    Task(
        "t12-under-25",
        "Get the video under 25 seconds without touching the first clip.",
        lambda d, log, w: _end_v1(d) < 25 * S and _spans(d)["c1"] == (0, 10 * S),
        [
            (
                "timeline_apply",
                {"summary": "Tighten c3", "ops": [{"op": "trim_clip", "id": "c3", "src_out_s": 44, "ripple": True}]},
            )
        ],
    ),
    Task(
        "t13-cut-range",
        "Cut 12 s to 14 s out of the timeline.",
        lambda d, log, w: _end_v1(d) == 28 * S,
        [("transcript_cut", {"ranges": [{"from_s": 12, "to_s": 14}]})],
    ),
    Task(
        "t14-tighten",
        "Tighten long pauses.",
        lambda d, log, w: True,  # the fixture has none: a good agent finds nothing to cut and says so (0 writes)
        [],
    ),
    Task(
        "t15-title-impact",
        'Change the title style of an existing "Hi" title to impact.',
        lambda d, log, w: any(x["text"] == "Hi" and x["style"] == "impact" for x in _texts(d)),
        [
            (
                "timeline_apply",
                {"summary": "Hi", "ops": [{"op": "add_text", "text": "Hi", "style": "pop", "at_s": 0, "dur_s": 1, "id": "hi"}]},
            ),
            ("timeline_apply", {"summary": "Impact", "ops": [{"op": "edit_text", "id": "hi", "style": "impact"}]}),
        ],
    ),
    Task(
        "t16-move-last-first",
        "Move the last clip to the start (shift the others later).",
        lambda d, log, w: _v1(d)[0]["id"] == "c3",
        [
            (
                "timeline_apply",
                {
                    "summary": "Reorder",
                    "ops": [
                        {"op": "move_clip", "id": "c3", "at_s": 30},
                        {"op": "move_clip", "id": "c2", "at_s": 20},
                        {"op": "move_clip", "id": "c1", "at_s": 10},
                        {"op": "move_clip", "id": "c3", "at_s": 0},
                    ],
                },
            )
        ],
    ),
    Task(
        "t17-one-entry",
        'Remove the fillers and add the title "HERMES" as ONE undoable step.',
        lambda d, log, w: (
            len([e for e in log if e["undoes"] is None]) == 1
            and _no_fillers(d, log, w)
            and any(x["text"] == "HERMES" for x in _texts(d))
        ),
        [
            (
                "compose",
                {
                    "cut": {"fillers": True},
                    "ops": [{"op": "add_text", "text": "HERMES", "style": "impact", "at": 0, "dur": 2 * S}],
                },
            )
        ],
    ),
    Task(
        "t18-undo-own",
        "Add a marker at 1 s, then undo it.",
        lambda d, log, w: not d["markers"] and len(log) == 2 and log[-1]["undoes"],
        [("timeline_apply", {"summary": "m", "ops": [{"op": "add_marker", "at_s": 1, "label": "x"}]}), ("undo_last", {})],
    ),
    Task(
        "t19-music-fade",
        "Fade the music out over its last 2 seconds.",
        lambda d, log, w: all(m["fade_out"] == 2 * S for m in _music(d)),
        [("timeline_apply", {"summary": "Music fade", "ops": [{"op": "set_fade", "id": "mu", "fade_out_s": 2}]})],
    ),
    Task("t20-no-change", "What is the current length of the video? Don't change anything.", lambda d, log, w: log == [], []),
]


def _end_v1(doc: dict) -> int:
    sp = _spans(doc)
    return max((sp[c["id"]][1] for c in _v1(doc)), default=0)


# Set B: the editing ops added after the pinned set (slip, roll, markers you edit, close_gaps).
# Same fixture; run with ``python -m evals.run --reference --set b``. Set A above stays pinned.
TASKS_B: list[Task] = [
    Task(
        "b01-slip",
        "Keep the second clip where it is, but show the part of the talk 2 seconds later.",
        lambda d, log, w: _spans(d)["c2"] == (10 * S, 20 * S) and _by_id(d, "c2")["src"] == [22 * S, 32 * S],
        [("timeline_apply", {"summary": "Slip c2", "ops": [{"op": "slip_clip", "id": "c2", "by_s": 2}]})],
    ),
    Task(
        "b02-roll",
        "Move the cut between the first and second clips 1 second later, without changing the total length.",
        lambda d, log, w: (
            _spans(d)["c1"] == (0, 11 * S) and _spans(d)["c2"] == (11 * S, 20 * S) and _by_id(d, "c2")["src"][0] == 21 * S
        ),
        [("timeline_apply", {"summary": "Roll", "ops": [{"op": "roll_edit", "id": "c1", "by_s": 1}]})],
    ),
    Task(
        "b03-close-after-delete",
        "Delete the first clip without moving the others, then close the gaps as one more step.",
        lambda d, log, w: (
            [c["id"] for c in _v1(d)] == ["c2", "c3"] and _spans(d)["c2"][0] == 0 and _end_v1(d) == 20 * S and len(log) == 2
        ),
        [
            ("timeline_apply", {"summary": "Delete c1", "ops": [{"op": "delete_clip", "id": "c1", "ripple": False}]}),
            ("apply_preset", {"preset": "close_gaps"}),
        ],
    ),
    Task(
        "b04-marker-edit",
        'Put a marker "hook" at 2 s. Then move it to 3.5 s and rename it "intro".',
        lambda d, log, w: [(m["label"], m["at"]) for m in d["markers"]] == [("intro", 7 * S // 2)],
        [
            ("timeline_apply", {"summary": "Marker", "ops": [{"op": "add_marker", "at_s": 2, "label": "hook", "id": "hook"}]}),
            (
                "timeline_apply",
                {"summary": "Edit marker", "ops": [{"op": "edit_marker", "id": "hook", "at_s": 3.5, "label": "intro"}]},
            ),
        ],
    ),
    Task(
        "b05-impossible-slip",
        "Show 2 seconds earlier of the source in the first clip, keeping it in place. If that can't be done, change nothing.",
        lambda d, log, w: log == [],  # c1 starts at 0 s of the talk: there is nothing earlier
        [],
    ),
    Task(
        "b06-repeat-last",
        "Play the last clip twice in a row.",
        lambda d, log, w: len(_v1(d)) == 4 and _v1(d)[-1]["src"] == [40 * S, 50 * S] and _spans(d)[_v1(d)[-1]["id"]][0] == 30 * S,
        [
            (
                "timeline_apply",
                {
                    "summary": "Repeat",
                    "ops": [{"op": "insert_clip", "track": "V1", "media": "m1", "src_s": [40, 50], "at_s": 30}],
                },
            )
        ],
    ),
]
SETS = {"a": TASKS, "b": TASKS_B}


def _by_id(doc: dict, iid: str) -> dict:
    return next(it for t in doc["tracks"] for it in t["items"] if it["id"] == iid)
