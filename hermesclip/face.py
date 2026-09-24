"""Speaker crop for Fill. Local Haar — not Opus ReframeAnything. Optional opencv."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def face_norm(video: Path, start: float, end: float) -> tuple[float, float] | None:
    """Return (nx, ny) in 0–1 if a face is found in the clip window."""
    try:
        import cv2
    except ImportError:
        return None
    bundled = Path(__file__).resolve().parent / "data" / "haarcascade_frontalface_default.xml"
    xml = str(bundled) if bundled.is_file() else ""
    if not xml:
        data = getattr(cv2, "data", None)
        if data is not None:
            xml = str(getattr(data, "haarcascades", "") or "") + "haarcascade_frontalface_default.xml"
    if not xml or not Path(xml).is_file():
        xml = "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"
    if not Path(xml).is_file():
        return None
    det = cv2.CascadeClassifier(xml)
    if det.empty():
        return None
    span = max(end - start, 0.4)
    stamps = [start + span * t for t in (0.2, 0.5, 0.8)]
    xs: list[float] = []
    ys: list[float] = []
    with tempfile.TemporaryDirectory(prefix="hermesclip-face-") as tmp:
        tmp_p = Path(tmp)
        for i, t in enumerate(stamps):
            dest = tmp_p / f"{i}.jpg"
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{max(t, 0):.3f}",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=320:-1",
                    "-q:v",
                    "5",
                    str(dest),
                ],
                capture_output=True,
            )
            if proc.returncode != 0 or not dest.is_file():
                continue
            img = cv2.imread(str(dest))
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = det.detectMultiScale(gray, 1.1, 4, minSize=(24, 24))
            if len(faces) == 0:
                continue
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            ih, iw = gray.shape[:2]
            xs.append((x + w / 2) / max(iw, 1))
            ys.append((y + h / 2) / max(ih, 1))
    if not xs:
        return None
    xs.sort()
    ys.sort()
    mid = len(xs) // 2
    return xs[mid], ys[mid]


def fill_crop_xy(
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
    nx: float,
    ny: float,
) -> tuple[int, int]:
    scale = max(out_w / max(src_w, 1), out_h / max(src_h, 1))
    sw, sh = src_w * scale, src_h * scale
    x = sw * nx - out_w / 2
    y = sh * ny - out_h / 2
    x = min(max(x, 0), max(sw - out_w, 0))
    y = min(max(y, 0), max(sh - out_h, 0))
    return even(x), even(y)
