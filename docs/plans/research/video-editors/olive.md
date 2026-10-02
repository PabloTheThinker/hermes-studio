# Olive teardown

**What it is:** a free, node-based NLE. The README itself says it "is alpha software and is considered highly unstable" ([README](https://github.com/olive-editor/olive)).
**Version on this box:** 0.2.0-nightly, build `8ac191ce`, from the official AppImage.
**Repo status:** last push 2024-12-05 UTC (gh api, Oct 1, 2026). Development looks dormant.
**License:** GPL-3.0 (verified via gh api).
**Screenshots:** `screenshots/olive/` holds 1 official image (the README `020-2.png`) and 6 of our own captures (10–15).

## 1. UI/UX

- **Premiere-like dock layout.** See `10-own-main-window-sequence.png` and `14-own-tools-menu.png`:
  - top-left: Footage Viewer / Parameter Editor (tabs)
  - top-right: Sequence Viewer
  - bottom-left: Project bin + History
  - centre: a vertical tool strip
  - bottom: Timeline, with an Audio Monitor (meters) on the far right
- **Inspector as a node graph.** The Parameter Editor shows a clip's node chain (Transform, etc.; `11-own-clip-selected-parameter-editor.png`). A Node Editor exposes the compositing graph directly (`12-own-node-editor.png`). Olive is the only OSS editor here that is node-based throughout, like Resolve Fusion.
- **History panel next to the bin.** This is the same idea as Shotcut's History.

## 2. Functions

From our own captures of the 0.2.0 menus plus the README:

| Area | Olive 0.2 |
|---|---|
| Cut/trim tools | Pointer, Track Select, Edit, Ripple, Rolling, Razor, Slip, Slide, Hand, Zoom, Transition, Add, Record (`14-own-tools-menu.png`); razor in use in `13-own-razor-tool.png` |
| Sequence ops | Sequence menu (`15-own-sequence-menu.png`) |
| Multi-track | Video/audio tracks |
| Transitions | Transition tool (drag between clips) |
| Effects/compositing | Node graph: every clip is a node chain |
| Color | OpenColorIO-managed color pipeline (OCIO is a required dependency in `CMakeLists.txt`) |
| Audio | Audio monitor meters |
| Keyframes | Per-parameter keyframes in the Parameter Editor |
| Export | FFmpeg-based |
| AI | None |

## 3. Keyboard model

The tool keys, read from our Tools-menu capture, follow Premiere's single-letter scheme:

| Key | Tool |
|---|---|
| V | Pointer |
| D | Track Select |
| X | Edit |
| B | Ripple |
| N | Rolling |
| C | Razor |
| Y | Slip |
| U | Slide |
| H | Hand |
| Z | Zoom |
| T | Transition |
| A | Add |
| R | Record |
| S | toggle Snapping |

## 4. Architecture, stack, license, reuse

- **Stack:** C++ with Qt 5 (Qt 6 is an experimental option), OpenGL, OpenColorIO ≥ 2.1.1, OpenImageIO ≥ 2.1.12, OpenEXR and FFmpeg (all from `CMakeLists.txt` via gh api). The engine is a node graph rendered on the GPU.
- **License:** GPL-3.0.
- **Reuse verdict:**
  - **Code: no** (GPL, and the project is unstable and dormant).
  - **Ideas:** "every clip is a node chain" is the right *internal* model for later effects. It is not for Phase 1 users, and our filter-graph render is already a node graph in effect.
  - Olive's Premiere-style tool keys are the de-facto standard to copy if we add tools.
