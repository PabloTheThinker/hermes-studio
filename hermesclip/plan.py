from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from hermesclip.transcribe import Transcript, Word

# BridgeClip rubric (local, no OpenRouter). Opus: hook / flow / value / standalone.

FILLER = {
    "um",
    "uh",
    "like",
    "yeah",
    "okay",
    "ok",
    "so",
    "anyway",
    "right",
    "basically",
}
WEAK_OPEN = {"so", "and", "but", "yeah", "okay", "um", "uh", "well"}
CONTEXT_NEED = (
    "as i said",
    "as i mentioned",
    "earlier",
    "going back",
    "like i said",
    "what we said",
)
HOOK_STEMS = (
    "what if",
    "have you",
    "why ",
    "how ",
    "nobody",
    "never",
    "always",
    "secret",
    "mistake",
    "actually",
    "wait",
    "stop ",
    "the truth",
    "hot take",
    "biggest",
    "insane",
    "crazy",
)
MAX_OVERLAP_SEC = 5.0


@dataclass
class ClipPlan:
    start: float
    end: float
    title: str
    emphasis: list[str]
    score: float


def plan_heuristic(
    tr: Transcript,
    max_clips: int = 3,
    min_sec: float = 12.0,
    max_sec: float = 45.0,
) -> list[ClipPlan]:
    """Self-contained moments: sentence snap, hook in first 3s, no overlap mash."""
    if not tr.words:
        dur = max(tr.duration, 1.0)
        end = min(dur, max_sec)
        return [ClipPlan(0.0, end, "clip", [], 0.5)]

    sents = _sentences(tr.words)
    if not sents:
        return [ClipPlan(tr.words[0].start, min(tr.words[-1].end, max_sec), "clip", [], 0.5)]

    candidates: list[ClipPlan] = []
    for i in range(len(sents)):
        words: list[Word] = []
        for j in range(i, len(sents)):
            words.extend(sents[j])
            start = words[0].start
            end = words[-1].end
            dur = end - start
            if dur < min_sec:
                continue
            if dur > max_sec:
                break
            if not _ends_thought(words[-1]):
                continue
            if _starts_weak(words):
                continue
            score, title, emp = _rubric(words, dur)
            if score < 0.22:
                continue
            candidates.append(ClipPlan(start, end, title, emp, score))

    if not candidates:
        # Fallback: first min_sec–max_sec on sentence bounds.
        w = tr.words
        a = w[0].start
        b = min(w[-1].end, a + max_sec)
        chunk = [x for x in w if x.start >= a and x.end <= b]
        return [
            ClipPlan(
                start=a,
                end=b,
                title=_title(chunk),
                emphasis=_emphasis(chunk),
                score=0.3,
            )
        ]

    candidates.sort(key=lambda c: c.score, reverse=True)
    picked: list[ClipPlan] = []
    for c in candidates:
        if len(picked) >= max_clips:
            break
        if any(_overlap_sec(c, p) > MAX_OVERLAP_SEC for p in picked):
            continue
        picked.append(c)
    picked.sort(key=lambda c: c.start)
    return picked


def plan_grok(tr: Transcript, max_clips: int, min_sec: float, max_sec: float) -> list[ClipPlan] | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    payload = {
        "model": os.environ.get("XAI_PLAN_MODEL", "grok-4-fast-non-reasoning"),
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You pick short-form clips like Opus Clip / BridgeClip. "
                    "Each clip is a self-contained idea: hook in first 3 seconds, setup+payoff, "
                    "ends on a completed thought, no mid-sentence start. "
                    "No two clips share more than 5 seconds. Spread across the timeline. "
                    f"Duration {min_sec}-{max_sec}s. Max {max_clips} clips. "
                    'JSON only: {"clips":[{"start":0,"end":20,"title":"...","emphasis":["word"]}]} '
                    "Title 2-7 words, curiosity not generic."
                ),
            },
            {"role": "user", "content": _transcript_for_llm(tr)[:12000]},
        ],
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode())
    text = body["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
    data = json.loads(text)
    out: list[ClipPlan] = []
    for row in data.get("clips", [])[:max_clips]:
        start = float(row["start"])
        end = float(row["end"])
        if end - start < min_sec * 0.7 or end <= start:
            continue
        out.append(
            ClipPlan(
                start=start,
                end=end,
                title=str(row.get("title") or "clip")[:80],
                emphasis=[str(x) for x in (row.get("emphasis") or [])][:5],
                score=0.8,
            )
        )
    return out or None


def save_plan(plans: list[ClipPlan], path: Path) -> None:
    path.write_text(json.dumps([asdict(p) for p in plans], indent=2))


def _sentences(words: list[Word]) -> list[list[Word]]:
    out: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt.start - w.end) if nxt else 9.0
        punct = w.text[-1:] in ".?!"
        if punct or gap > 0.55:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _text(words: list[Word]) -> str:
    return " ".join(w.text.strip() for w in words if w.text.strip())


