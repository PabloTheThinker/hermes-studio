from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "is", "it",
    "that", "this", "with", "you", "we", "i", "me", "my", "our", "your", "be", "as",
    "at", "so", "if", "not", "was", "are", "just", "like", "um", "uh", "yeah", "okay",
}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9']{2,}", text.lower()) if w not in STOP]


def copy_heuristic(title: str, transcript: str, clip_title: str = "") -> dict:
    blob = " ".join(x for x in (clip_title, title, transcript) if x)
    toks = _words(blob)
    freq: dict[str, int] = {}
    for w in toks:
        freq[w] = freq.get(w, 0) + 1
    tags = [k for k, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:8]]
    hook = (clip_title or title or "Watch this").strip()[:80]
    titles = [
        hook,
        (hook.rstrip(".!?") + " — you need to hear this")[:90],
        ("Wait. " + hook)[:90] if not hook.lower().startswith("wait") else hook,
    ]
    # unique preserve order
    seen: set[str] = set()
    uniq = []
    for t in titles:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    sent = re.split(r"(?<=[.!?])\s+", (transcript or "").strip())
    desc = " ".join(sent[:2]).strip()[:280] or hook
    hashtags = ["#" + t.replace("'", "") for t in tags[:6]]
    return {
        "titles": uniq[:3],
        "description": desc,
        "hashtags": hashtags,
        "source": "heuristic",
    }


def copy_grok(title: str, transcript: str, clip_title: str = "") -> dict | None:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        return None
    payload = {
        "model": os.environ.get("XAI_PLAN_MODEL", "grok-4-fast-non-reasoning"),
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Write short-form social copy for one clip. JSON only: "
                    "titles (3 strings, hook-first, max 90 chars), description (max 280), "
                    "hashtags (6 strings starting with #). Never tell the user to post. No URLs."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"video_title": title, "clip_title": clip_title, "transcript": (transcript or "")[:2500]}
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
        a, b = text.find("{"), text.rfind("}")
        data = json.loads(text[a : b + 1])
    except Exception:
        return None
    titles = [str(t)[:90] for t in (data.get("titles") or []) if str(t).strip()][:3]
    tags = [str(h) if str(h).startswith("#") else "#" + str(h).lstrip("#") for h in (data.get("hashtags") or [])][:6]
    desc = str(data.get("description") or "")[:280]
    if not titles:
        return None
    return {"titles": titles, "description": desc, "hashtags": tags, "source": "hermes"}


def copy_pack(title: str, transcript: str, clip_title: str = "") -> dict:
    base = copy_heuristic(title, transcript, clip_title)
    grok = copy_grok(title, transcript, clip_title)
    return grok or base


def copy_from_job_dir(job_dir: Path, clip_title: str = "") -> dict:
    job_dir = Path(job_dir)
    title = job_dir.name
    transcript = ""
    man = job_dir / "job.json"
    if man.is_file():
        try:
            data = json.loads(man.read_text())
            title = data.get("title") or title
        except Exception:
            pass
    for cand in (job_dir / "work" / "transcript.json", job_dir / "transcript.json"):
        if cand.is_file():
            try:
                transcript = json.loads(cand.read_text()).get("text") or ""
            except Exception:
                transcript = cand.read_text()[:4000]
            break
    pack = copy_pack(title, transcript, clip_title)
    dest = job_dir / "copy.json"
    dest.write_text(json.dumps(pack, indent=2))
    pack["file"] = str(dest)
    return pack
