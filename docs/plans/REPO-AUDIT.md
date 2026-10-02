# Hermes Studio: repo audit

Repo: https://github.com/PabloTheThinker/hermes-studio (public, default branch `main`)
Read remotely with `gh` / `gh api` on Thu Oct 1, 2026, about 3:00 AM ET. Nothing was cloned, changed or pushed.
State read: `main` after PR #31 was merged (Oct 1, 2:54 AM ET). 104 commits, 31 PRs (all merged), 4 releases (latest **v0.5.2**, Sep 30, 4:03 PM ET).

---

## 1. Short version

Hermes Studio today is **a local clipper plus a Canva-style design editor. It is not a timeline video editor yet.**
It takes a long video or a link, transcribes it with Whisper, scores moments, and renders captioned 9:16 shorts with FFmpeg.
It also has a Design page (Fabric.js) for carousels and thumbnails.
People can use it, and agents can drive it through a CLI (`--json`), an MCP server and a Hermes plugin.

The repo's own Hermes skill lists a "CapCut-class timeline editor" as **parked** (`skills/hermes-studio/SKILL.md`). What Pablo wants now is that parked piece, plus an agent chat sidebar.

The foundations are good to build on: one Python core (`api.py`), a tested JSON/exit-code contract, a working MCP server, a JSON document with an op list for designs, a packaged desktop app with FFmpeg inside, and solid security habits.

---

## 2. Stack

| Layer | What it is | Where |
|---|---|---|
| Engine / core | Python 3.11+, standard-library HTTP server, no web framework | `hermes_studio/` (~24 modules) |
| Speech-to-text | faster-whisper (default model `tiny`; presets tiny / base.en / small.en) | `transcribe.py`, `pipeline.py` |
| Media | FFmpeg + ffprobe called as subprocesses (argument lists, never a shell); libass for captions; PyAV | `render.py`, `edit.py`, `captions.py` |
| Downloads | yt-dlp (YouTube, X, Twitch, livestream slices) | `download.py` |
| Vision | OpenCV (optional `[reframe]` extra), YuNet face detector (bundled ONNX), Haar fallback, U²-Net small for cut-outs | `face.py`, `framing.py`, `photo.py` |
| Image render | Pillow (design pages rendered server-side for agents and export) | `design.py` |
| UI ("the desk") | One vanilla HTML/JS page (`ui/index.html`, ~99 KB) and `ui/design.js` (~64 KB), Fabric.js vendored. No build step, no framework | `hermes_studio/ui/` |
| Desktop app | Electron 44 shell. It starts the bundled engine (portable Python + hermes-studio + FFmpeg) on a free loopback port and loads the desk | `desktop/main.js`, `electron-builder.json` |
| Agent surfaces | CLI with `--json`; MCP stdio server (18 tools); Hermes plugin (14 tools); Hermes skill | `cli.py`, `mcp.py`, `hermes_plugin/`, `skills/` |
| CI | GitHub Actions: ruff + pytest on every PR; gitleaks; CodeQL; desktop build for Linux AppImage + Windows NSIS with SHA-pinned FFmpeg; Pages site | `.github/workflows/` |
| Packaging | One-line installers (`install.sh`, `install.ps1`) with SHA-256 checks; systemd user unit | `scripts/`, `packaging/` |

Languages GitHub reports: Python 394 KB, HTML 173 KB, JS 76 KB, Shell 24 KB, PowerShell 10 KB.

## 3. Structure (what each part does)

```
hermes_studio/
  api.py        single core: validation, errors (code + hint), results. CLI/MCP/plugin are thin layers on top
  pipeline.py   jobs: transcribe -> plan -> render, the library on disk, restyle, rename, manifests
  plan.py       clip scoring (hook/flow/value/standalone, ported from BridgeClip), optional LLM ranking
  render.py     FFmpeg filter graphs: crop/fit/split layouts, ASS captions, time-map concat (filler removal)
  edit.py       post-cut file ops: trim, split, duplicate, drop to .trash, restore
  captions.py / look.py / framing.py / face.py / layout.py / pacing.py   caption styling, filters, face-aware crop
  design.py     Design documents: JSON pages + layers, apply_ops(), Pillow render, resize, templates
  studio.py     the local web desk (port 3870): REST API + media serving, host/origin checks
  mcp.py        MCP stdio server, 18 tools, progress notifications, `mcp install <client>`
  cli.py        `hermes-studio` command (run, show, list, studio, design, photo, mcp, doctor, app, update ...)
  ui/           desk front end (Clips, Design, Other tools, Library, Jobs, Settings)
hermes_plugin/hermes-studio/   native Hermes plugin (register(ctx) -> ctx.register_tool x14)
skills/hermes-studio/          Hermes skill (SKILL.md)
desktop/                       Electron main + preload
site/                          GitHub Pages landing site and demo media
tests/                         11 files, about 91 tests (CLI/MCP contract, design, security, framing, installer ...)
```

## 4. What works today (checked against the code)

