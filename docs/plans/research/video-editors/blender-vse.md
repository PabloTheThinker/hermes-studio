# Blender Video Sequencer (VSE) teardown

**What it is:** the Video Sequencer built into Blender. The manual we read is labelled "Blender 5.2 LTS Manual" ([Editing Strips](https://docs.blender.org/manual/en/latest/video_editing/edit/montage/editing.html)).
**Install:** none (we kept the pass focused).
**License:** GNU GPL. The `COPYING` file in `blender/blender` says "Apart from the GNU GPL, Blender is not available under other licenses". The source header of `source/blender/sequencer/intern/strip_edit.cc` is `SPDX-License-Identifier: GPL-2.0-or-later` (gh api, Oct 1, 2026).
**Screenshots:** `screenshots/blender-vse/` holds 13 official figures from docs.blender.org.

## 1. UI/UX

- **The Video Editing app template/workspace** ([Video Editing](https://docs.blender.org/manual/en/latest/video_editing/index.html); `01-video-editing-screen-layout.png`, `02-app-template.png`):
  - file browser
  - preview
  - properties sidebar
  - the Sequencer timeline of **channels** (numbered rows; any strip type on any channel; higher channels draw on top)
- **Strips are the unit.** Movie, Sound, Image, Color, Text, Adjustment Layer, Scene, Clip, Mask, Compositor, and Effect strips (Cross, Gamma Cross, Wipe, Speed Control, Multicam Selector, Glow, Blur, Add/Subtract/Multiply, Alpha Over…). See `03-strips-introduction-add-menu.png`, `08-strips-transitions-cross-example.png`, `09-strips-effects-multicam-example.png` and `12-strips-text-example.png`.
- **Transitions are strips** (Cross, Wipe) placed over two overlapping strips. This is the same overlap-based model as Shotcut and Pitivi.
- **Meta strips** group strips (`05-meta-example.png`). Modifiers stack per strip (`06-strip-modifiers-panel.png`, `07-sidebar-color-balance-modifier.png`, `13-vse-compositor-modifier-example.png`).

## 2. Functions

| Area | Blender VSE (manual) |
|---|---|
| Edit | Move (G), Move/Extend from Current Frame (E), **Slip Strip Contents (S)**, Snap to current frame (Shift+S), Split (K), **Hold Split (Shift+K)**, Duplicate (Shift+D), Duplicate Linked (Alt+D), Delete, **Remove Gaps (Backspace)**, Insert Gaps (Shift+=), Clear Strip Offset (Alt+O) |
| Snapping | Toggle snapping, snap targets (strips, playhead, markers, hold offsets, retiming keys) |
| Retiming | **Retiming keys** on strips (Ctrl+R toggles them), freeze frames, speed transitions, Set Speed (`04-retiming.png`); Speed Control effect strip with keyframing (`10-strips-effects-speed-control-keyframing.png`) |
| Keyframes | Any property keyframable (Blender animation system) |
| Color | Modifiers: color balance, curves, hue correct and others; Compositor modifier |
| Audio | Sound strips with volume/pan, waveform display (`11-strips-sound-editing.png`) |
| Text | Text strips (`12-strips-text-example.png`) |
| Multicam | Multicam Selector strip |
| Proxies | Proxy settings (manual section "Proxy") |
| Export | Blender's render output (FFmpeg) |

## 3. Keyboard model

From the [Editing Strips](https://docs.blender.org/manual/en/latest/video_editing/edit/montage/editing.html) page:

- **Strip edits:**
  - G move, E extend, S **slip**, K split, Shift+K hold split
  - Backspace remove gaps, Shift+= insert gaps
  - Shift+D duplicate, Alt+D duplicate linked, Delete delete
  - Ctrl+R toggles retiming keys
- **Modifiers while dragging:** Ctrl toggles snapping.
- **Blender-wide conventions:** modal G/S-style operators and right-click menus.

## 4. Architecture, stack, license, reuse

- **Stack:** C/C++ inside Blender, with FFmpeg for I/O and Python scripting (`bpy`).
- **License:** GPL (source files GPL-2.0-or-later).
- **Reuse verdict:**
  - **Code: no.**
  - **Ideas:**
    - **retiming keys drawn on the strip**: speed changes without a separate graph editor. This is a good Phase 3 speed-ramp UI.
    - "Remove Gaps" as a one-key op
    - transitions as overlap objects
    - Blender's `bpy` shows the value of a scriptable editor (which our MCP tool registry already gives us)