def _starts_weak(words: list[Word]) -> bool:
    first = (words[0].text if words else "").strip(".,!?").lower()
    return first in WEAK_OPEN and not any(ch in (words[0].text if words else "") for ch in "?!")


def _ends_thought(w: Word) -> bool:
    t = w.text.strip()
    return t[-1:] in ".?!" or len(t) > 12


def _rubric(words: list[Word], dur: float) -> tuple[float, str, list[str]]:
    blob = _text(words).lower()
    open_w = [w for w in words if w.start <= words[0].start + 3.0]
    open_t = _text(open_w).lower()

    hook = 0.15
    if "?" in open_t:
        hook += 0.25
    if any(s in open_t for s in HOOK_STEMS):
        hook += 0.25
    if re.search(r"\d", open_t) or "$" in open_t:
        hook += 0.15
    if "you" in open_t.split() or "your" in open_t.split():
        hook += 0.1
    if open_t.split()[:1] and open_t.split()[0] in WEAK_OPEN:
        hook -= 0.2
    hook = max(0.0, min(1.0, hook))

    standalone = 0.7
    if any(p in blob for p in CONTEXT_NEED):
        standalone = 0.15
    fillers = sum(1 for w in words if w.text.strip(".,!?").lower() in FILLER)
    standalone -= min(0.35, fillers / max(len(words), 1) * 1.2)
    standalone = max(0.0, min(1.0, standalone))

    arc = 0.35
    if "?" in blob and ("because" in blob or "so " in blob or "that's" in blob or "that is" in blob):
        arc = 0.8
    if "?" in open_t and "?" not in _text(words[-8:]).lower():
        arc = max(arc, 0.7)
    if dur >= 18:
        arc += 0.1
    arc = min(1.0, arc)

    quotability = 0.2
    if any(s in blob for s in HOOK_STEMS):
        quotability += 0.3
    longish = [w for w in words if len(w.text.strip(".,!?")) >= 6]
    quotability += min(0.3, len(longish) / max(len(words), 1))
    quotability = min(1.0, quotability)

    ending = 0.85 if words[-1].text.strip()[-1:] in ".?!" else 0.35

    score = 0.28 * hook + 0.22 * standalone + 0.2 * arc + 0.18 * quotability + 0.12 * ending
    return round(score, 3), _title(open_w or words), _emphasis(words)


def _overlap_sec(a: ClipPlan, b: ClipPlan) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def _title(words: list[Word]) -> str:
    toks = [w.text.strip(".,!?") for w in words if w.text.strip(".,!?")]
    toks = [t for t in toks if t.lower() not in FILLER][:7]
    return " ".join(toks[:6]) or "clip"


def _emphasis(words: list[Word]) -> list[str]:
    scored = sorted(words, key=lambda w: (len(w.text.strip(".,!?")), w.end - w.start), reverse=True)
    out: list[str] = []
    for w in scored:
        t = w.text.strip(".,!?").lower()
        if len(t) < 4 or t in FILLER or t in out:
            continue
        out.append(t)
        if len(out) >= 4:
            break
    return out


def _transcript_for_llm(tr: Transcript) -> str:
    lines = [f"{w.start:.1f}-{w.end:.1f} {w.text}" for w in tr.words]
    return "\n".join(lines) if lines else tr.text
