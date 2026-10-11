"""Transition kinds: what a cut between two clips can be.

The render is ffmpeg's ``xfade``, which ships a fixed set of named transitions. Rather than
hardcoding a guess, :func:`ffmpeg_kinds` reads the real list out of the installed ffmpeg and
:func:`kinds` joins it with the names and groups the page shows. A kind ffmpeg does not have is
never offered, so the page can't ask for something the render would refuse.

Groups are how Resolve and Final Cut present them (Dissolve, Wipe, Slide, Shape, Other), so
Sir finds the one he wants; the file also carries the small set of aliases people say instead
("dissolve" is what ffmpeg calls a straight dissolve, "fade" a cross-fade).
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache

# The fallback list: this build's xfade transitions (ffmpeg 6.x, `ffmpeg -h filter=xfade`).
# Used when ffmpeg can't be run, so the page still works.
KNOWN = (
    "fade", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circlecrop", "rectcrop", "distance", "radial", "smoothleft", "smoothright",
    "smoothup", "smoothdown", "circleopen", "circleclose", "vertopen", "vertclose",
    "horzopen", "horzclose", "pixelize", "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice", "hblur", "fadegrays",
    "wipetl", "wipetr", "wipebl", "wipebr", "squeezeh", "squeezev", "zoomin",
    "fadefast", "fadeslow", "hlwind", "hrwind", "vuwind", "vdwind",
    "coverleft", "coverright", "coverup", "coverdown",
    "revealleft", "revealright", "revealup", "revealdown",
    "fadeblack", "fadewhite",
)

# What the page calls each kind, grouped the way the pro editors group them.
LABELS = {
    "fade": "Cross Fade", "dissolve": "Dissolve", "fadeblack": "Fade to Black",
    "fadewhite": "Fade to White", "fadegrays": "Fade through Grey", "fadefast": "Fast Fade",
    "fadeslow": "Slow Fade",
    "wipeleft": "Wipe Left", "wiperight": "Wipe Right", "wipeup": "Wipe Up", "wipedown": "Wipe Down",
    "wipetl": "Wipe to Top Left", "wipetr": "Wipe to Top Right",
    "wipebl": "Wipe to Bottom Left", "wipebr": "Wipe to Bottom Right",
    "smoothleft": "Smooth Left", "smoothright": "Smooth Right",
    "smoothup": "Smooth Up", "smoothdown": "Smooth Down",
    "slideleft": "Slide Left", "slideright": "Slide Right", "slideup": "Slide Up",
    "slidedown": "Slide Down",
    "coverleft": "Cover Left", "coverright": "Cover Right", "coverup": "Cover Up",
    "coverdown": "Cover Down", "revealleft": "Reveal Left", "revealright": "Reveal Right",
    "revealup": "Reveal Up", "revealdown": "Reveal Down",
    "circlecrop": "Circle", "rectcrop": "Rectangle", "circleopen": "Circle Open",
    "circleclose": "Circle Close", "vertopen": "Venetian Open", "vertclose": "Venetian Close",
    "horzopen": "Horizontal Open", "horzclose": "Horizontal Close",
    "radial": "Radial", "distance": "Distance", "pixelize": "Pixelize",
    "diagtl": "Diagonal ↗", "diagtr": "Diagonal ↘", "diagbl": "Diagonal ↙", "diagbr": "Diagonal ↖",
    "hlslice": "Slice Left", "hrslice": "Slice Right", "vuslice": "Slice Up", "vdslice": "Slice Down",
    "hlwind": "Wind Left", "hrwind": "Wind Right", "vuwind": "Wind Up", "vdwind": "Wind Down",
    "hblur": "Blur", "squeezeh": "Squeeze Wide", "squeezev": "Squeeze Tall", "zoomin": "Zoom In",
}

GROUPS = {
    "fade": "Dissolve", "dissolve": "Dissolve", "fadeblack": "Dissolve", "fadewhite": "Dissolve",
    "fadegrays": "Dissolve", "fadefast": "Dissolve", "fadeslow": "Dissolve",
    "wipeleft": "Wipe", "wiperight": "Wipe", "wipeup": "Wipe", "wipedown": "Wipe",
    "wipetl": "Wipe", "wipetr": "Wipe", "wipebl": "Wipe", "wipebr": "Wipe",
    "slideleft": "Slide", "slideright": "Slide", "slideup": "Slide", "slidedown": "Slide",
    "coverleft": "Slide", "coverright": "Slide", "coverup": "Slide", "coverdown": "Slide",
    "revealleft": "Slide", "revealright": "Slide", "revealup": "Slide", "revealdown": "Slide",
    "circlecrop": "Shape", "rectcrop": "Shape", "circleopen": "Shape", "circleclose": "Shape",
    "vertopen": "Shape", "vertclose": "Shape", "horzopen": "Shape", "horzclose": "Shape",
    "radial": "Shape", "distance": "Shape", "pixelize": "Shape", "squeezeh": "Shape",
    "squeezev": "Shape", "zoomin": "Shape", "diagtl": "Shape", "diagtr": "Shape",
    "diagbl": "Shape", "diagbr": "Shape", "hblur": "Shape",
    "smoothleft": "Other", "smoothright": "Other", "smoothup": "Other", "smoothdown": "Other",
    "hlslice": "Other", "hrslice": "Other", "vuslice": "Other", "vdslice": "Other",
    "hlwind": "Other", "hrwind": "Other", "vuwind": "Other", "vdwind": "Other",
}

GROUP_ORDER = ("Dissolve", "Wipe", "Slide", "Shape", "Other")

# What people type, mapped to what ffmpeg wants. Said, not asked.
ALIASES = {
    "crossdissolve": "fade", "crossfade": "fade", "cross": "fade", "mix": "fade",
    "dissolve": "fade", "mixdissolve": "fade",
    "dip": "fadeblack", "dipblack": "fadeblack", "diptoblack": "fadeblack",
    "fadethroughblack": "fadeblack", "toblack": "fadeblack",
    "fadethroughwhite": "fadewhite", "towhite": "fadewhite", "dipwhite": "fadewhite",
    "fadethroughgrey": "fadegrays", "fadethroughgray": "fadegrays", "bw": "fadegrays",
    "fade": "fade",
}


def label(kind: str) -> str:
    return LABELS.get(kind, kind.replace("_", " ").title())


def group(kind: str) -> str:
    return GROUPS.get(kind, "Other")


@lru_cache(maxsize=1)
def ffmpeg_kinds() -> frozenset[str]:
    """Every transition name this ffmpeg's ``xfade`` accepts, read from the binary. Empty set
    if it can't be run (the caller then falls back to :data:`KNOWN`)."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-h", "filter=xfade"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names = re.findall(r"^\s{5}([a-z0-9_]+)\s+-?\d+\s+\.\.FV", out, re.M)
    return frozenset(names) or frozenset()


