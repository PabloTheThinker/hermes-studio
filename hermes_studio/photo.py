"""Photo tools for the design editor and for agents. All local, no upload.

- cutout: remove the background (U^2-Net small, 4.5 MB, Apache-2.0, run with OpenCV DNN).
- enhance: auto levels, lifted shadows, gentle clarity and sharpening; skin keeps its texture.
- look: named colour looks (bw, warm, cool, punch, fade, noir).

Inputs are decoded with OpenCV from bytes we already hold, so no path from a request is
ever opened by these functions. PNG, JPEG and WebP only.
"""

from __future__ import annotations

from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CUTOUT_MODEL = DATA / "u2netp.onnx"
MAX_PIXELS = 40_000_000
LOOKS = ("none", "bw", "warm", "cool", "punch", "fade", "noir")


class PhotoError(ValueError):
    pass


def _cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # opencv ships with hermes-studio[reframe] and the desktop app
        raise PhotoError("photo tools need OpenCV: pip install 'hermes-studio[reframe]'") from exc
    return cv2, np


def decode(data: bytes):
    """Bytes -> BGR or BGRA uint8 array. Refuses anything that is not PNG/JPEG/WebP."""
    cv2, np = _cv()
    head = bytes(data[:12])
    if not (head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        raise PhotoError("only PNG, JPEG or WebP images")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise PhotoError("could not read that image")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[0] * img.shape[1] > MAX_PIXELS:
        raise PhotoError("image too large (40 megapixels max)")
    if img.dtype != np.uint8:
        img = (img / 256).astype(np.uint8)
    return img


def write(path: Path, img) -> None:
    cv2, _ = _cv()
    ext = ".png" if img.shape[2] == 4 else ".jpg"
    if path.suffix.lower() != ext:
        path = path.with_suffix(ext)
    params = [cv2.IMWRITE_JPEG_QUALITY, 94] if ext == ".jpg" else [cv2.IMWRITE_PNG_COMPRESSION, 6]
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise PhotoError("could not encode image")
    path.write_bytes(buf.tobytes())


def encode(img, ext: str = ".png") -> bytes:
    cv2, _ = _cv()
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise PhotoError("could not encode image")
    return buf.tobytes()


def matte(img):
    """Soft alpha (float 0-1, HxW) for the main subject."""
    cv2, np = _cv()
    if not CUTOUT_MODEL.is_file():
        raise PhotoError("background model missing (data/u2netp.onnx)")
    bgr = img[:, :, :3]
    net = cv2.dnn.readNetFromONNX(str(CUTOUT_MODEL))
    x = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (320, 320), interpolation=cv2.INTER_AREA)
    x = (x.astype(np.float32) / 255.0 - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
        [0.229, 0.224, 0.225], np.float32)
    net.setInput(x.transpose(2, 0, 1)[None].astype(np.float32))
    d = net.forward()[0, 0]
    d = (d - d.min()) / (d.max() - d.min() + 1e-8)
    a = cv2.resize(d, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
    # Guided-style refinement: snap the soft model edge to real image edges.
    guide = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    r = max(2, round(min(bgr.shape[:2]) / 300))
    a = _guided(guide, a.astype(np.float32), r, 1e-3)
    a = np.clip((a - 0.08) / 0.84, 0, 1)  # firm up the core, keep the soft rim
    return a


def _guided(I, p, r: int, eps: float):
    cv2, _ = _cv()
    k = (2 * r + 1, 2 * r + 1)
    mI, mp = cv2.blur(I, k), cv2.blur(p, k)
    cov = cv2.blur(I * p, k) - mI * mp
    var = cv2.blur(I * I, k) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return cv2.blur(a, k) * I + cv2.blur(b, k)


def cutout(img):
    """BGRA with the background removed."""
    _, np = _cv()
    a = matte(img)
    bgr = img[:, :, :3]
    return np.dstack([bgr, (a * 255).astype(np.uint8)])


def enhance(img, strength: float = 1.0):
    """Auto levels + lifted shadows + local contrast + light sharpen. Alpha is kept."""
    cv2, np = _cv()
    s = max(0.0, min(1.5, float(strength)))
    alpha = img[:, :, 3] if img.shape[2] == 4 else None
    bgr = img[:, :, :3].astype(np.float32) / 255.0
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0] / 100.0
    lo, hi = np.percentile(L, 0.5), np.percentile(L, 99.6)
    Ln = np.clip((L - lo) / max(hi - lo, 1e-3), 0, 1)
    Ln = L + (Ln - L) * 0.7 * s
    Ln = Ln + 0.10 * s * (1 - Ln) * np.exp(-((Ln - 0.25) ** 2) / 0.04)  # lift shadows
    clahe = cv2.createCLAHE(clipLimit=1.2 + 0.8 * s, tileGridSize=(8, 8))
    Lc = clahe.apply((np.clip(Ln, 0, 1) * 255).astype(np.uint8)).astype(np.float32) / 255.0
    Ln = Ln * (1 - 0.35 * s) + Lc * 0.35 * s
    lab[:, :, 0] = np.clip(Ln, 0, 1) * 100
    lab[:, :, 1:] *= 1 + 0.06 * s  # a touch more colour
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(out, (0, 0), max(1.0, min(out.shape[:2]) / 800))
    out = np.clip(out + (out - blur) * 0.45 * s, 0, 1)  # unsharp mask
    res = (out * 255).astype(np.uint8)
    return np.dstack([res, alpha]) if alpha is not None else res


