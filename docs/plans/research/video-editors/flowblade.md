# Flowblade teardown

**What it is:** a "multitrack non-linear video editor for Linux released under GPL 3 license" ([README](https://github.com/jliljebl/flowblade)).
**Version on this box:** 2.20 from Debian apt. The README says the latest release is 2.24 (December 2025).
**License:** GPL-3.0 (verified via gh api).
**Screenshots:** `screenshots/flowblade/` holds 3 official images (main window 2.10, compositing tools, edit-tool cursors) and 4 of our own captures (10–13).

## 1. UI/UX

- **Fixed (not dockable) layout.** See `10-own-main-window-clips-on-v1.png`:
  - bins/sequences on the left
  - media grid in the centre-left, with tabs Media / Range Log / Edit / Jobs / Render
  - monitor top-right
  - a full-width timeline at the bottom with V1–V5 / A1–A4
  - a filter list on the far right
- **Tool-centric editing.** A tool dropdown on the timeline toolbar holds 6 numbered tools (`11-own-edit-tool-menu.png`; README: "Toolset with 6 editing tools"). The cursor changes per tool (`03-cursors-edit-tools.png`).
- **Range Log.** You save in/out ranges of source clips as a "best bits" log, like Final Cut keywords or Premiere subclips.

## 2. Functions

From the README features list and our captures:

| Area | Flowblade |
|---|---|
| Edit tools | Move (1), Multitrim (2), Spacer (3), Insert (4), Cut (5), Keyframe (6), from our capture |
| Edit ops | "4 methods to insert / overwrite / append clips"; drag from monitor or media panel; clip parenting and audio sync |
| Tracks | "Max. 21 combined video and audio tracks" |
| Compositing | Track compositing with per-clip blend modes, or compositor objects (mix, zoom, move, rotate, keyframed); 19 blends; 40+ pattern wipes |
| Filters | 50+ image filters (including freeze frame); 30+ audio filters (including keyframed volume) |
| Text | Text Tool for text plates; generator plugin framework; G'MIC tool |
| Export | MLT/FFmpeg encoding, GPU VAAPI and NVENC, user-defined FFmpeg args, batch encoding |
| Other | Media relinking, USB shuttle/jog support |
| AI | None |

## 3. Keyboard model

Tools are bound to the number keys 1–6 (our capture). The clip context menu is in `13-own-clip-context-menu.png`. We did not fetch a full Flowblade shortcut list; the docs URL we tried came back empty.

## 4. Architecture, stack, license, reuse

- **Stack:** Python 3 + GTK 3 (PyGObject) on MLT's Python bindings. Debian's `flowblade` package depends on `python3-gi`, `gir1.2-gtk-3.0`, `python3-mlt` and `frei0r-plugins`. The README says media support "depends on installed MLT/FFMPEG codecs".
- **License:** GPL-3.0.
- **Reuse verdict:**
  - **Code: no.**
  - **Ideas:** it shows a **Python app can drive a real multitrack NLE on MLT**. That is relevant if we ever take MLT as render v2, via its LGPL bindings or the `melt` executable.
  - One combined trim tool ("Multitrim") instead of separate ripple/roll/slip tools echoes Resolve's context-sensitive trim and FCP's single Trim tool.
