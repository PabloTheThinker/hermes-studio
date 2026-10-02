# Final Cut Pro teardown (proprietary, Mac; reference only)

**Sources:** Apple's [Final Cut Pro User Guide](https://support.apple.com/guide/final-cut-pro/welcome/mac) (topic pages listed per figure in `screenshots/final-cut-pro/SOURCES.md`) and [apple.com/final-cut-pro](https://www.apple.com/final-cut-pro/).
**Screenshots:** `screenshots/final-cut-pro/` holds 28 official images (22 User Guide figures and 6 apple.com images).

## 1. UI/UX

- **Main window:** Libraries sidebar → Browser → Viewer (an optional Event Viewer for two-up source/record) → Inspector, with the **Magnetic Timeline** below. See:
  - `01-main-window-annotated.png`
  - `03-libraries-sidebar-browser-annotated.png`
  - `04-viewer-annotated.png`
  Ctrl-Cmd-1 shows/hides the Browser, Ctrl-Cmd-2 the Timeline and Cmd-4 the Inspector ([interface](https://support.apple.com/guide/final-cut-pro/final-cut-pro-interface-ver92bd100a/mac)).
- **Magnetic Timeline** ([intro](https://support.apple.com/guide/final-cut-pro/intro-to-the-magnetic-timeline-verb8fcfc133/mac)). There are no fixed tracks:
  - a **primary storyline** that closes gaps automatically
  - **connected clips** attached to storyline clips (B-roll, titles, music move with their parent)
  - **gap clips** as explicit placeholders
  - **roles** and **audio lanes** that organize audio by type (dialogue/music/effects; `06-timeline-index-roles-audio-lanes.png`)
  See `05-magnetic-timeline-annotated.png` and `20-magnetic-timeline-2.png`.
- **Skimmer vs playhead.** Hovering previews (skims) without moving the playhead.
- **Precision editor:** an expanded view of an edit point showing the outgoing and incoming media with handles (`27-precision-editor-1.png`, `28-precision-editor-2.png`).

## 2. Functions

| Area | FCP (User Guide topics) |
|---|---|
| Tools menu (`07-timeline-tools-menu.png`) | Select **A**, Trim **T** (ripple/roll/slip/slide by context), Position **P** (overwrites and leaves gap clips), Range Selection **R**, Blade **B** (hold B for a temporary blade), Zoom **Z**, Hand **H** ([editing tools](https://support.apple.com/guide/final-cut-pro/editing-tools-ver2bea7297/mac)) |
| Cuts/trims | Blade at playhead Cmd-B; Blade All Shift-Cmd-B; Trim Start Option-[, Trim End Option-], Trim to Selection Option-\\. Roll (`21/22-roll-edit-*.png`), Slip (`25/26-…`), Slide (`23/24-…`) |
| Transitions/effects | Effects and Transitions browsers; Add Default Transition Cmd-T ([keyboard shortcuts](https://support.apple.com/guide/final-cut-pro/keyboard-shortcuts-ver90ba5929/mac)); Flow transition to merge jump cuts (Guide topic "Merge jump cuts with the Flow transition") |
| Keyframes | Video animation keyframes in the timeline (`10-video-animation-keyframes-1.png`) |
| Speed | Change clip speed, variable speed, hold segments, speed transitions, reverse (Guide topics with those names; `12/13-retime-speed-*.png`) |
| Captions | Closed captions/subtitles; **Generate Captions** creates captions automatically from speech ([create closed captions](https://support.apple.com/guide/final-cut-pro/create-closed-captions-vere399dab5e/mac)); import/export/convert formats (`14-closed-captions-1.png`) |
| Music | Edit to the beat (`16-edit-to-the-beat-1.png`, `32-apple-com-beat-detection.png`) |
| Color | Color correction with curves and hue/saturation curves effects, video scopes (Guide topics; `18-color-correction-1.png`) |
| Reframe/AI | Smart Conform (`34-apple-com-smart-conform-crop.png`), object tracking (`33-…`), magnetic masks; apple.com AI highlight image (`31-…`) |
| Multicam | Up to 64 angles per the User Guide PDF |
| Proxies | Proxy and optimized media |

## 3. Keyboard model

- **Tool keys:** single letters A/T/P/R/B/Z/H, with **hold-to-temporarily-switch** (hold B, release to go back).
- **Transport:** J play reverse, K stop, L play forward; press J or L repeatedly to speed up ([keyboard shortcuts](https://support.apple.com/guide/final-cut-pro/keyboard-shortcuts-ver90ba5929/mac)).
- **Cuts:** Cmd-B blade at the playhead.
- **Trims to playhead:** Option-[ / ] trim start or end to the playhead.

## 4. Lessons for Hermes Studio

- The **magnetic primary storyline** is a strong fit for talking-head/transcript-first editing. A transcript cut is a ripple delete on the storyline, and B-roll/captions are "connected" to a word or clip so they move with it. Our 4-track plan (T1/V1/A1/A2) can get most of this by making **V1+A1 ripple by default** and **anchoring T1 text and A2 overlays to a V1 clip** (store `anchor_clip_id` + offset). This is cheap and worth deciding before the schema freezes in slice 1.
- **Hold-key temporary tools** and **Option-[ / ]** are worth copying for the keyboard map.
- **Roles** (dialogue/music/effects) map naturally to A1 voice / A2 music.
