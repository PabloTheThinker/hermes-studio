from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from hermesclip.download import LIVE_DEFAULT_SEC, SourceInfo, fetch, probe
from hermesclip.plan import plan_grok, plan_heuristic, save_plan
from hermesclip.render import probe_duration, render_clip
from hermesclip.transcribe import Transcript, Word, load_transcript, transcribe

Progress = Callable[[str, float, str], None]


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
    layout: str = "fit"
    style: str = "pop"
    pacing: str = "tight"
    plan: str = "heuristic"
    whisper: str = "tiny"
    max_clips: int = 3
    live_seconds: int = 1200
    live_from_start: bool = False
    clips: list[dict] = field(default_factory=list)
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


def load_job(job_id: str) -> Job | None:
    path = library_root() / job_id / "job.json"
    if not path.is_file():
        return None
    return job_from_dict(json.loads(path.read_text()))


def list_jobs() -> list[Job]:
    rows: list[Job] = []
    root = library_root()
    for child in root.iterdir():
        man = child / "job.json"
        if not man.is_file():
            continue
        try:
            rows.append(job_from_dict(json.loads(man.read_text())))
        except Exception:
            continue
    rows.sort(key=lambda j: j.created_at, reverse=True)
    return rows


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
        dest = library_root() / job_id
        if (dest / "job.json").is_file():
            continue
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
    job_id = uuid.uuid4().hex[:12]
    dest = library_root() / job_id
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
        layout=layout,
        style=style,
        pacing=pacing,
        plan=plan,
        whisper=whisper,
        max_clips=max_clips,
        live_seconds=live_seconds,
        live_from_start=live_from_start,
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
        if not tr.words:
            dur = probe_duration(video)
            tr = Transcript("en", dur, "", [Word("…", 0.0, min(dur, 45.0))])

        bump("plan", 0.55, "Scoring hook-first windows")
        plans = None
        if job.plan in ("auto", "grok"):
            plans = plan_grok(tr, job.max_clips, 12.0, 45.0)
        if not plans:
            plans = plan_heuristic(tr, job.max_clips, 12.0, 45.0)
        save_plan(plans, work / "plan.json")

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
                pacing=job.pacing,
                style=job.style,
                layout=job.layout,
            )
            thumb = _thumb(dest, out_dir / f"clip-{i:02d}.jpg")
            written.append(
                {
                    "file": dest.name,
                    "title": plan.title,
                    "start": plan.start,
                    "end": plan.end,
                    "score": plan.score,
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
) -> dict:
    """CLI-shaped run. Writes clips into out_dir (not necessarily the library)."""
    work = work or Path(tempfile.mkdtemp(prefix="hermesclip-"))
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    def bump(stage: str, pct: float, msg: str) -> None:
        if on_progress:
            on_progress(stage, pct, msg)

    bump("download", 0.05, "Fetching source")
    info = None
    try:
        info = probe(src)
    except Exception:
        info = None
    video = fetch(
        src,
        work,
        live_seconds=live_seconds,
        live_from_start=live_from_start,
        info=info,
    )
    if transcript:
        tr = load_transcript(transcript)
    else:
        bump("transcribe", 0.25, f"Whisper ({whisper})")
        tr = transcribe(video, work, model_size=whisper)
        if not tr.words:
            dur = probe_duration(video)
            tr = Transcript("en", dur, "", [Word("…", 0.0, min(dur, 45.0))])
    bump("plan", 0.55, "Scoring windows")
    plans = None
    if plan in ("auto", "grok"):
        plans = plan_grok(tr, max_clips, 12.0, 45.0)
    if not plans:
        plans = plan_heuristic(tr, max_clips, 12.0, 45.0)
    save_plan(plans, work / "plan.json")
    written = []
    n = max(len(plans), 1)
    for i, item in enumerate(plans, 1):
        bump("render", 0.6 + 0.35 * (i - 1) / n, f"Render clip {i:02d}")
        dest = out_dir / f"clip-{i:02d}.mp4"
        render_clip(video, item, tr, dest, work, pacing=pacing, style=style, layout=layout)
        written.append(str(dest))
    (out_dir / "manifest.json").write_text(
        json.dumps({"source": str(video), "clips": written, "work": str(work)}, indent=2)
    )
    bump("done", 1.0, "done")
    return {"source": str(video), "clips": written, "work": str(work), "title": (info.title if info else src)}
