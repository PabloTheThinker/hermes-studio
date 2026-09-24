from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Transcript:
    language: str
    duration: float
    text: str
    words: list[Word]


def extract_wav(video: Path, wav: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        check=True,
        capture_output=True,
    )


def transcribe(video: Path, work: Path, model_size: str = "tiny") -> Transcript:
    wav = work / "audio.wav"
    extract_wav(video, wav)
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(wav), word_timestamps=True)
    words: list[Word] = []
    parts: list[str] = []
    last_end = 0.0
    for seg in segments:
        if seg.text:
            parts.append(seg.text.strip())
        for w in seg.words or []:
            t = (w.word or "").strip()
            if not t:
                continue
            words.append(Word(text=t, start=float(w.start), end=float(w.end)))
            last_end = max(last_end, float(w.end))
    duration = float(getattr(info, "duration", 0.0) or last_end)
    tr = Transcript(
        language=str(getattr(info, "language", "en") or "en"),
        duration=duration,
        text=" ".join(parts).strip(),
        words=words,
    )
    (work / "transcript.json").write_text(json.dumps(_dump(tr), indent=2))
    return tr


def load_transcript(path: Path) -> Transcript:
    data = json.loads(path.read_text())
    return Transcript(
        language=data.get("language", "en"),
        duration=float(data["duration"]),
        text=data.get("text", ""),
        words=[Word(**w) for w in data["words"]],
    )


def _dump(tr: Transcript) -> dict:
    return {
        "language": tr.language,
        "duration": tr.duration,
        "text": tr.text,
        "words": [asdict(w) for w in tr.words],
    }
