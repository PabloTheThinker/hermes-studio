---
name: hermesclip
description: Use when cutting 9:16 shorts in Hermes. Local Whisper.
---

# HermesClip (Hermes Studio)

Clipper under **Hermes Studio**. Linux. Local Whisper + FFmpeg. Does not post.

Repo: https://github.com/PabloTheThinker/hermes-studio

## When

Long video or YouTube URL → captioned 9:16 shorts. Hermes Agent tool, not a cloud clipper.

## Install (Hermes)

Copy `hermes_plugin/hermesclip/` to `$HERMES_HOME/plugins/hermesclip/` and merge `hermesclip` into `plugins.enabled`. New session. Tools:

- `hermesclip_run` — full cut (`src` path or URL)
- `hermesclip_transcribe` — Whisper only
- `hermesclip_plan` — score windows, no render
- `hermesclip_list` — existing clips

Never auto-post.

## CLI

```bash
git clone https://github.com/PabloTheThinker/hermes-studio.git
cd hermes-studio
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m hermesclip run VIDEO.mp4 --out ./clips --layout fit --plan heuristic
```

`--layout fit` (default) = whole frame on blur. `--layout fill` = punch-in.

## Family

Hermes Studio is the title. HermesClip ships now. Editor later, same title.
