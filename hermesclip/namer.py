"""AI clip names, the way Opus Clip titles its shorts.

One batched call names every clip in a run from its own words.
Local-first: Ollama on this machine. Optional: any OpenAI-compatible endpoint.
No LLM reachable → a smarter offline title from the clip's strongest line.

Env:
  HERMESCLIP_NAMER            ollama (default) | openai | off
  HERMESCLIP_NAMER_MODEL      default "qwen3.5:9b" for ollama
  HERMESCLIP_NAMER_URL        default http://127.0.0.1:11434 (ollama) or an /v1/chat/completions URL
  HERMESCLIP_NAMER_KEY        bearer key for openai-compatible endpoints
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from hermesclip.transcribe import Transcript, Word

SYSTEM = (
    "You title short-form video clips the way Opus Clip does. "
    "Each title is 3 to 8 words, Title Case, specific to what is said in that clip, "
    "and makes a viewer want to watch. Lead with the payoff, the tension or the number. "
    "Use the speaker's own strongest words when they are good. "
    "No quotes, emojis, hashtags, colons at the end, or trailing punctuation except ? or !. "
    "Never invent facts that are not in the words. Never use generic titles like 'Clip 1', "
    "'Interesting Moment' or 'Must Watch'. Every title in the list must be different."
)

SMALL = {"a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "by", "is", "it", "as"}
FILLER = {"um", "uh", "like", "so", "yeah", "okay", "ok", "right", "you", "know", "i", "mean", "just", "actually", "basically"}
STRONG = re.compile(r"(\d|\$|never|always|nobody|everyone|secret|mistake|wrong|why|how|stop|biggest|worst|best|truth|real|money|hours?|years?|million|free)", re.I)


def clip_text(tr: Transcript, start: float, end: float, fixes: dict | None = None) -> str:
    words = [w for w in tr.words if w.start >= start - 0.05 and w.end <= end + 0.05]
    text = " ".join(w.text.strip() for w in words).strip()
    if fixes:
        from hermesclip.captions import _fix_word

        fx = {str(k).lower(): str(v) for k, v in fixes.items()}
        text = " ".join(_fix_word(t, fx) for t in text.split())
    return text


def title_case(s: str) -> str:
    toks = s.split()
    out = []
    for i, t in enumerate(toks):
        low = t.lower()
        if 0 < i < len(toks) - 1 and low in SMALL:
            out.append(low)
        elif t.isupper() and len(t) > 1:
            out.append(t)
        else:
            out.append(t[:1].upper() + t[1:])
    return " ".join(out)


def clean(title: str) -> str:
    t = re.sub(r"[\"“”#*_`]|[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", str(title or "")).strip()
    t = re.sub(r"\s+", " ", t).strip(" .,:;-–—")
    words = t.split()
    if len(words) > 9:
        t = " ".join(words[:9])
    return title_case(t) if t else ""


def offline_title(text: str) -> str:
    """Strongest sentence, filler stripped, 3-7 words, Title Case."""
    sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
    if not sents:
        return ""

    def rank(s: str) -> float:
        n = len(s.split())
        return (2.0 if "?" in s else 0) + 1.5 * len(STRONG.findall(s)) - abs(n - 9) * 0.1

    best = max(sents, key=rank)
    if len(best.split()) > 8:
        parts = [c for c in re.split(r"[,;:]|\s(?:because|but|and so|so)\s", best) if len(c.split()) >= 3]
        if parts:
            best = max(parts, key=rank) + ("?" if best.rstrip().endswith("?") else "")
    toks = [t.strip(".,!;:") for t in best.split()]
    while toks and toks[0].lower() in FILLER | SMALL:
        toks.pop(0)
    toks = [t for t in toks if t and t.lower() not in {"um", "uh"}]
    if len(toks) > 9:
        toks = toks[:7]
        while toks and toks[-1].lower() in SMALL | FILLER:
            toks.pop()
    t = " ".join(toks)
    if "?" in best and not t.endswith("?"):
        t += "?"
    return clean(t)


def _ollama(url: str, model: str, prompt: str) -> str:
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.4},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=float(os.environ.get("HERMESCLIP_NAMER_TIMEOUT", "180"))) as r:
        return json.loads(r.read().decode())["message"]["content"]


def _openai(url: str, model: str, key: str, prompt: str) -> str:
    body = {
        "model": model,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=float(os.environ.get("HERMESCLIP_NAMER_TIMEOUT", "180"))) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def _parse(raw: str, n: int) -> list[str]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1]
    data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    titles = data.get("titles") if isinstance(data, dict) else data
    if not isinstance(titles, list):
        # {"Clip 1": "...", "Clip 2": "..."} or {"1": {...}} shapes
        titles = [v for k, v in sorted(data.items()) if k != "video"] if isinstance(data, dict) else []
    out = []
    for i in range(n):
        item = titles[i] if i < len(titles) else ""
        if isinstance(item, dict):
            item = item.get("title") or next((v for v in item.values() if isinstance(v, str) and len(v.split()) >= 2), "")
        out.append(clean(item))
    return out


def ai_titles(texts: list[str], context: str = "") -> tuple[list[str], str]:
    """Return (titles, source). source = model name, or 'offline'."""
    mode = os.environ.get("HERMESCLIP_NAMER", "ollama").strip().lower()
    fallback = [offline_title(t) for t in texts]
    if mode == "off" or not texts or not any(texts):
        return fallback, "offline"
    lines = [f"Video: {context[:120]}" if context else "", f"Name these {len(texts)} clips."]
    for i, t in enumerate(texts, 1):
        lines.append(f"\nClip {i} words:\n{t[:1500]}")
    lines.append(f'\nJSON only: {{"titles": ["...", ...]}} with exactly {len(texts)} titles, in order.')
    prompt = "\n".join(x for x in lines if x)
    if mode == "openai":
        url = os.environ.get("HERMESCLIP_NAMER_URL", "").strip()
        model = os.environ.get("HERMESCLIP_NAMER_MODEL", "").strip()
        if not url or not model:
            return fallback, "offline"
    else:
        url = os.environ.get("HERMESCLIP_NAMER_URL", "http://127.0.0.1:11434")
        model = os.environ.get("HERMESCLIP_NAMER_MODEL", "qwen3.5:9b")

    def good(t: str) -> bool:
        return bool(t) and 2 <= len(t.split()) <= 9

    titles: list[str] = [""] * len(texts)
    for _attempt in range(2):
        try:
            raw = _openai(url, model, os.environ.get("HERMESCLIP_NAMER_KEY", ""), prompt) if mode == "openai" else _ollama(url, model, prompt)
            titles = _parse(raw, len(texts))
        except Exception:
            continue
        if sum(good(t) for t in titles) == len(texts):
            break
    seen: set[str] = set()
    out = []
    used_ai = 0
    for t, fb in zip(titles, fallback):
        if good(t) and t.lower() not in seen:
            pick = t
            used_ai += 1
        else:
            pick = fb
        seen.add(pick.lower())
        out.append(pick)
    return out, (model if used_ai == len(texts) else ("offline" if not used_ai else f"{model}+offline"))


def slug(title: str, fallback: str = "clip") -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-")
    return (s[:60].rstrip("-") or fallback)


def words_from(tr: Transcript | None) -> list[Word]:
    return list(tr.words) if tr else []
