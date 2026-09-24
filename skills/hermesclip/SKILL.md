---
name: hermesclip
description: Use when cutting 9:16 shorts in Hermes. Local Whisper.
---

# HermesClip (Hermes Studio)

Clipper under **Hermes Studio**. Linux. Local Whisper + FFmpeg. Does not post.

Repo: https://github.com/PabloTheThinker/hermes-studio

## When to Use

- Long video, YouTube / X / Twitch URL, or a livestream → captioned shorts
- Another Hermes agent needs to clip, caption, probe, list, or trim
- User is on the localhost desk (Create / Library / Jobs)

Don't use for: auto-post, Opus cloud MCP, CapCut-class timeline editor (parked).

## Agent tools (native plugin — prefer these)

`hermesclip_probe` → `hermesclip_run` (or `_captions`) → `hermesclip_list` → `hermesclip_edit` if a trim is needed.

- `hermesclip_run` — cut (`src`, optional `prompt` hunt, `aspect`, `layout`, `hook`, `mode`)
- `hermesclip_captions` — burn captions on the full take
- `hermesclip_transcribe` / `hermesclip_plan` — Whisper / score windows, no render
- `hermesclip_list` / `hermesclip_probe`
- `hermesclip_edit` — trim an existing file (`start`, `end`)
- `hermesclip_studio` — do not call; desk is `hermes-studio.service`

New plugin tools appear on the **next** session. Never bounce the gateway for this.

## Local MCP (optional)

Same jobs over stdio for MCP clients. Not `https://mcp.opus.pro/mcp` (that posts and spends credits).

```yaml
mcp_servers:
  hermesclip:
    command: "python3"
    args: ["-m", "hermesclip.mcp"]
    timeout: 3600
```

Run from a venv that has `hermesclip` installed. Filter out any future publish tools if someone adds them.

## Desk

User unit `hermes-studio.service` — loopback `:3870`, Restart=on-failure.
Serve HTTPS (never Funnel). If dead, `systemctl --user restart hermes-studio`. Never bounce hermes-gateway.

## CLI

```bash
python -m hermesclip run VIDEO.mp4 --out ./clips --layout fit --plan heuristic
python -m hermesclip captions VIDEO.mp4 --out ./clips
python -m hermesclip edit clip.mp4 --start 2 --end 18
```

## Family

Hermes Studio is the title. HermesClip ships now. Timeline editor later, same title.
