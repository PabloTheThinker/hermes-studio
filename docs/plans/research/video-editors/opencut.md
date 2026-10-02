# OpenCut teardown

**What it is:** "A free and open source video editor for web, desktop, and mobile" ([README](https://github.com/OpenCut-app/OpenCut)), pitched as a privacy-first, free CapCut alternative ([classic README](https://github.com/OpenCut-app/opencut-classic): "Most basic CapCut features are now paywalled").
**Two codebases (gh api, Oct 1, 2026):**
- **`OpenCut-app/OpenCut`:** MIT, 91,033 stars, last push 2026-09-24 UTC. The README says it "is being rewritten from the ground up". Planned items listed there:
  - an Editor API
  - plugins
  - a Rust core for desktop/mobile/browser
  - an **MCP server (for AI agents)**
  - headless mode
  - a scripting tab
  It is "not set up to take outside contributions yet". opencut.app still runs the classic version; the rewrite lives at new.opencut.app.
- **`OpenCut-app/opencut-classic`:** MIT ("Copyright 2025-2026 OpenCut"), **archived**, "no longer maintained".

**Screenshots:** `screenshots/opencut/` holds 2 official images (from the classic repo) and 9 of our own captures (10–18 and 20). The own captures come from the live classic web app at opencut.app, driven by Playwright with no account. In 14–18 the preview shows OpenCut's own sample portrait.

## 1. UI/UX (classic, as captured)

A CapCut-style 4-zone layout; see `10-own-editor-two-tracks.png` and `11-own-clip-selected-inspector-split.png`:

- **Left icon rail plus panel:**
  - Assets (Import, list/sort)
  - Text (`12-own-text-panel.png`)
  - Stickers (`13-…`)
  - Effects (`14-…`)
  - Transitions (`15-…`)
  - Captions (`16-…`)
  - Adjustments (`17-…`)
  - Settings (`18-…`)
- **Centre:** the preview, with timecode, play, Fit zoom and fullscreen.
- **Right:** a properties inspector with a column of icon tabs. Transform (width/height/X/Y/rotation, each with a keyframe diamond) is shown in `11-…`; the other tabs are not labelled in our capture.
- **Top bar:** project name, **Export** (popover: `20-own-export-popover.png`), theme toggle.
- **Bottom timeline:**
  - a toolbar of icon buttons; reading the icons, they look like split, split-left, split-right, link, duplicate, freeze, delete, bookmark and keyframe-graph
  - a "Main scene" selector
  - two toggles on the right (by icon, snapping and ripple) plus a zoom slider
  - tracks stacked with per-track mute/hide/lock icons
  - no fixed V/A split: element tracks only

## 2. Functions (classic)

From the command layer in `apps/web/src/commands/` (gh api) plus our captures:

| Area | OpenCut classic |
|---|---|
| Timeline element commands | insert, move, split, delete, duplicate, update, toggle-source-audio-separation |
| Effects | add / remove / reorder / toggle (`commands/timeline/element/effects`) |
| Keyframes, masks | `commands/timeline/element/keyframes`, `…/masks`; `docs/keyframes.md` |
| Tracks | add, remove, toggle mute, toggle visibility |
| Clipboard | paste, paste-keyframes |
| Undo | `Command` base class with `execute` / `undo` / `redo`, plus `BatchCommand`, which runs a list and undoes it in reverse (`base-command.ts`, `batch-command.ts`) |
| Captions | Captions panel (`16-own-captions-panel.png`); in-browser transcription is presumably via `@huggingface/transformers` (a dependency); we did not trace the code path |
| Audio | waveforms (`wavesurfer.js`), time-stretch (`soundtouchjs`) |
| Media I/O | `mediabunny` (in-browser demux/decode/encode) |
| Compositing | `opencut-wasm`: the README's `rust/` core, "GPU compositor, effects, masks, and WASM bindings" |
| Export | Export popover (format/quality) |
| AI | Transcription for captions (see above). Rewrite: MCP server and headless mode are *planned*, not shipped |

## 3. Keyboard model (classic defaults)

From `apps/web/src/actions/definitions.ts`; `docs/actions.md` describes the registry.

- **Playback:**
  - Space or k play/pause; j / l seek ∓1 s
  - ←/→ step a frame; Shift+←/→ jump 5 s
  - Home/Enter go to start; End go to end
- **Editing:**
  - **s** split at playhead
  - **q** split and remove left; **w** split and remove right
  - Backspace/Delete delete
  - Ctrl+C / Ctrl+V copy and paste at the playhead; Ctrl+D duplicate
- **Other:**
  - n toggle snapping
  - Ctrl+A select all; Esc cancel
  - Ctrl+Z undo; Ctrl+Shift+Z or Ctrl+Y redo
  - a "toggle ripple editing" action exists with no default key

## 4. Architecture, stack, license, reuse

- **Classic stack** (`apps/web/package.json`, via gh api):
  - Next.js 16.1.3, React 19, zustand 5
  - mediabunny ^1.29.1, wavesurfer.js ^7.9.8, soundtouchjs ^0.3.0
  - @huggingface/transformers ^3.8.1
  - opencut-wasm ^0.2.10 (MIT on npm)
  - deployed with @opennextjs/cloudflare
  - Bun + Docker (Postgres/Redis) for dev, per the README
- **Licenses checked:**
  - OpenCut and opencut-classic: **MIT** (repo LICENSE)
  - opencut-wasm: MIT (npm)
  - **Dependencies to watch if you copy code that imports them:**
    - mediabunny: **MPL-2.0** (gh api). File-level copyleft; using it as an unmodified npm dependency is fine.
    - soundtouchjs: **LGPL-2.1** (npm metadata).
    - wavesurfer.js: BSD-3-Clause.
    - transformers.js: Apache-2.0.
- **Reuse verdict: the one editor here whose code Hermes Studio may legally copy** (MIT, keeping the copyright and license notice).
  - **Best candidates:**
    1. The **action registry** pattern (`actions/definitions.ts`: id → label, default keys, category). It maps cleanly onto our shared MCP/ACP tool registry plus keyboard map.
    2. The **Command / BatchCommand** undo shape. It is conceptually the same as our oplog with inverses and `group_id`. Copying the idea is enough; our source of truth is the Python engine.
    3. **Timeline UI components** (React/Next.js). These are **not drop-in.** `REPO-AUDIT.md` describes the Hermes Studio UI as "One vanilla HTML/JS page… No build step, no framework", and the root `package.json` (v0.5.3) has only Electron, electron-builder and playwright-core. Borrowing OpenCut's timeline components would mean adding React plus a build step. Reading them for interaction details (drag, trim handles, snapping maths) is the realistic reuse.
  - **Caveats:**
    - Classic is archived, so there are no upstream fixes.
    - The rewrite is a moving target with no outside contributions.
    - Classic's state lives in the browser (zustand). Hermes Studio's plan makes the **engine the only writer**, so any copied UI must be re-plumbed to read engine state and send ops, never mutate locally.
  - **Watch:** the rewrite's planned MCP server and headless mode make it the closest future competitor to Hermes Studio's agent-driven editor.
