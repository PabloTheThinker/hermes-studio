from __future__ import annotations

import json
import subprocess
from pathlib import Path


def trim_file(src: Path, dest: Path, start: float, end: float, *, overwrite: bool = False) -> Path:
    """Local analog of Opus edit_clip trim. Re-encodes so cuts land cleanly. Does not post.

    An existing ``dest`` is refused unless ``overwrite`` (the desk re-trims its own clip copy)."""
    from hermes_studio.guard import PathRefused

    src = Path(src).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if end <= start:
        raise ValueError("end must be after start")
    if not overwrite and (dest.exists() or dest.is_symlink()):
        raise PathRefused(f"refusing to overwrite an existing file: {dest.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dest.is_file():
        raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg failed")[-1500:])
    return dest


def split_file(src: Path, at: float, dest_a: Path | None = None, dest_b: Path | None = None) -> tuple[Path, Path]:
    """Local analog of Opus edit_clip split. Does not post."""
    from hermes_studio.render import probe_duration

    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dur = probe_duration(src)
    if at <= 0.2 or at >= dur - 0.2:
        raise ValueError("split point must sit inside the clip")
    from hermes_studio.guard import default_out_file, out_file

    dest_a = out_file(dest_a) if dest_a else default_out_file(src, "-a")
    dest_b = out_file(dest_b) if dest_b else default_out_file(src, "-b")
    a = trim_file(src, dest_a, 0.0, at)
    b = trim_file(src, dest_b, at, dur)
    return a, b


def duplicate_file(src: Path, dest: Path | None = None) -> Path:
    """Safe copy to edit. Opus duplicate_clip analog. Does not post.

    ``src`` must be a video/audio file under a media root (``local_source``); ``dest`` must be a
    media file inside the Studio folder that does not exist yet (created exclusively, never
    overwritten). The default lands next to a Studio clip, else in ``<studio>/edits``."""
    import shutil

    from hermes_studio.download import MEDIA_EXTS, local_source
    from hermes_studio.guard import default_out_file, out_file

    src = local_source(str(src))
    dest = out_file(dest, MEDIA_EXTS) if dest else default_out_file(src, "-copy")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as r, open(dest, "xb") as w:  # "x": fail if it appeared meanwhile
        shutil.copyfileobj(r, w)
    shutil.copystat(src, dest)
    return dest


def drop_file(src: Path, meta: dict | None = None) -> Path:
    """Move a clip aside. Does not post. Recoverable trash in the job folder."""
    import json

    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    trash = src.parent / ".trash"
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / src.name
    n = 1
    while dest.exists():
        dest = trash / f"{src.stem}-{n}{src.suffix}"
        n += 1
    src.rename(dest)
    if meta is not None:
        dest.with_name(dest.name + ".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
    return dest


def restore_file(src: Path, dest: Path | None = None) -> tuple[Path, dict]:
    """Undo drop. Opus restore analog. Does not post."""
    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if src.parent.name != ".trash":
        raise ValueError("restore only from .trash")
    dest = Path(dest).expanduser().resolve() if dest else src.parent.parent / src.name
    if dest.exists():
        dest = dest.with_name(src.stem + "-restored" + src.suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    side = src.with_name(src.name + ".meta.json")
    meta: dict = {}
    if side.is_file():
        try:
            loaded = json.loads(side.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except Exception:
            meta = {}
    src.rename(dest)
    if side.is_file():
        side.unlink()
    return dest, meta


def list_trash(job_dir: Path) -> list[dict]:
    trash = Path(job_dir).expanduser() / ".trash"
    if not trash.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(trash.iterdir()):
        if not p.is_file() or p.name.endswith(".meta.json"):
            continue
        if p.suffix.lower() != ".mp4":
            continue
        out.append({"file": p.name})
    return out
