# OpenShot teardown

**What it is:** a beginner-oriented NLE. The UI (`openshot-qt`) is Python/PyQt and the engine (`libopenshot`) is C++.
**Versions:** 3.1.1 on this box from Debian apt. Upstream's latest release is **v4.0.1**, published 2026-09-27 22:16 UTC (6:16 PM ET) according to `gh api repos/OpenShot/openshot-qt/releases/latest`. So our captures show an older UI than current.
**Licenses (verified via gh api, Oct 1, 2026):**
- `openshot-qt`: GPL-3.0
- `libopenshot`: LGPL-3.0
- `libopenshot-audio`: GPL-3.0
**Screenshots:** `screenshots/openshot/` holds 9 official images from openshot.org and 3 of our own captures (20–22). The preview renders black under Xvfb.

## 1. UI/UX

The [Main Window guide](https://www.openshot.org/static/files/user-guide/main_window.html) (4.0.1 docs) describes one main window:

- main toolbar
- function tabs (Project Files, Transitions, Effects, Emojis)
- Preview Window
- Timeline Toolbar (snapping, markers, razor, jump between markers, center on playhead)
- Zoom Slider (a mini-map you drag to zoom and pan)
- playhead/ruler (click the timecode to type an exact time; Shift+drag snaps)
- timeline with track headers (lock, keyframe-panel toggle)

New projects start with 5 tracks, and the top track is the top layer. See `screenshots/openshot/01-2-track-timeline.png`, `20-own-main-window-2-tracks.png`, `21-own-transitions-tab.png` and `22-own-effects-tab.png`.

The 4.0.x timeline toolbar groups **Snap, Retime (Timing tool) and Razor**. The Timing tool retimes a clip by dragging its edges. Clip right-click menus offer Fade, Animate/Motion presets, Rotate, Layout, Time/Speed (reverse, repeat, speed, Freeze, Freeze & Zoom), Visual Styles and Color (wheels, scopes). Source: [Clips guide](https://www.openshot.org/static/files/user-guide/clips.html).

## 2. Functions

| Area | OpenShot (official guide and features page) |
|---|---|
| Cut/trim | Razor tool, Slice All/Selected with Keep Both / Left / Right, Keep Left/Right (Ripple), drag-trim edges, Delete (Ripple), nudge by 1 or 5 frames |
| Multi-track | Layered tracks (5 by default, add more with Ctrl+Y), track lock |
| Transitions | Transition library with mask-based wipes (`09-transitions.png`). Hovering a transition previews its mask |
| Effects | Effects tab (`22-own-effects-tab.png`, `04-effects-lens-flare.png`), mask effect (`06-mask-effect-and-preview.png`) |
| Color | Color wheels editor and video scopes ("Analyze Colors"), LUTs (`03-color-view-with-lut.png`) |
| Audio | Waveforms, volume keyframes, audio visual effects (`02-audio-rainbow-bars.png`) |
| Text | Title templates (`08-title-templates.png`) |
| Keyframes | Per-property keyframes with a per-track keyframe panel (`05-keyframe-editing.png`); Fade/Motion presets write keyframes |
| Speed | Reverse, repeat, speed up/slow down, Freeze, Freeze & Zoom, Timing tool |
| Recording | Screen, webcam, mic and system audio recording, new in 4.0 (`07-recording-view.png`; openshot.org news "OpenShot 4.0") |
| Export | FFmpeg-based export profiles via libopenshot; Export Project to EDL / Adobe / Final Cut Pro formats ("partially supported") |
| AI | None listed on the pages we read |

## 3. Keyboard model

Defaults from the [Main Window guide § Keyboard Shortcuts](https://www.openshot.org/static/files/user-guide/main_window.html); all can be changed in Preferences.

- **Transport:**
  - J rewind, L fast forward, Space play/pause.
  - Left/Right (or `,` and `.`) step one frame. Home/End jump to start/end.
  - M adds a marker; Shift+M / Ctrl+Shift+M jump to the next/previous marker.
- **Tools:** C/B/R toggle the Razor, T the Timing tool, S snapping.
- **Slicing:**
  - Ctrl+K / Ctrl+J / Ctrl+L slice the selected clip, keeping both / left / right.
  - Ctrl+Shift+K/J/L slice all tracks the same way.
  - **W / Q** slice selected and keep left / right **with ripple**. This is the same idea as OpenCut's q/w.
- **Delete:** Delete removes; Shift+Delete ripple-deletes.
- **Nudge:** Ctrl+Left/Right nudges 1 frame; adding Shift nudges 5.
- **Other:** Alt+Shift+K inserts a keyframe. `=` / `-` / `\` zoom in, zoom out, fit.

## 4. Architecture, stack, license, reuse

- **Stack:**
  - `openshot-qt` is Python 3 + PyQt (the repo is Python per GitHub). The 4.0 docs mention a "QWidget timeline".
  - `libopenshot` is C++ with Python bindings, using FFmpeg, with optional ImageMagick and OpenCV (`ENABLE_MAGICK`, `ENABLE_OPENCV` in its `CMakeLists.txt`).
- **Licenses:**
  - The app is GPL-3.0.
  - `libopenshot` is LGPL-3.0, but it depends on `libopenshot-audio`, which is **GPL-3.0** (verified). So linking libopenshot pulls in a GPL dependency, and it is **not** a clean LGPL option for an MIT app.
- **Reuse verdict:**
  - **Code: no.**
  - **Ideas: yes.** Worth taking:
    - closest to Hermes Studio in spirit (Python + desktop shell, beginner-first)
    - the zoom-slider mini-map
    - right-click presets that compile to keyframes ("Fade in", "Freeze & Zoom"), a nice pattern for agent presets in Phase 2
