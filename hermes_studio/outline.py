"""``timeline_outline``: the timeline in seconds and plain words, for an agent to read cheaply.

``get_timeline`` is the exact document (ticks, anchors, fractions); the outline is what a person
would sketch: each track's items in time order with their start and end in seconds, what they
show (a clip's media and source range, a text's words), crossfades, the gaps on the main track,
markers and the total length. ``text`` is the same thing as a few lines. It is read-only and
derived from the doc, so it is never out of date; write with the ids it gives.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from hermes_studio import timeline as T


def _s(ticks: int) -> float:
    return round(float(Fraction(ticks, T.TICK_RATE)), 3)


def _f(v: Any) -> float:
    return float(Fraction(v[0], v[1])) if isinstance(v, list) else float(v)


def _item(it: dict, span: tuple[int, int]) -> dict:
    row: dict[str, Any] = {"id": it["id"], "type": it["type"], "start_s": _s(span[0]), "end_s": _s(span[1])}
    if it["type"] == "transition":
        row.update(type="crossfade", between=list(it["between"]))
        return row
    if it["type"] == "clip":
        row.update(media=it["media"], src_s=[_s(it["src"][0]), _s(it["src"][1])])
        props = it.get("props") or {}
        for k in ("speed", "volume"):
            if k in props and _f(props[k]) != 1:
                row[k] = round(_f(props[k]), 4)
    else:
        row.update(text=it["text"], style=it["style"])
    if "anchor" in it:
        row["rides_on"] = it["anchor"]["to"]
    for k in ("fade_in", "fade_out"):
        if it.get(k):
            row[k + "_s"] = _s(it[k])
    return row


def _gaps(items: list[dict], spans: dict) -> list[list[float]]:
    out, cursor = [], 0
    for it in sorted((x for x in items if x["type"] == "clip"), key=lambda x: spans[x["id"]][0]):
        a, b = spans[it["id"]]
        if a > cursor:
            out.append([_s(cursor), _s(a)])
        cursor = max(cursor, b)
    return out


def _line(r: dict) -> str:
    when = f"{r['start_s']:.2f}-{r['end_s']:.2f}"
    if r["type"] == "crossfade":
        return f"crossfade {r['between'][0]}>{r['between'][1]} {when}"
    if r["type"] == "clip":
        what = f"{r['media']}[{r['src_s'][0]:.2f}-{r['src_s'][1]:.2f}]"
        what += "".join(f" {k} {r[k]:g}" for k in ("speed", "volume") if k in r)
    else:
        what = f'"{r["text"]}" ({r["style"]})'
    ride = f" on {r['rides_on']}" if "rides_on" in r else ""
    return f"{r['id']} {when} {what}{ride}"


def _clock(sec: float) -> str:
    s = int(sec)
    h, m = divmod(s // 60, 60)
    return f"{h}:{m:02d}:{s % 60:02d}" if h else f"{m}:{s % 60:02d}"


def chapters(markers: list[dict], length_s: float) -> str:
    """Markers as video chapters, one ``M:SS label`` line each (``H:MM:SS`` past an hour), in
    time order. The list starts at 0:00 (an ``Intro`` line is added when no marker is there, as
    video sites want), markers past the end are left out, and so is a marker on the same second
    as the one before it."""
    rows, seen = [], set()
    for m in sorted(markers, key=lambda m: (m["at_s"], m["id"])):
        sec = int(m["at_s"])
        if m["at_s"] > length_s or sec in seen:
            continue
        seen.add(sec)
        rows.append((sec, (m["label"] or "Chapter").strip() or "Chapter"))
    if not rows or rows[0][0] != 0:
        rows.insert(0, (0, "Intro"))
    return "\n".join(f"{_clock(sec)} {label}" for sec, label in rows)


def outline(doc: dict) -> dict:
    spans = T.resolve(doc)
    length = max((e for _, e in spans.values()), default=0)
    tracks = []
    for tr in doc["tracks"]:
        rows = [_item(it, spans[it["id"]]) for it in sorted(tr["items"], key=lambda x: (spans[x["id"]][0], x["id"]))]
        row: dict[str, Any] = {"id": tr["id"], "role": tr["role"], "items": rows}
        if tr["id"] == T.MAIN_TRACK:
            row["gaps_s"] = _gaps(tr["items"], spans)
        tracks.append(row)
    markers = [
        {"id": m["id"], "at_s": _s(m["at"]), "label": m["label"]}
        for m in sorted(doc["markers"], key=lambda m: (m["at"], m["id"]))
    ]
    fps = _f(doc["fps"])
    lines = [
        f"{doc['id']} v{doc['version']}: {doc['size'][0]}x{doc['size'][1]} at {fps:g} fps, {_s(length):.2f} s long, "
        f"{len(doc['media'])} media"
    ]
    for m_id, m in sorted(doc["media"].items()):
        lines.append(f"  media {m_id}: {str(m['path']).replace(chr(92), '/').split('/')[-1]}, {_s(m['dur']):.2f} s")
    for t in tracks:
        if not t["items"]:
            continue
        lines.append(f"{t['id']} ({t['role']}):")
        lines += [f"  {_line(r)}" for r in t["items"]]
        lines += [f"  gap {a:.2f}-{b:.2f}" for a, b in t.get("gaps_s", [])]
    if markers:
        lines.append("markers: " + ", ".join(f'{m["id"]} {m["at_s"]:.2f} "{m["label"]}"' for m in markers))
    return {
        "project_id": doc["id"],
        "version": doc["version"],
        "hash": doc.get("hash"),
        "size": list(doc["size"]),
        "fps": fps,
        "length_s": _s(length),
        "tracks": tracks,
        "markers": markers,
        "chapters": chapters(markers, _s(length)) if markers else "",
        "text": "\n".join(lines),
    }


def explain(log: Any, op_id: str) -> dict | None:
    """``history_explain``: what one history entry changed, as outline lines. ``removed`` are the
    lines of the outline before it that are gone after it, ``added`` the new ones (items, gaps and
    the markers line; the header line is left out, the lengths are given instead). None when the
    log has no such entry."""
    from collections import Counter

    from hermes_studio import frames as F

    e = next((x for x in log._entries if x["op_id"] == op_id), None)
    if e is None:
        return None
    before, after = outline(F.doc_at(log, e["base_version"])), outline(F.doc_at(log, e["new_version"]))
    b, a = before["text"].splitlines()[1:], after["text"].splitlines()[1:]
    gone, new = Counter(b) - Counter(a), Counter(a) - Counter(b)

    def pick(lines: list[str], keep: Counter) -> list[str]:
        out = []
        for ln in lines:
            if keep[ln] > 0 and not ln.endswith(":"):  # a track heading alone isn't a change
                keep[ln] -= 1
                out.append(ln.strip())
        return out

    return {
        "op_id": e["op_id"],
        "summary": e["summary"],
        "actor": e["actor"],
        "undoes": e["undoes"],
        "before_version": e["base_version"],
        "after_version": e["new_version"],
        "length_s": [before["length_s"], after["length_s"]],
        "removed": pick(b, gone),
        "added": pick(a, new),
    }
