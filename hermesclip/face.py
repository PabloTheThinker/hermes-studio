"""Face detection for framing. Local, no network.

Detector: OpenCV YuNet (MIT, bundled ONNX, ~230 KB) with five landmarks, so we know
where the eyes are and which way the head turns. Falls back to the Haar cascade on
OpenCV builds without FaceDetectorYN. Both are optional: without OpenCV there are no
faces and framing falls back to Fit.

Callers get a FaceTrack: every detection of the main subject across the clip, with
times, so framing can choose a locked camera or a smooth pan (Google AutoFlip's
stationary-vs-track idea). Framing math lives in framing.py.
"""

from __future__ import annotations

import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
YUNET = DATA / "face_detection_yunet_2023mar.onnx"
HAAR = DATA / "haarcascade_frontalface_default.xml"
PROBE_W = 640  # sample frames are scaled to this width before detection


@dataclass(frozen=True)
class Face:
    """One detection, normalised 0-1 to the source frame."""

    t: float          # seconds from the clip start
    x: float
    y: float
    w: float
    h: float
    eye_y: float      # eye line; estimated from the box when there are no landmarks
    yaw: float = 0.0  # -1 turned screen-left .. +1 screen-right
    score: float = 1.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class FaceTrack:
    """Detections of the main subject over a clip window."""

    faces: list[Face] = field(default_factory=list)
    samples: int = 0

    def __bool__(self) -> bool:
        return bool(self.faces)

    @property
    def coverage(self) -> float:
        """Share of sampled frames where the subject was found."""
        return len(self.faces) / self.samples if self.samples else 0.0

    def median(self) -> Face | None:
        if not self.faces:
            return None
        m, f = statistics.median, self.faces
        return Face(
            t=m(x.t for x in f), x=m(x.x for x in f), y=m(x.y for x in f),
            w=m(x.w for x in f), h=m(x.h for x in f), eye_y=m(x.eye_y for x in f),
            yaw=m(x.yaw for x in f), score=m(x.score for x in f),
        )

    def box(self) -> tuple[float, float, float, float] | None:
        """Median (x, y, w, h)."""
        md = self.median()
        return (md.x, md.y, md.w, md.h) if md else None

    def spread_x(self) -> float:
        """How far the face centre travels across the clip, as a share of frame width."""
        if len(self.faces) < 2:
            return 0.0
        xs = [f.cx for f in self.faces]
        return max(xs) - min(xs)


class _Detector:
    def __init__(self) -> None:
        self.kind = "none"
        self.cv2 = None
        self._yn = None
        self._haar = None
        try:
            import cv2
        except ImportError:
            return
        self.cv2 = cv2
        if hasattr(cv2, "FaceDetectorYN") and YUNET.is_file():
            try:
                # score 0.7, nms 0.3, top 50
                self._yn = cv2.FaceDetectorYN.create(str(YUNET), "", (320, 320), 0.7, 0.3, 50)
                self.kind = "yunet"
                return
            except Exception:
                self._yn = None
        if hasattr(cv2, "CascadeClassifier") and HAAR.is_file():
            det = cv2.CascadeClassifier(str(HAAR))
            if not det.empty():
                self._haar = det
                self.kind = "haar"

    def detect(self, img, t: float) -> list[Face]:
        ih, iw = img.shape[:2]
        out: list[Face] = []
        if self._yn is not None:
            self._yn.setInputSize((iw, ih))
            _ok, rows = self._yn.detect(img)
            for r in rows if rows is not None else []:
                x, y, w, h = (float(v) for v in r[:4])
                rex, rey, lex, ley, nose_x = (float(v) for v in r[4:9])
                eye_mid = (rex + lex) / 2
                gap = max(abs(lex - rex), 1.0)
                yaw = max(-1.0, min(1.0, (nose_x - eye_mid) / gap * 2))
                out.append(Face(t, x / iw, y / ih, w / iw, h / ih, (rey + ley) / 2 / ih, yaw, float(r[14])))
        elif self._haar is not None:
            gray = self.cv2.cvtColor(img, self.cv2.COLOR_BGR2GRAY)
            for x, y, w, h in self._haar.detectMultiScale(gray, 1.1, 5, minSize=(18, 18)):
                # Haar boxes run brow to chin; the eyes sit about 40% down.
                out.append(Face(t, x / iw, y / ih, w / iw, h / ih, (y + h * 0.4) / ih, 0.0, 0.5))
        return out


_DET: _Detector | None = None


def detector() -> _Detector:
    global _DET
    if _DET is None:
        _DET = _Detector()
    return _DET


def available() -> str:
    """'yunet', 'haar' or 'none'."""
    return detector().kind


def sample_frames(video: Path, start: float, end: float, n: int):
    """Yield (seconds from start, BGR image) for n evenly spaced frames."""
    det = detector()
    if det.kind == "none":
        return
    span = max(end - start, 0.4)
    with tempfile.TemporaryDirectory(prefix="hermesclip-face-") as tmp:
        for i in range(n):
            rel = span * (i + 0.5) / n
            dest = Path(tmp) / f"{i}.jpg"
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(start + rel, 0):.3f}", "-i", str(video),
                 "-frames:v", "1", "-vf", f"scale={PROBE_W}:-2", "-q:v", "4", str(dest)],
                capture_output=True,
            )
            if proc.returncode != 0 or not dest.is_file():
                continue
            img = det.cv2.imread(str(dest))
            if img is not None:
                yield rel, img


def main_subject(per_frame: list[list[Face]]) -> list[Face]:
    """Follow one person across frames.

    Seed on the median of each frame's biggest face, then take the nearest face in every
    frame. A stray detection (a poster, a game character, a guest walking by) is skipped
    instead of yanking the crop.
    """
    seeds = [max(fs, key=lambda f: f.w * f.h) for fs in per_frame if fs]
    if not seeds:
        return []
    ref_x = statistics.median(f.cx for f in seeds)
    ref_y = statistics.median(f.cy for f in seeds)
    ref_w = statistics.median(f.w for f in seeds)
    picked: list[Face] = []
    for fs in per_frame:
        if not fs:
            continue
        best = min(fs, key=lambda f: abs(f.cx - ref_x) + abs(f.cy - ref_y) + abs(f.w - ref_w))
        if abs(best.cx - ref_x) > max(0.35, ref_w * 3) or not (ref_w / 2.5 < best.w < ref_w * 2.5):
            continue
        picked.append(best)
        ref_x = (ref_x + best.cx) / 2
        ref_y = (ref_y + best.cy) / 2
    return picked


def face_track(video: Path, start: float, end: float, samples: int = 9) -> FaceTrack:
    """Detections of the main subject across [start, end] in source seconds."""
    det = detector()
    per = [det.detect(img, rel) for rel, img in sample_frames(video, start, end, samples)]
    return FaceTrack(main_subject(per), samples=len(per))


def face_box(video: Path, start: float, end: float, samples: int = 9) -> tuple[float, float, float, float] | None:
    """Median face box (x, y, w, h) 0-1 of the main subject, or None."""
    return face_track(video, start, end, samples).box()
