# Pitivi teardown

**What it is:** GNOME's video editor, built on GStreamer Editing Services (GES).
**Version on this box:** 2023.03 from Debian apt.
**License:** LGPL-2.1-or-later (from the header of `COPYING` in the `GNOME/pitivi` GitHub mirror). GES is LGPL-2.1 (`subprojects/gst-editing-services/COPYING` in `GStreamer/gstreamer`, verified via gh api).
**Screenshots:** `screenshots/pitivi/` holds 1 official image (`01-main-window-2020.05.png`, from pitivi.org). Our own capture **failed**: under Xvfb the viewer sink opened as a separate window and the main panels did not draw. This is noted in SOURCES.md.

## 1. UI/UX

From the official 2020.05 image (`01-main-window-2020.05.png`):

- **Header bar:** Undo/Redo, Render, Save and a menu.
- **Left:** Media Library / Effect Library tabs with Import, search and tags.
- **Centre:** a Clip / Transition inspector, with Transformation X/Y/Width/Height, a keyframe diamond with prev/next, and Effects plus "Add Effect".
- **Right:** a viewer with transport controls and a timecode field.
- **Bottom:** a **layer** timeline (Layer 0, Layer 1, each with show/mute toggles and an "Add layer" button). Each clip carries video and audio together, with the waveform drawn in the clip, and a zoom slider sits on the left.
- **Right of the timeline:** a vertical strip of buttons (split/razor, delete, group/ungroup, align, paste and similar).
- **Transitions:** the orange handles where two clips overlap on Layer 1 are an overlap transition.

## 2. Functions

Visible in the official image: split, delete, layering, an overlap transition, a transform inspector with keyframes, an effect library, render. We did not fetch Pitivi's user manual this pass, so the full inventory (proxies, titles, audio tools) is **not verified**.

## 3. Keyboard model

Not verified this pass.

## 4. Architecture, stack, license, reuse

- **Stack:** Python + GTK 3 UI on GES/GStreamer. Debian's `pitivi` package depends on `python3-ges-1.0`, `python3-gst-1.0`, `gir1.2-gtk-3.0` and `gstreamer1.0-gtk3`.
- **License:** LGPL-2.1-or-later for the app; GES is LGPL-2.1.
- **Reuse verdict:**
  - Pitivi's Python code and GES are **LGPL**. Hermes Studio could use GES as a dynamically loaded library (or via GObject-introspection bindings) and comply by keeping it replaceable and shipping its source and notice. LGPL code copied *into* MIT files would make those files LGPL, so don't do that.
  - Practically, adopting GStreamer as a second media stack beside FFmpeg/PyAV is a large step. It is not recommended; MLT is the closer render-v2 candidate (`RESEARCH.md`).
  - Low activity on the GitHub mirror (126 stars; the canonical repo is on GNOME GitLab).
