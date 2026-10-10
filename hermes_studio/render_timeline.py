"""Render a timeline document to a file with ffmpeg.

The op log decides what the cut is; this module turns that decision into pixels and
sound. Nothing here writes the timeline: it only reads it.

Shape of a render:
  * Every clip on the main track is trimmed from its source, scaled to the canvas
    with ``contain`` (the whole frame is kept, never cropped) and laid end to end.
    A gap between clips renders as black, not a frozen frame.
  * Voice and music items are placed at their own times on the timeline through
    ``adelay``, so a gap in a sound track stays a gap instead of being squeezed.
    Voice sits at full level, music under it. Output is loudness-normalised.
  * Text items burn in as captions through the same ASS builder the clips use, so
    the Edit page and a finished clip look like the same product.
  * The output is exactly the canvas size: a Phone cut is 1080x1920, a Desktop cut
    1920x1080, with no guessing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from hermes_studio.editor import EditorError, resolve_media

# Voice is the story; music sits under it.
MIX = {"voice": 1.0, "music": 0.35}


class RenderError(Exception):
    pass


def _run(cmd: list[str], *, timeout: int = 7200) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RenderError(proc.stderr[-2500:] or "ffmpeg failed")


def _probe_size(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        w, h = (int(x) for x in proc.stdout.strip().split(",")[:2])
    except ValueError as exc:
        raise RenderError(f"cannot read that picture: {path.name}") from exc
    if proc.returncode != 0 or w <= 0 or h <= 0:
        raise RenderError(f"cannot read that picture: {path.name}")
    return w, h


def _has_audio(path: Path) -> bool:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode == 0 and "audio" in proc.stdout


def _fps(doc: dict) -> float:
    raw = doc.get("fps") or [30, 1]
    try:
        num, den = int(raw[0]), int(raw[1])
    except (IndexError, TypeError, ValueError):
        return 30.0
    return num / den if num > 0 and den > 0 else 30.0


def _t2s(ticks: int, rate: int) -> float:
    return ticks / rate


def _ass_escape_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _canvas(doc: dict) -> tuple[int, int]:
    size = list(doc.get("size") or [1920, 1080])
    try:
        w, h = int(size[0]), int(size[1])
    except (IndexError, TypeError, ValueError) as exc:
        raise RenderError("canvas is not a width and a height") from exc
    if not (1 <= w <= 16384 and 1 <= h <= 16384):
        raise RenderError("canvas must be 1 to 16384 on each side")
    return w, h


def _contain(sw: int, sh: int, w: int, h: int) -> tuple[int, int, int, int]:
    """Scale to fit the canvas, centred. Widths are even so the encoder is happy."""
    if sw <= 0 or sh <= 0 or w <= 0 or h <= 0:
        raise RenderError("canvas must be 1 to 16384 on each side")
    scale = min(w / sw, h / sh)
    dw = max(2, int(round(sw * scale)) // 2 * 2)
    dh = max(2, int(round(sh * scale)) // 2 * 2)
    return dw, dh, (w - dw) // 2, (h - dh) // 2


# --------------------------------------------------------------------------- plan


def _build_plan(doc: dict, folder: Path) -> dict:
    """Turn a timeline doc into a render plan. Pure: ffmpeg is never touched here."""
    w, h = _canvas(doc)
    rate = doc["tick_rate"]
    media = doc.get("media") or {}

    def items(role: str) -> list[dict]:
        for tr in doc["tracks"]:
            if tr.get("role") == role:
                return [it for it in tr["items"] if "at" in it and it.get("type") != "transition"]
        return []

    main = sorted(items("main"), key=lambda it: it["at"])
    if not main:
        raise RenderError("nothing on the main track")

    inputs: list[dict] = []
    seen: dict[str, int] = {}
    end_tick = 0
    cursor = 0
    for it in main:
        i0, o1 = it["src"]
        if i0 >= o1:
            raise RenderError("a clip has no length")
        rel = str(media.get(it.get("media") or "", {}).get("path") or "")
        if not rel:
            raise RenderError("a clip has no picture")
        path = resolve_media(folder, rel)
        if not path.is_file():
            raise RenderError(f"picture file is missing: {path.name}")
        if cursor < it["at"]:
            inputs.append({"role": "gap", "at": cursor, "end": it["at"]})
        cursor = it["at"] + (o1 - i0)
        end_tick = max(end_tick, cursor)
        idx = seen.get(rel)
        if idx is None:
            idx = len(inputs)
            seen[rel] = idx
            sw, sh = _probe_size(path)
            inputs.append({"role": "clip", "idx": idx, "path": path, "src": (i0, o1), "at": it["at"], "size": (sw, sh)})
        else:
            inputs.append({"role": "clip", "idx": idx, "path": path, "src": (i0, o1), "at": it["at"], "size": None})

    audio: list[dict] = []
    for role in ("voice", "music"):
        for it in items(role):
            i0, o1 = it["src"]
            rel = str(media.get(it.get("media") or "", {}).get("path") or "")
            if not rel or i0 >= o1:
                continue
            path = resolve_media(folder, rel)
            if not path.is_file():
                raise RenderError(f"sound file is missing: {path.name}")
            idx = seen.get(rel)
            if idx is None:
                idx = len(inputs)
                seen[rel] = idx
                inputs.append({"role": "sound", "idx": idx, "path": path, "src": None, "at": it["at"], "size": None})
            audio.append(
                {
                    "idx": idx,
                    "role": role,
                    "src": (i0, o1),
                    "at": it["at"],
                    "fade_in": it.get("fade_in") or 0,
                    "fade_out": it.get("fade_out") or 0,
                }
            )
            end_tick = max(end_tick, it["at"] + (o1 - i0))

    captions = []
    for it in items("text"):
        text = " ".join(str(it.get("text") or "").split())
        if not text:
            continue
        captions.append({"at": it["at"], "dur": it.get("dur") or 0, "text": text, "style": str(it.get("style") or "pop")})
        end_tick = max(end_tick, it["at"] + (it.get("dur") or 0))

    if end_tick <= 0:
        raise RenderError("nothing to render")

    return {
        "width": w,
        "height": h,
        "fps": _fps(doc),
        "rate": rate,
        "inputs": inputs,
        "audio": audio,
        "captions": captions,
        "end_tick": end_tick,
        "silent": not any(True for _ in audio),
    }


def _build_ass(plan: dict, cache: Path) -> Path | None:
    """Captions as an ASS file under the project cache. None when the cut has no text."""
    from hermes_studio.captions import STYLES, build_ass
    from hermes_studio.transcribe import Word

    if not plan["captions"]:
        return None
    rate = plan["rate"]
    words: list[Word] = []
    for cap in plan["captions"]:
        start = _t2s(cap["at"], rate)
        end = max(start + 0.01, _t2s(cap["at"] + cap["dur"], rate))
        for tok in cap["text"].split():
            words.append(Word(text=tok, start=start, end=end))
    if not words:
        return None
    styles = {c["style"] for c in plan["captions"]}
    style = styles.pop() if len(styles) == 1 else "pop"
    st = STYLES.get(style, STYLES["pop"])
    cache.mkdir(parents=True, exist_ok=True)
    ass = cache / "render.ass"
    ass.write_text(
        build_ass(
            words,
            0.0,
            _t2s(plan["end_tick"], plan["rate"]) + 1.0,
            None,
            plan["width"],
            plan["height"],
            style,
            layout="fit",
            place=(2, st.margin_v_fit),
        )
    )
    return ass


# --------------------------------------------------------------------------- graph


def _build_graph(plan: dict, ass: Path | None) -> tuple[str, str]:
    """The filter graph, and the label to map as the output video."""
    w, h = plan["width"], plan["height"]
    rate = plan["rate"]
    total = _t2s(plan["end_tick"], rate)
    fps = plan["fps"]
    fc: list[str] = []
    v_in: list[str] = []

    # The same source cut more than once needs a split so each piece keeps its trim.
    v_uses: dict[int, int] = {}
    a_uses: dict[int, int] = {}
    for inp in plan["inputs"]:
        if inp["role"] == "clip":
            v_uses[inp["idx"]] = v_uses.get(inp["idx"], 0) + 1
    for row in plan["audio"]:
        a_uses[row["idx"]] = a_uses.get(row["idx"], 0) + 1
    for idx, count in v_uses.items():
        if count > 1:
            outs = "".join(f"[s{idx}_{k}]" for k in range(count))
            fc.append(f"[{idx}:v]split={count}{outs}")
    for idx, count in a_uses.items():
        if count > 1:
            outs = "".join(f"[sa{idx}_{k}]" for k in range(count))
            fc.append(f"[{idx}:a]asplit={count}{outs}")

    cut_v: dict[int, int] = {}
    cut_a: dict[int, int] = {}
    for n, inp in enumerate(plan["inputs"]):
        kind = inp["role"]
        if kind == "clip":
            idx = inp["idx"]
            k = cut_v.get(idx, 0)
            cut_v[idx] = k + 1
            src = f"s{idx}_{k}" if v_uses.get(idx, 0) > 1 else f"{idx}:v"
            i0, o1 = inp["src"]
            s_in = _t2s(i0, rate)
            dur = _t2s(o1 - i0, rate)
            v_in.append(f"[v{n}]")
            sw, sh = inp["size"] or (w, h)
            dw, dh, x, y = _contain(sw, sh, w, h)
            chain = f"scale={dw}:{dh}:flags=bicubic,pad={w}:{h}:{x}:{y}:black,fps={fps:.3f},format=yuv420p"
            fc.append(f"[{src}]trim=start={s_in:.3f}:end={s_in + dur:.3f},setpts=PTS-STARTPTS,{chain}[v{n}]")
        elif kind == "gap":
            dur = _t2s(inp["end"] - inp["at"], rate)
            v_in.append(f"[v{n}]")
            fc.append(f"[{inp['idx']}:v]trim=start=0:end={dur:.3f},setpts=PTS-STARTPTS,fps={fps:.3f},format=yuv420p[v{n}]")

    if len(v_in) == 1:
        fc.append(f"{v_in[0]}copy[outv]")
    else:
        fc.append("".join(v_in) + f"concat=n={len(v_in)}:v=1:a=0[outv]")

    # Sound: each item is placed at its own time, then padded to the full length so
    # amix sees streams of equal size and a gap stays a gap.
    a_ready: list[str] = []
    for n, row in enumerate(plan["audio"]):
        idx = row["idx"]
        i0, o1 = row["src"]
        s_in = _t2s(i0, rate)
        dur = _t2s(o1 - i0, rate)
        delay_ms = int(round(_t2s(row["at"], rate) * 1000))
        fade = ""
        fi, fo = row["fade_in"], row["fade_out"]
        if fi:
            fade += f",afade=t=in:st=0:d={_t2s(fi, rate):.3f}"
        if fo:
            fade += f",afade=t=out:st={max(0.0, dur - _t2s(fo, rate)):.3f}:d={_t2s(fo, rate):.3f}"
        lab = f"au{n}"
        k = cut_a.get(idx, 0)
        cut_a[idx] = k + 1
        asrc = f"sa{idx}_{k}" if a_uses.get(idx, 0) > 1 else f"{idx}:a"
        fc.append(
            f"[{asrc}]atrim=start={s_in:.3f}:end={s_in + dur:.3f},asetpts=PTS-STARTPTS"
            f"{fade},aresample=48000,adelay=delays={delay_ms}:all=1,"
            f"apad=whole_dur={total:.3f}[{lab}]"
        )
        a_ready.append((lab, row["role"]))

    if not a_ready:
        fc.append(f"anullsrc=r=48000:cl=stereo:d={total:.3f}[outa]")
    else:
        weights = [MIX.get(role, 1.0) for _lab, role in a_ready]
        scale = 1.0 / max(1e-6, sum(weights))
        wstr = " ".join(f"{wgt * scale:.4f}" for wgt in weights)
        fc.append(
            "".join(f"[{lab}]" for lab, _role in a_ready)
            + f"amix=inputs={len(a_ready)}:duration=first:normalize=0:weights='{wstr}',"
            "alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,"
            f"atrim=duration={total:.3f},asetpts=PTS-STARTPTS[outa]"
        )

    vout = "outv"
    if ass is not None:
        fc.append(f"[outv]ass='{_ass_escape_path(ass)}'[outv2]")
        vout = "outv2"

    return ";".join(fc), vout


def _encode(plan: dict, graph: str, vout: str, out_path: Path) -> list[str]:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-nostdin"]
    for inp in plan["inputs"]:
        kind = inp["role"]
        if kind == "clip":
            cmd += ["-i", str(inp["path"])]
        elif kind == "sound":
            cmd += ["-i", str(inp["path"])]
        elif kind == "gap":
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s={plan['width']}x{plan['height']}:r={plan['fps']:.3f}"]
    cmd += [
        "-filter_complex",
        graph,
        "-map",
        f"[{vout}]",
        "-map",
        "[outa]",
        "-t",
        f"{_t2s(plan['end_tick'], plan['rate']):.3f}",
        "-r",
        f"{plan['fps']:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return cmd


def render_project(pid: str, out_path: Path | None = None) -> dict:
    """Render a project to a file. The file lands in the project folder by default."""
    from hermes_studio import editor as E

    folder = E._dir(pid)
    if not (folder / "base.json").exists():
        raise EditorError("no such project")
    plan = _build_plan(E._log(folder).doc, folder)
    if shutil.which("ffmpeg") is None:
        raise RenderError("ffmpeg is not installed")
    ass = _build_ass(plan, folder / "cache")
    graph, vout = _build_graph(plan, ass)
    dest = out_path or (folder / f"{pid}-render.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(_encode(plan, graph, vout, dest))
    if not dest.is_file() or dest.stat().st_size < 1024:
        raise RenderError("the render produced no file")
    return {
        "ok": True,
        "path": str(dest),
        "name": dest.name,
        "size": [plan["width"], plan["height"]],
        "duration": round(_t2s(plan["end_tick"], plan["rate"]), 3),
        "bytes": dest.stat().st_size,
        "captions": bool(ass),
    }


__all__ = ["RenderError", "render_project", "MIX"]
