"""Transcript exports: SRT, VTT and plain text from word timings. Local only."""
from __future__ import annotations

from pathlib import Path

from hermesclip.transcribe import Transcript, Word

MAX_CHARS = 42
MAX_GAP = 0.8
MAX_SPAN = 5.0


def cues(words: list[Word]) -> list[tuple[float, float, str]]:
    """Group words into subtitle cues: ~42 chars, break on pauses and sentence ends."""
    out: list[tuple[float, float, str]] = []
    cur: list[Word] = []

    def flush() -> None:
        if cur:
            out.append((cur[0].start, cur[-1].end, " ".join(w.text for w in cur).strip()))
            cur.clear()

    for w in words:
        if cur:
            text_len = len(" ".join(x.text for x in cur)) + 1 + len(w.text)
            gap = w.start - cur[-1].end
            span = w.end - cur[0].start
            if text_len > MAX_CHARS or gap > MAX_GAP or span > MAX_SPAN:
                flush()
        cur.append(w)
        if w.text.endswith((".", "?", "!")) and len(cur) > 2:
            flush()
    flush()
    return out


def _stamp(sec: float, sep: str) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms == 1000:
        s, ms = s + 1, 0
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(words: list[Word]) -> str:
    rows = []
    for i, (a, b, text) in enumerate(cues(words), 1):
        rows.append(f"{i}\n{_stamp(a, ',')} --> {_stamp(b, ',')}\n{text}\n")
    return "\n".join(rows)


def to_vtt(words: list[Word]) -> str:
    rows = ["WEBVTT", ""]
    for a, b, text in cues(words):
        rows.append(f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n{text}\n")
    return "\n".join(rows)


def to_text(tr: Transcript) -> str:
    """Readable paragraphs: break on long pauses."""
    paras: list[str] = []
    cur: list[str] = []
    last = None
    for w in tr.words:
        if last is not None and w.start - last > 2.0 and cur:
            paras.append(" ".join(cur))
            cur = []
        cur.append(w.text)
        last = w.end
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras) if paras else (tr.text or "")


def write_exports(tr: Transcript, out_dir: Path, stem: str = "transcript") -> list[dict]:
    """Write .srt/.vtt/.txt next to the run. Returns file rows for the job."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for ext, body, label in (
        ("srt", to_srt(tr.words), "Subtitles (SRT)"),
        ("vtt", to_vtt(tr.words), "Subtitles (VTT)"),
        ("txt", to_text(tr), "Transcript (text)"),
    ):
        path = out_dir / f"{stem}.{ext}"
        path.write_text(body, encoding="utf-8")
        rows.append({"file": path.name, "kind": ext, "label": label, "bytes": path.stat().st_size})
    return rows
