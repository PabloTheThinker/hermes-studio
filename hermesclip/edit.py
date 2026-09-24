from __future__ import annotations

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
