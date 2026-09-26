from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from hermesclip.download import LIVE_DEFAULT_SEC, SourceInfo, fetch, probe
from hermesclip.layout import canvas, even, probe_size
from hermesclip.plan import ClipPlan, plan_grok, plan_heuristic, save_plan
from hermesclip.render import probe_duration, render_clip
from hermesclip.transcribe import Transcript, Word, load_transcript, transcribe

Progress = Callable[[str, float, str], None]


MODES = ("clip", "captions", "reframe", "tighten", "transcript")
WHISPER_PRESETS = {"fast": "tiny", "balanced": "base.en", "accurate": "small.en"}


def whisper_model(value: str) -> str:
    """Map a quality preset (fast/balanced/accurate) or raw model name to a faster-whisper model."""
    v = (value or "tiny").strip()
    return WHISPER_PRESETS.get(v, v)


def library_root() -> Path:
    p = Path.home() / ".hermes" / "clips" / "library"
    p.mkdir(parents=True, exist_ok=True)
    return p


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ClipItem:
    file: str
    title: str
    start: float
    end: float
    score: float
    thumb: str = ""


@dataclass
class Job:
    id: str
    src: str
    title: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    created_at: str = ""
    finished_at: str | None = None
    is_live: bool = False
    live_status: str | None = None
    extractor: str = ""
    platform: str = ""
    layout: str = "fit"
    style: str = "pop"
    pacing: str = "tight"
    plan: str = "heuristic"
    whisper: str = "tiny"
    max_clips: int = 3
    live_seconds: int = 1200
    live_from_start: bool = False
    aspect: str = "9:16"
    captions: bool = True
    min_sec: float = 12.0
    max_sec: float = 45.0
    start_time: float | None = None
    end_time: float | None = None
    prompt: str = ""
    hook: bool = True
    mode: str = "clip"
    keywords: str = ""
    clips: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    work: str = ""
    dir: str = ""

    def path(self) -> Path:
        return Path(self.dir)

    def save(self) -> None:
        dest = self.path()
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "job.json").write_text(json.dumps(asdict(self), indent=2))


def job_from_dict(data: dict) -> Job:
    clips = data.get("clips") or []
    return Job(**{k: v for k, v in data.items() if k in Job.__dataclass_fields__} | {"clips": clips})


def _manifests() -> list[Path]:
    """job.json files: <library>/<Platform>/<Title [id]>/ and legacy flat <library>/<id>/."""
    root = library_root()
    out = list(root.glob("*/job.json")) + list(root.glob("*/*/job.json"))
    return [m for m in out if ".trash" not in m.parts]


def job_dir(job_id: str) -> Path | None:
    """Folder for a job id, wherever it lives in the library."""
    if not job_id or "/" in job_id or "\\" in job_id or job_id.startswith("."):
        return None
    root = library_root()
    flat = root / job_id
    if (flat / "job.json").is_file():
        return flat
    for m in root.glob(f"*/*[[]{job_id}[]]/job.json"):
        return m.parent
    for m in _manifests():
        try:
            if json.loads(m.read_text()).get("id") == job_id:
                return m.parent
        except Exception:
            continue
    return None


def load_job(job_id: str) -> Job | None:
    d = job_dir(job_id)
    if not d:
        return None
    job = job_from_dict(json.loads((d / "job.json").read_text()))
    if Path(job.dir) != d:  # folder moved: trust where it is now
        job.dir = str(d)
    return job


def list_jobs() -> list[Job]:
    rows: list[Job] = []
    for man in _manifests():
        try:
            job = job_from_dict(json.loads(man.read_text()))
        except Exception:
            continue
        job.dir = str(man.parent)
        if not job.platform:
            from hermesclip.folders import platform_of

            job.platform = platform_of(job.src, job.extractor)
        rows.append(job)
    rows.sort(key=lambda j: j.created_at, reverse=True)
    return rows


