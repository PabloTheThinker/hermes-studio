# Hermes Studio (Hermes Agent plugin)

Local video NLE + clip factory for any Hermes Agent. Long video or URL in → captioned shorts, timeline edit, designs, photo tools. **Does not post.**

## Install

```bash
# 1) Studio engine (CLI + desk)
curl -fsSL https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.sh | bash

# 2) This plugin (catalog, once merged)
hermes plugins install hermes-studio
```

Or from source: `hermes plugins install ./hermes_plugin/hermes-studio` after cloning this repo.

## What you get

| Surface | Capability |
|--------|------------|
| **Agent tools** | `hermes_studio_run` (clip/captions/reframe/tighten/transcript), recommend, edit, restyle, name, copy, design, photo, desk, probe, list |
| **Desktop** | Sidebar **Studio** → in-app page `/studio` with the live timeline (tokened desk embed) |
| **CLI / MCP** | `hermes-studio` CLI and MCP server (engine package) |

## Disclosure (catalog rule 13)

- **Local compute:** FFmpeg + Whisper on the host; jobs write under the Studio library / project dirs.
- **Network:** optional fetch of public media URLs via yt-dlp / HTTP when you pass a URL; oEmbed for titles. No telemetry. Never publishes to social networks.
- **Shell:** tools invoke the `hermes-studio` CLI (or a source checkout). Desktop companion may call `shell.exec` on the gateway to mint a desk embed URL when the Studio desk is running.
- **Credentials:** none required. Optional local Ollama for clip naming (`HERMES_STUDIO_NAMER`); no cloud key by default.
- **Does not post.** You seal every publish.

## Desktop companion

`desktop/plugin.js` registers `SIDEBAR_NAV` + route `/studio`. It loads a frame URL from the Studio desk (embed path). Start the desk with `hermes_studio_desk` or `hermes-studio studio` / the user unit. Without a running desk the page shows a recoverable empty state.

## License

MIT · Pablo Navarro. See repo `NOTICE` for BridgeClip-derived framing credit.
