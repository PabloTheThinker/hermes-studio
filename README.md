# HermesClip

Part of **Hermes Studio** — video tools for [Hermes Agent](https://hermes-agent.nousresearch.com/). HermesClip is the clipper (now). A timeline editor comes later under the same title.

Long video or YouTube URL in. Captioned 9:16 shorts out. Nothing is posted for you.

Local [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + FFmpeg. Optional Grok planner if `XAI_API_KEY` is set.

## Needs

- Linux
- Python 3.11+
- FFmpeg with the libass `ass` filter

## Install

```bash
git clone <this-repo>
cd hermesclip
python3 -m venv .venv
.venv/bin/pip install -e .
```

## CLI

```bash
.venv/bin/python -m hermesclip run VIDEO.mp4 \
  --out ./clips --max-clips 3 \
  --pacing tight --style pop
```

- Styles: `pop` | `impact` | `clean`
- Pacing: `tight` (cut filler and dead air) | `natural`

## Hermes plugin

Copy `hermes_plugin/hermesclip/` into `$HERMES_HOME/plugins/hermesclip/` and add `hermesclip` to `plugins.enabled`. After a **new session**, the tool is `hermesclip_run`.

## Site

Static landing: `site/index.html`.

```bash
python3 -m http.server 3860 --bind 127.0.0.1 --directory site
```

## License

Use and share. Do not treat this as a hosted rendering service.
