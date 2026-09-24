from __future__ import annotations

import re
from dataclasses import dataclass

from hermesclip.transcribe import Word

FILLER = frozenset({"um", "uh", "uhm", "umm", "uhh", "erm", "er", "hmm", "hm", "mm", "mhm"})
MAX_PAUSE = 0.70
KEEP_PAUSE = 0.26
LEAD_IN = 0.12
TAIL = 0.38
MIN_CUT = 0.20
MIN_PIECE = 0.40


def _bare(word: str) -> str:
    return re.sub(r"[^a-z]", "", word.lower())


def is_filler(word: str) -> bool:
    return _bare(word) in FILLER


@dataclass
class TimeMap:
    """Source-clip seconds → output seconds after tight cuts."""

    keeps: list[tuple[float, float]]  # relative to clip start

    def to_output(self, t: float) -> float:
        out = 0.0
        for a, b in self.keeps:
            if t < a:
                return out
            if t <= b:
                return out + (t - a)
            out += b - a
        return out

    @property
    def duration(self) -> float:
        return sum(b - a for a, b in self.keeps)

    @property
    def removed(self) -> float:
        if not self.keeps:
            return 0.0
        span = self.keeps[-1][1] - self.keeps[0][0]
        return max(0.0, span - self.duration)


def keep_intervals(words: list[Word], clip_start: float, clip_end: float) -> TimeMap:
    width = max(0.05, clip_end - clip_start)
    spoken: list[Word] = []
    for w in words:
        if is_filler(w.text):
            continue
        if w.end <= clip_start or w.start >= clip_end:
            continue
        spoken.append(Word(w.text, max(clip_start, w.start), min(clip_end, w.end)))
    if not spoken:
        return TimeMap([(0.0, width)])

    pieces: list[tuple[float, float]] = []
    cur_a = max(0.0, spoken[0].start - clip_start - LEAD_IN)
    cur_b = spoken[0].end - clip_start
    for w in spoken[1:]:
        s = w.start - clip_start
        e = w.end - clip_start
        gap = s - cur_b
        if gap > MAX_PAUSE and (gap - KEEP_PAUSE) >= MIN_CUT:
            pieces.append((cur_a, cur_b))
            cur_a = max(0.0, s - KEEP_PAUSE / 2)
            cur_b = e
        else:
            cur_b = e
    pieces.append((cur_a, min(width, cur_b + TAIL)))

    merged: list[tuple[float, float]] = []
    for a, b in pieces:
        a = max(0.0, min(a, width))
        b = max(a + 0.04, min(b, width))
        if merged and (a <= merged[-1][1] + 0.05 or b - a < MIN_PIECE):
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return TimeMap(merged or [(0.0, width)])


def remap_words(words: list[Word], clip_start: float, clip_end: float, tm: TimeMap) -> list[Word]:
    out: list[Word] = []
    for w in words:
        if is_filler(w.text):
            continue
        if w.end <= clip_start or w.start >= clip_end:
            continue
        s = tm.to_output(w.start - clip_start)
        e = tm.to_output(w.end - clip_start)
        if e <= s:
            e = s + 0.05
        out.append(Word(w.text, s, e))
    return out
