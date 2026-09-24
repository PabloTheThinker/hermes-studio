---
name: hermesclip
description: Use when cutting 9:16 shorts in Hermes. Local Whisper.
---

# HermesClip (Hermes Studio)

Clipper under **Hermes Studio**. Linux. Local Whisper + FFmpeg. Localhost library. Does not post.

Repo: https://github.com/PabloTheThinker/hermes-studio

## When

Long video, YouTube / X / Twitch URL, or a livestream → captioned 9:16 shorts.

## Localhost

```bash
python -m hermesclip studio --host 127.0.0.1 --port 3870
```

http://127.0.0.1:3870/ — Create, Library, Jobs. Loopback only.

## Hermes tools

- `hermesclip_run` — full cut (`src` path or URL; live URLs take live-seconds)
- `hermesclip_transcribe` — Whisper only
- `hermesclip_plan` — score windows, no render
- `hermesclip_list` — library
- `hermesclip_probe` — title / live flag
- `hermesclip_studio` — start loopback desk

Never auto-post. Do not bounce the gateway.

## CLI

```bash
git clone https://github.com/PabloTheThinker/hermes-studio.git
cd hermes-studio
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m hermesclip run VIDEO.mp4 --out ./clips --layout fit --plan heuristic
```

`--layout fit` (default) = whole frame on blur. `--layout fill` = punch-in.

Live YouTube / X / Twitch: timed capture (default 20 min, max 2 h), then the same planner.

## Family

Hermes Studio is the title. HermesClip ships now. Editor later, same title.