@lru_cache(maxsize=1)
def _kind_set() -> frozenset[str]:
    return frozenset(kinds())


@lru_cache(maxsize=1)
def kinds() -> tuple[str, ...]:
    """The kinds the page offers, in group order. Intersects the labels with what ffmpeg has,
    so a kind is only ever offered when the render can do it."""
    have = ffmpeg_kinds() or frozenset(KNOWN)
    have = have - {"custom"}
    order = {k: i for i, k in enumerate(GROUP_ORDER)}
    return tuple(sorted(have, key=lambda k: (order.get(group(k), 99), group(k), LABELS.get(k, k))))


def resolve(name: str) -> str | None:
    """A kind from the page (or a spoken alias) to an ffmpeg name, or None if unknown."""
    said = (name or "").strip().lower()
    if not said:
        return None
    squash = said.replace(" ", "").replace("_", "").replace("-", "")
    # An alias must never shadow a real ffmpeg kind (ffmpeg's own "dissolve" beats the alias
    # that calls a cross-dissolve "dissolve"): exact names, then labels, then aliases.
    for cand in (said, squash):
        if cand in _kind_set():
            return cand
        for k in _kind_set():
            if k == cand or label(k).lower().replace(" ", "") == cand:
                return k
    n = ALIASES.get(said) or ALIASES.get(squash) or squash
    for k in kinds():
        if k == n or k.replace("_", "") == n or label(k).lower().replace(" ", "") == n:
            return k
    return None


def catalog() -> list[dict]:
    """For the page: groups with their kinds, each {id, label}."""
    out: list[dict] = []
    for g in GROUP_ORDER:
        items = [{"id": k, "label": label(k)} for k in kinds() if group(k) == g]
        if items:
            out.append({"group": g, "kinds": items})
    rest = [{"id": k, "label": label(k)} for k in kinds() if group(k) not in GROUP_ORDER]
    if rest:
        out.append({"group": "Other", "kinds": rest})
    return out