def look(img, name: str):
    cv2, np = _cv()
    if name not in LOOKS:
        raise PhotoError(f"look must be one of {', '.join(LOOKS)}")
    if name == "none":
        return img
    alpha = img[:, :, 3] if img.shape[2] == 4 else None
    f = img[:, :, :3].astype(np.float32) / 255.0
    if name in ("bw", "noir"):
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if name == "noir":
            g = np.clip((g - 0.5) * 1.35 + 0.47, 0, 1)
        f = np.dstack([g, g, g])
    elif name == "warm":
        f = f * np.array([0.92, 1.0, 1.08], np.float32)
    elif name == "cool":
        f = f * np.array([1.08, 1.0, 0.93], np.float32)
    elif name == "punch":
        hsv = cv2.cvtColor(np.clip(f, 0, 1), cv2.COLOR_BGR2HSV)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.25, 0, 1)
        f = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        f = np.clip((f - 0.5) * 1.12 + 0.5, 0, 1)
    elif name == "fade":
        f = f * 0.86 + 0.08
    res = (np.clip(f, 0, 1) * 255).astype(np.uint8)
    return np.dstack([res, alpha]) if alpha is not None else res


def run_file(op: str, src: str, out: str = "", *, look_name: str = "", strength: float = 1.0) -> dict:
    """CLI/agent entry: read an image file, apply op, write the result next to it (or to out)."""
    p = Path(src).expanduser()
    if not p.is_file():
        raise PhotoError(f"no file {src}")
    if p.stat().st_size > 60 * 1024 * 1024:
        raise PhotoError("image too large (60 MB max)")
    img = decode(p.read_bytes())
    if op == "cutout":
        res = cutout(img)
    elif op == "enhance":
        res = enhance(img, strength)
    elif op == "look":
        res = look(img, look_name or "warm")
    else:
        raise PhotoError("op must be cutout, enhance or look")
    ext = ".png" if res.shape[2] == 4 else ".jpg"
    dest = Path(out).expanduser() if out else p.with_name(f"{p.stem}-{op}{ext}")
    dest = dest.with_suffix(ext)
    write(dest, res)
    return {"ok": True, "op": op, "src": str(p), "file": str(dest), "w": res.shape[1], "h": res.shape[0],
            "transparent": res.shape[2] == 4}