- **Clipping pipeline.** Long video or URL -> Whisper words -> scored, sentence-snapped moments -> 9:16 renders with burned-in captions, layouts (fit / fill / split), looks and filters, filler-word tightening. Jobs can be detached and polled.
- **Post-cut editing at file level only.** `edit.py` re-encodes whole files for trim and split; drop and restore use a `.trash` folder. There is **no multi-clip, multi-track timeline, no project file for a cut, and no undo for clip edits** (drop/restore is the only reversible step).
- **The Design editor is the most "editor-like" piece.** It has a JSON document per design, layer ops (`add_page`, `add`, `update`, `remove`, `add_image`, `background`, `title`), undo/redo in the UI (snapshot history in `design.js`), autosave, and server-side render so an agent can "see" a page. **This is the pattern to copy for the video timeline.**
- **Agent access is real.** MCP tools: `run, show, list, restyle, edit, probe, recommend, copy, name, tools, doctor, design_new, design_list, design_show, design_edit, design_render, design_resize, photo`. Tests guard the JSON, exit-code and MCP contracts (`tests/test_cli_contract.py`).
- **Desktop app ships for Linux and Windows** (v0.5.2: AppImage 493 MB, Setup.exe 313 MB, plus SHA256SUMS). No macOS.
- **CI is green** on the latest merge (ci, pages, CodeQL all passed). `main` is a protected branch.
- **Security posture is good for a local tool:** loopback only by default, Host allow-list (stops DNS rebinding), JSON-only writes with Origin check, strict CSP, media served only by exact job id and file name, ffmpeg/yt-dlp called without a shell.

## 5. What's missing for "an editor humans and agents both drive"

1. No timeline data model (tracks, clips with in/out points, gaps, transitions, effects, keyframes).
2. No preview/playback of a multi-clip edit. The desk plays finished MP4s only.
3. No edit history (op log) with actor (human vs agent), so no per-edit undo or diff.
4. No live sync between processes. The MCP server is a separate process from the desk, and the UI does not update when an agent edits (the Design page reads files, but there is no push channel).
5. No chat sidebar or agent session in the app. "Settings -> Use with your AI" only shows config lines to copy.
6. No scene detection (only face sampling); no frame/thumbnail-strip tool for models to look at a range of time.
7. No auth on the desk API (SECURITY.md says so). That's fine while only the local user's browser calls it. Once an agent can write through it, it needs a per-session token.

## 6. License

- **Project: MIT** (`LICENSE`, Copyright 2026 Pablo Navarro). `NOTICE` correctly credits BridgeClip (MIT), YuNet (MIT), Fabric.js (MIT), U²-Net small (Apache-2.0) and the OFL fonts.
- **Gap to fix: FFmpeg.** The desktop build downloads the **BtbN `gpl` static FFmpeg build** (`.github/workflows/desktop.yml`, lines 18-22) and ships it inside the AppImage/installer. `NOTICE` does not mention FFmpeg, its GPL license, or where to get its source. Shipping a separate GPL executable next to an MIT app is normally fine (it is a separate program, not linked in), but the GPL still asks for the license text and access to the corresponding source to go with the binary. Easy fix: add an FFmpeg section to `NOTICE` with the exact build URL and a source link, or switch to an LGPL build if x264 isn't needed. (FFmpeg's own checklist: https://ffmpeg.org/legal.html.)
- Other bundled or used pieces to list in `NOTICE` for completeness: faster-whisper (MIT) and its model weights, yt-dlp (Unlicense), PyAV, Electron (MIT) and Chromium notices, OpenCV (Apache-2.0).

## 7. README claims vs. reality

| README says | Reality | Verdict |
|---|---|---|
| "Video and design tools for people and AI agents" | True for clipping and design. There is no general video editing | OK, but don't call it a video editor yet |
| One-line install, no admin, no Python, no FFmpeg; SHA-256 checked | Installers and release assets exist; CI tests clean installs on Linux and Windows | True |
| macOS "not yet" | No mac target in `desktop.yml` | True |
| Design: drag/resize/snap, multi-page, undo/redo, autosave, export PNG/JPG, background removal | Present in `design.js` / `design.py` (undo/redo is client-side snapshots) | True |
| MCP tool list (`run` ... `photo`) | Matches `mcp.py` exactly (18 tools) | True |
| Hermes plugin tools | Plugin registers 14 tools, including `transcribe`, `plan`, `captions` that MCP doesn't expose. MCP has `design_*` split into 6 tools; the plugin has one `hermes_studio_design` | Two different agent surfaces that drift. Pick MCP as the main one |
| Plugin version | `plugin.yaml` says **0.5.1**, package is **0.5.2** | Small drift; fix at next release |
| AGENTS.md: tool list | Lists only the clip tools, not the `design_*` tools | Slightly stale |
| "Nothing is uploaded or posted" | Outbound calls are only optional AI naming, oEmbed titles, model download, yt-dlp | True |
| "The desk is local-only and hardened" | Host/Origin/CSP checks are in `studio.py`; tests in `test_security.py` | True (no auth, as documented) |
| Speech model "about 75 MB" | Default is Whisper `tiny` (~75 MB) | True |
| SKILL.md: "CapCut-class timeline editor (parked)" | Correct; that's the gap this plan fills | True |

## 8. What to reuse in the new editor

- `api.py` as the single core: add `timeline_*` behaviour there, then expose it through CLI, MCP and the desk. This is the repo's own rule in `AGENTS.md`.
- `design.py`'s `apply_ops()` pattern (validated JSON ops on a JSON document) as the model for timeline ops.
- `render.py` filter-graph building and caption burn-in, as the first render backend.
- `transcribe.py` (word timestamps) for text-based editing; `framing.py` / `face.py` for reframe.
- The MCP server's progress notifications and detach/poll pattern for long renders.
- The security rules in `studio.py` and the contract tests.
