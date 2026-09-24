from __future__ import annotations

from dataclasses import dataclass

from hermesclip.transcribe import Word

# ASS colors are BGR (&HAABBGGRR).


@dataclass(frozen=True)
class Style:
    name: str
    font: str
    size: int
    uppercase: bool
    words_per_line: int
    primary: str
    highlight: str
    emphasis: str
    outline: str
    outline_w: int
    margin_v_fit: int
    margin_v_fill: int
    margin_x: int
    spacing: float


STYLES = {
    "pop": Style(
        "pop",
        "DejaVu Sans",
        48,
        False,
        3,
        "&H00FFFFFF",
        "&H0000E5FF",
        "&H0000FFFF",
        "&H00000000",
        3,
        88,
        220,
        72,
        1.2,
    ),
    "impact": Style(
        "impact",
        "DejaVu Sans",
        56,
        True,
        3,
        "&H00FFFFFF",
        "&H0024E2FF",
        "&H000000FF",
        "&H00000000",
        5,
        96,
        240,
        80,
        0.8,
    ),
    "clean": Style(
        "clean",
        "DejaVu Sans",
        42,
        False,
        4,
        "&H00F0F0F0",
        "&H00FFFFFF",
        "&H00FFFFFF",
        "&H00404040",
        2,
        80,
        200,
        80,
        0.6,
    ),
}


def _ts(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    emphasis: list[str] | None = None,
    play_x: int = 1080,
    play_y: int = 1920,
    style: str = "pop",
    layout: str = "fit",
) -> str:
    """Word-highlight ASS. Fit puts captions in the lower pad; fill keeps them off the chin."""
    st = STYLES.get(style, STYLES["pop"])
    margin_v = st.margin_v_fit if layout != "fill" else st.margin_v_fill
    emp = {e.lower() for e in (emphasis or [])}
    local = [
        Word(
            w.text.upper() if st.uppercase else w.text,
            max(0.0, w.start - clip_start),
            max(0.0, w.end - clip_start),
        )
        for w in words
        if w.end > clip_start and w.start < clip_end
    ]
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in local:
        if not cur:
            cur = [w]
            continue
        gap = w.start - cur[-1].end
        endish = cur[-1].text[-1:] in ".!?"
        if len(cur) >= st.words_per_line or gap > 0.55 or endish:
            groups.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        groups.append(cur)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_x}
PlayResY: {play_y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Face,{st.font},{st.size},{st.primary},&H000000FF,{st.outline},&H80000000,-1,0,0,0,100,100,{st.spacing},0,1,{st.outline_w},0,2,{st.margin_x},{st.margin_x},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for g in groups:
        g0 = max(0.0, g[0].start)
        for i, w in enumerate(g):
            a = max(g0, w.start)
            b = w.end if i + 1 == len(g) else max(w.end, g[i + 1].start)
            if b <= a:
                b = a + 0.08
            line = []
            for j, x in enumerate(g):
                raw = x.text
                low = raw.strip(".,!?").lower()
                if j == i:
                    col = rf"{{\c{st.emphasis}}}" if low in emp else rf"{{\c{st.highlight}}}"
                else:
                    col = rf"{{\c{st.primary}}}"
                line.append(col + _esc(raw))
            text = r"{\an2}" + " ".join(line)
            events.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Face,,0,0,0,,{text}")
    return header + "\n".join(events) + "\n"


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
