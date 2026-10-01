"""Design: Canva-style multi-page designs for people (the desk editor) and agents (MCP/CLI).

One document format, used by both:

    {
      "version": 1, "id": "d-…", "title": "…", "w": 1080, "h": 1350,
      "pages": [
        {"bg": "#0b0b0c", "layers": [
          {"type": "image", "src": "assets/<file>", "x": 0, "y": 0, "w": 1080, "h": 1350, "fit": "cover",
           "opacity": 1, "radius": 0, "angle": 0, "flip": false},
          {"type": "text", "text": "Hello", "x": 80, "y": 120, "w": 920, "size": 96, "font": "archivo",
           "weight": 800, "italic": false, "color": "#f2efe8", "align": "left", "line": 1.05,
           "spacing": 0, "upper": false, "bg": "", "opacity": 1, "angle": 0,
           "effect": {"kind": "shadow", "color": "#000000", "offset": 12, "blur": 16, "dir": 135, "opacity": 0.55}},
          {"type": "rect", "x": 80, "y": 900, "w": 920, "h": 220, "fill": "#ffc83d", "radius": 24,
           "stroke": "", "stroke_w": 0, "opacity": 1, "angle": 0,
           "shadow": {"color": "#000000", "offset": 14, "blur": 22, "dir": 135, "opacity": 0.5}},
          {"type": "ellipse", ...same as rect...},
          {"type": "line", "x": 80, "y": 600, "w": 920, "h": 0, "stroke": "#ffc83d", "stroke_w": 6}
        ]}
      ]
    }

Coordinates are document pixels, top-left origin. Text boxes have a width and wrap.
Designs live in <studio home>/designs/<id>/ with design.json, assets/ and export/.
Rendering here (Pillow) is what agents get; the desk renders the same document with Fabric.js.
"""

from __future__ import annotations

import copy
import json
import math
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "data" / "fonts"

# id -> (file, label, CSS family). Every font is OFL and ships in data/fonts (see NOTICE).
FONTS: dict[str, tuple[str, str, str]] = {
    "archivo": ("Archivo.ttf", "Archivo", "Archivo"),
    "playfair": ("PlayfairDisplay-Italic.ttf", "Playfair Italic", "Playfair Display"),
    "caveat": ("Caveat.ttf", "Caveat (hand)", "Caveat"),
    "mono": ("JetBrainsMono.ttf", "JetBrains Mono", "JetBrains Mono"),
    "opensans": ("OpenSans.ttf", "Open Sans", "Open Sans"),
}

SIZES: dict[str, tuple[int, int, str]] = {
    "tiktok-carousel": (1080, 1350, "TikTok / Instagram carousel 4:5"),
    "story": (1080, 1920, "Story, Reel, TikTok cover 9:16"),
    "square": (1080, 1080, "Square post 1:1"),
    "youtube-thumb": (1280, 720, "YouTube thumbnail 16:9"),
    "x-post": (1600, 900, "X / LinkedIn post"),
}

LAYER_TYPES = ("image", "text", "rect", "ellipse", "line")
MAX_PAGES = 30
MAX_LAYERS = 120
MAX_SIDE = 4000
ASSET_RE = re.compile(r"^assets/[a-z0-9][a-z0-9-]{3,60}\.(png|jpg|webp)$")
ID_RE = re.compile(r"^d-[a-z0-9]{6,40}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")

INK = "#f2efe8"
AMBER = "#ffc83d"
BLACK = "#0b0b0c"


class DesignError(ValueError):
    pass


# --------------------------------------------------------------------------- storage

def designs_root() -> Path:
    from hermes_studio.pipeline import library_root

    p = library_root().parent / "designs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_id(design_id: str) -> bool:
    return bool(ID_RE.match(str(design_id or "")))


def design_dir(design_id: str) -> Path:
    if not safe_id(design_id):
        raise DesignError("bad design id")
    d = designs_root() / design_id
    if not (d / "design.json").is_file():
        raise DesignError(f"no design {design_id}")
    return d


def new_id() -> str:
    return "d-" + datetime.now(UTC).strftime("%y%m%d") + secrets.token_hex(4)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- validation

def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return max(lo, min(hi, f))


def _color(v, default: str) -> str:
    v = str(v or "").strip()
    if v in ("", "none", "transparent"):
        return ""
    return v if COLOR_RE.match(v) else default


EFFECTS = ("none", "shadow", "lift", "hollow", "splice", "echo", "glitch", "neon", "outline")


def clean_effect(effect) -> dict | None:
    """A text effect with sane values, or None. One effect at a time, as in Canva."""
    if not isinstance(effect, dict) or effect.get("kind") not in EFFECTS[1:]:
        return None
    return {
        "kind": effect["kind"],
        "color": _color(effect.get("color"), "#000000") or "#000000",
        "offset": _num(effect.get("offset"), 0, 400, 14),
        "blur": _num(effect.get("blur"), 0, 200, 0),
        "dir": _num(effect.get("dir"), 0, 360, 135),
        "opacity": _num(effect.get("opacity"), 0, 1, 0.6),
        "thickness": _num(effect.get("thickness"), 1, 60, 6),
    }


def clean_shadow(shadow) -> dict | None:
    """A drop shadow for shapes and photos."""
    if not isinstance(shadow, dict):
        return None
    return {
        "color": _color(shadow.get("color"), "#000000") or "#000000",
        "offset": _num(shadow.get("offset"), 0, 400, 14),
        "blur": _num(shadow.get("blur"), 0, 200, 20),
        "dir": _num(shadow.get("dir"), 0, 360, 135),
        "opacity": _num(shadow.get("opacity"), 0, 1, 0.5),
    }


