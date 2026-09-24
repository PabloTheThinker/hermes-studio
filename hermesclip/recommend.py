from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import asdict, dataclass, field

from hermesclip.download import LIVE_DEFAULT_SEC, SourceInfo, kind_of, probe
from hermesclip.render import probe_duration


@dataclass
class Recommendation:
    aspect: str = "9:16"
    layout: str = "fit"
    min_sec: float = 30.0
    max_sec: float = 60.0
    dur: str = "short"
    max_clips: int = 3
    pacing: str = "tight"
    style: str = "pop"
    captions: bool = True
    hook: bool = True
    mode: str = "clip"
    live_seconds: int = LIVE_DEFAULT_SEC
    prompt: str = ""
    keywords: str = ""
    plan: str = "heuristic"
    why: list[str] = field(default_factory=list)

    def as_job(self) -> dict:
        d = asdict(self)
        d["why"] = self.why or []
        return d


def _duration(info: SourceInfo) -> float | None:
    if info.duration and info.duration > 0:
        return float(info.duration)
    if info.extractor == "file":
        try:
            return float(probe_duration(info.src))
        except Exception:
            return None
    return None


def recommend_heuristic(info: SourceInfo) -> Recommendation:
    rec = Recommendation(why=[])
    why = rec.why
    kind = kind_of(info.src)
    dur = _duration(info)
    title = (info.title or "").lower()

    rec.aspect = "9:16"
    why.append("Vertical 9:16 — Shorts / Reels / TikTok default.")
    if any(w in title for w in ("instagram", "ig feed", "carousel")):
        rec.aspect = "4:5"
        why.append("Instagram/feed title: 4:5 portrait.")

    if info.is_live or kind == "twitch":
        rec.layout = "fill"
        rec.live_seconds = LIVE_DEFAULT_SEC
        rec.dur, rec.min_sec, rec.max_sec = "short", 30, 60
        rec.max_clips = 5
        rec.pacing = "tight"
        why.append("Live / stream: punch-in fill, 20 min slice, five tight shorts.")
    elif kind == "x":
        rec.layout = "fill"
        rec.dur, rec.min_sec, rec.max_sec = "xshort", 10, 30
        rec.max_clips = 3
        why.append("X source: extra-short punch-ins.")
    elif dur and dur < 90:
        rec.mode = "captions"
        rec.layout = "fit"
        rec.max_clips = 1
        rec.dur, rec.min_sec, rec.max_sec = "short", 12, max(dur, 30)
        why.append("Under 90s: captions on the full take instead of chopping.")
    elif dur and dur >= 45 * 60:
        rec.layout = "fit"
        rec.dur, rec.min_sec, rec.max_sec = "medium", 60, 120
        rec.max_clips = 8
        rec.pacing = "tight"
        why.append("Long talk: eight 1–2 min hook windows, Classic fit.")
    else:
        rec.layout = "fit"
        rec.dur, rec.min_sec, rec.max_sec = "short", 30, 60
        rec.max_clips = 3
        why.append("Standard VOD: three 30–60s hook-first clips, Classic fit.")

    talk = any(w in title for w in ("podcast", "interview", "stream", "live", "talk", "ep ", "episode"))
    if talk and rec.mode == "clip":
        rec.layout = "fill"
        rec.style = "pop"
        rec.hook = True
        why.append("Talk title: fill + hook overlay.")

    slides = any(w in title for w in ("slide", "deck", "tutorial", "course", "webinar", "keynote"))
    if slides:
        rec.layout = "fit"
        rec.style = "clean"
        why.append("Tutorial/slides: Classic fit, clean captions.")

    from hermesclip.captions import parse_keywords

    rec.keywords = " ".join(parse_keywords(info.title or "")[:5])
    if rec.keywords:
        why.append("Highlight title words in captions.")

    rec.why = why
    return rec


def recommend_grok(info: SourceInfo, base: Recommendation) -> Recommendation | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    dur = _duration(info)
    payload = {
        "model": os.environ.get("XAI_PLAN_MODEL", "grok-4-fast-non-reasoning"),
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You pick HermesClip job settings for one video. "
                    "Return JSON only with keys: aspect (9:16|1:1|16:9|4:5), layout (fit|fill), "
                    "dur (xshort|short|medium|long|midform), max_clips (1-8), pacing (tight|natural), "
                    "style (pop|impact|clean|glow|neon|boxed), mode (clip|captions), "
                    "hook (bool), prompt (short hunt words or empty), keywords (space-separated highlight words), why (array of short reasons). "
                    "Prefer 9:16 shorts. Never post. No social accounts."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": info.title,
                        "duration": dur,
                        "is_live": info.is_live,
                        "extractor": info.extractor,
                        "kind": kind_of(info.src),
                    }
                ),
            },
        ],
    }
    req = urllib.request.Request(
        os.environ.get("XAI_API_URL", "https://api.x.ai/v1/chat/completions"),
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode())
        text = body["choices"][0]["message"]["content"]
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start : end + 1])
    except Exception:
        return None
    rec = Recommendation(**{k: getattr(base, k) for k in Recommendation.__dataclass_fields__ if k != "why"})
    rec.why = []
    if data.get("aspect") in ("9:16", "1:1", "16:9", "4:5"):
        rec.aspect = data["aspect"]
    if data.get("layout") in ("fit", "fill"):
        rec.layout = data["layout"]
    dur_map = {
        "xshort": (10, 30),
        "short": (30, 60),
        "medium": (60, 120),
        "long": (120, 300),
        "midform": (180, 900),
    }
    if data.get("dur") in dur_map:
        rec.dur = data["dur"]
        rec.min_sec, rec.max_sec = dur_map[rec.dur]
    if isinstance(data.get("max_clips"), int) and 1 <= data["max_clips"] <= 8:
        rec.max_clips = data["max_clips"]
    if data.get("pacing") in ("tight", "natural"):
        rec.pacing = data["pacing"]
    if data.get("style") in ("pop", "impact", "clean", "glow", "neon", "boxed"):
        rec.style = data["style"]
    if data.get("mode") in ("clip", "captions"):
        rec.mode = data["mode"]
    if isinstance(data.get("hook"), bool):
        rec.hook = data["hook"]
    if isinstance(data.get("prompt"), str):
        rec.prompt = data["prompt"][:80]
    if isinstance(data.get("keywords"), str):
        rec.keywords = data["keywords"][:80]
    why = data.get("why")
    rec.why = [str(x) for x in why][:6] if isinstance(why, list) else ["Hermes pick after analysis."]
    rec.plan = "heuristic"
    return rec


def recommend_for(src: str) -> tuple[SourceInfo, Recommendation]:
    info = probe(src)
    base = recommend_heuristic(info)
    grok = recommend_grok(info, base)
    rec = grok or base
    if grok:
        rec.why = (rec.why or []) + ["Hermes agent scored this after probe."]
    else:
        rec.why = (rec.why or []) + ["Local analysis (no cloud clipper)."]
    return info, rec
