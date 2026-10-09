"""S5 frame cache: one still frame of the timeline at time t, keyed by what is visible there.

The key is ``sha256(canonical recipe) + size``. The recipe lists only what shows at ``t``: the
canvas, the main-track clip (or the two clips of a transition and the mix), each clip's media
(path and duration), the source frame shown, fades, props, and the text items on screen. Nothing
else in the timeline goes in, so an edit at 0:40 leaves the frame at 0:05 cached, and version
12's "after" frame is version 13's "before" frame (Prove C10).

A frame is made from the media's S4 proxy when it exists (else the source) with one
``ffmpeg -ss``; transitions, fades and text are composed with Pillow. This is a preview: the exact
look (captions, looks) is the S6 render's job.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import threading
from fractions import Fraction
from pathlib import Path
from typing import Any

from hermes_studio import media as M
from hermes_studio import timeline as T

DEFAULT_WIDTH = 320
MAX_WIDTH = 1080
CACHE_CAP_BYTES = int(os.environ.get("HERMES_FRAME_CACHE_BYTES", str(2 * 1024**3)))
SHEET_MAX = 48
RECIPE_VERSION = 1  # bump when the rendering changes, so old cached frames are never reused

_FONT = Path(__file__).parent / "data" / "fonts" / "Archivo.ttf"


# --------------------------------------------------------------------------- recipe


def _fade(start: int, end: int, t: int, fin: int, fout: int) -> Fraction:
    """Opacity 0..1 of an item at ``t`` from its fade-in / fade-out (linear)."""
    a = Fraction(1)
    if fin and t - start < fin:
        a = min(a, Fraction(t - start, fin))
    if fout and end - t < fout:
        a = min(a, Fraction(end - t, fout))
    return max(Fraction(0), a)


def _src_frame(doc: dict, it: dict, start: int, t: int) -> tuple[int, int | None]:
    """The source time (ticks) shown at timeline ``t``, snapped down to the source frame that
    shows then, and that frame's index (None for audio-only media)."""
    props = {**T.DEFAULT_PROPS, **(it.get("props") or {})}
    speed = Fraction(*props["speed"])
    src_t = it["src"][0] + int((t - start) * speed)
    fps = doc["media"][it["media"]]["fps"]
    if fps is None:
        return src_t, None
    rate = Fraction(*fps)
    idx = int(Fraction(src_t, T.TICK_RATE) * rate)
    return int(Fraction(idx) / rate * T.TICK_RATE), idx


def _clip_layer(doc: dict, it: dict, span: tuple[int, int], t: int) -> dict:
    src_t, idx = _src_frame(doc, it, span[0], t)
    m = doc["media"][it["media"]]
    props = {**T.DEFAULT_PROPS, **(it.get("props") or {})}
    return {
        "media": it["media"],
        "path": m["path"],
        "media_dur": m["dur"],
        "src_t": src_t,
        "frame": idx,
        "crop": props["crop"],
        "look": props["look"],
        "alpha": str(_fade(span[0], span[1], t, it.get("fade_in", 0), it.get("fade_out", 0))),
    }