def clean_layer(layer: dict, w: int, h: int) -> dict | None:
    """A layer with only known keys and sane values, or None to drop it."""
    if not isinstance(layer, dict):
        return None
    t = layer.get("type")
    if t not in LAYER_TYPES:
        return None
    span = max(w, h) * 3
    out = {
        "type": t,
        "x": _num(layer.get("x"), -span, span, 0),
        "y": _num(layer.get("y"), -span, span, 0),
        "w": _num(layer.get("w"), 0, span, w / 2),
        "opacity": _num(layer.get("opacity"), 0, 1, 1),
        "angle": _num(layer.get("angle"), -360, 360, 0),
    }
    if layer.get("name"):
        out["name"] = str(layer["name"])[:60]
    if t == "image":
        src = str(layer.get("src") or "")
        if not ASSET_RE.match(src):
            return None
        out.update(src=src, h=_num(layer.get("h"), 1, span, h / 2),
                   fit="contain" if layer.get("fit") == "contain" else "cover",
                   radius=_num(layer.get("radius"), 0, 2000, 0), flip=bool(layer.get("flip")))
        out["w"] = max(out["w"], 1)
    elif t == "text":
        out.update(
            text=str(layer.get("text") or "")[:2000],
            size=_num(layer.get("size"), 6, 600, 64),
            font=layer.get("font") if layer.get("font") in FONTS else "archivo",
            weight=int(_num(layer.get("weight"), 100, 900, 700)),
            italic=bool(layer.get("italic")),
            color=_color(layer.get("color"), INK) or INK,
            align=layer.get("align") if layer.get("align") in ("left", "center", "right") else "left",
            line=_num(layer.get("line"), 0.6, 3, 1.15),
            spacing=_num(layer.get("spacing"), -50, 200, 0),
            upper=bool(layer.get("upper")),
            bg=_color(layer.get("bg"), ""),
        )
        out["w"] = max(out["w"], 20)
    else:
        out.update(h=_num(layer.get("h"), 0, span, 100),
                   fill=_color(layer.get("fill"), AMBER) if t != "line" else "",
                   stroke=_color(layer.get("stroke"), ""),
                   stroke_w=_num(layer.get("stroke_w"), 0, 200, 0),
                   radius=_num(layer.get("radius"), 0, 2000, 0) if t == "rect" else 0)
        if t == "line":
            out["stroke"] = out["stroke"] or AMBER
            out["stroke_w"] = out["stroke_w"] or 6
    if t == "text":
        eff = clean_effect(layer.get("effect"))
        if eff:
            out["effect"] = eff
    elif t in ("rect", "ellipse", "image"):
        sh = clean_shadow(layer.get("shadow"))
        if sh:
            out["shadow"] = sh
    if layer.get("locked"):
        out["locked"] = True
    if layer.get("blend") in BLENDS:
        out["blend"] = layer["blend"]
    if t == "image":
        adj = clean_adjust(layer.get("adjust"))
        if adj:
            out["adjust"] = adj
    return out


def clean_doc(doc: dict) -> dict:
    if not isinstance(doc, dict):
        raise DesignError("design must be an object")
    w = int(_num(doc.get("w"), 64, MAX_SIDE, 1080))
    h = int(_num(doc.get("h"), 64, MAX_SIDE, 1350))
    pages_in = doc.get("pages") or [{}]
    if not isinstance(pages_in, list):
        raise DesignError("pages must be a list")
    pages = []
    for p in pages_in[:MAX_PAGES]:
        p = p if isinstance(p, dict) else {}
        layers = [x for x in (clean_layer(lay, w, h) for lay in (p.get("layers") or [])[:MAX_LAYERS]) if x]
        pages.append({"bg": _color(p.get("bg"), BLACK) or BLACK, "layers": layers})
    return {
        "version": 1,
        "id": doc.get("id") if safe_id(doc.get("id", "")) else "",
        "title": (str(doc.get("title") or "Untitled design").strip() or "Untitled design")[:120],
        "w": w, "h": h,
        "pages": pages or [{"bg": BLACK, "layers": []}],
        "created": str(doc.get("created") or "")[:40],
        "updated": str(doc.get("updated") or "")[:40],
    }


# --------------------------------------------------------------------------- templates

def _t(text, x, y, w, size, **kw) -> dict:
    return {"type": "text", "text": text, "x": x, "y": y, "w": w, "size": size, **kw}


