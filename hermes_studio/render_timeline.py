"""S6 render v1: a timeline document to one H.264/AAC file with a single FFmpeg filter graph.

Video: a black canvas the length of the timeline; each V1 clip is cut from its source (speed,
crop, fades applied), scaled to cover the canvas and overlaid at its time. A transition is the
incoming clip fading in over the overlap with an alpha fade, so the overlay is a true crossfade.
Text items and captions are one ASS file burned in last. Audio: every clip on every track with
audio is cut the same way, delayed to its time, and mixed (``normalize=0``), padded to length.

Long timelines (more than ``SEGMENT_OVER`` clips) render in windows cut where no transition
spans, then join with the concat demuxer (stream copy). A window is rendered by the same code:
every item is built whole, then trimmed to the window, so fades and transitions that start
before the window still look right inside it.

Times are exact ticks until the last step, where FFmpeg needs seconds (6 decimals).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

from hermes_studio import timeline as T

SEGMENT_OVER = 40
CRF = 18  # final renders: visually lossless (C11 SSIM >= 0.98 against the source)
Progress = Callable[[float], None]


def _s(ticks: int | Fraction) -> str:
    return f"{float(Fraction(ticks) / T.TICK_RATE):.6f}"


def _props(it: dict) -> dict:
    return {**T.DEFAULT_PROPS, **(it.get("props") or {})}


def _speed(it: dict) -> Fraction:
    return Fraction(*_props(it)["speed"])


def _ratio(v: Any) -> Fraction:
    return Fraction(*v) if isinstance(v, list) else Fraction(v)


def timeline_end(doc: dict) -> int:
    return max((e for _, e in T.resolve(doc).values()), default=0)


def _has_audio(path: str, cache: dict[str, bool]) -> bool:
    if path not in cache:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        cache[path] = bool(p.stdout.strip())
    return cache[path]


def _has_video(path: str, cache: dict[str, bool]) -> bool:
    key = "v:" + path
    if key not in cache:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        cache[key] = bool(p.stdout.strip())
    return cache[key]


# --------------------------------------------------------------------------- ASS for text + captions


def _ass_time(ticks: int) -> str:
    cs = max(0, int(Fraction(ticks, T.TICK_RATE) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def build_ass(doc: dict, w: int, h: int, a: int, b: int, words: list[dict] | None) -> str:
    """Text items (lower third, by style) and caption words (bottom) for the window [a, b)."""
    spans = T.resolve(doc)
    big = max(10, h // 14)
    small = max(10, h // 22)
    out = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: text,DejaVu Sans,{big},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(2, big // 12)},0,5,"
        f"{w // 12},{w // 12},0,1",
        f"Style: impact,DejaVu Sans,{int(big * 1.25)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,"
        f"{max(3, big // 8)},0,5,{w // 12},{w // 12},0,1",
        f"Style: cap,DejaVu Sans,{small},&H00FFFFFF,&H0000E5FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(2, small // 10)},0,2,"
        f"{w // 10},{w // 10},{h // 9},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for tr in doc["tracks"]:
        if tr["role"] != "text":
            continue
        for it in tr["items"]:
            s, e = spans[it["id"]]
            if e <= a or s >= b:
                continue
            fi = int(Fraction(it.get("fade_in", 0), T.TICK_RATE) * 1000)
            fo = int(Fraction(it.get("fade_out", 0), T.TICK_RATE) * 1000)
            fad = f"{{\\fad({fi},{fo})\\pos({w // 2},{int(h * 0.72)})}}"
            style = "impact" if it["style"] == "impact" else "text"
            out.append(
                f"Dialogue: 1,{_ass_time(max(s, a) - a)},{_ass_time(min(e, b) - a)},{style},,0,0,0,,{fad}{_ass_text(it['text'])}"
            )
    return "\n".join(out) + "\n"


def caption_ass(words: list[dict], w: int, h: int, a: int, b: int, style: str) -> str | None:
    """The clip pipeline's own word-by-word captions (``captions.build_ass``) for the window
    [a, b): the same look as Hermes clips. None when no word falls in the window."""
    from hermes_studio.captions import build_ass as clip_ass
    from hermes_studio.transcribe import Word

    local = [
        Word(wd["w"], float(Fraction(max(wd["at"], a) - a, T.TICK_RATE)), float(Fraction(min(wd["end"], b) - a, T.TICK_RATE)))
        for wd in words
        if wd["end"] > a and wd["at"] < b and wd["end"] > wd["at"]
    ]
    if not local:
        return None
    return clip_ass(local, 0.0, float(Fraction(b - a, T.TICK_RATE)), play_x=w, play_y=h, style=style, layout="fit")


# --------------------------------------------------------------------------- the graph


def plan(
    doc: dict,
    project_dir: Path,
    a: int,
    b: int,
    size: tuple[int, int],
    words: list[dict] | None,
    work: Path,
    caption_style: str = "pop",
) -> dict:
    """The two FFmpeg passes for the window [a, b) of ``doc``: ``video`` and ``audio``, each
    ``(input args, filter_complex)``, plus ``info``. Audio is its own pass: one graph pulling
    video and audio from the same seeked inputs at different rates can stall FFmpeg."""
    w, h = size
    fps = Fraction(*doc["fps"])
    spans = T.resolve(doc)
    by_id = {it["id"]: it for tr in doc["tracks"] for it in tr["items"]}
    probe: dict[str, bool] = {}
    inputs: list[str] = []
    ainputs: list[str] = []

    def src_of(mid: str) -> str:
        return doc["media"][mid]["path"]

    def inp(into: list[str], path: str, start: int, length: int) -> int:
        """One input per clip, seeked to its source range: decoders never wait on each other."""
        into.extend(["-ss", _s(start), "-t", _s(length), "-i", path])
        return into.count("-i") - 1

    # transitions: incoming clip id -> overlap ticks; outgoing clip id -> overlap ticks
    fade_alpha_in: dict[str, int] = {}
    fade_audio_out: dict[str, int] = {}
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["type"] == "transition":
                out_id, in_id = it["between"]
                fade_alpha_in[in_id] = it["dur"]
                fade_audio_out[out_id] = it["dur"]

    dur = b - a
    graph: list[str] = [f"color=c=black:s={w}x{h}:r={fps.numerator}/{fps.denominator}:d={_s(dur)},format=yuv420p[base]"]
    last = "base"
    audio_labels: list[str] = []
    agraph: list[str] = []
    n_video = 0
    for tr in doc["tracks"]:
        for it in tr["items"]:
            if it["type"] != "clip":
                continue
            s, e = spans[it["id"]]
            if e <= a or s >= b:
                continue
            path = src_of(it["media"])
            sp = _speed(it)
            src_in, src_out = it["src"]
            lo, hi = max(s, a) - s, min(e, b) - s  # the window's part, in clip-local timeline ticks
            place = max(s, a) - a
            fi, fo = it.get("fade_in", 0), it.get("fade_out", 0)
            props = _props(it)
            if tr["id"] == T.MAIN_TRACK and _has_video(path, probe):
                n_video += 1
                k = inp(inputs, path, src_in, src_out - src_in)
                f = [f"[{k}:v]trim=duration={_s(src_out - src_in)}", "setpts=PTS-STARTPTS"]
                if sp != 1:
                    f.append(f"setpts=PTS/{float(sp):.6f}")
                f.append(f"fps={fps.numerator}/{fps.denominator}")
                crop = props["crop"]
                if isinstance(crop, dict):
                    x, y, cw, ch = (_ratio(crop[q]) for q in "xywh")
                    f.append(f"crop=iw*{float(cw):.6f}:ih*{float(ch):.6f}:iw*{float(x):.6f}:ih*{float(y):.6f}")
                f += [f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}", "setsar=1", "format=yuva420p"]
                clip_len = e - s
                if fi:
                    f.append(f"fade=t=in:st=0:d={_s(fi)}")
                if fo:
                    f.append(f"fade=t=out:st={_s(clip_len - fo)}:d={_s(fo)}")
                if it["id"] in fade_alpha_in:
                    f.append(f"fade=t=in:st=0:d={_s(fade_alpha_in[it['id']])}:alpha=1")
                f += [f"trim=start={_s(lo)}:end={_s(hi)}", f"setpts=PTS-STARTPTS+{_s(place)}/TB"]
                lab = f"v{n_video}"
                graph.append(",".join(f) + f"[{lab}]")
                graph.append(f"[{last}][{lab}]overlay=eof_action=pass:format=auto[o{n_video}]")
                last = f"o{n_video}"
            if _has_audio(path, probe) and _ratio(props["volume"]) > 0:
                k = inp(ainputs, path, src_in, src_out - src_in)
                af = [f"[{k}:a]atrim=duration={_s(src_out - src_in)}", "asetpts=PTS-STARTPTS"]
                rest = sp
                while rest > 2:
                    af.append("atempo=2")
                    rest /= 2
                while rest < Fraction(1, 2):
                    af.append("atempo=0.5")
                    rest *= 2
                if rest != 1:
                    af.append(f"atempo={float(rest):.6f}")
                af += ["aformat=sample_rates=48000:channel_layouts=stereo"]
                vol = _ratio(props["volume"])
                if vol != 1:
                    af.append(f"volume={float(vol):.6f}")
                clip_len = e - s
                if fi:
                    af.append(f"afade=t=in:st=0:d={_s(fi)}")
                if fo:
                    af.append(f"afade=t=out:st={_s(clip_len - fo)}:d={_s(fo)}")
                if it["id"] in fade_alpha_in:
                    af.append(f"afade=t=in:st=0:d={_s(fade_alpha_in[it['id']])}")
                if it["id"] in fade_audio_out:
                    d = fade_audio_out[it["id"]]
                    af.append(f"afade=t=out:st={_s(clip_len - d)}:d={_s(d)}")
                af += [f"atrim=start={_s(lo)}:end={_s(hi)}", "asetpts=PTS-STARTPTS"]
                ms = int(Fraction(place, T.TICK_RATE) * 1000)
                if ms:
                    af.append(f"adelay={ms}:all=1")
                lab = f"a{len(audio_labels) + 1}"
                agraph.append(",".join(af) + f"[{lab}]")
                audio_labels.append(lab)

    def sub(name: str, text: str) -> str:
        f = work / name
        f.write_text(text, encoding="utf-8")
        arg = str(f).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        return f"subtitles=filename='{arg}'"

    subs = [sub("overlay.ass", build_ass(doc, w, h, a, b, None))]
    caps = caption_ass(words, w, h, a, b, caption_style) if words else None
    if caps:
        subs.append(sub("captions.ass", caps))
    graph.append(f"[{last}]{','.join(subs)},trim=duration={_s(dur)},format=yuv420p[outv]")
    if audio_labels:
        mix = "".join(f"[{x}]" for x in audio_labels)
        agraph.append(f"{mix}amix=inputs={len(audio_labels)}:normalize=0:dropout_transition=0,apad,atrim=duration={_s(dur)}[ca]")
    else:
        agraph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={_s(dur)}[ca]")
    _ = by_id
    return {
        "video": (inputs, ";".join(graph)),
        "audio": (ainputs, ";".join(agraph)),
        "info": {"clips": n_video, "audio_streams": len(audio_labels), "duration": dur},
    }


def _encode(passes: dict, fps: Fraction, out: Path, dur: int, on_progress: Progress | None, cancel: Callable[[], bool]) -> None:
    """Audio pass to a WAV next to ``out`` (about 5% of the bar), then the video pass muxing it."""
    wav = out.with_name(f".{out.stem}.audio.wav")
    ain, agraph = passes["audio"]
    _ffmpeg(
        [*ain, "-filter_complex", agraph, "-map", "[ca]", "-c:a", "pcm_s16le", "-ar", "48000", "-t", _s(dur), str(wav)],
        dur,
        (lambda f: on_progress(0.05 * f)) if on_progress else None,
        cancel,
    )
    vin, vgraph = passes["video"]
    n = vin.count("-i")
    try:
        _ffmpeg(
            [
                *vin,
                "-i",
                str(wav),
                "-filter_complex",
                vgraph,
                "-map",
                "[outv]",
                "-map",
                f"{n}:a",
                "-r",
                f"{fps.numerator}/{fps.denominator}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(CRF),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ar",
                "48000",
                "-t",
                _s(dur),
                "-movflags",
                "+faststart",
                "-f",
                "mp4",
                str(out),
            ],
            dur,
            (lambda f: on_progress(0.05 + 0.95 * f)) if on_progress else None,
            cancel,
        )
    finally:
        wav.unlink(missing_ok=True)


def _ffmpeg(args: list[str], dur: int, on_progress: Progress | None, cancel: Callable[[], bool]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error", "-progress", "pipe:1", "-y", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    total = max(1, dur * 1_000_000 // T.TICK_RATE)
    try:
        assert p.stdout is not None
        for line in p.stdout:
            if cancel():
                p.kill()
                break
            k, _, v = line.strip().partition("=")
            if k == "out_time_us" and v.isdigit() and on_progress:
                on_progress(min(1.0, int(v) / total))
        p.wait()
        err = p.stderr.read() if p.stderr else ""
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        for s in (p.stdout, p.stderr):
            if s:
                s.close()
    if cancel():
        raise RuntimeError("render cancelled")
    if p.returncode != 0:
        raise RuntimeError(err.strip()[-1500:] or f"ffmpeg exit {p.returncode}")


def windows(doc: dict, every: int = SEGMENT_OVER) -> list[tuple[int, int]]:
    """Cut points for a long timeline: V1 clip starts, every ``every`` clips, never inside a
    transition (or an anchored item's span, which is drawn whole by its window)."""
    end = timeline_end(doc)
    spans = T.resolve(doc)
    main = next((tr for tr in doc["tracks"] if tr["id"] == T.MAIN_TRACK), {"items": []})
    clips = sorted(spans[it["id"]][0] for it in main["items"] if it["type"] == "clip")
    if len(clips) <= every:
        return [(0, end)]
    busy = [spans[it["id"]] for tr in doc["tracks"] for it in tr["items"] if it["type"] == "transition"]
    cuts = [0]
    for i in range(every, len(clips), every):
        t = clips[i]
        if t > cuts[-1] and not any(s < t < e for s, e in busy):
            cuts.append(t)
    cuts.append(end)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1) if cuts[i + 1] > cuts[i]]