def organize_library() -> list[dict]:
    """Move every run into <Platform>/<Clear Title [id]>/. Fills missing titles. Idempotent."""
    from hermesclip.folders import folder_name, platform_of, pretty_title, youtube_id, youtube_title

    root = library_root()
    moved: list[dict] = []
    for man in _manifests():
        d = man.parent
        try:
            data = json.loads(man.read_text())
        except Exception:
            continue
        job = job_from_dict(data)
        if job.status in ("queued", "running"):
            continue
        plat = job.platform or platform_of(job.src, job.extractor)
        title = job.title
        title = pretty_title(title, job.src)
        if plat == "YouTube":
            yid = youtube_id(job.src, job.title) or youtube_id("", job.id)
            if yid and (yid in title or not title or title == job.id):
                title = youtube_title(yid) or title
        dest = root / plat / folder_name(title, job.id)
        job.platform, job.title = plat, title
        if d.resolve() != dest.resolve():
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            old = str(d)
            shutil.move(str(d), str(dest))
            if job.work.startswith(old):
                job.work = str(dest) + job.work[len(old):]
            moved.append({"id": job.id, "from": d.name, "to": f"{plat}/{dest.name}"})
        job.dir = str(dest)
        job.save()
    for child in root.iterdir():  # drop empty platform folders
        if child.is_dir() and not any(child.iterdir()):
            child.rmdir()
    return moved


def import_legacy() -> int:
    """Fold older clip folders under ~/.hermes/clips into the library."""
    base = Path.home() / ".hermes" / "clips"
    n = 0
    if not base.is_dir():
        return 0
    for child in base.iterdir():
        if not child.is_dir() or child.name == "library":
            continue
        man = child / "manifest.json"
        if not man.is_file():
            continue
        job_id = child.name
        if job_dir(job_id):
            continue
        dest = library_root() / job_id
        try:
            data = json.loads(man.read_text())
        except Exception:
            continue
        clips = []
        for i, p in enumerate(data.get("clips") or [], 1):
            clips.append(
                {
                    "file": Path(p).name if isinstance(p, str) else f"clip-{i:02d}.mp4",
                    "title": f"Clip {i:02d}",
                    "start": 0,
                    "end": 0,
                    "score": 0,
                    "thumb": "",
                }
            )
        dest.mkdir(parents=True, exist_ok=True)
        for clip in child.glob("clip-*.mp4"):
            target = dest / clip.name
            if not target.exists():
                shutil.copy2(clip, target)
            jpg = dest / (clip.stem + ".jpg")
            if not jpg.exists():
                name = _thumb(target, jpg)
                for item in clips:
                    if item["file"] == clip.name:
                        item["thumb"] = name
        job = Job(
            id=job_id,
            src=str(data.get("source") or ""),
            title=job_id,
            status="completed",
            stage="done",
            progress=1.0,
            message="Imported",
            created_at=utcnow(),
            finished_at=utcnow(),
            clips=clips,
            work=str(data.get("work") or ""),
            dir=str(dest),
        )
        job.save()
        n += 1
    return n


def new_job(
    src: str,
    *,
    max_clips: int = 3,
    whisper: str = "tiny",
    pacing: str = "tight",
    style: str = "pop",
    plan: str = "heuristic",
    layout: str = "fit",
    live_seconds: int = LIVE_DEFAULT_SEC,
    live_from_start: bool = False,
    aspect: str = "9:16",
    captions: bool = True,
    min_sec: float = 12.0,
    max_sec: float = 45.0,
    start_time: float | None = None,
    end_time: float | None = None,
    prompt: str = "",
    hook: bool = True,
    mode: str = "clip",
    keywords: str = "",
) -> Job:
    info: SourceInfo | None = None
    title = src
    is_live = False
    live_status = None
    extractor = ""
    try:
        info = probe(src)
        title = info.title
        is_live = info.is_live
        live_status = info.live_status
        extractor = info.extractor
    except Exception:
        info = None
    from hermesclip.folders import folder_name, platform_of, pretty_title, youtube_title, youtube_id

    job_id = uuid.uuid4().hex[:12]
    platform = platform_of(src, extractor)
    title = pretty_title(title, src)
    if platform == "YouTube":
        yid = youtube_id(src, title)
        if yid and (yid in title or not title):
            title = youtube_title(yid) or title
    dest = library_root() / platform / folder_name(title, job_id)
    dest.mkdir(parents=True, exist_ok=True)
    job = Job(
        id=job_id,
        src=src,
        title=title,
        status="queued",
        stage="queued",
        created_at=utcnow(),
        is_live=is_live,
        live_status=live_status,
        extractor=extractor,
        platform=platform,
        layout=layout,
        style=style,
        pacing=pacing,
        plan=plan,
        whisper=whisper_model(whisper),
        max_clips=max_clips,
        live_seconds=live_seconds,
        live_from_start=live_from_start,
        aspect=aspect if aspect in ("9:16", "16:9", "1:1", "4:5", "source") else "9:16",
        captions=bool(captions),
        min_sec=float(min_sec),
        max_sec=float(max_sec),
        start_time=start_time,
        end_time=end_time,
        prompt=prompt or "",
        hook=bool(hook),
        mode=mode if mode in MODES else "clip",
        keywords=keywords or "",
        dir=str(dest),
        work=str(dest / "work"),
    )
    job.save()
    job._info = info  # type: ignore[attr-defined]
    return job


