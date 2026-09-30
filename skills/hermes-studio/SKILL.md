---
name: hermes-studio
description: Use when cutting 9:16 shorts in Hermes. Local Whisper.
---

# Hermes Studio

Clipper under **Hermes Studio**. Linux. Local Whisper + FFmpeg. Does not post.

Repo: https://github.com/PabloTheThinker/hermes-studio

## When to Use

- Long video / YouTube / X / Twitch / livestream → captioned shorts
- Another Hermes agent must clip, caption, recommend, copy, trim, or split
- User is on the localhost desk (Create / Library / Jobs)

Don't use for: auto-post, Opus cloud MCP (`mcp.opus.pro`), CapCut-class timeline editor (parked).

## Fastest path (any agent)

- MCP: `hermes-studio mcp install claude|grok|codex|cursor|hermes`, then tools `run` / `show` / `list` / `restyle` / `copy` / `doctor`.
- CLI: every command takes `--json` (one object on stdout; exit 0 ok, 1 failed, 2 bad input, 3 missing dependency, 4 not found). Long runs: `run … --detach --json` then poll `show <id> --json`.
- Unsure the box is ready: `hermes-studio doctor`.

## Procedure (Hermes plugin tools)

1. `hermes_studio_probe` — title / live / duration.
2. Prefer `hermes_studio_recommend` then `hermes_studio_run` with those fields, or `hermes_studio_run` with `--recommend`.
3. Hunt: pass `prompt`. Captions-only: `hermes_studio_captions` or `mode=captions`. Highlight: `keywords` (comma/space) plus hunt words get extra ASS color.
4. Fill layout follows a speaker if opencv 4 is installed (`hermes-studio[reframe]`).
5. `hermes_studio_list` — library. `hermes_studio_copy` — titles/hashtags (does not post).
6. `hermes_studio_edit` — `op=trim` (`start`,`end`), `op=split` (`at`), `op=duplicate`, `op=drop` (trash), `op=restore` (from `.trash`). Desk: Up/Down reorders; Dropped row restores.
7. Do **not** call `hermes_studio_desk`. Desk is `hermes-studio.service`.

New plugin tools appear on the **next** session. Never bounce the gateway for this.

## Desk

User unit `hermes-studio.service` — loopback `:3870`, Restart=on-failure.
Serve HTTPS (never Funnel). If dead, `systemctl --user restart hermes-studio`.
Create: **Best recommendation** skips the wizard after analysis. Library: Social copy, Split.

## Local MCP (optional)

```yaml
mcp_servers:
  hermes-studio:
    command: "python3"
    args: ["-m", "hermes_studio.mcp"]
    timeout: 3600
```

Not `https://mcp.opus.pro/mcp`.

## Pitfalls

- Tight pacing already drops um/uh at render. Split/trim are post-cut only.
- Haar fill is still; no per-frame tracker.
- You seal every post. Hermes Studio never publishes.