def render(
    doc: dict,
    project_dir: Path,
    out: Path,
    *,
    size: tuple[int, int] | None = None,
    words: list[dict] | None = None,
    caption_style: str = "pop",
    on_progress: Progress | None = None,
    cancel: Callable[[], bool] = lambda: False,
    segment_over: int = SEGMENT_OVER,
) -> dict:
    """Render a valid doc to ``out`` (mp4). Returns ``{path, duration, segments, clips}``."""
    size = size or tuple(doc["size"])
    if size[0] % 2 or size[1] % 2:
        raise ValueError("width and height must be even")
    end = timeline_end(doc)
    if end <= 0:
        raise ValueError("the timeline is empty")
    fps = Fraction(*doc["fps"])
    work = out.parent / f".{out.stem}.work"
    work.mkdir(parents=True, exist_ok=True)
    wins = windows(doc, segment_over)
    done = 0
    parts: list[Path] = []
    clips = 0
    try:
        for i, (a, b) in enumerate(wins):
            seg_dir = work / f"seg{i:04d}"
            seg_dir.mkdir(exist_ok=True)
            target = out if len(wins) == 1 else seg_dir / "part.mp4"
            tmp = target.with_name(f".{target.stem}.tmp.mp4")
            passes = plan(doc, project_dir, a, b, size, words, seg_dir, caption_style)
            clips += passes["info"]["clips"]

            def prog(f: float, a=a, b=b, done=done) -> None:
                if on_progress:
                    on_progress(min(1.0, (done + f * (b - a)) / end))

            _encode(passes, fps, tmp, b - a, prog, cancel)
            os.replace(tmp, target)
            parts.append(target)
            done += b - a
        if len(wins) > 1:
            lst = work / "parts.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
            tmp = out.with_name(f".{out.stem}.tmp.mp4")
            p = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(lst),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(tmp),
                ],
                capture_output=True,
                text=True,
            )
            if p.returncode != 0:
                raise RuntimeError(p.stderr.strip()[-1500:] or "concat failed")
            os.replace(tmp, out)
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    if on_progress:
        on_progress(1.0)
    return {"path": str(out), "duration": end, "segments": len(wins), "clips": clips}
