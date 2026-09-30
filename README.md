# Hermes Studio

Video tools for people and AI agents, built for [Hermes Agent](https://hermes-agent.nousresearch.com/). One name everywhere: the app, the `hermes-studio` command, the MCP server and the Hermes plugin.

Repo: https://github.com/PabloTheThinker/hermes-studio

Long video, YouTube, X, Twitch, or a livestream slice in. Captioned 9:16 shorts out. Nothing is posted for you.

## Download the app

Hermes Studio installs like any desktop app. The engine, FFmpeg and the downloader are inside. No Python, no terminal, no account.

- **Windows:** `Hermes-Studio-Setup-<version>.exe` from [Releases](https://github.com/PabloTheThinker/hermes-studio/releases/latest). Run it, then open Hermes Studio from the desktop or Start menu.
- **Linux:** `Hermes-Studio-<version>.AppImage` from [Releases](https://github.com/PabloTheThinker/hermes-studio/releases/latest). Make it executable (`chmod +x`) and open it.
- **macOS:** not yet.

It runs on your computer only. The speech model (about 75 MB) downloads the first time you clip; after that it works offline. Nothing is uploaded or posted.

## Command line

Install once. You need Python 3.11+ and FFmpeg with libass (the desktop app has both built in).

```bash
uv tool install git+https://github.com/PabloTheThinker/hermes-studio    # or: pipx install git+https://…
# gives you the `hermes-studio` command
hermes-studio doctor                                                      # checks FFmpeg, captions, speech, links
```

Everyday use:

```bash
hermes-studio run talk.mp4                      # 3 hook-first shorts
hermes-studio run https://youtu.be/ID -n 5      # 5 shorts from a link (live streams too)
hermes-studio run talk.mp4 --mode captions      # caption the whole video
hermes-studio run stream.mp4 --layout split     # facecam on top, gameplay below
hermes-studio run talk.mp4 --prompt "the pricing part" --filter cinematic
hermes-studio list                              # your runs, newest first
hermes-studio show <id>                         # clips, scores, files
hermes-studio open <id>                         # open the folder
hermes-studio studio                            # the desk in your browser
```

`hermes-studio --help` and `hermes-studio <command> --help` list everything. Clips are saved to your library (`clips/library` inside your Hermes folder; `hermes-studio doctor` shows where); `-o DIR` also copies them to DIR. Typos get a "did you mean".

Coming from the old `hermesclip` name? Update with the same install line, then re-run `hermes-studio mcp install <app>` so your AI app uses the new name. The old `hermesclip` command still works and tells you the new name. Old `HERMESCLIP_*` settings still work.

### For scripts and AI agents

- Add `--json` to any command: stdout is exactly one JSON object; progress goes to stderr as JSON lines.
- Exit codes: `0` ok · `1` the job failed · `2` bad input · `3` missing dependency · `4` not found. Errors carry `code` and a `hint`.
- `hermes-studio run … --detach --json` returns an id straight away; poll `hermes-studio show <id> --json` until `status` is `completed` or `failed`.
- Each clip in a result has `path`, `title`, `score`, `start`, `end` and `seconds`.

## Use it from Claude, Grok, Codex, Cursor or any MCP app

```bash
hermes-studio mcp install claude     # Claude Code
hermes-studio mcp install grok       # Grok CLI
hermes-studio mcp install codex      # Codex CLI
hermes-studio mcp install cursor     # Cursor (~/.cursor/mcp.json)
hermes-studio mcp install hermes     # Hermes Agent (config.yaml)
hermes-studio mcp config             # the JSON block for anything else
```

Then ask it: *"make 3 shorts from ~/Videos/talk.mp4"*. Tools: `run`, `show`, `list`, `restyle`, `edit`, `probe`, `recommend`, `copy`, `name`, `tools`, `doctor`. Standard MCP stdio; long runs report progress, or pass `detach: true` and poll `show`. The desktop app's **Settings → Use with your AI** shows the same lines with a copy button.

## Run from source

```bash
git clone https://github.com/PabloTheThinker/hermes-studio.git
cd hermes-studio
python3 -m venv .venv
.venv/bin/pip install -e '.[reframe]'
.venv/bin/hermes-studio doctor
```

## Hermes plugin

Copy `hermes_plugin/hermes-studio/` into `$HERMES_HOME/plugins/hermes-studio/` and add `hermes-studio` to `plugins.enabled` (or use `hermes-studio mcp install hermes`). Hermes skill: copy `skills/hermes-studio/` into `$HERMES_HOME/skills/hermes-studio/`. Tools appear in the next session. Does not post.

## Site

https://pablothethinker.github.io/hermes-studio/

## Credits

Inspired by and partly ported from [BridgeClip](https://github.com/bridge-mind/bridgeclip) by BridgeMind (MIT). The clip scoring rubric and the framing modes started there. See [NOTICE](NOTICE).

Built for [Hermes Agent](https://hermes-agent.nousresearch.com) by Nous Research.

## License

MIT. See [LICENSE](LICENSE). Third-party notices are in [NOTICE](NOTICE).

## Security

The desk is local-only and hardened against browser attacks. See [SECURITY.md](SECURITY.md), and report problems privately.
