"""3D LUT (.cube) import, validation, sampling and ffmpeg wiring.

Preview and render share :func:`sample_trilinear` (ffmpeg ``lut3d`` ``interp=trilinear``).
Intensity blends the graded picture toward the LUT result (1 = full LUT, 0 = unchanged).
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hermes_studio import grade as _G

MAX_BYTES = 20 * 1024 * 1024
LUT_DIR = "luts"
_FILE_RE = re.compile(r"^luts/[0-9a-f]{32}\.cube$")  # first 32 hex chars of sha256(content)


@dataclass(frozen=True)
class Lut3D:
    size: int
    domain_min: tuple[float, float, float]
    domain_max: tuple[float, float, float]
    title: str
    # Flat r,g,b in file order (R varies fastest in standard .cube).
    data: tuple[float, ...]

    def at(self, ri: int, gi: int, bi: int) -> tuple[float, float, float]:
        n = self.size
        i = (bi * n * n + gi * n + ri) * 3
        return self.data[i], self.data[i + 1], self.data[i + 2]


def decode_bytes(raw: bytes) -> str:
    if not raw:
        raise ValueError("empty LUT file")
    if len(raw) > MAX_BYTES:
        raise ValueError(f"a .cube LUT can be at most {MAX_BYTES // (1024 * 1024)} MB")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("a .cube LUT must be UTF-8 text") from exc


def parse(text: str) -> Lut3D:
    """Parse a 3D .cube LUT. Rejects 1D LUTs, bad sizes, NaN/inf and wrong row counts."""
    if not isinstance(text, str):
        raise ValueError("LUT text must be a string")
    size: int | None = None
    domain_min = (0.0, 0.0, 0.0)
    domain_max = (1.0, 1.0, 1.0)
    title = ""
    rows: list[tuple[float, float, float]] = []
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("LUT_1D_SIZE"):
            raise ValueError("only 3D LUTs are supported (LUT_3D_SIZE)")
        if up.startswith("LUT_3D_SIZE"):
            size = int(s.split()[-1])
            continue
        if up.startswith("DOMAIN_MIN"):
            domain_min = _triple(s, "DOMAIN_MIN")
            continue
        if up.startswith("DOMAIN_MAX"):
            domain_max = _triple(s, "DOMAIN_MAX")
            continue
        if up.startswith("TITLE"):
            title = _title_value(s)
            continue
        parts = s.split()
        if len(parts) != 3:
            raise ValueError(f"expected three numbers, got: {s[:40]}")
        try:
            rgb = tuple(float(x) for x in parts)
        except ValueError as exc:
            raise ValueError(f"expected three numbers, got: {s[:40]}") from exc
        if not all(math.isfinite(v) for v in rgb):
            raise ValueError("LUT values must be finite numbers")
        rows.append(rgb)
    if size is None:
        raise ValueError("LUT_3D_SIZE is required")
    if not (2 <= size <= 65):
        raise ValueError("LUT_3D_SIZE must be from 2 to 65")
    need = size ** 3
    if len(rows) != need:
        raise ValueError(f"expected {need} RGB rows, got {len(rows)}")
    flat: list[float] = []
    for r, g, b in rows:
        flat.extend((r, g, b))
    return Lut3D(size=size, domain_min=domain_min, domain_max=domain_max, title=title, data=tuple(flat))


def _triple(line: str, key: str) -> tuple[float, float, float]:
    parts = line.split()
    if len(parts) != 4:
        raise ValueError(f"{key} needs three numbers")
    try:
        v = tuple(float(x) for x in parts[1:4])
    except ValueError as exc:
        raise ValueError(f"{key} needs three numbers") from exc
    if not all(math.isfinite(x) for x in v):
        raise ValueError(f"{key} must be finite")
    return v


def _title_value(line: str) -> str:
    rest = line[5:].strip()
    if rest.startswith('"') and rest.endswith('"') and len(rest) >= 2:
        return rest[1:-1]
    return rest


def store_text(folder: Path, text: str) -> str:
    """Write a validated LUT under ``folder/luts/<sha256>.cube``; return the relative path."""
    parse(text)  # validate before storing
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    rel = f"{LUT_DIR}/{digest}.cube"
    base = folder.resolve()
    path = (base / rel).resolve()
    path.relative_to(base)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return rel


def store_bytes(folder: Path, raw: bytes) -> str:
    return store_text(folder, decode_bytes(raw))


def _name_file(folder: Path, rel: str) -> Path:
    if not _FILE_RE.match(rel):
        raise ValueError("LUT path must be luts/<hash>.cube")
    base = folder.resolve()
    path = (base / f"{rel[: -len('.cube')]}.name").resolve()
    path.relative_to(base)
    return path


def save_display_name(folder: Path, rel: str, name: str) -> None:
    p = _name_file(folder, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(unicodedata.normalize("NFC", name[:120]), encoding="utf-8")


def display_name(folder: Path, rel: str) -> str:
    nf = _name_file(folder, rel)
    if nf.is_file():
        return nf.read_text(encoding="utf-8").strip()
    try:
        return parse(resolve_path(folder, rel).read_text(encoding="utf-8")).title or Path(rel).stem
    except (OSError, ValueError):
        return Path(rel).stem


def load_file(folder: Path, rel: str) -> Lut3D:
    return parse(resolve_path(folder, rel).read_text(encoding="utf-8"))


def resolve_path(folder: Path, rel: str) -> Path:
    if not _FILE_RE.match(rel):
        raise ValueError("LUT path must be luts/<hash>.cube")
    base = folder.resolve()
    path = (base / rel).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("LUT path escapes the project") from exc
    if not path.is_file():
        raise ValueError("LUT file is missing")
    return path


def _map_domain(lut: Lut3D, r: float, g: float, b: float) -> tuple[float, float, float]:
    out = []
    for v, lo, hi in zip((r, g, b), lut.domain_min, lut.domain_max, strict=True):
        if abs(hi - lo) < 1e-12:
            out.append(lo)
        else:
            out.append((v - lo) / (hi - lo))
    return tuple(max(0.0, min(1.0, x)) for x in out)


def _mix(a: tuple[float, ...], b: tuple[float, ...], t: float) -> tuple[float, float, float]:
    return tuple(a[i] + t * (b[i] - a[i]) for i in range(3))


def sample_trilinear(lut: Lut3D, r: float, g: float, b: float) -> tuple[float, float, float]:
    """Sample the LUT at linear RGB ``r,g,b`` in 0..1 (trilinear, matching ffmpeg lut3d)."""
    r, g, b = _map_domain(lut, r, g, b)
    n = lut.size
    if n == 1:
        return lut.at(0, 0, 0)
    scale = n - 1
    x = r * scale
    y = g * scale
    z = b * scale
    xi = min(n - 2, max(0, int(x)))
    yi = min(n - 2, max(0, int(y)))
    zi = min(n - 2, max(0, int(z)))
    xf = x - xi
    yf = y - yi
    zf = z - zi
    c000 = lut.at(xi, yi, zi)
    c100 = lut.at(xi + 1, yi, zi)
    c010 = lut.at(xi, yi + 1, zi)
    c110 = lut.at(xi + 1, yi + 1, zi)
    c001 = lut.at(xi, yi, zi + 1)
    c101 = lut.at(xi + 1, yi, zi + 1)
    c011 = lut.at(xi, yi + 1, zi + 1)
    c111 = lut.at(xi + 1, yi + 1, zi + 1)
    c00 = _mix(c000, c100, xf)
    c01 = _mix(c001, c101, xf)
    c10 = _mix(c010, c110, xf)
    c11 = _mix(c011, c111, xf)
    c0 = _mix(c00, c10, yf)
    c1 = _mix(c01, c11, yf)
    return _mix(c0, c1, zf)


def apply_pixel(lut: Lut3D, intensity: float, rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """Blend ``rgb`` (0..1) toward the LUT by ``intensity`` in 0..1."""
    t = max(0.0, min(1.0, float(intensity)))
    if t <= 1e-12:
        return rgb
    out = sample_trilinear(lut, *rgb)
    if t >= 1.0 - 1e-12:
        return out
    return tuple(rgb[i] + t * (out[i] - rgb[i]) for i in range(3))


def preview_pack(lut: Lut3D) -> dict[str, Any]:
    """Compact LUT for the desk preview and JS pin tests."""
    return {
        "size": lut.size,
        "domain_min": list(lut.domain_min),
        "domain_max": list(lut.domain_max),
        "data": [round(v, 7) for v in lut.data],
    }


def ffmpeg_chain(path: Path, intensity: float) -> tuple[str, str]:
    """Return ``(inline_filters, labelled_graph)`` to apply after the primary grade.

    ``inline_filters`` is a single filter for intensity 1 (no labels). When intensity is
    below 1, ``labelled_graph`` maps ``[stem]`` to ``[stem]`` via split, ``lut3d`` and
    ``blend`` (caller writes ``[mid]{graph}`` with ``stem=mid``).
    """
    t = max(0.0, min(1.0, float(intensity)))
    if t <= 1e-12:
        return "", ""
    fp = _G._filter_path(path)
    lut = f"lut3d=file={fp}:interp=trilinear"
    if t >= 1.0 - 1e-12:
        return lut, ""
    o = f"{t:.6f}"
    return "", (
        f"split=2[{{stem}}a][{{stem}}b];[{{stem}}b]{lut}[{{stem}}c];"
        f"[{{stem}}a][{{stem}}c]blend=all_mode=normal:all_opacity={o}[{{stem}}]"
    )


def ffmpeg_graph(path: Path, intensity: float, stem: str) -> str:
    """Labelled filter graph from ``[stem]`` to ``[stem]`` (see :func:`ffmpeg_chain`)."""
    _, graph = ffmpeg_chain(path, intensity)
    if not graph:
        return f"null[{stem}]"
    return graph.format(stem=stem)


def make_test_cube(size: int = 17) -> str:
    """A warm/teal 3D LUT for tests (gradient in lattice space)."""
    lines = [
        'TITLE "hermes test warm teal"',
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0 0 0",
        "DOMAIN_MAX 1 1 1",
    ]
    n = size - 1
    for bi in range(size):
        for gi in range(size):
            for ri in range(size):
                r, g, b = ri / n, gi / n, bi / n
                rr = min(1.0, max(0.0, r * 0.85 + 0.12 * (1.0 - b) + 0.05 * g))
                gg = min(1.0, max(0.0, g * 0.92 + 0.04 * r))
                bb = min(1.0, max(0.0, b * 1.08 - 0.06 * r + 0.03 * (1.0 - g)))
                lines.append(f"{rr:.7f} {gg:.7f} {bb:.7f}")
    return "\n".join(lines) + "\n"
