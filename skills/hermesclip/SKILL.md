---
name: hermesclip
description: Use when cutting 9:16 shorts in Hermes. Local Whisper.
---

# HermesClip (Hermes Studio)

Clipper under **Hermes Studio**. Linux. Local Whisper + FFmpeg. Does not post.

Repo: https://github.com/PabloTheThinker/hermes-studio

## When to Use

- Long video / YouTube / X / Twitch / livestream → captioned shorts
- Another Hermes agent must clip, caption, recommend, copy, trim, or split
- User is on the localhost desk (Create / Library / Jobs)

Don't use for: auto-post, Opus cloud MCP (`mcp.opus.pro`), CapCut-class timeline editor (parked).

## Procedure (agents)

1. `hermesclip_probe` — title / live / duration.
2. Prefer `hermesclip_recommend` then `hermesclip_run` with those fields, or `hermesclip_run` with `--recommend`.
3. Hunt: pass `prompt`. Captions-only: `hermesclip_captions` or `mode=captions`.
4. Fill layout follows a speaker if opencv 4 is installed (`hermesclip[reframe]`).
5. `hermesclip_list` — library. `hermesclip_copy` — titles/hashtags (does not post).
6. `hermesclip_edit` — `op=trim` (`start`,`end`), `op=split` (`at`), `op=duplicate`, `op=drop` (trash), `op=restore` (from `.trash`). Desk: Up/Down reorders; Dropped row restores.
7. Do **not** call `hermesclip_studio`. Desk is `hermes-studio.service`.

New plugin tools appear on the **next** session. Never bounce the gateway for this.

## Desk

User unit `hermes-studio.service` — loopback `:3870`, Restart=on-failure.
Serve HTTPS (never Funnel). If dead, `systemctl --user restart hermes-studio`.
Create: **Best recommendation** skips the wizard after analysis. Library: Social copy, Split.

## Local MCP (optional)

```yaml
mcp_servers:
  hermesclip:
    command: "python3"
    args: ["-m", "hermesclip.mcp"]
    timeout: 3600
```

Not `https://mcp.opus.pro/mcp`.

## Pitfalls

- Tight pacing already drops um/uh at render. Split/trim are post-cut only.
- Haar fill is still; no per-frame tracker.
- You seal every post. HermesClip never publishes.
