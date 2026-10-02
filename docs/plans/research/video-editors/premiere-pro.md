# Adobe Premiere (Pro) teardown (proprietary; text reference only)

**Source:** the [Premiere desktop user guide](https://helpx.adobe.com/premiere-pro/user-guide.html) table of contents and [Default keyboard shortcuts](https://helpx.adobe.com/premiere-pro/using/default-keyboard-shortcuts.html) (last updated Jan 7, 2026), both fetched as text with WebFetch on Oct 1, 2026. Adobe now titles the product "Adobe Premiere".
**Screenshots:** **none.** helpx.adobe.com and adobe.com returned 403s or an offline page to curl and headless Chrome, so no images could be downloaded. Nothing was substituted.

## 1. UI/UX

- **Panels and workspaces.**
  - Project panel (Icon/List/Freeform views), Source Monitor, Program Monitor, Timeline, Effect Controls, Properties panel, Essential Sound, Lumetri, Audio Track Mixer, Tools panel, History.
  - The "Overview of workspaces" topic lists 16 default workspaces (Essentials, Vertical, Learning, Assembly, Captions and Graphics, Review, Production, and others).
  - Panels dock, group and undock.
- **Source/Program two-monitor model** with source patching and track targeting.
- **Text-Based Editing:**
  - transcribe, then edit the sequence by editing the transcript
  - detect and delete pauses
  - remove all instances of one speaker
  - "Create a sequence with Paper Edit"
- **Color mode (beta):** a new dedicated grading mode (Clip Grid, HUDs, Color Controls panel).

## 2. Functions (from guide topic titles)

| Area | Premiere |
|---|---|
| Trim | Ripple, rolling, slip, slide, J/L cuts, Trim mode, asymmetrical trimming, **J-K-L dynamic trimming**, trimming tracked in History |
| Speed | Speed/Duration, **Rate Stretch tool**, Time Remapping, interpolation methods, freeze frame |
| Sequence ops | Lift/extract, sync lock, track lock, snap, Scene Edit Detection, nesting, multicam |
| Transitions | Default transitions, single-sided, Morph Cut (jump cuts), "Modern transitions" |
| Effects | Effect Controls, adjustment layers, presets, Ultra Key, Warp Stabilizer, Auto Reframe, "Modern effects" |
| Masks | Shapes/pen, **object masking** with tracking, HSL/luma masks |
| Keyframes | Full keyframe/graph editing, Bezier interpolation |
| Audio | Essential Sound, Enhance Speech, auto-ducking, loudness match, remix, Audio Track Mixer automation |
| Captions | Speech to Text, caption styles, **single-word captions**, translate captions |
| Proxies | Ingest/proxy workflow (create, attach, detach, export proxies) |
| AI | Generative Extend, Generative Media Tool, Generate Music (beta), media intelligence search, **Premiere AI Assistant (beta)** |
| Export | Media Encoder, EDL, FCP XML, AAF, OMF, Content Credentials |

## 3. Keyboard model (from the Default keyboard shortcuts page)

- Undo Ctrl+Z, Redo Ctrl+Shift+Z, Ripple Delete Shift+Delete, Group Ctrl+G, Apply Default Transitions to Selection Shift+D, Trim Edit Shift+T, Go to Next/Previous Marker Shift+M / Ctrl+Shift+M, Keyboard Shortcuts editor Ctrl+Alt+K.
- The Sequence-menu table also lists Ctrl+K and Ctrl+Shift+K (Add Edit / Add Edit to All Tracks). Our text extraction dropped those row labels, so treat the label as unconfirmed.
- The Timeline panel has nudge/slide/slip clip selection by 1 or 5 frames with modifier+arrow and modifier+`,`/`.` combos.

## 4. Lessons for Hermes Studio

- Premiere shows the incumbent direction: **text-based editing, single-word captions, pause deletion and an AI assistant panel** are now standard pro features, not niche. That validates the plan's transcript-first default.
- **Rate Stretch** (drag a clip edge to change speed) is a simple, keyframe-free speed UI that fits Phase 1's constant `speed` prop.
