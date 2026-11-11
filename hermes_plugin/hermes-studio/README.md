# Hermes Studio (Hermes Agent plugin)

Local video NLE + clip factory for any Hermes Agent. Long video or URL in → captioned shorts, timeline edit, designs, photo tools. **Does not post.**

Plugin version 0.6.1.

## Install

```bash
# 1) Studio engine (CLI + desk)
curl -fsSL https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.sh | bash

# 2) This plugin (catalog, once merged)
hermes plugins install hermes-studio
```

Or from source: `hermes plugins install ./hermes_plugin/hermes-studio` after cloning this repo.

The chat tools call the `hermes-studio` CLI. If it is not installed they return a `missing_dependency` error with the install command above, instead of a raw traceback.


## What you get

| Surface | Capability |
|--------|------------|
| **Agent tools** | `hermes_studio_run` (clip/captions/reframe/tighten/transcript), recommend, edit, restyle, name, copy, design, photo, desk, probe, list |
| **Chat** | Slash command `studio` (`clip`, `captions`, `reframe`, `tighten`, `transcribe`, `this`, `desk`) |
| **CLI / MCP** | `hermes-studio` CLI and MCP server (engine package) |

## Disclosure (catalog rule 13)

- **Shell commands:** every tool runs the `hermes-studio` CLI as a subprocess (`hermes-studio <verb> ... --json`), found on `PATH`, else a source checkout at `$HERMES_STUDIO_HOME` or `~/projects/hermes-studio`, else `python -m hermes_studio`. Each call has a timeout (30 s to 60 min, by tool), so nothing waits forever under cron or the gateway.
- **Long-running background process:** `hermes_studio_desk` (and `/studio desk`) starts the local Studio desk with `subprocess.Popen` as a detached process, bound to **127.0.0.1:3870** (loopback only). It keeps running after the tool returns; stop it by ending the `hermes-studio studio` process. Its log goes to `~/.hermes/clips/studio.log`.
- **Separate engine install:** the plugin does not install the engine. Install it with `uv tool install git+https://github.com/PabloTheThinker/hermes-studio` or the `install.sh` above. Without it, every tool returns a `missing_dependency` error in chat with those commands.
- **Network:** only when you pass a URL: public media is fetched with yt-dlp / HTTP, and oEmbed is read for titles. Otherwise no network calls.
- **Optional local Ollama:** clip naming can use a local Ollama model (`HERMES_STUDIO_NAMER`). No cloud key by default.
- **Files outside the plugin:** reads the media paths you pass; writes jobs under the Studio library / project dirs, caption cues to `~/.hermes/clips/agent-cues.json`, and the desk log above.
- **Local compute:** FFmpeg + Whisper on this machine.
- **Credentials:** none read or stored. No `.env`, `auth.json` or other credential files.
- **No telemetry. Never posts** to social networks; you publish yourself.

## License

MIT · Pablo Navarro. See repo `NOTICE` for BridgeClip-derived framing credit.
