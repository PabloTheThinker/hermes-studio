# Hermes Studio

Video and design tools for people and AI agents, built for [Hermes Agent](https://hermes-agent.nousresearch.com/). One name everywhere: the app, the `hermes-studio` command, the MCP server and the Hermes plugin.

Repo: https://github.com/PabloTheThinker/hermes-studio

Long video, YouTube, X, Twitch, or a livestream slice in. Captioned 9:16 shorts out. A Canva-style **Design** page for carousels, story covers, thumbnails and posts, which your AI agent can build and edit too. Nothing is posted for you.

## Install

One line. It downloads the latest app from this repo's Releases, checks it against the published SHA-256, and sets everything up. No admin rights, no Python, no FFmpeg, nothing else to install. Run the same line again to update.

**Linux** (any terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.sh | bash
```

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.ps1 | iex
```

You get:

- **Hermes Studio** in your app menu (Start menu and desktop on Windows).
- The **`hermes-studio` command**, using the engine inside the app, so it works with no extra setup.
- A fixed place your AI apps can start it from: `hermes-studio mcp install claude` just works.

Then:

```bash
hermes-studio doctor          # everything green?
hermes-studio app             # open the app
hermes-studio update          # later: get the newest release
```

Linux options: `… | bash -s -- --version v0.5.1` pins a release, `--uninstall` removes the app (your clips stay), `--help` lists the rest. It installs to `~/.local/share/hermes-studio` and needs no FUSE.

**macOS:** not yet. The command line below works today.

It runs on your computer only. The speech model (about 75 MB) downloads the first time you clip; after that it works offline. Nothing is uploaded or posted.

### Or download the installer yourself

From [Releases](https://github.com/PabloTheThinker/hermes-studio/releases/latest): `Hermes-Studio-Setup-<version>.exe` (Windows) or `Hermes-Studio-<version>.AppImage` (Linux: `chmod +x`, then open it). `SHA256SUMS.txt` lists the checksums.

## Design (carousels, covers, thumbnails)

Open the desk (`hermes-studio studio`) and pick **Design**. Choose a size (carousel 4:5, story 9:16, square, YouTube thumbnail, X/LinkedIn), start blank or from a template, then:

- drag, resize, rotate and snap to the centre and edges; multi-page with a page strip
- text in five bundled fonts (Archivo, Playfair Display, Caveat, JetBrains Mono, Open Sans; all OFL), colours, alignment, spacing, banners
- shapes, lines, cards, pills and a bottom shade for text over photos
- photos from your computer or your clips: remove background, enhance, looks (black and white, warm, cool, punch, fade, noir), all on your machine
- brand colours, layers, undo/redo, keyboard nudges, autosave
- resize a design into another format; export every page as PNG or JPG

Designs live in `clips/designs` in your Hermes folder as plain JSON plus images, so an AI agent and you edit the same file. From the command line:

```bash
hermes-studio design new --template carousel --size tiktok-carousel   # returns an id
hermes-studio design edit <id> '[{"op":"update","page":1,"index":0,"set":{"text":"MY HOOK"}}]'
hermes-studio design render <id> --format jpg                         # PNG/JPG per page
hermes-studio design resize <id> --size story
hermes-studio photo cutout me.jpg                                     # transparent PNG
```

Background removal uses U²-Net small (Apache-2.0, 4.5 MB, bundled; runs offline). The editor uses [Fabric.js](https://fabricjs.com) (MIT), bundled.

## Command line only (Python developers)

If you'd rather install it as a Python package: you need Python 3.11+ and FFmpeg with libass (the app above has both built in).

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

Then ask it: *"make 3 shorts from ~/Videos/talk.mp4"*. Tools: `run`, `show`, `list`, `restyle`, `edit`, `probe`, `recommend`, `copy`, `name`, `tools`, `doctor`, plus `design_new`, `design_list`, `design_show`, `design_edit`, `design_render`, `design_resize` and `photo`. Ask: *"make me a 5-slide carousel about my launch"*. Standard MCP stdio; long runs report progress, or pass `detach: true` and poll `show`. The desktop app's **Settings → Use with your AI** shows the same lines with a copy button.

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
