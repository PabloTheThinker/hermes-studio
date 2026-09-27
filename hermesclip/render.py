from __future__ import annotations

import subprocess
from pathlib import Path

from hermesclip.captions import build_ass
from hermesclip.layout import frame_filters, probe_size
from hermesclip.pacing import TimeMap, keep_intervals, remap_words
from hermesclip.plan import ClipPlan
from hermesclip.transcribe import Transcript


def probe_duration(video: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        text=True,
    ).strip()
    return float(out)


def _ass_escape(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def render_clip(
    video: Path,
    plan: ClipPlan,
    tr: Transcript,
    out_path: Path,
    work: Path,
    width: int = 1080,
    height: int = 1920,
    pacing: str = "tight",
    style: str = "pop",
    layout: str = "fit",
    hook: str = "",
    captions: bool = True,
    look=None,
    fixes: dict | None = None,
) -> Path:
    """Render one clip. Pacing always cuts on the real words; `captions=False` only hides the burn-in.

    look (hermesclip.look.Look): auto/fit/fill/split framing, face top/bottom, colour filter,
    caption position, audio clean-up, progress bar. Returns out_path; the layout actually
    used is written to `render_clip.last_layout`.
    """
    from hermesclip.look import AUDIO_CLEAN, Look, caption_margin, choose_layout

    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_w, src_h = probe_size(video)
    lk = look or Look(layout=layout)
    if look is None or lk.layout not in ("auto", "fit", "fill", "split"):
        lk.layout = layout
    box = None
    need_face = lk.layout in ("auto", "fill", "split") and not (lk.layout == "split" and lk.face_box)
    if need_face:
        from hermesclip.face import face_box

        box = face_box(video, plan.start, plan.end)
    used = lk.layout
    if used == "auto":
        used, _why = choose_layout(box, src_w, src_h, width, height)
    face = (box[0] + box[2] / 2, box[1] + box[3] / 2) if box else None
    layout = used
    render_clip.last_layout = used  # type: ignore[attr-defined]
    if pacing == "tight":
        tm = keep_intervals(tr.words, plan.start, plan.end)
        cap_words = remap_words(tr.words, plan.start, plan.end, tm)
        cap_start, cap_end = 0.0, max(tm.duration, 0.2)
    else:
        tm = TimeMap([(0.0, plan.end - plan.start)])
        cap_words = tr.words
        cap_start, cap_end = plan.start, plan.end

    if not captions:
        cap_words = []
    from hermesclip.captions import STYLES

    st = STYLES.get(style, STYLES["pop"])
    seam = None
    if layout == "split":
        fh = int(height * lk.face_ratio) // 2 * 2
        seam = fh if lk.face == "top" else height - fh
    place = caption_margin(lk, layout, height, st.size, seam)
    ass = work / f"{out_path.stem}.ass"
    ass.write_text(
        build_ass(
            cap_words,
            cap_start,
            cap_end,
            plan.emphasis,
            width,
            height,
            style,
            layout=layout,
            hook=hook,
            place=place,
            fixes=fixes,
        )
    )
    ass_f = _ass_escape(ass)
    out_dur = tm.duration if tm.keeps else (plan.end - plan.start)
    graph = frame_filters(
        src_w, src_h, width, height, layout, ass_f, vin="cv", vout="outv",
        face=face, look=lk, box=box, clip_dur=out_dur,
    )
    audio = AUDIO_CLEAN if lk.audio == "clean" else ""
    if len(tm.keeps) <= 1:
        a, b = tm.keeps[0] if tm.keeps else (0.0, plan.end - plan.start)
        cmd = _simple(video, plan.start + a, plan.start + b, graph, out_path, audio)
    else:
        cmd = _concat(video, plan.start, tm, graph, out_path, audio)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2500:] or "ffmpeg failed")
    return out_path


def _encode_tail(out_path: Path) -> list[str]:
    return [
        "-map",
        "[outv]",
        "-map",
        "[ca]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
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


def _simple(video: Path, start: float, end: float, graph: str, out_path: Path, audio: str = "") -> list[str]:
    af = ("," + audio) if audio else ""
    fc = (
        f"[0:v]trim=start=0:end={end - start:.3f},setpts=PTS-STARTPTS[cv];"
        f"[0:a]atrim=start=0:end={end - start:.3f},asetpts=PTS-STARTPTS{af}[ca];"
        f"{graph}"
    )
    return [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(video),
        "-filter_complex",
        fc,
        *_encode_tail(out_path),
    ]


def _concat(video: Path, clip_start: float, tm: TimeMap, graph: str, out_path: Path, audio: str = "") -> list[str]:
    parts_v = []
    parts_a = []
    fc = []
    for i, (a, b) in enumerate(tm.keeps):
        s = clip_start + a
        e = clip_start + b
        fc.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        fc.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        parts_v.append(f"[v{i}]")
        parts_a.append(f"[a{i}]")
    n = len(tm.keeps)
    streams = "".join(x + y for x, y in zip(parts_v, parts_a))
    if audio:
        fc.append(f"{streams}concat=n={n}:v=1:a=1[cv][cr]")
        fc.append(f"[cr]{audio}[ca]")
    else:
        fc.append(f"{streams}concat=n={n}:v=1:a=1[cv][ca]")
    fc.append(graph)
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-filter_complex",
        ";".join(fc),
        *_encode_tail(out_path),
    ]
