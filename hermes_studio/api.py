"""One core for every way in: the CLI, the MCP server and the Hermes plugin.

Every function returns a plain dict with ``ok`` and raises ``HermesStudioError``
(with a short message, a stable ``code`` and a ``hint`` saying what to do next)
for anything the caller got wrong. Nothing here prints. Nothing here posts.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hermes_studio import __version__

Progress = Callable[[str, float, str], None]

# Exit codes shared by the CLI (and reported to MCP/plugin callers as `code`).
EXIT = {"ok": 0, "failed": 1, "bad_input": 2, "missing_dependency": 3, "not_found": 4}

MODES = ("clip", "captions", "reframe", "tighten", "transcript")
ASPECTS = ("9:16", "16:9", "1:1", "4:5", "source")
LAYOUTS = ("auto", "fit", "fill", "split")
CAPTION_POS = ("auto", "top", "middle", "bottom")
PACING = ("tight", "natural")
PLANS = ("auto", "heuristic", "grok")
QUALITY = ("fast", "balanced", "accurate")


def _styles() -> tuple[str, ...]:
    from hermes_studio.captions import STYLES as S

    return tuple(S)


def _filters() -> tuple[str, ...]:
    from hermes_studio.look import FILTERS as F

    return tuple(F)


STYLES = _styles()
FILTERS = _filters()


class HermesStudioError(Exception):
    """A problem the caller can fix. ``code`` is one of EXIT's keys."""

    def __init__(self, message: str, *, code: str = "bad_input", hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code in EXIT else "failed"
        self.hint = hint

    @property
    def exit_code(self) -> int:
        return EXIT[self.code]

    def as_dict(self) -> dict:
        d = {"ok": False, "error": self.message, "code": self.code}
        if self.hint:
            d["hint"] = self.hint
        return d


# --------------------------------------------------------------------------- checks


def _is_url(src: str) -> bool:
    return str(src).startswith(("http://", "https://"))


def check_source(src: str) -> str:
    """Validate a source before any job is created, so a typo never leaves an empty run behind."""
    from hermes_studio.download import MEDIA_EXTS, local_source

    s = str(src or "").strip()
    if not s:
        raise HermesStudioError("No source given.", hint="Pass a video file or an http(s) link.")
    if _is_url(s):
        return s
    if "://" in s:
        raise HermesStudioError(f"Only http(s) links are supported: {s}", hint="Use a https:// link or a local file.")
    try:
        return str(local_source(s))
    except FileNotFoundError:
        raise HermesStudioError(f"File not found: {s}", code="not_found", hint="Check the path. Quote it if it has spaces.") from None
    except ValueError as exc:
        msg = str(exc)
        if "not a video or audio" in msg:
            exts = " ".join(sorted(MEDIA_EXTS))
            raise HermesStudioError(msg[0].upper() + msg[1:] + ".", hint=f"Supported: {exts}") from None
        raise HermesStudioError(
            "That file is outside the folders Hermes Studio may read.",
            hint="Move it into your home folder or a mounted drive, or add its folder to HERMES_STUDIO_MEDIA_ROOTS.",
        ) from None


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HermesStudioError(
            "FFmpeg is not installed (ffmpeg and ffprobe must be on PATH).",
            code="missing_dependency",
            hint="Ubuntu/Debian: sudo apt install ffmpeg · macOS: brew install ffmpeg · or use the desktop app, which has it built in. Then run: hermes-studio doctor",
        )


def _one_of(name: str, value, allowed: tuple) -> None:
    if value not in (None, "") and value not in allowed:
        raise HermesStudioError(f"{name} must be one of: {', '.join(allowed)} (got {value!r}).")


# --------------------------------------------------------------------------- jobs


def _job_summary(job) -> dict:
    d = asdict(job) if not isinstance(job, dict) else dict(job)
    clips = d.get("clips") or []
    return {
        "id": d.get("id"),
        "title": d.get("title"),
        "status": d.get("status"),
        "mode": d.get("mode"),
        "platform": d.get("platform"),
        "clips": len(clips),
        "created_at": d.get("created_at"),
        "dir": d.get("dir"),
        "is_live": d.get("is_live"),
        "error": d.get("error"),
    }


def _clip_rows(job_dict: dict) -> list[dict]:
    root = Path(job_dict.get("dir") or ".")
    rows = []
    for i, c in enumerate(job_dict.get("clips") or [], 1):
        start, end = c.get("start"), c.get("end")
        rows.append(
            {
                "n": i,
                "file": c.get("file"),
                "path": str(root / (c.get("file") or "")),
                "title": c.get("title") or "",
                "start": start,
                "end": end,
                "seconds": round(float(end) - float(start), 1) if start is not None and end is not None else None,
                "score": c.get("score"),
                "virality": c.get("virality"),
                "liked": c.get("liked"),
            }
        )
    return rows


def run(
    src: str,
    *,
    mode: str = "clip",
    out: str | Path | None = None,
    max_clips: int = 3,
    min_sec: float = 12,
    max_sec: float = 45,
    whisper: str = "fast",
    plan: str = "auto",
    pacing: str | None = None,
    style: str = "pop",
    aspect: str | None = None,
    layout: str | None = None,
    captions: bool | None = None,
    hook: bool | None = None,
    prompt: str = "",
    keywords: str = "",
    look: dict | None = None,
    fixes: str = "",
    transcript: str | Path | None = None,
    work: str | Path | None = None,
    live_seconds: int | None = None,
    live_from_start: bool = False,
    recommend: bool = False,
    on_progress: Progress | None = None,
    on_created: Callable[[Any], None] | None = None,
) -> dict:
    """Run one Studio tool on a video or link. Clips land in the library; ``out`` also copies them there."""
    from hermes_studio.download import LIVE_DEFAULT_SEC
    from hermes_studio.pipeline import run_once
    from hermes_studio.tools import tool

    _one_of("mode", mode, MODES)
    _one_of("aspect", aspect, ASPECTS)
    _one_of("layout", layout, LAYOUTS)
    _one_of("style", style, STYLES)
    _one_of("plan", plan, PLANS)
    _one_of("pacing", pacing, PACING)
    if not 1 <= int(max_clips) <= 20:
        raise HermesStudioError("max_clips must be between 1 and 20.")
    if float(min_sec) <= 0 or float(max_sec) <= float(min_sec):
        raise HermesStudioError("Clip length needs 0 < min_sec < max_sec.")
    source = check_source(src)
    require_ffmpeg()

    defaults = (tool(mode) or {}).get("defaults", {})
    kw: dict[str, Any] = dict(
        mode=mode,
        max_clips=int(max_clips),
        min_sec=float(min_sec),
        max_sec=float(max_sec) if mode == "clip" else 1e9,
        whisper=whisper or "fast",
        plan=plan,
        pacing=pacing or defaults.get("pacing", "tight"),
        style=style,
        aspect=aspect or defaults.get("aspect", "9:16"),
        layout=layout or defaults.get("layout", "auto"),
        captions=defaults.get("captions", True) if captions is None else bool(captions),
        hook=defaults.get("hook", True) if hook is None else bool(hook),
        prompt=prompt or "",
        keywords=keywords or "",
        look=look or {},
        fixes=fixes or "",
        transcript=Path(transcript).expanduser() if transcript else None,
        work=Path(work).expanduser().resolve() if work else None,
        live_seconds=int(live_seconds or LIVE_DEFAULT_SEC),
        live_from_start=bool(live_from_start),
    )
    rec = None
    if recommend:
        from hermes_studio.recommend import recommend_for

        _info, r = recommend_for(source)
        rec = r.as_job()
        for k in ("max_clips", "pacing", "style", "plan", "layout", "live_seconds", "min_sec", "max_sec", "hook", "mode", "aspect", "captions"):
            if rec.get(k) is not None:
                kw[k] = rec[k]
        kw["prompt"] = rec.get("prompt") or kw["prompt"]
        kw["keywords"] = rec.get("keywords") or kw["keywords"]
    t0 = time.monotonic()
    out_dir = Path(out).expanduser().resolve() if out else None
    res = run_once(source, out_dir, on_progress=on_progress, on_created=on_created, **kw)
    res["seconds"] = round(time.monotonic() - t0, 1)
    if rec is not None:
        res["recommendation"] = rec
    return res


def library(*, limit: int | None = None, status: str | None = None) -> dict:
    from hermes_studio.pipeline import import_legacy, list_jobs

    import_legacy()
    jobs = [j for j in list_jobs() if not status or j.status == status]
    total = len(jobs)
    if limit:
        jobs = jobs[: int(limit)]
    return {"ok": True, "total": total, "jobs": [_job_summary(j) for j in jobs]}


def show(job_id: str) -> dict:
    from hermes_studio.pipeline import load_job, safe_job_id

    jid = str(job_id or "").strip()
    if not safe_job_id(jid):
        raise HermesStudioError(f"Not a job id: {job_id!r}", hint="Job ids are 12 letters/numbers. Run: hermes-studio list")
    job = load_job(jid)
    if not job:
        raise HermesStudioError(f"No run with id {jid}.", code="not_found", hint="Run: hermes-studio list")
    d = asdict(job)
    return {"ok": True, **_job_summary(job), "source": d.get("src"), "message": d.get("message"), "items": _clip_rows(d),
            "settings": {k: d.get(k) for k in ("aspect", "layout", "style", "pacing", "whisper", "captions", "hook", "prompt", "keywords", "look")}}


def probe_source(src: str) -> dict:
    from hermes_studio.download import probe

    source = check_source(src)
    try:
        info = probe(source)
    except Exception as exc:  # yt-dlp / ffprobe failures
        raise HermesStudioError(f"Could not read that source: {str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else type(exc).__name__}",
                              code="failed", hint="Check the link opens in a browser, or try a local file.") from None
    duration = info.duration
    if duration is None and not _is_url(source):
        try:
            from hermes_studio.render import probe_duration

            duration = round(probe_duration(Path(source)), 2)
        except Exception:
            duration = None
    return {"ok": True, "title": info.title, "is_live": info.is_live, "live_status": info.live_status,
            "duration": duration, "extractor": info.extractor, "id": info.video_id, "source": source}


def recommend(src: str) -> dict:
    from hermes_studio.recommend import recommend_for

    source = check_source(src)
    try:
        info, rec = recommend_for(source)
    except Exception as exc:
        raise HermesStudioError(f"Could not analyse that source: {exc}"[:400], code="failed") from None
    return {"ok": True, "title": info.title, "is_live": info.is_live, "duration": info.duration, "recommendation": rec.as_job()}


def restyle(job_id: str, file: str, *, look: dict | None = None, style: str | None = None, captions: bool | None = None,
            hook: bool | None = None, start: float | None = None, end: float | None = None, fixes: str = "", title: str | None = None) -> dict:
    from hermes_studio.pipeline import restyle_clip

    show(job_id)  # validates id + existence with a helpful error
    _one_of("style", style, STYLES)
    res = restyle_clip(job_id, file, look=look or {}, style=style, captions=captions, hook=hook, start=start, end=end,
                       fixes=fixes, title=title)
    if not res.get("ok"):
        raise HermesStudioError(res.get("error") or "Restyle failed.", code="failed")
    return res


def edit(src: str, op: str = "trim", *, start: float | None = None, end: float | None = None, at: float | None = None,
         out: str | None = None) -> dict:
    from hermes_studio.edit import drop_file, duplicate_file, restore_file, split_file, trim_file

    _one_of("op", op, ("trim", "split", "duplicate", "drop", "restore"))
    path = Path(src).expanduser()
    if op != "restore" and not path.is_file():
        raise HermesStudioError(f"File not found: {src}", code="not_found")
    try:
        if op == "split":
            if at is None:
                raise HermesStudioError("split needs --at (seconds).")
            a, b = split_file(path, float(at))
            return {"ok": True, "op": op, "files": [str(a), str(b)]}
        if op == "duplicate":
            return {"ok": True, "op": op, "file": str(duplicate_file(path, Path(out).expanduser() if out else None))}
        if op == "drop":
            return {"ok": True, "op": op, "file": str(drop_file(path))}
        if op == "restore":
            p, _meta = restore_file(path)
            return {"ok": True, "op": op, "file": str(p)}
        if start is None or end is None:
            raise HermesStudioError("trim needs --start and --end (seconds).")
        dest = Path(out).expanduser() if out else path.with_name(path.stem + "-trim" + path.suffix)
        return {"ok": True, "op": op, "file": str(trim_file(path, dest, float(start), float(end)))}
    except HermesStudioError:
        raise
    except Exception as exc:
        raise HermesStudioError(str(exc).strip()[-600:] or "Edit failed.", code="failed") from None


def name(job_id: str, file: str = "", title: str = "") -> dict:
    from hermes_studio.pipeline import name_job, rename_clip

    show(job_id)
    res = rename_clip(job_id, file, title) if file else name_job(job_id)
    if not res.get("ok"):
        raise HermesStudioError(res.get("error") or "Naming failed.", code="failed")
    return res


def copy(src: str, clip_title: str = "") -> dict:
    import json

    from hermes_studio.copy import copy_from_job_dir, copy_pack
    from hermes_studio.pipeline import job_dir, load_job

    p = Path(str(src)).expanduser()
    if p.is_dir():
        return {"ok": True, **copy_from_job_dir(p, clip_title)}
    if p.name == "transcript.json" and p.is_file():
        text = json.loads(p.read_text()).get("text") or ""
        return {"ok": True, **copy_pack(p.parent.name, text, clip_title)}
    job = load_job(str(src))
    root = Path(job.dir) if job else job_dir(str(src))
    if not root or not Path(root).is_dir():
        raise HermesStudioError(f"Not a run id, run folder or transcript.json: {src}", code="not_found", hint="Run: hermes-studio list")
    return {"ok": True, **copy_from_job_dir(Path(root), clip_title)}


def transcribe_only(src: str, *, work: str | None = None, whisper: str = "fast") -> dict:
    import tempfile

    from hermes_studio.download import fetch
    from hermes_studio.pipeline import whisper_model
    from hermes_studio.transcribe import transcribe

    source = check_source(src)
    require_ffmpeg()
    wd = Path(work).expanduser().resolve() if work else Path(tempfile.mkdtemp(prefix="hermes-studio-"))
    wd.mkdir(parents=True, exist_ok=True)
    video = fetch(source, wd)
    tr = transcribe(video, wd, model_size=whisper_model(whisper))
    return {"ok": True, "transcript": str(wd / "transcript.json"), "words": len(tr.words), "duration": tr.duration}


def tools() -> dict:
    from hermes_studio.tools import catalogue

    return {"ok": True, **catalogue(), "styles": list(STYLES), "filters": list(FILTERS), "aspects": list(ASPECTS)}


# --------------------------------------------------------------------------- doctor


def _whisper_cached(model: str = "tiny") -> bool:
    homes = [os.environ.get("HF_HUB_CACHE"), os.environ.get("HF_HOME") and os.path.join(os.environ["HF_HOME"], "hub"),
             os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")]
    return any(h and os.path.isdir(os.path.join(h, f"models--Systran--faster-whisper-{model}")) for h in homes)


def doctor() -> dict:
    """Check everything Hermes Studio needs. Required checks decide ``ok``."""
    from importlib import metadata

    checks: list[dict] = []

    def add(cid: str, name_: str, ok: bool, detail: str, fix: str = "", required: bool = True) -> None:
        checks.append({"id": cid, "name": name_, "ok": bool(ok), "required": required, "detail": detail, "fix": "" if ok else fix})

    def ver(pkg: str) -> str | None:
        try:
            return metadata.version(pkg)
        except metadata.PackageNotFoundError:
            return None

    add("python", "Python", sys.version_info >= (3, 11), sys.version.split()[0], "Install Python 3.11 or newer.")

    ff = shutil.which("ffmpeg")
    libass = False
    if ff:
        try:
            out = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
            libass = any(line.split()[1:2] == ["ass"] for line in out.splitlines() if line.strip())
        except Exception:
            libass = False
    add("ffmpeg", "FFmpeg", bool(ff), ff or "not found", "Ubuntu/Debian: sudo apt install ffmpeg · macOS: brew install ffmpeg")
    add("ffprobe", "FFprobe", bool(shutil.which("ffprobe")), shutil.which("ffprobe") or "not found", "Comes with FFmpeg.")
    if ff:
        add("libass", "Caption burn-in (libass)", libass, "ass filter present" if libass else "ass filter missing",
            "Your FFmpeg was built without libass. Install a full build (apt ffmpeg, brew ffmpeg, or a BtbN static build).")

    try:
        from hermes_studio.download import _ytdlp

        cmd = _ytdlp()
        add("ytdlp", "yt-dlp (links)", True, f"{ver('yt-dlp') or '?'} via {' '.join(Path(c).name for c in cmd)}")
    except Exception as exc:
        add("ytdlp", "yt-dlp (links)", False, str(exc), "pip install yt-dlp (needed for YouTube/X/Twitch links; local files work without it)", required=False)

    fw = ver("faster-whisper")
    add("whisper", "Speech (faster-whisper)", bool(fw), fw or "not installed", "pip install faster-whisper")
    av = ver("av")
    av_ok = bool(av) and int((av or "0").split(".")[0]) < 19
    add("av", "Audio decode (PyAV)", av_ok, av or "not installed", "pip install 'av<19' (PyAV 19 breaks faster-whisper 1.2).")
    cached = _whisper_cached("tiny")
    add("model", "Speech model (fast)", True, "downloaded" if cached else "downloads on first run (~75 MB), then works offline", required=False)
    cv = ver("opencv-python-headless") or ver("opencv-python")
    add("opencv", "Face framing (OpenCV)", bool(cv), cv or "not installed", "pip install 'hermes-studio[reframe]' (without it, Speaker/Split framing falls back to Classic)", required=False)

    try:
        from hermes_studio.pipeline import library_root

        root = library_root()
        probe_file = root / ".write-test"
        probe_file.write_text("ok")
        probe_file.unlink()
        add("library", "Library folder", True, str(root))
    except Exception as exc:
        from hermes_studio.pipeline import library_root as _lib

        try:
            where = str(_lib())
        except Exception:
            where = "the clips library folder"
        add("library", "Library folder", False, str(exc), f"Make {where} writable, or set HERMES_HOME to a writable folder.")

    namer = os.environ.get("HERMES_STUDIO_NAMER", "ollama").strip().lower() or "ollama"
    if namer == "off":
        add("namer", "AI clip titles", True, "off (offline titles from the transcript)", required=False)
    elif namer == "ollama":
        from hermes_studio import net

        url = os.environ.get("HERMES_STUDIO_NAMER_URL", "http://127.0.0.1:11434").rstrip("/")
        try:
            net.get_json(url + "/api/tags", timeout=1.5)
            add("namer", "AI clip titles", True, f"Ollama at {url}", required=False)
        except Exception:
            add("namer", "AI clip titles", False, f"Ollama not reachable at {url}; titles fall back to the transcript",
                "Optional: install Ollama and run `ollama pull qwen3.5:9b`, or set HERMES_STUDIO_NAMER=off to silence this.", required=False)
    else:
        add("namer", "AI clip titles", bool(os.environ.get("HERMES_STUDIO_NAMER_URL")), f"{namer} endpoint",
            "Set HERMES_STUDIO_NAMER_URL (and _KEY) for an OpenAI-compatible endpoint.", required=False)

    ok = all(c["ok"] for c in checks if c["required"])
    return {"ok": ok, "version": __version__, "python": sys.executable, "checks": checks}


# --------------------------------------------------------------------------- design + photo


def _design_call(fn, *args, **kw) -> dict:
    from hermes_studio.design import DesignError
    from hermes_studio.photo import PhotoError

    try:
        return fn(*args, **kw)
    except (DesignError, PhotoError) as exc:
        msg = str(exc)
        code = "not_found" if msg.startswith("no ") else "missing_dependency" if "OpenCV" in msg else "bad_input"
        raise HermesStudioError(msg, code=code, hint="hermes-studio design --help") from None


def design_new(title: str = "", size: str = "tiktok-carousel", template: str = "blank",
               w: int | None = None, h: int | None = None) -> dict:
    from hermes_studio import design

    doc = _design_call(design.create, title, size, template, w, h)
    return {"ok": True, "id": doc["id"], "design": doc, "folder": str(design.design_dir(doc["id"]))}


def design_list() -> dict:
    from hermes_studio import design

    return {"ok": True, "designs": design.list_designs()}


def design_show(design_id: str) -> dict:
    from hermes_studio import design

    doc = _design_call(design.load, design_id)
    return {"ok": True, "id": design_id, "design": doc, "folder": str(design.design_dir(design_id))}


def design_edit(design_id: str, ops: list[dict]) -> dict:
    from hermes_studio import design

    doc = _design_call(design.apply_ops, design_id, ops)
    return {"ok": True, "id": design_id, "design": doc}


def design_render(design_id: str, pages: list[int] | None = None, fmt: str = "png") -> dict:
    from hermes_studio import design

    return _design_call(design.render, design_id, pages=pages, fmt=fmt)


def design_options() -> dict:
    from hermes_studio import design, photo

    return {"ok": True, "sizes": {k: {"w": w, "h": h, "label": lab} for k, (w, h, lab) in design.SIZES.items()},
            "templates": design.templates(), "fonts": {k: v[1] for k, v in design.FONTS.items()},
            "layer_types": list(design.LAYER_TYPES), "looks": list(photo.LOOKS)}


def photo_edit(op: str, src: str, out: str = "", look: str = "", strength: float = 1.0) -> dict:
    from hermes_studio import photo

    return _design_call(photo.run_file, op, src, out, look_name=look, strength=strength)


def design_resize(design_id: str, size: str = "", w: int | None = None, h: int | None = None) -> dict:
    from hermes_studio import design

    doc = _design_call(design.resize, design_id, size, w, h)
    return {"ok": True, "id": doc["id"], "design": doc, "from": design_id}
