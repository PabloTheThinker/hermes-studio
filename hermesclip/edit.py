from __future__ import annotations

import json
import subprocess
from pathlib import Path


def trim_file(src: Path, dest: Path, start: float, end: float) -> Path:
    """Local analog of Opus edit_clip trim. Re-encodes so cuts land cleanly. Does not post."""
    src = Path(src).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    if end <= start:
        raise ValueError("end must be after start")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
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
    from hermesclip.render import probe_duration

    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dur = probe_duration(src)
    if at <= 0.2 or at >= dur - 0.2:
        raise ValueError("split point must sit inside the clip")
    dest_a = Path(dest_a).expanduser().resolve() if dest_a else src.with_name(src.stem + "-a" + src.suffix)
    dest_b = Path(dest_b).expanduser().resolve() if dest_b else src.with_name(src.stem + "-b" + src.suffix)
    a = trim_file(src, dest_a, 0.0, at)
    b = trim_file(src, dest_b, at, dur)
    return a, b


def duplicate_file(src: Path, dest: Path | None = None) -> Path:
    """Safe copy to edit. Opus duplicate_clip analog. Does not post."""
    import shutil

    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(str(src))
    dest = Path(dest).expanduser().resolve() if dest else src.with_name(src.stem + "-copy" + src.suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
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