def _templates(w: int, h: int) -> dict[str, dict]:
    """House templates. Text sits on a black field so a photo never fights the words."""
    m = round(w * 0.074)  # margin
    inner = w - 2 * m
    tall = h / w
    u = min(w, h * 0.8)  # type unit: wide pages scale type by height, not width
    return {
        "blank": {"label": "Blank", "pages": [{"bg": BLACK, "layers": []}]},
        "carousel": {
            "label": "Carousel: hook, points, follow",
            "pages": [
                {"bg": BLACK, "layers": [
                    _t("A SHORT LINE THAT STOPS THE SCROLL", m, round(h * .16), inner, round(u * .095),
                       weight=800, upper=True, line=1.0),
                    _t("the part they didn't tell you", m, round(h * .16 + u * .32), inner, round(u * .07),
                       font="playfair", italic=True, weight=500, color="#f5e6c8"),
                    {"type": "rect", "x": m, "y": round(h * .72), "w": round(u * .2), "h": 8, "fill": AMBER},
                    _t("swipe for more", m, round(h * .75), inner, round(u * .06), font="caveat", weight=600,
                       color="#ff8fb4"),
                ]},
                {"bg": BLACK, "layers": [
                    _t("01", m, round(h * .12), inner, round(u * .05), font="mono", weight=500, color=AMBER),
                    _t("Your first point, said plainly.", m, round(h * .12 + u * .09), inner,
                       round(u * .085), weight=800, line=1.02),
                    _t("One or two sentences that explain it. Keep it short enough to read in three seconds.",
                       m, round(h * .12 + u * .42), inner, round(u * .042), weight=400, color="#c9c5bd",
                       line=1.35),
                ]},
                {"bg": BLACK, "layers": [
                    _t("02", m, round(h * .12), inner, round(u * .05), font="mono", weight=500, color=AMBER),
                    _t("Your second point.", m, round(h * .12 + u * .09), inner, round(u * .085),
                       weight=800, line=1.02),
                    {"type": "rect", "x": m, "y": round(h * .5), "w": inner, "h": round(h * .3),
                     "fill": "#f5f1e8", "radius": 28},
                    _t("A card for the proof: a number, a quote or a screenshot.", m + 40, round(h * .5) + 40,
                       inner - 80, round(u * .045), weight=600, color="#111111", line=1.25),
                ]},
                {"bg": BLACK, "layers": [
                    _t("FOLLOW FOR PART 2", m, round(h * .4), inner, round(u * .09), weight=800,
                       align="center", upper=True),
                    _t("@yourhandle", m, round(h * .4 + u * .25), inner, round(u * .05), font="mono",
                       align="center", color=AMBER, weight=500),
                ]},
            ],
        },
        "quote": {
            "label": "Quote card",
            "pages": [{"bg": BLACK, "layers": [
                _t("“", m, round(h * .14), inner, round(u * .3), font="playfair", italic=True, color=AMBER,
                   weight=600, line=0.8),
                _t("Write the line people screenshot.", m, round(h * .34), inner, round(u * .085),
                   font="playfair", italic=True, weight=500, line=1.1),
                _t("— NAME, ROLE", m, round(h * (0.78 if tall > 1.1 else 0.8)), inner, round(u * .035),
                   font="mono", color="#c9c5bd", weight=500),
            ]}],
        },
        "thumbnail": {
            "label": "Thumbnail",
            "pages": [{"bg": BLACK, "layers": [
                {"type": "rect", "x": 0, "y": 0, "w": round(w * .6) if w > h else w, "h": h if w > h else round(h * .62),
                 "fill": "#151516"},
                _t("THREE WORDS MAX", round(m * .8), round(h * .14), (round(w * .6) if w > h else w) - round(m * 1.6),
                   fit_size("THREE WORDS MAX", (round(w * .6) if w > h else w) - round(m * 1.6),
                            round(h * .62) if w > h else round(h * .44), weight=900),
                   weight=900, upper=True, line=0.98),
                {"type": "rect", "x": round(m * .8), "y": round(h * .86) if w > h else round(h * .66),
                 "w": round(u * .2), "h": 12, "fill": AMBER},
            ]}],
        },
        "announcement": {
            "label": "Announcement",
            "pages": [{"bg": BLACK, "layers": [
                _t("NEW", m, round(h * .14), inner, round(u * .04), font="mono", color=AMBER, weight=500),
                _t("Say what shipped.", m, round(h * .14 + u * .07), inner, round(u * .11), weight=800,
                   line=1.0),
                _t("One line on why it matters to the person reading.", m, round(h * .14 + u * .42), inner,
                   round(u * .045), color="#c9c5bd", line=1.3),
                {"type": "rect", "x": m, "y": round(h * .8), "w": round(u * .34), "h": round(u * .1),
                 "fill": AMBER, "radius": round(u * .05)},
                _t("Try it free", m, round(h * .8 + u * .025), round(u * .34), round(u * .04), weight=700,
                   color="#110c00", align="center"),
            ]}],
        },
    }


def templates(size: str = "tiktok-carousel") -> list[dict]:
    w, h, _ = SIZES.get(size, SIZES["tiktok-carousel"])
    return [{"id": k, "label": v["label"], "pages": len(v["pages"])} for k, v in _templates(w, h).items()]


# --------------------------------------------------------------------------- CRUD

def _write(d: Path, doc: dict) -> None:
    tmp = d / "design.json.tmp"
    tmp.write_text(json.dumps(doc, indent=1))
    tmp.replace(d / "design.json")


def create(title: str = "", size: str = "tiktok-carousel", template: str = "blank",
           w: int | None = None, h: int | None = None) -> dict:
    if size not in SIZES and not (w and h):
        raise DesignError(f"size must be one of {', '.join(SIZES)} (or give w and h)")
    dw, dh = (int(w), int(h)) if (w and h) else SIZES[size][:2]
    tpls = _templates(dw, dh)
    if template not in tpls:
        raise DesignError(f"template must be one of {', '.join(tpls)}")
    did = new_id()
    d = designs_root() / did
    (d / "assets").mkdir(parents=True)
    (d / "export").mkdir()
    doc = clean_doc({"id": did, "title": title or tpls[template]["label"], "w": dw, "h": dh,
                     "pages": copy.deepcopy(tpls[template]["pages"])})
    doc["id"] = did
    doc["created"] = doc["updated"] = _now()
    _write(d, doc)
    return doc


