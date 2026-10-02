# Kdenlive teardown

**What it is:** KDE's multitrack non-linear editor (NLE), built on Qt and MLT.
**Version on this box:** 24.12.3, installed from Debian apt. The online manual we read is labelled for 26.08.
**License:** GPL-3.0, from the `COPYING` file via `gh api repos/KDE/kdenlive` on Oct 1, 2026. Source files carry `SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL`, for example `src/timeline2/model/timelinemodel.cpp`.
**Screenshots:** `screenshots/kdenlive/` holds 20 official images from docs.kdenlive.org and 12 of our own captures (30–41).

## 1. UI/UX

- **Dockable panels plus workspaces.** Kdenlive is one window made of dockable widgets: Project Bin, Clip Monitor, Project Monitor, Effects/Compositions lists, Effect Stack (the inspector), Timeline, Audio Mixer, Subtitles and Speech Editor. A top-right switcher picks named workspaces: Logging, Editing, Audio, Effects and Color. The [User Interface manual](https://docs.kdenlive.org/en/user_interface.html) shows the layout. See:
  - `screenshots/kdenlive/01-ui-screen-layout.png`
  - `screenshots/kdenlive/02-workspaces.png`
  - our captures `36-own-effects-workspace.png`, `37-own-color-workspace.png`, `38-own-audio-workspace.png` and `39-own-logging-workspace.png`
- **Two monitors.** There is a Clip Monitor for the source and a Project Monitor for the timeline. This is the classic source/record model.
- **Track-based timeline.** Video tracks sit above a split, audio tracks below. Clips split their audio and video automatically when dropped (a toggle). Each track header has lock, mute/hide, active and target buttons. The status bar has toggles for snap, thumbnails, waveforms, markers and zoom. Source: [Editing manual](https://docs.kdenlive.org/en/cutting_and_assembling/editing.html), and see:
  - `03-timeline.png`
  - `05-track-header.png`
  - `20-timeline-toolbar-detail.png`
  - our capture `30-own-editing-workspace-2clips-split.png`
- **Edit modes.** Normal will not let a dropped clip overlap another. Overwrite replaces what is underneath. Insert pushes clips right, on the destination track only. Source: the Editing manual; see `10-insert-mode.gif` and `11-overwrite-mode.gif`.
- **Transcript-first editing exists as a side panel.** The Speech Editor transcribes a bin clip with VOSK or Whisper. You can select text and insert just that range, delete a selection, or use "Remove non speech zones" (VOSK only). Source: [Speech to text manual](https://docs.kdenlive.org/en/effects_and_filters/speech_to_text.html); see `17-speech-editor.png`, `18-s2t-whisper.png` and our capture `31-own-speech-editor-tab.png`.

## 2. Functions (tool inventory)

| Area | What Kdenlive has (source: manual pages above unless noted) |
|---|---|
| Cut/trim tools | Selection (S), Razor (X), Spacer (M), Slip, Ripple, Multicam tool. Esc returns to Selection from any tool. Captures: `35-own-razor-tool-active.png`, `40-own-tool-menu.png`; official: `13-slip.gif`, `12-ripple-trim.png` |
| Ripple trim to playhead | With ripple enabled, `(` cuts and removes everything left of the playhead and `)` does the same to the right |
| Edit operations | Insert, Overwrite, Extract, Lift (zone-based), 3-point editing (`09-3point-insert.gif`), ripple delete with Shift+R then Shift+Del (Extract) |
| Multi-track | Multiple video/audio tracks, targets, active-track toggles, Split Audio and Video Automatically (`08-splitAV.gif`) |
| Transitions | "Mixes" (same-track crossfades) and compositions (wipes, etc.) between tracks |
| Effects | MLT/frei0r effect stack per clip and per track, with keyframes (`07-keyframe-improvements.gif`) |
| Color | Color workspace with scopes and color-correction effects (`37-own-color-workspace.png`) |
| Audio | Audio mixer with per-track meters and faders (`34-own-audio-mixer-tab.png`), audio waveforms (zoomable 1×/2×/4×/8×), audio effects |
| Text/captions | Subtitles track and editor (`32-own-subtitles-tab.png`), automatic subtitles from speech-to-text (VOSK/Whisper, optional translation to English with SeamlessM4T), titler |
| Speed | Ctrl+drag a clip edge changes speed (`15-adjust-speed.gif`). Time remapping panel (`33-own-time-remapping-tab.png`) |
| Multicam | Multicam tool: put angles on tracks, then press 1/2/3… during playback to cut (`14-multicam.gif`) |
| Proxies / preview | Proxy clips; timeline preview render (pre-rendered zones) |
| Markers | Clip markers and timeline guides with comments |
| Export | MLT render profiles via FFmpeg |
| AI | Speech-to-text (VOSK, Whisper), translation (SeamlessM4T) |

## 3. Keyboard model

From the [Editing manual](https://docs.kdenlive.org/en/cutting_and_assembling/editing.html) and our own Tool/Timeline menu captures (`40-own-tool-menu.png`, `41-own-timeline-menu.png`):

- **Transport:** Space plays; J/K/L map to seek backward / pause / seek forward (defaults in `src/monitor/monitormanager.cpp`: `monitor_seek_backward` = J, `monitor_pause` = K, `monitor_seek_forward` = L). Kdenlive also ships an alternative Premiere keymap (`/usr/share/kdenlive/shortcuts/Premiere` in the 24.12.3 package). Left/Right step one frame; Shift+Left/Right step one second.
- **Tools:** S select, X razor, M spacer. Shift+R cuts at the playhead on the active track.
- **Trim:** `(` and `)` resize an item's start or end to the playhead; with ripple on, they ripple-trim to the playhead.
- **Tracks:** 1–9 select a video track; Alt+1–9 an audio track. A toggles the track active, Shift+T toggles target, Shift+A toggles all tracks.
- **Zones:** Shift+Z sets the zone to the selection. Insert/Overwrite/Extract/Lift work on the zone.
- **Modifiers:** Shift+resize trims only the audio or video part. Alt+move moves audio and video independently. Ctrl+drag an edge changes speed.

## 4. Architecture, stack, license, reuse

- **Stack:** C++ with Qt/KDE Frameworks and QML for the timeline (the `timeline2` model/view in the repo), on top of MLT (LGPL-2.1, `mltframework/mlt`), which uses FFmpeg, frei0r and LADSPA. The project file is MLT XML.
- **License:** GPL-3.0 (verified). MLT itself is LGPL-2.1 (verified via `gh api repos/mltframework/mlt`).
- **Reuse verdict for Hermes Studio (MIT):**
  - **Code: no.** GPL code cannot be linked in-process into an MIT app. It could only ship as a separate executable, and nothing here is worth that.
  - **Ideas: yes.** Worth taking:
    - the Speech Editor (insert a selected text range, delete non-speech)
    - `(` / `)` ripple-to-playhead
    - same-track "mixes" as the simplest transition model, which matches our xfade-only Phase 1
    - workspaces as saved panel layouts
    - track active/target toggles
  - **MLT** remains a render-v2 candidate (LGPL: dynamic link or a separate `melt` process). `RESEARCH.md` already covers this.
