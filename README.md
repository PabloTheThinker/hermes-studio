# Hermes Studio

Video tools for [Hermes Agent](https://hermes-agent.nousresearch.com/). **HermesClip** is the clipper (now). A timeline editor comes later under this title.

Repo: https://github.com/PabloTheThinker/hermes-studio

Long video or YouTube URL in. Captioned 9:16 shorts out. Nothing is posted for you.

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

## CLI

```bash
.venv/bin/python -m hermesclip run VIDEO.mp4 \
  --out ./clips --max-clips 3 \
  --layout fit --plan heuristic --pacing tight --style pop
```

- Layout: `fit` (default) | `fill`
- Styles: `pop` | `impact` | `clean`
- Pacing: `tight` | `natural`

## Hermes plugin

Copy `hermes_plugin/hermesclip/` into `$HERMES_HOME/plugins/hermesclip/` and merge `hermesclip` into `plugins.enabled`. After a **new session**: `hermesclip_run`, `hermesclip_transcribe`, `hermesclip_plan`, `hermesclip_list`.

## Site

https://pablothethinker.github.io/hermes-studio/

## License

Use and share. Do not treat this as a hosted rendering service.
