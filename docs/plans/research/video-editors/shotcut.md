# Shotcut teardown

**What it is:** a cross-platform NLE from the MLT maintainers (Meltytech).
**Version on this box:** 25.03.29 with MLT 7.30.0, from Debian apt.
**License:** GPL-3.0. Verified via `gh api repos/mltframework/shotcut`; the `src/main.cpp` header says "either version 3 of the License, or (at your option) any later version".
**Screenshots:** `screenshots/shotcut/` holds 5 official images from shotcut.org and 8 of our own captures (10–17). Under Xvfb the preview area renders black in our captures (an OpenGL limitation); the panels are accurate.

## 1. UI/UX

- **Panel layout.** Dockable panels: Playlist (doubles as the bin), Source/Project player (one viewer that switches between them with P), Filters (the inspector), Properties, Keyframes, History, Jobs, Export and Timeline.
- **Layouts.** Top-right buttons switch between Logging, Editing, FX, Color, Audio and Player. See:
  - `screenshots/shotcut/10-own-main-window-split-clip-history.png`
  - `14-own-color-layout.png`
  - `15-own-audio-layout.png`
  - `16-own-logging-layout.png`
- **Viewer.** One player with Source/Project tabs, unlike Kdenlive's two monitors.
- **Timeline.** Track-based, with thumbnails and waveforms (`03-waveforms.png`). Fades are drawn as handles on each clip. Overlapping two clips on the same track creates a crossfade. Source: [Features](https://www.shotcut.org/features/).
- **Filters panel.** A searchable "+" list grouped as Favorites / Video / Audio (`11-own-filters-add-menu.png`). The Keyframes panel shows parameter lanes (`13-own-keyframes-panel.png`).
- **History panel.** A visible undo stack with every command listed (`10-own-main-window-split-clip-history.png`). This is a good model for our oplog view.

## 2. Functions

Everything in this table is from the [Full List of Features](https://www.shotcut.org/features/).

| Area | Shotcut |
|---|---|
| Cut/trim | Split (S), Split All Tracks (Shift+S), trim in/out to playhead (I/O, ripple with Shift), ripple mode toggles (one track, all tracks, markers) |
| Edit ops | Append (A), Insert (V), Overwrite (B), Replace (R), Lift (Z), Ripple Delete (X), 3-point editing, nudge |
| Multi-track | Video compositing across tracks with blend modes, plus hide/mute/lock per track |
| Transitions | Same-track overlap dissolve; wipe transitions (bar, barn door, box, clock, diagonal, iris, matrix, custom gradient) |
| Effects | A long filter list: blur, chroma key, crop, LUT, masks, stabilize, motion tracker, text, Time Remap, and many more. OpenFX is work in progress |
| Color | 3-way color wheels, eye-dropper white balance, LUT, HDR10/HLG, tone-map, 10-bit end to end, linear color processing |
| Audio | Scopes (loudness, peak, waveform, spectrum), compressor, EQ, gate, normalize, RNNoise denoise, pitch compensation for speed, automatic ducking, mixing UI in the timeline, record voiceover to timeline |
| Text/captions | Create, import (SRT/VTT/ASS/SSA), edit, export and burn in subtitles; "Convert spoken word to subtitle text and text-to-speech" |
| Keyframes | Keyframes for filter parameters with easing functions |
| Speed | Speed ramping, reverse, freeze frame, Time Remap filter |
| Masking | Mask: Simple Shape / From File / Chroma Key / Apply |
| Proxies | Use Proxy toggle (F4), preview scaling 360p/540p/720p (F7–F9) |
| Export | FFmpeg-based export presets (`12-own-export-presets.png`), EDL (CMX3600) export, image sequence, batch conversion |
| AI | Speech-to-subtitles and text-to-speech (from the features list); no generative tools listed |

## 3. Keyboard model

Everything in this list is from the [Keyboard Shortcuts how-to](https://www.shotcut.org/howtos/keyboard-shortcuts/).

- **Transport:**
  - J rewind, K pause, L play / fast-forward. Space plays or pauses.
  - K+J and K+L step a frame; Left/Right also step a frame.
  - Page Up/Down jump 1 s; with Shift, 2 s; with Ctrl, 5 s.
  - I/O set in/out. Alt+Left/Right seek to the previous/next edit.
- **Editing:**
  - A append, V insert, B overwrite, R replace.
  - S split, Shift+S split all tracks.
  - Z or Del lift; X or Shift+Del ripple delete.
  - I/O trim clip in/out; Shift+I/O ripple trim.
- **Markers:** M adds or edits a marker, Alt+M adds one around the selection, `<` / `>` jump between markers.
- **Zoom and layouts:**
  - `=` / `-` / `0` zoom in, zoom out, zoom to fit.
  - Ctrl+1…0 toggle panels (e.g. Ctrl+5 Timeline, Ctrl+8 History).
  - `?` or `/` opens the shortcut list.

## 4. Architecture, stack, license, reuse

- **Stack:** C++/Qt with QML UI parts (timeline, filter UIs). MLT is the engine; FFmpeg handles I/O. The project file is MLT XML.
- **License:** the app is GPL-3.0-or-later; MLT is LGPL-2.1 (both verified).
- **Reuse verdict:**
  - **Code: no** (GPL).
  - **Ideas: yes.** Worth taking:
    - the single-key edit grammar (A/V/B/R/S/X/Z), which is very teachable and maps one-to-one onto our ops
    - the visible History panel
    - in-timeline fade handles
    - "overlap = crossfade" on the same track, which matches our xfade-only Phase 1
    - the F4 proxy toggle and preview scaling