def load(design_id: str) -> dict:
    d = design_dir(design_id)
    doc = clean_doc(json.loads((d / "design.json").read_text()))
    doc["id"] = design_id
    return doc


def save(design_id: str, doc: dict) -> dict:
    d = design_dir(design_id)
    old = json.loads((d / "design.json").read_text())
    new = clean_doc(doc)
    new["id"] = design_id
    new["created"] = old.get("created") or _now()
    new["updated"] = _now()
    for p in new["pages"]:  # images must point at files that exist in this design
        p["layers"] = [lay for lay in p["layers"] if lay["type"] != "image" or (d / lay["src"]).is_file()]
    _write(d, new)
    return new


def list_designs() -> list[dict]:
    out = []
    for f in designs_root().glob("d-*/design.json"):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        thumb = f.parent / "export" / "page-1.png"
        out.append({"id": f.parent.name, "title": doc.get("title", ""), "w": doc.get("w"), "h": doc.get("h"),
                    "pages": len(doc.get("pages") or []), "updated": doc.get("updated", ""),
                    "thumb": "export/page-1.png" if thumb.is_file() else ""})
    out.sort(key=lambda x: x["updated"], reverse=True)
    return out


def delete(design_id: str) -> dict:
    d = design_dir(design_id)
    trash = designs_root() / ".trash"
    trash.mkdir(exist_ok=True)
    shutil.move(str(d), str(trash / d.name))
    return {"ok": True, "id": design_id, "trashed": True}


def duplicate(design_id: str) -> dict:
    d = design_dir(design_id)
    doc = load(design_id)
    nid = new_id()
    nd = designs_root() / nid
    shutil.copytree(d, nd)
    doc["id"] = nid
    doc["title"] = (doc["title"] + " (copy)")[:120]
    doc["created"] = doc["updated"] = _now()
    _write(nd, doc)
    return doc


# --------------------------------------------------------------------------- assets

def add_asset(design_id: str, data: bytes, *, name_hint: str = "img") -> str:
    """Store image bytes (PNG/JPEG/WebP only) as assets/<name>. Returns 'assets/<name>'."""
    from hermes_studio import photo

    d = design_dir(design_id)
    try:
        img = photo.decode(data)
    except photo.PhotoError as e:
        raise DesignError(str(e)) from None
    stem = re.sub(r"[^a-z0-9-]", "", name_hint.lower())[:24] or "img"
    name = f"{stem}-{secrets.token_hex(5)}.png" if img.shape[2] == 4 else f"{stem}-{secrets.token_hex(5)}.jpg"
    photo.write(d / "assets" / name, img)
    return f"assets/{name}"