def _thumb(clip: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "1",
            "-i",
            str(clip),
            "-frames:v",
            "1",
            "-vf",
            "scale=360:-2",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    return dest.name if proc.returncode == 0 and dest.is_file() else ""


def _finish(job: Job, clips: list[dict], message: str) -> Job:
    job.clips = clips
    job.status = "completed"
    job.stage = "done"
    job.progress = 1.0
    job.message = message
    job.finished_at = utcnow()
    job.save()
    return job


def execute_job(job: Job, on_progress: Progress | None = None) -> Job:
    def bump(stage: str, pct: float, msg: str) -> None:
        job.stage = stage
        job.progress = max(0.0, min(1.0, pct))
        job.message = msg
        job.status = "running"
        job.save()
        if on_progress:
            on_progress(stage, job.progress, msg)

    out_dir = job.path()
    work = Path(job.work) if job.work else out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    live_seconds = int(job.live_seconds or LIVE_DEFAULT_SEC)
    live_from_start = bool(job.live_from_start)
    info = getattr(job, "_info", None)

    try:
        bump("download", 0.05, "Fetching source")
        video = fetch(
            job.src,
            work,
            live_seconds=live_seconds,
            live_from_start=live_from_start,
            info=info,
        )
        bump("transcribe", 0.25, f"Whisper ({job.whisper})")
        tr = transcribe(video, work, model_size=job.whisper)
        if job.start_time is not None or job.end_time is not None:
            lo = float(job.start_time or 0.0)
            hi = float(job.end_time) if job.end_time is not None else 1e9
            tr.words = [w for w in tr.words if w.end >= lo and w.start <= hi]
        if not tr.words:
            dur = probe_duration(video)
            lo = float(job.start_time or 0.0)
            hi = min(dur, float(job.end_time) if job.end_time is not None else min(dur, lo + job.max_sec))
            tr = Transcript("en", dur, "", [Word("…", lo, hi)])

        width, height = canvas(job.aspect)
        layout = job.layout if job.layout in ("fit", "fill") else "fit"
        style = job.style if job.captions else "clean"

        from hermesclip.export import write_exports

        job.files = write_exports(tr, out_dir)
        job.save()

        if job.mode == "transcript":
            bump("export", 0.9, "Transcript files")
            return _finish(job, [], f"{len(job.files)} files")

        if job.mode in ("reframe", "tighten"):
            dur = probe_duration(video)
            lo = float(job.start_time or 0.0)
            hi = float(job.end_time or dur)
            label = "Reframe" if job.mode == "reframe" else "Tighten"
            bump("render", 0.6, label)
            plan = ClipPlan(lo, hi, job.title[:60], [], 0.5)
            if job.mode == "reframe":
                w_, h_, pace = width, height, "natural"
            else:
                # Tighten keeps the source frame unless a canvas was picked.
                if job.aspect == "source":
                    sw, sh = probe_size(video)
                    w_, h_ = even(sw), even(sh)
                else:
                    w_, h_ = width, height
                pace = "tight"
            dest = out_dir / f"{job.mode}.mp4"
            render_clip(
                video, plan, tr, dest, work,
                width=w_, height=h_, pacing=pace, style=style, layout=layout,
                hook="", captions=job.captions,
            )
            thumb = _thumb(dest, out_dir / f"{job.mode}.jpg")
            out_len = probe_duration(dest)
            row = {"file": dest.name, "title": label, "start": lo, "end": hi, "score": 1.0, "virality": 0, "thumb": thumb}
            msg = label
            if job.mode == "tighten":
                saved = max(0.0, (hi - lo) - out_len)
                row["saved"] = round(saved, 1)
                msg = f"Tightened · {saved:.0f}s cut"
            return _finish(job, [row], msg)

        if job.mode == "captions":
            bump("render", 0.6, "Captions only")
            dur = probe_duration(video)
            from hermesclip.captions import parse_keywords

            keys = parse_keywords(job.keywords, job.prompt)
            plan = ClipPlan(float(job.start_time or 0.0), float(job.end_time or dur), job.title[:60], keys, 0.5)
            dest = out_dir / "captions.mp4"
            render_clip(
                video, plan, tr, dest, work,
                width=width, height=height, pacing="natural", style=style, layout=layout,
                hook=plan.title if job.hook else "",
            )
            thumb = _thumb(dest, out_dir / "captions.jpg")
            job.clips = [{"file": dest.name, "title": "Captions", "start": plan.start, "end": plan.end, "score": 1.0, "virality": 0, "thumb": thumb}]
            job.status = "completed"
            job.stage = "done"
            job.progress = 1.0
            job.message = "captions"
            job.finished_at = utcnow()
            job.save()
            return job

        bump("plan", 0.55, "Scoring hook-first windows")
        min_sec = float(job.min_sec or 12.0)
        max_sec = float(job.max_sec or 45.0)
        plans = None
        if job.plan in ("auto", "grok"):
            plans = plan_grok(tr, job.max_clips, min_sec, max_sec)
        if not plans:
            plans = plan_heuristic(tr, job.max_clips, min_sec, max_sec)
        if job.prompt:
            keys = [k for k in job.prompt.lower().replace(",", " ").split() if len(k) > 2]
            for item in plans:
                blob = (item.title or "").lower()
                hits = sum(1 for k in keys if k in blob)
                item.score = min(1.0, item.score + 0.1 * hits)
            plans.sort(key=lambda x: x.score, reverse=True)
        from hermesclip.captions import parse_keywords

        extra = parse_keywords(job.keywords, job.prompt)
        if extra:
            for item in plans:
                have = {e.lower() for e in item.emphasis}
                for w in extra:
                    if w not in have:
                        item.emphasis.append(w)
                        have.add(w)
        if os.environ.get("HERMESCLIP_NAMER", "ollama").lower() != "off":
            bump("name", 0.58, "Naming clips")
            from hermesclip.namer import ai_titles, clip_text

            names, _src = ai_titles([clip_text(tr, pl.start, pl.end) for pl in plans], job.title)
            for pl, nm in zip(plans, names):
                if nm:
                    pl.title = nm
        save_plan(plans, work / "plan.json")

        width, height = canvas(job.aspect)
        layout = job.layout if job.layout in ("fit", "fill") else "fit"
        style = job.style if job.captions else "clean"
        written: list[dict] = []
        n = max(len(plans), 1)
        for i, plan in enumerate(plans, 1):
            bump("render", 0.6 + 0.35 * (i - 1) / n, f"Render clip {i:02d}")
            dest = out_dir / f"clip-{i:02d}.mp4"
            render_clip(
                video,
                plan,
                tr,
                dest,
                work,
                width=width,
                height=height,
                pacing=job.pacing,
                style=style,
                layout=layout,
                hook=plan.title if job.hook else "",
                captions=job.captions,
            )
            thumb = _thumb(dest, out_dir / f"clip-{i:02d}.jpg")
            written.append(
                {
                    "file": dest.name,
                    "title": plan.title,
                    "start": plan.start,
                    "end": plan.end,
                    "score": plan.score,
                    "virality": int(round(plan.score * 100)),
                    "thumb": thumb,
                }
            )
        job.clips = written
        job.status = "completed"
        job.stage = "done"
        job.progress = 1.0
        job.message = f"{len(written)} clips"
        job.finished_at = utcnow()
        job.save()
        (out_dir / "manifest.json").write_text(
            json.dumps({"source": str(video), "clips": [c["file"] for c in written], "work": str(work)}, indent=2)
        )
        return job
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[-2000:]
        job.message = "Failed"
        job.finished_at = utcnow()
        job.save()
        raise


def run_once(
    src: str,
    out_dir: Path,
    *,
    max_clips: int = 3,
    whisper: str = "tiny",
    pacing: str = "tight",
    style: str = "pop",
    plan: str = "heuristic",
    layout: str = "fit",
    work: Path | None = None,
    live_seconds: int = LIVE_DEFAULT_SEC,
    live_from_start: bool = False,
    transcript: Path | None = None,
    on_progress: Progress | None = None,
    min_sec: float = 12.0,
    max_sec: float = 45.0,
    prompt: str = "",
    hook: bool = True,
    mode: str = "clip",
    aspect: str = "9:16",
    captions: bool = True,
    keywords: str = "",
) -> dict:
    """CLI-shaped run. Writes clips into out_dir (not necessarily the library)."""
    job = new_job(
        src,
        max_clips=max_clips,
        whisper=whisper,
        pacing=pacing,
        style=style,
        plan=plan,
        layout=layout,
        live_seconds=live_seconds,
        live_from_start=live_from_start,
        aspect=aspect,
        captions=captions if mode != "captions" else True,
        min_sec=min_sec,
        max_sec=max_sec,
        prompt=prompt,
        hook=hook,
        mode=mode,
        keywords=keywords,
    )
    if work:
        job.work = str(work)
        job.save()
    job = execute_job(job, on_progress=on_progress)
    dest = Path(job.dir)
    files = [str(dest / c["file"]) for c in job.clips] + [str(dest / f["file"]) for f in (job.files or [])]
    if out_dir.resolve() != dest.resolve():
        out_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        for p in files:
            srcp = Path(p)
            if srcp.is_file():
                target = out_dir / srcp.name
                shutil.copy2(srcp, target)
                copied.append(str(target))
        files = copied or files
    return {
        "ok": job.status == "completed",
        "source": job.src,
        "clips": files,
        "work": job.work,
        "title": job.title,
        "mode": job.mode,
        "message": job.message,
        "error": job.error,
    }


def name_job(job_id: str) -> dict:
    """AI-name every clip in an existing run from its transcript. Returns {ok, titles, source}."""
    from hermesclip.namer import ai_titles, clip_text
    from hermesclip.transcribe import load_transcript

    job = load_job(job_id)
    if not job:
        return {"ok": False, "error": "job not found"}
    clips = list(job.clips or [])
    if not clips:
        return {"ok": False, "error": "no clips to name"}
    from hermesclip.transcribe import transcribe

    tpath = Path(job.dir) / "work" / "transcript.json"
    tr = load_transcript(tpath) if tpath.is_file() else None
    texts: list[str] = []
    for c in clips:
        start, end = float(c.get("start") or 0), float(c.get("end") or 0)
        text = clip_text(tr, start, end) if tr and end > start else ""
        if not text:
            # No run transcript (imported/old run): listen to the clip file itself.
            media = Path(job.dir) / str(c.get("file") or "")
            if media.is_file():
                cw = Path(job.dir) / "work" / "names" / media.stem
                cw.mkdir(parents=True, exist_ok=True)
                try:
                    text = transcribe(media, cw, whisper_model(job.whisper or "fast")).text
                except Exception:
                    text = ""
        texts.append(text)
    if not any(texts):
        return {"ok": False, "error": "no words found in these clips"}
    names, src = ai_titles(texts, job.title)
    for c, nm in zip(clips, names):
        if nm:
            c["title"] = nm
    job.clips = clips
    job.save()
    return {"ok": True, "titles": names, "source": src}


def rename_clip(job_id: str, file: str, title: str) -> dict:
    from hermesclip.namer import clean

    job = load_job(job_id)
    if not job:
        return {"ok": False, "error": "job not found"}
    t = clean(title)
    if not t:
        return {"ok": False, "error": "title is empty"}
    hit = False
    for c in job.clips or []:
        if c.get("file") == file:
            c["title"] = t
            hit = True
    if not hit:
        return {"ok": False, "error": "clip not in run"}
    job.save()
    return {"ok": True, "file": file, "title": t}
