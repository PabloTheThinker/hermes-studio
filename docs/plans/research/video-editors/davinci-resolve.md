# DaVinci Resolve teardown (paid/free proprietary; reference only)

**What it is:** Blackmagic Design's all-in-one post suite. The site currently lists **DaVinci Resolve 21** (free) and **DaVinci Resolve Studio 21** ($295); source: [Cut page](https://www.blackmagicdesign.com/products/davinciresolve/cut) footer, fetched Oct 1, 2026.
**Install:** none (task rules).
**Screenshots:** `screenshots/davinci-resolve/` holds 27 official marketing images from blackmagicdesign.com.

## 1. UI/UX

- **Pages, not workspaces.** The bottom bar switches between Media, Cut, Edit, Fusion, Color, Fairlight and Deliver, plus a new **Photo** page in 21 ([What's new](https://www.blackmagicdesign.com/products/davinciresolve/whatsnew)). Each page is a purpose-built UI over one project/timeline. See:
  - `01-overview-edit-page.png`
  - `02-overview-cut-page.png`
  - `03-overview-color-page.png`
  - `04-overview-fairlight-page.png`
  - `05-overview-fusion-page.png`
  - `06-overview-media-page.png`
- **Edit page:** a classic NLE.
  - media pool top-left, source viewer and timeline viewer, inspector top-right, full-width track timeline (`08-edit-timeline.png`)
  - dropping a clip on the timeline viewer pops an **edit overlay**: insert, overwrite, replace, fit to fill, place on top, append at end, ripple overwrite
  - stacked and tabbed timelines
  - a timeline curve editor under clips (`12-edit-curve-keyframes.png`)
  Source: [Edit page](https://www.blackmagicdesign.com/products/davinciresolve/edit).
- **Cut page:** a speed-first editor ([Cut page](https://www.blackmagicdesign.com/products/davinciresolve/cut)).
  - **Dual timeline:** the upper one shows the whole program, the lower one is zoomed around the playhead, so "you never have to zoom again" (`19-cut-timelines-dual.png`).
  - **Source tape:** all bin clips play as one long tape (`17-cut-source-tape.png`).
  - **Smart indicator / intelligent edits** that need no in/out points (`18-cut-intelligent-edit-modes.png`).
  - **Automatic trim tools** chosen by where the mouse is, with an A/B trim editor in the viewer (`16-cut-trimming.png`).
  - **Boring detector** for long shots and jump cuts.
  - Designed for small screens (`29-cut-small-screen.png`) and for the Speed Editor hardware (`24-cut-keyboard.png`).

## 2. Functions

All from the Cut, Edit and What's-new pages linked above.

| Area | Resolve |
|---|---|
| Edit ops | Insert, overwrite, replace, fit to fill, place on top, append at end, ripple overwrite, source overwrite, smart insert, close up (AI face zoom); swap/shuffle |
| Trim | Context-sensitive smart trim (ripple, roll, slip, slide chosen by cursor position), dynamic **JKL trimming**, asymmetric trimming, multi-point trims, trim to playhead, A/B trimmer |
| Multi-track | Track targeting, locking, sync tools in headers; stacked/tabbed timelines |
| Transitions/effects | Over 100 transitions; over 80 GPU/CPU effects; OpenFX plug-ins; hover-scrub preview of any effect; Smooth Cut (optical-flow jump-cut fix) |
| Titles | Text generators; over 100 Fusion title templates (2D/3D); a subtitle generator |
| Keyframes | Diamond keyframes for any inspector parameter; keyframe and curve editors in the timeline; Dynamic Zoom (start/end boxes) |
| Speed | Retime controls, speed ramps with a curve editor; optical flow / frame blend / nearest; Speed Warp (Studio); Fit to Fill |
| Color | Color page (nodes, `25-color-nodes.png`), HDR wheels, Power Windows, Magic Mask (AI) |
| Audio | Fairlight page (`26-fairlight-mixer.png`); clip EQ with 6 bands; Fairlight FX; Voice Isolation and Music Remixer (AI); audio folders in 21 |
| Captions | Import TTML/SRT/XML/embedded MXF/IMF; subtitle tracks per language; render in or export TTML/SRT/VTT; transcription for subtitles and **text-based editing** (Studio, per the Edit page and the overview comparison) |
| Multicam | Sync bin (Cut); full multicam (Edit) with 4/9/16/25+ angles, sync by waveform/timecode/in-out |
| Proxies | "Robust Proxy Editing" (overview section heading) |
| Collaboration | Multi-user database, bin/timeline locking, built-in chat, Blackmagic Cloud |
| Export | Quick Export (presets including YouTube/Vimeo/TikTok upload) and the Deliver page |
| AI (21) | IntelliSearch (search media by content and dialogue words), AI Slate ID, AI CineFocus, Face Age Transformer, Face Reshaper, UltraSharpen, Motion Deblur, voice models (TTS from text or from a sample of your own voice), facial recognition bins, Magic Mask |

## 3. Keyboard model

- **Customization:** fully customizable, with built-in presets that mimic other editors' keymaps ([Edit page](https://www.blackmagicdesign.com/products/davinciresolve/edit), "Custom Keyboard Shortcuts").
- **Basics:** I/O mark in and out, and JKL dynamic trimming during looping playback.
- **Hardware:** dedicated keyboards (Speed Editor, Editor Keyboard) with a search dial.
- We did not fetch the full default keymap.

## 4. Lessons for Hermes Studio

- **One project, many purpose-built pages.** This is closest to how Hermes Studio already has Clips / Edit / Design pages.
- **Auto-selected trim tool by cursor zone** (ripple at an edge, roll in the middle of a cut, slip in the clip middle). This gives pro trims **without tool modes**, ideal for a beginner-first app. It is also how we would expose slip/roll later without new UI modes.
- **Dual timeline (overview + zoomed)** fixes the biggest timeline-UX pain, zooming. It is cheap for us: a 1-row mini-map over the 250 px timeline.
- **Edit overlay on drop** teaches edit types without shortcuts.
- **Boring/jump-cut detector** is an agent-friendly analysis that maps straight onto our "scenes / pacing" data.