def add_asset_file(design_id: str, path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_file():
        raise DesignError(f"no file {path}")
    if p.stat().st_size > 40 * 1024 * 1024:
        raise DesignError("image too large (40 MB max)")
    return add_asset(design_id, p.read_bytes(), name_hint=p.stem)


def asset_path(design_id: str, rel: str) -> Path:
    if not ASSET_RE.match(rel):
        raise DesignError("bad asset name")
    p = design_dir(design_id) / rel
    if not p.is_file():
        raise DesignError(f"no asset {rel}")
    return p


def save_export(design_id: str, page: int, data: bytes) -> str:
    """Store a browser-rendered page PNG as export/page-<n>.png."""
    from hermes_studio import photo

    d = design_dir(design_id)
    photo.decode(data)  # refuse anything that isn't a real image
    if not data.startswith(b"\x89PNG"):
        raise DesignError("export must be PNG")
    n = int(_num(page, 1, MAX_PAGES, 1))
    (d / "export" / f"page-{n}.png").write_bytes(data)
    return f"export/page-{n}.png"


# --------------------------------------------------------------------------- render (Pillow)

def _font(font_id: str, size: float, weight: int):
    from PIL import ImageFont

    file = FONTS.get(font_id, FONTS["archivo"])[0]
    f = ImageFont.truetype(str(FONT_DIR / file), max(1, round(size)))
    try:
        axes = f.get_variation_axes()
        vals = []
        for ax in axes:
            tag = ax.get("name", b"")
            tag = tag.decode() if isinstance(tag, bytes) else str(tag)
            if tag.lower().startswith("weight"):
                vals.append(max(int(ax["minimum"] or 0), min(int(ax["maximum"] or 1000), weight)))
            else:
                vals.append(ax.get("default", ax["minimum"]))
        if vals:
            f.set_variation_by_axes(vals)
    except Exception:  # static font or FreeType without variations: use as is
        pass
    return f


def _rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    a = int(c[6:8], 16) if len(c) == 8 else 255
    return r, g, b, round(a * opacity)


def wrap_text(text: str, font, width: float, spacing: float = 0) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for word in words:
            trial = (cur + " " + word) if cur else word
            if _text_w(trial, font, spacing) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _text_w(s: str, font, spacing: float) -> float:
    return font.getlength(s) + spacing * max(0, len(s) - 1)


def fit_size(text: str, width: float, height: float, *, font: str = "archivo", weight: int = 800,
             line: float = 0.98, upper: bool = True, max_size: float = 600) -> int:
    """Largest type size where every word fits the width and the wrapped block fits the height."""
    lo, hi = 8, int(max_size)
    t = text.upper() if upper else text
    while lo < hi:
        mid = (lo + hi + 1) // 2
        f = _font(font, mid, weight)
        words_ok = all(_text_w(wd, f, 0) <= width for wd in t.split())
        lines = wrap_text(t, f, width)
        if words_ok and len(lines) * mid * line <= height:
            lo = mid
        else:
            hi = mid - 1
    return lo


def text_height(layer: dict) -> float:
    font = _font(layer["font"], layer["size"], layer["weight"])
    text = layer["text"].upper() if layer.get("upper") else layer["text"]
    n = len(wrap_text(text, font, layer["w"], layer["spacing"] * layer["size"] / 1000))
    return n * layer["size"] * layer["line"]


def _shadowed(tile, lay: dict):
    """A layer's drop shadow, with the layer centred on the grown tile."""
    if not lay.get("shadow"):
        return tile
    shadow, pad = _shadow_tile(tile, lay["shadow"])
    shadow.alpha_composite(tile, (pad, pad))
    return shadow


def _shadow_tile(tile, shadow: dict):
    """A blurred shadow of the tile's alpha, padded so it can be pasted at the tile's top-left."""
    from PIL import Image, ImageFilter

    ang = math.radians(shadow["dir"])
    dx, dy = shadow["offset"] * math.cos(ang), shadow["offset"] * math.sin(ang)
    blur = shadow["blur"]
    pad = math.ceil(blur * 2 + abs(dx) + abs(dy)) + 2
    canvas = Image.new("RGBA", (tile.width + 2 * pad, tile.height + 2 * pad), (0, 0, 0, 0))
    alpha = tile.getchannel("A").point(lambda v: round(v * shadow["opacity"]))
    if blur:
        alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
    shade = Image.new("RGBA", tile.size, _rgba(shadow["color"]))
    shade.putalpha(alpha)
    canvas.alpha_composite(shade, (round(pad + dx), round(pad + dy)))
    return canvas, pad


def _outline(tile, thick: int, color: tuple, *, fill: bool):
    """Stroke around the tile's alpha, with the original fill kept (outline) or removed (hollow)."""
    from PIL import Image, ImageFilter

    grown = tile.getchannel("A").filter(ImageFilter.MaxFilter(thick * 2 + 1))
    out = Image.new("RGBA", tile.size, color)
    out.putalpha(grown)
    if fill:
        out.alpha_composite(tile)
    return out


def _stamped(tile, copies: list[tuple]):
    """Copies of the tile behind it at (dx, dy, opacity), for echo and splice."""
    from PIL import Image

    pad = math.ceil(max(abs(dx) for dx, _, _ in copies) + max(abs(dy) for _, dy, _ in copies)) + 2
    canvas = Image.new("RGBA", (tile.width + 2 * pad, tile.height + 2 * pad), (0, 0, 0, 0))
    for dx, dy, op in copies:
        canvas.alpha_composite(_with_opacity(tile.copy(), op), (round(pad + dx), round(pad + dy)))
    canvas.alpha_composite(tile, (pad, pad))
    return canvas


def _apply_text_effect(tile, lay: dict):
    """Canva's text effects: shadow, lift, hollow, outline, splice, echo, glitch, neon."""
    from PIL import Image, ImageFilter

    eff = lay.get("effect")
    if not eff:
        return tile
    kind = eff["kind"]
    ang = math.radians(eff["dir"])
    dx, dy = eff["offset"] * math.cos(ang), eff["offset"] * math.sin(ang)
    if kind in ("shadow", "lift"):
        spec = eff
        if kind == "lift":  # Canva's one-click soft lift: blur only, no offset
            spec = {**eff, "offset": 0, "blur": max(eff["blur"], lay["size"] * 0.18),
                    "opacity": 0.35 + eff["opacity"] * 0.45}
        shadow, pad = _shadow_tile(tile, spec)
        shadow.alpha_composite(tile, (pad, pad))
        return shadow
    if kind == "neon":
        glow = tile.getchannel("A").filter(ImageFilter.GaussianBlur(max(2, eff["blur"] or lay["size"] * 0.14)))
        glow = glow.point(lambda v: min(255, round(v * (0.6 + eff["opacity"]))))
        canvas = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        g = Image.new("RGBA", tile.size, _rgba(lay["color"]))  # neon glows in the text's own colour
        g.putalpha(glow)
        canvas.alpha_composite(g)
        canvas.alpha_composite(tile)
        return canvas
    if kind in ("hollow", "outline"):
        return _outline(tile, max(1, round(eff["thickness"])), _rgba(eff["color"]), fill=kind == "outline")
    if kind == "echo":
        return _stamped(tile, [(2 * dx, 2 * dy, 0.25), (dx, dy, 0.5)])
    if kind == "splice":
        return _stamped(_outline(tile, max(1, round(eff["thickness"])), _rgba(lay["color"]), fill=False),
                        [(dx, dy, eff["opacity"])])
    if kind == "glitch":
        _r, _g, _b, a = tile.split()
        canvas = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        for col, ox in ((_rgba("#00f0ff"), -dx), (_rgba("#ff2d6a"), dx)):
            layer = Image.new("RGBA", tile.size, col)
            layer.putalpha(a)
            canvas.alpha_composite(layer.crop((max(0, round(-ox)), 0, tile.width, tile.height)), (max(0, round(ox)), 0))
        canvas.alpha_composite(tile)
        return canvas
    return tile



BLENDS = ("multiply", "screen", "overlay", "softlight")


def clean_adjust(adjust) -> dict | None:
    """Photo adjustments, each -100..100 except blur 0..100. None when everything is neutral."""
    if not isinstance(adjust, dict):
        return None
    out = {k: _num(adjust.get(k), 0, 100, 0) if k == "blur" else _num(adjust.get(k), -100, 100, 0)
           for k in ("brightness", "contrast", "saturation", "warmth", "blur", "sharpen")}
    return out if any(v for v in out.values()) else None


def _apply_adjust(tile, adjust: dict):
    """Brightness, contrast, saturation, warmth, blur and sharpen. Neutral values change nothing."""
    from PIL import Image, ImageEnhance, ImageFilter

    if adjust.get("brightness"):
        tile = ImageEnhance.Brightness(tile).enhance(1 + adjust["brightness"] / 100)
    if adjust.get("contrast"):
        tile = ImageEnhance.Contrast(tile).enhance(1 + adjust["contrast"] / 100)
    if adjust.get("saturation"):
        tile = ImageEnhance.Color(tile).enhance(max(0, 1 + adjust["saturation"] / 100))
    if adjust.get("warmth"):
        r, g, b, a = tile.split()
        w = adjust["warmth"] / 100
        r = r.point(lambda v: min(255, max(0, v * (1 + 0.25 * w))))
        b = b.point(lambda v: min(255, max(0, v * (1 - 0.25 * w))))
        tile = Image.merge("RGBA", (r, g, b, a))
    if adjust.get("blur"):
        tile = tile.filter(ImageFilter.GaussianBlur(adjust["blur"] / 12))
    if adjust.get("sharpen"):
        tile = tile.filter(ImageFilter.UnsharpMask(radius=2, percent=int(adjust["sharpen"] * 2.5), threshold=2))
    return tile


def _blend(base, tile, x: float, y: float, mode: str) -> None:
    """Composite a tile onto the page with a blend mode, clipped to the page."""
    from PIL import Image, ImageChops

    x, y = round(x), round(y)
    region = (max(0, x), max(0, y), min(base.width, x + tile.width), min(base.height, y + tile.height))
    if region[0] >= region[2] or region[1] >= region[3]:
        return
    crop = tile.crop((region[0] - x, region[1] - y, region[2] - x, region[3] - y))
    dst = base.crop(region)
    op = {"multiply": ImageChops.multiply, "screen": ImageChops.screen,
          "overlay": ImageChops.overlay, "softlight": ImageChops.soft_light}[mode]
    blended = op(dst.convert("RGBA"), Image.new("RGBA", crop.size, (0, 0, 0, 0)))
    # blend the colour, then reveal it by the tile's own alpha
    mixed = op(dst, crop)
    mixed.putalpha(crop.getchannel("A"))
    out = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    out.alpha_composite(dst)
    out.alpha_composite(mixed)
    base.paste(out, region[:2])
    del blended

def _place(base, tile, x: float, y: float, angle: float, blend: str = "") -> None:
    """Paste a tile, rotated about its centre, with an optional blend mode."""
    if blend in BLENDS and not angle:
        _blend(base, tile, x, y, blend)
        return
    _paste_rotated(base, tile, x, y, angle)


def _paste_rotated(base, tile, x: float, y: float, angle: float) -> None:
    """Paste RGBA tile with its top-left at (x, y), rotated about its centre."""
    from PIL import Image

    if angle:
        cx, cy = x + tile.width / 2, y + tile.height / 2
        tile = tile.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
        x, y = cx - tile.width / 2, cy - tile.height / 2
    base.alpha_composite(tile, (round(x), round(y))) if x >= 0 and y >= 0 else _composite_any(base, tile, x, y)


def _composite_any(base, tile, x: float, y: float) -> None:
    """alpha_composite refuses negative offsets; crop the tile instead."""
    x, y = round(x), round(y)
    cx, cy = max(0, -x), max(0, -y)
    if cx >= tile.width or cy >= tile.height:
        return
    base.alpha_composite(tile.crop((cx, cy, tile.width, tile.height)), (max(0, x), max(0, y)))


def _with_opacity(tile, opacity: float):
    if opacity >= 1:
        return tile
    a = tile.getchannel("A").point(lambda v: round(v * opacity))
    tile.putalpha(a)
    return tile


def _rounded_mask(w: int, h: int, r: float):
    from PIL import Image, ImageDraw

    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=max(0, min(r, min(w, h) / 2)), fill=255)
    return m


