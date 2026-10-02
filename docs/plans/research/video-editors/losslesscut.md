# LosslessCut teardown

**What it is:** "the swiss army knife of lossless video/audio editing", described in its README as "the ultimate cross platform FFmpeg GUI for extremely fast and lossless operations" ([README](https://github.com/mifi/lossless-cut)).
**Version on this box:** 3.69.0 from the official Linux tarball. This is also the latest GitHub release.
**License:** GPL-2.0-only (`"license": "GPL-2.0-only"` in `package.json`; gh api reports GPL-2.0).
**Screenshots:** `screenshots/losslesscut/` holds 1 official image (the README `main_screenshot.jpg`) and 7 of our own captures (10–16).

## 1. UI/UX

- **A different model: segments, not tracks.** One file is open at a time:
  - a big player
  - a single segment timeline with thumbnails and a waveform
  - a right-hand "Segments to export" list showing each segment's start/end/duration/frames/size
  - a bottom transport bar
  - top-right export-mode controls (format, "Separate files" / merge)
  See `10-own-main-window-segments-advanced-view.png`.
- **Tracks panel** listing every stream, with per-track include/exclude and metadata (`11-own-tracks-panel.png`).
- **Export dialog** with options explained inline (`16-own-export-options.png`).
- **Search-filterable keyboard & mouse shortcuts dialog.** Each action shows its internal action id (e.g. `togglePlayResetSpeed`) and an editable binding (`12-own-keyboard-shortcuts-dialog.png`). This is a good pattern: our tool registry names could be shown the same way.

## 2. Functions

From the README features list:

- **Cutting:**
  - lossless cutting (stream copy)
  - experimental "smart cut"
  - cut out or rearrange segments
  - lossless merge/concat of same-codec files
- **Streams and metadata:**
  - multi-track stream editing: combine, remove, replace or extract tracks
  - remux to another container
  - edit metadata, rotation and chapters
  - per-file timecode offset
- **Navigation:** timeline zoom and keyframe jumping, thumbnails and waveform, undo/redo.
- **Detection and segmenting:**
  - black-scene, silence and scene-change detection that turns into segments
  - split the timeline into N, or into chunks by length or size
- **Segment data:**
  - segment labels and tags
  - a JS expression language to query and mutate segments
  - import/export of segments as chapters, CSV, CUE, YouTube, and XML for DaVinci and Final Cut Pro
- **Frames:** snapshots and frame-range export.
- **Automation:**
  - "View FFmpeg last command log", so you can re-run the exact command
  - basic CLI and HTTP API
- **What it lacks:** transitions, text, effects and color. It is not a compositing editor.

## 3. Keyboard model

From our capture of the in-app shortcuts dialog, plus the Segments/Tools/Help menu captures (13–15):

- **Playback:**
  - Space play/pause; K play/pause without resetting speed
  - L speeds up and J slows down (Shift+L / Shift+J for larger steps)
  - Alt+↑/↓ change volume
- **Segments:** B splits a segment at the cursor (how we made the segments in our capture).
- **Dialogs:** E opens export, and Shift+/ (`?`) opens the shortcuts dialog.
- **Customizing:** every action can be rebound or left unbound, and the dialog is searchable.

## 4. Architecture, stack, license, reuse

- **Stack** (`package.json` v3.69.0): Electron ^42, electron-vite, Vite, React 19, TypeScript. It **spawns the `ffmpeg`/`ffprobe` executables** for all media work and ships them with the app (the 3.69.0 Linux tarball contains `resources/ffmpeg`).
  - This is the same "GPL FFmpeg as a separate executable" pattern Hermes Studio adopted in v0.5.3.
  - It is also the same app shape as ours: Electron + a media-tool subprocess.
- **License:** GPL-2.0-only.
- **Reuse verdict:**
  - **Code: no.** LosslessCut itself is GPL-2.0-only, so its TypeScript can't be copied into MIT Hermes Studio.
  - **Ideas: strongly yes.** Worth taking:
    - silence/scene detection → segments (our "remove fillers/pauses")
    - the "last FFmpeg command" transparency log (fits our agent-audit story)
    - the searchable rebindable shortcut dialog with action ids
    - the segment list as an alternative to a timeline for quick trims
    - EDL/CSV/FCP-XML import/export of cut lists