def recipe_at(doc: dict, t: int, width: int = DEFAULT_WIDTH) -> dict:
    """What is visible at timeline tick ``t`` of a valid doc, as plain JSON (see the module doc)."""
    cw, ch = doc["size"]
    height = max(2, round(width * ch / cw) // 2 * 2)
    spans = T.resolve(doc)
    by_id = {it["id"]: it for tr in doc["tracks"] for it in tr["items"]}
    main = next((tr for tr in doc["tracks"] if tr["id"] == T.MAIN_TRACK), {"items": []})
    video: list[dict] = []
    trans = [it for it in main["items"] if it["type"] == "transition" and spans[it["id"]][0] <= t < spans[it["id"]][1]]
    if trans:
        tr = trans[0]
        a, b = (by_id[i] for i in tr["between"])
        s, e = spans[tr["id"]]
        video = [
            {**_clip_layer(doc, a, spans[a["id"]], min(t, spans[a["id"]][1] - 1)), "mix": "1"},
            {**_clip_layer(doc, b, spans[b["id"]], t), "mix": str(Fraction(t - s, e - s))},
        ]
    else:
        for it in main["items"]:
            if it["type"] == "clip" and spans[it["id"]][0] <= t < spans[it["id"]][1]:
                video = [{**_clip_layer(doc, it, spans[it["id"]], t), "mix": "1"}]
                break
    text = []
    for tr in doc["tracks"]:  # validated role order: text tracks first, top of the stack first
        if tr["role"] != "text":
            continue
        for it in tr["items"]:
            s, e = spans[it["id"]]
            if it["type"] == "text" and s <= t < e:
                text.append(
                    {
                        "text": it["text"],
                        "style": it["style"],
                        "alpha": str(_fade(s, e, t, it.get("fade_in", 0), it.get("fade_out", 0))),
                    }
                )
    text.reverse()  # draw bottom of the stack first
    return {"v": RECIPE_VERSION, "canvas": [cw, ch], "size": [width, height], "video": video, "text": text}


def key_of(recipe: dict) -> str:
    raw = json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    w, h = recipe["size"]
    return f"{hashlib.sha256(raw).hexdigest()}-{w}x{h}"


# --------------------------------------------------------------------------- rendering


def _grab(path: Path, src_t: int, w: int, h: int, crop: Any) -> Any:
    """One frame of ``path`` at ``src_t`` ticks, cropped to cover ``w``×``h`` (or to ``crop``)."""
    from PIL import Image

    sec = f"{Fraction(src_t, T.TICK_RATE).__float__():.6f}"
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if isinstance(crop, dict):  # {x, y, w, h}, each a [num, den] fraction of the source frame
        x, y, cw_, ch_ = (Fraction(*crop[k]) for k in "xywh")
        vf = f"crop=iw*{float(cw_):.6f}:ih*{float(ch_):.6f}:iw*{float(x):.6f}:ih*{float(y):.6f}," + vf
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        sec,
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-vf",
        vf,
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    p = subprocess.run(cmd, capture_output=True, timeout=60)
    if p.returncode != 0 or not p.stdout:
        return Image.new("RGB", (w, h), (0, 0, 0))  # past the end or unreadable: black, like a gap
    return Image.open(io.BytesIO(p.stdout)).convert("RGB")


def _text(img: Any, layers: list[dict]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    w, h = img.size
    for layer in layers:
        a = float(Fraction(layer["alpha"]))
        if a <= 0 or not layer["text"].strip():
            continue
        size = max(8, int(h * (0.075 if layer["style"] == "impact" else 0.06)))
        try:
            font = ImageFont.truetype(str(_FONT), size)
        except OSError:
            font = ImageFont.load_default()
        over = img.copy()
        d = ImageDraw.Draw(over)
        box = d.multiline_textbbox((0, 0), layer["text"], font=font, align="center", stroke_width=max(1, size // 12))
        x = (w - (box[2] - box[0])) // 2
        y = int(h * 0.72) - (box[3] - box[1]) // 2
        d.multiline_text(
            (x, y),
            layer["text"],
            font=font,
            fill=(255, 255, 255),
            align="center",
            stroke_width=max(1, size // 12),
            stroke_fill=(0, 0, 0),
        )
        img.paste(over if a >= 1 else Image.blend(img, over, a))


def render(recipe: dict, project_dir: Path) -> bytes:
    """The JPEG bytes for a recipe."""
    from PIL import Image

    w, h = recipe["size"]
    img = Image.new("RGB", (w, h), (0, 0, 0))
    for layer in recipe["video"]:
        proxy = M.cache_paths(project_dir, layer["media"])["proxy"]
        src = proxy if proxy.is_file() else Path(layer["path"])
        frame = _grab(src, layer["src_t"], w, h, layer["crop"])
        a = float(Fraction(layer["alpha"]))
        if a < 1:
            frame = Image.blend(Image.new("RGB", (w, h), (0, 0, 0)), frame, a)
        mix = float(Fraction(layer["mix"]))
        img = frame if mix >= 1 else Image.blend(img, frame, mix)
    _text(img, recipe["text"])
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


# --------------------------------------------------------------------------- the cache


class FrameCache:
    """``<project>/cache/frames/<key>.jpg``, LRU by access time, capped in bytes."""

    def __init__(self, project_dir: Path, cap: int = CACHE_CAP_BYTES) -> None:
        self.dir = project_dir / "cache" / "frames"
        self.project_dir = project_dir
        self.cap = cap
        self.lock = threading.Lock()
        self.hits = self.misses = 0

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.jpg"

    def get(self, recipe: dict) -> tuple[str, Path, bool]:
        """(key, path, hit). Renders on a miss; touches on a hit."""
        key = key_of(recipe)
        p = self.path(key)
        if p.is_file():
            with contextlib.suppress(OSError):
                os.utime(p)
            self.hits += 1
            return key, p, True
        data = render(recipe, self.project_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{key}.{threading.get_ident()}.tmp"
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
        self.misses += 1
        self.evict()
        return key, p, False

    def evict(self) -> int:
        """Drop the least recently used frames until the cache is under its cap; returns how many."""
        with self.lock:
            try:
                files = [(f.stat().st_mtime_ns, f.stat().st_size, f) for f in self.dir.glob("*.jpg")]
            except OSError:
                return 0
            total = sum(s for _, s, _ in files)
            dropped = 0
            for _, size, f in sorted(files):
                if total <= self.cap:
                    break
                with contextlib.suppress(OSError):
                    f.unlink()
                    total -= size
                    dropped += 1
            return dropped


# --------------------------------------------------------------------------- what an entry changed


def doc_at(log: Any, version: int) -> dict:
    """The doc at ``version`` (an entry's base or new version), from the log's checkpoints."""
    if version == log._base["version"]:
        return T.stamp_hash(log._base)[0]
    n = next(i for i, e in enumerate(log._entries, 1) if e["new_version"] == version)
    done = max(k for k in log._checkpoints if k <= n)
    from hermes_studio import oplog as O

    then = O.Oplog(log._base)
    then._doc, retired = log._checkpoints[done]
    then._retired = set(retired)
    for prev in log._entries[done:n]:
        new, _, _ = then._run(prev["ops"], internal=True)
        then._retire(new)
        then._doc = new
    return copy.deepcopy(then._doc)


def first_changed_time(before: dict, after: dict, changed: list[str]) -> int:
    """The earliest timeline time an entry touched: the start of any changed item or marker in
    either version, else 0 (a media-only or track-only change)."""
    times = []
    for d in (before, after):
        spans = T.resolve(d)
        times += [spans[i][0] for i in changed if i in spans]
        times += [mk["at"] for mk in d["markers"] if mk["id"] in changed]
    return min(times) if times else 0


def entry_frames(log: Any, op_id: str, width: int = DEFAULT_WIDTH) -> dict:
    """Before/after recipes for one entry at its first changed time (clamped into each doc)."""
    e = next((x for x in log._entries if x["op_id"] == op_id), None)
    if e is None:
        return {}
    before, after = doc_at(log, e["base_version"]), doc_at(log, e["new_version"])
    t = first_changed_time(before, after, e["changed_ids"])
    return {
        "op_id": op_id,
        "at": t,
        "before": recipe_at(before, t, width),
        "after": recipe_at(after, t, width),
        "before_version": e["base_version"],
        "after_version": e["new_version"],
    }


def timeline_end(doc: dict) -> int:
    spans = T.resolve(doc)
    return max((e for _, e in spans.values()), default=0)


def contact_sheet(images: list[tuple[int, Path]], cols: int = 4) -> bytes:
    """Tile frames into one JPEG with each frame's time under it."""
    from PIL import Image, ImageDraw, ImageFont

    if not images:
        raise ValueError("no frames")
    first = Image.open(images[0][1])
    w, h = first.size
    label = max(12, h // 10)
    cols = max(1, min(cols, len(images)))
    rows = -(-len(images) // cols)
    sheet = Image.new("RGB", (cols * w, rows * (h + label)), (11, 11, 12))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(str(Path(__file__).parent / "data" / "fonts" / "JetBrainsMono.ttf"), max(9, label - 4))
    except OSError:
        font = ImageFont.load_default()
    for i, (t, p) in enumerate(images):
        x, y = (i % cols) * w, (i // cols) * (h + label)
        sheet.paste(Image.open(p).convert("RGB"), (x, y))
        s = Fraction(t, T.TICK_RATE)
        d.text((x + 4, y + h + 1), f"{int(s // 60)}:{float(s % 60):05.2f}", fill=(255, 200, 61), font=font)
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=80)
    return buf.getvalue()