def _draw_image(base, d: Path, lay: dict) -> None:
    from PIL import Image, ImageChops, ImageOps

    w, h = max(1, round(lay["w"])), max(1, round(lay["h"]))
    src = Image.open(d / lay["src"]).convert("RGBA")
    if lay.get("flip"):
        src = ImageOps.mirror(src)
    if lay.get("fit") == "contain":
        src.thumbnail((w, h), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        tile.alpha_composite(src, ((w - src.width) // 2, (h - src.height) // 2))
    else:
        tile = ImageOps.fit(src, (w, h), Image.Resampling.LANCZOS)
    if lay.get("adjust"):
        tile = _apply_adjust(tile, lay["adjust"])
    if lay.get("radius"):
        tile.putalpha(ImageChops.multiply(tile.getchannel("A"), _rounded_mask(w, h, lay["radius"])))
    tile = _shadowed(tile, lay)
    _place(base, _with_opacity(tile, lay["opacity"]),
                   lay["x"] - (tile.width - w) / 2, lay["y"] - (tile.height - h) / 2, lay["angle"], lay.get("blend", ""))


def _draw_shape(base, lay: dict) -> None:
    from PIL import Image, ImageDraw

    sw = lay.get("stroke_w") or 0
    w, h = max(1, round(lay["w"])), max(1, round(lay["h"]))
    if lay["type"] == "line":
        th = max(1, round(sw))
        tile = Image.new("RGBA", (w, th), _rgba(lay["stroke"]))
        _place(base, _with_opacity(tile, lay["opacity"]), lay["x"], lay["y"] - th / 2, lay["angle"], lay.get("blend", ""))
        return
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(tile)
    fill = _rgba(lay["fill"]) if lay.get("fill") else None
    outline = _rgba(lay["stroke"]) if lay.get("stroke") and sw else None
    box = (0, 0, w - 1, h - 1)
    if lay["type"] == "ellipse":
        dr.ellipse(box, fill=fill, outline=outline, width=round(sw))
    else:
        dr.rounded_rectangle(box, radius=min(lay.get("radius", 0), min(w, h) / 2), fill=fill, outline=outline,
                             width=round(sw))
    tile = _shadowed(tile, lay)
    _place(base, _with_opacity(tile, lay["opacity"]),
                   lay["x"] - (tile.width - w) / 2, lay["y"] - (tile.height - h) / 2, lay["angle"], lay.get("blend", ""))


def _draw_text(base, lay: dict) -> None:
    from PIL import Image, ImageDraw

    font = _font(lay["font"], lay["size"], lay["weight"])
    text = lay["text"].upper() if lay.get("upper") else lay["text"]
    track = lay["spacing"] * lay["size"] / 1000  # Fabric charSpacing is 1/1000 em
    lines = wrap_text(text, font, lay["w"], track)
    lh = lay["size"] * lay["line"]
    pad = 0  # text background fills the text box exactly, as in the desk editor
    w = max(1, round(lay["w"]))
    h = max(1, round(len(lines) * lh))
    tile = Image.new("RGBA", (w, h), _rgba(lay["bg"]) if lay.get("bg") else (0, 0, 0, 0))
    dr = ImageDraw.Draw(tile)
    color = _rgba(lay["color"])
    asc, desc = font.getmetrics()
    for i, line in enumerate(lines):
        lw = _text_w(line, font, track)
        x = pad + {"left": 0, "center": (lay["w"] - lw) / 2, "right": lay["w"] - lw}[lay["align"]]
        # Fabric puts the glyph box centred in each line; match it so both renders agree.
        y = pad + i * lh + (lh - (asc + desc)) / 2
        if track:
            for ch in line:
                dr.text((x, y), ch, font=font, fill=color)
                x += font.getlength(ch) + track
        else:
            dr.text((x, y), line, font=font, fill=color)
    if lay.get("italic") and lay["font"] not in ("playfair", "caveat"):
        tile = tile.transform(tile.size, Image.Transform.AFFINE, (1, 0.2, -0.2 * h / 2, 0, 1, 0), Image.Resampling.BICUBIC)
    tile = _apply_text_effect(tile, lay)
    # Effects grow the tile; keep the original text box centred inside the grown tile.
    _place(base, _with_opacity(tile, lay["opacity"]),
                   lay["x"] - (tile.width - w) / 2, lay["y"] - (tile.height - h) / 2, lay["angle"], lay.get("blend", ""))


def render_page(doc: dict, d: Path, index: int):
    from PIL import Image

    page = doc["pages"][index]
    base = Image.new("RGBA", (doc["w"], doc["h"]), _rgba(page["bg"]))
    for lay in page["layers"]:
        t = lay["type"]
        if t == "image":
            if (d / lay["src"]).is_file():
                _draw_image(base, d, lay)
        elif t == "text":
            _draw_text(base, lay)
        else:
            _draw_shape(base, lay)
    return base.convert("RGB")


def render(design_id: str, *, pages: list[int] | None = None, fmt: str = "png") -> dict:
    """Render pages to export/page-<n>.<fmt>. Returns absolute paths (for agents)."""
    if fmt not in ("png", "jpg"):
        raise DesignError("format must be png or jpg")
    doc = load(design_id)
    d = design_dir(design_id)
    want = pages or list(range(1, len(doc["pages"]) + 1))
    files = []
    for n in want:
        if not 1 <= n <= len(doc["pages"]):
            raise DesignError(f"page {n} out of range (1-{len(doc['pages'])})")
        img = render_page(doc, d, n - 1)
        out = d / "export" / f"page-{n}.{fmt}"
        if fmt == "jpg":
            img.save(out, quality=93, optimize=True, progressive=True)
        else:
            img.save(out, optimize=True)
        files.append(str(out))
    return {"ok": True, "id": design_id, "files": files, "w": doc["w"], "h": doc["h"]}


# --------------------------------------------------------------------------- agent edits

def apply_ops(design_id: str, ops: list[dict]) -> dict:
    """Small edit language for agents, so they don't have to resend the whole document.

    ops: {"op": "add_page", "bg"?, "after"?} | {"op": "delete_page", "page"} |
         {"op": "add", "page", "layer": {...}} | {"op": "update", "page", "index", "set": {...}} |
         {"op": "remove", "page", "index"} | {"op": "add_image", "page", "path", "x"?, "y"?, "w"?, "h"?, "fit"?} |
         {"op": "background", "page", "color"} | {"op": "title", "title"}
    Pages are 1-based; layer index is 0-based, bottom to top.
    """
    doc = load(design_id)
    if not isinstance(ops, list):
        raise DesignError("ops must be a list")
    for op in ops[:200]:
        kind = (op or {}).get("op")
        pages = doc["pages"]

        def page_at(key: str = "page", ops_=op, pages_=pages) -> dict:
            n = int(_num(ops_.get(key), 1, 10_000, 1))
            if n > len(pages_):
                raise DesignError(f"page {n} out of range (1-{len(pages_)})")
            return pages_[n - 1]

        if kind == "add_page":
            after = int(_num(op.get("after"), 0, len(pages), len(pages)))
            pages.insert(after, {"bg": _color(op.get("bg"), BLACK) or BLACK, "layers": []})
        elif kind == "delete_page":
            if len(pages) == 1:
                raise DesignError("a design keeps at least one page")
            pages.remove(page_at())
        elif kind == "add":
            page_at()["layers"].append(op.get("layer") or {})
        elif kind == "add_image":
            rel = add_asset_file(design_id, str(op.get("path") or ""))
            page_at()["layers"].append({"type": "image", "src": rel, "x": op.get("x", 0), "y": op.get("y", 0),
                                        "w": op.get("w", doc["w"]), "h": op.get("h", doc["h"]),
                                        "fit": op.get("fit", "cover"), "radius": op.get("radius", 0)})
        elif kind == "update":
            layers = page_at()["layers"]
            i = int(_num(op.get("index"), -1, 10_000, -1))
            if not 0 <= i < len(layers):
                raise DesignError(f"layer {i} out of range (0-{len(layers) - 1})")
            layers[i] = {**layers[i], **(op.get("set") or {})}
        elif kind == "remove":
            layers = page_at()["layers"]
            i = int(_num(op.get("index"), -1, 10_000, -1))
            if not 0 <= i < len(layers):
                raise DesignError(f"layer {i} out of range")
            layers.pop(i)
        elif kind == "background":
            page_at()["bg"] = _color(op.get("color"), BLACK) or BLACK
        elif kind == "title":
            doc["title"] = str(op.get("title") or doc["title"])
        else:
            raise DesignError(f"unknown op {kind!r}")
    return save(design_id, doc)


def template_pages(template: str, w: int, h: int) -> list[dict]:
    """A template's pages laid out for a w x h design (for 'add pages from template')."""
    tpls = _templates(int(w), int(h))
    if template not in tpls:
        raise DesignError(f"template must be one of {', '.join(tpls)}")
    return clean_doc({"w": w, "h": h, "pages": copy.deepcopy(tpls[template]["pages"])})["pages"]


def resize(design_id: str, size: str = "", w: int | None = None, h: int | None = None) -> dict:
    """Copy a design into a new size (like Canva's Resize). Layers keep their place relative to the
    page and text scales with the smaller side, so nothing runs off the edge. The original stays."""
    if size and size in SIZES:
        nw, nh = SIZES[size][:2]
    elif w and h:
        nw, nh = int(w), int(h)
    else:
        raise DesignError(f"size must be one of {', '.join(SIZES)} (or give w and h)")
    src = load(design_id)
    sx, sy = nw / src["w"], nh / src["h"]
    s = min(sx, sy)
    pages = []
    for p in src["pages"]:
        layers = []
        for lay in p["layers"]:
            lay = dict(lay)
            cx, cy = lay["x"] + lay["w"] / 2, lay["y"] + lay.get("h", 0) / 2
            if lay["type"] == "image" and lay["w"] >= src["w"] * 0.9 and lay.get("h", 0) >= src["h"] * 0.9:
                lay.update(x=0, y=0, w=nw, h=nh)  # full-bleed stays full-bleed
                layers.append(lay)
                continue
            if lay["type"] == "text":
                th = text_height(lay)
                lay["size"] = lay["size"] * s
                nwid = min(lay["w"] * s if sx > sy else lay["w"] * sx, nw)
                # Same centre rule as shapes, so text on a card stays on its card.
                lay["x"], lay["y"], lay["w"] = cx * sx - nwid / 2, (lay["y"] + th / 2) * sy - th * s / 2, nwid
            else:
                ow, oh = lay["w"], lay.get("h", 0)
                nwid, nhei = ow * s, oh * s
                if lay["type"] in ("rect", "line") and ow >= src["w"] * 0.9:
                    nwid = ow * sx  # full-width bars stay full width
                nx, ny = cx * sx - nwid / 2, cy * sy - nhei / 2
                # A layer that touches an edge stays on that edge (a cut-out photo sitting on the bottom, a side panel).
                edge = 2
                if lay["x"] <= edge:
                    nx = lay["x"] * s
                elif lay["x"] + ow >= src["w"] - edge:
                    nx = nw - nwid + (lay["x"] + ow - src["w"]) * s
                if lay["type"] != "line":
                    if lay["y"] <= edge:
                        ny = lay["y"] * s
                    elif lay["y"] + oh >= src["h"] - edge:
                        ny = nh - nhei + (lay["y"] + oh - src["h"]) * s
                lay["x"], lay["y"], lay["w"] = nx, ny, nwid
                if "h" in lay:
                    lay["h"] = nhei
                if lay["type"] == "line":
                    lay["y"] = cy * sy
                if "radius" in lay:
                    lay["radius"] = lay["radius"] * s
            layers.append(lay)
        pages.append({"bg": p["bg"], "layers": layers})
    doc = create(f"{src['title']} ({nw}x{nh})"[:120], w=nw, h=nh)
    nd = design_dir(doc["id"])
    for f in (design_dir(design_id) / "assets").iterdir():
        if f.is_file():
            shutil.copy2(f, nd / "assets" / f.name)
    return save(doc["id"], {**doc, "pages": pages})
