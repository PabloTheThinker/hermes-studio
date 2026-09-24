# Hermes Studio

Video tools for [Hermes Agent](https://hermes-agent.nousresearch.com/). **HermesClip** is the clipper (now). A timeline editor comes later under this title.

Repo: https://github.com/PabloTheThinker/hermes-studio

Long video, YouTube, X, Twitch, or a livestream slice in. Captioned 9:16 shorts out. Nothing is posted for you.

## Needs

- Linux
- Python 3.11+
- FFmpeg with the libass `ass` filter

## Install

```bash
git clone https://github.com/PabloTheThinker/hermes-studio.git
cd hermes-studio
python3 -m venv .venv
.venv/bin/pip install -e .
```

Hermes skill: copy `skills/hermesclip/` into `$HERMES_HOME/skills/hermesclip/`.

## Localhost Studio

Create · Library · Jobs on loopback.

```bash
.venv/bin/python -m hermesclip studio --host 127.0.0.1 --port 3870
```

Open http://127.0.0.1:3870/

Paste a YouTube / X / Twitch URL (including a live stream). Live sources capture a timed slice (default 20 min), then Clip cuts. Finished runs land in Library.

## CLI

```bash
.venv/bin/python -m hermesclip probe URL
.venv/bin/python -m hermesclip run VIDEO.mp4 \
  --out ./clips --max-clips 3 \
  --layout fit --plan heuristic --pacing tight --style pop
.venv/bin/python -m hermesclip run 'https://youtube.com/watch?v=…' --live-seconds 1200
.venv/bin/python -m hermesclip list
```

- Layout: `fit` (default) | `fill`
- Styles: `pop` | `impact` | `clean`
- Pacing: `tight` | `natural`
- Live: `--live-seconds` (max 7200), `--live-from-start` (YouTube)

## Hermes plugin

Copy `hermes_plugin/hermesclip/` into `$HERMES_HOME/plugins/hermesclip/` and merge `hermesclip` into `plugins.enabled`. After a **new session**:

- `hermesclip_run`
- `hermesclip_transcribe`
- `hermesclip_plan`
- `hermesclip_list`
- `hermesclip_probe`
- `hermesclip_studio`

Does not post.

## Site

https://pablothethinker.github.io/hermes-studio/

## License

Use and share. Do not treat this as a hosted rendering service.
