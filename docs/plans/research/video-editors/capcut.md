# CapCut teardown (proprietary, freemium; reference only)

**What it is:** a video editor "from the creators of TikTok" ([How to use CapCut](https://www.capcut.com/resource/how-to-use-capcut), updated Sep 10, 2026). It comes as desktop, web and mobile apps.
**Install:** none (an account is needed for many features; task rules).
**Screenshots:** `screenshots/capcut/` holds 22 official images:
- 10 marketing images from capcut.com tool pages (01–10)
- 12 real desktop UI figures from the official how-to guide (11–22)

## 1. UI/UX

The desktop editor has a 4-zone layout. See `11-howto-fig1.png`, `12-howto-fig2.png` and `18-howto-fig8.png`:

- **Left panel with category tabs:** Media (local, CapCut space, and a stock **Library**), Audio (Music, Sound effects), Text (presets, effects, templates, Auto Captions), Stickers (including "AI generated"), Effects, Transitions, Filters, and similar. Source: the how-to guide §5.
- **Centre:** the player.
- **Right:** a contextual properties panel with tabs per selection type: **Video** (Basic, Mask, Cutout, Motion tracking, Auto reframe, Stabilize, Relight), **Audio** (loudness normalization, noise reduction, vocal isolation, Enhance voice), **Speed** (Normal / Curve), **Adjustment** (Basic, HSL, Curves). Source: how-to guide §2–4; see `16-howto-fig6.png` and `22-howto-fig12.png`.
- **Bottom:** the timeline, with the edit toolbar "just above the timeline track": Split, Delete left, Delete right, Delete, Add marker, Freeze, Reverse, Mirror, Rotate, Crop/resize (how-to §1; `15-howto-fig5.png`, `19-howto-fig9.png`). A main video track has overlay, text and audio tracks stacked around it.
- **Captions UI:** Auto captions panel (`04-…`), recognize spoken language (`05-…`), a caption **text list panel** where the transcript is editable as text (`06-…`), and caption style presets (`07-…`, `08-…`). Source: [auto caption generator](https://www.capcut.com/tools/auto-caption-generator).
- **Export dialog:** cover, title, frame rate up to 60 fps, resolution up to 4K, MOV/MP4, codec, bit rate, audio-only export (MP3/WAV/FLAC), and an optional "Run a copyright check". Quick share to TikTok/YouTube (how-to §1; `10-export-dialog.png`, `21-howto-fig11.png`).

## 2. Functions

All from the how-to guide unless noted.

| Area | CapCut desktop |
|---|---|
| Basic | Split, crop, freeze, reverse, rotate, flip/mirror, delete left/right, markers |
| Advanced | Keyframes, masks, transform, blend modes, adjustment (Basic/HSL/Curves), **speed curve** with presets (bullet, montage, jump cut, hero time, flash in/out) and custom curves |
| AI (free per guide) | Auto cutout, chroma key, stabilizer, background removal, AI-generated stickers, text-to-speech, relight, loudness normalization, noise reduction |
| Pro (paid export) | Vocal isolation, camera/motion tracking, auto reframe, "AI movement", removing video flickers, enhance voice |
| Assets | Filters, stickers, animations, transitions (MG, blur, split, slide, mask…), stock video, stock music, sound effects |
| Captions | Auto captions with spoken-language recognition, editable caption text list, style presets ([auto caption generator](https://www.capcut.com/tools/auto-caption-generator)) |
| Recording | Built-in voiceover recorder creates a new track; voice-changing filters (how-to FAQ) |
| Export | Up to 4K / 60 fps, MP4/MOV, audio export, copyright check, share to TikTok/YouTube |

**Freemium note.** Per the guide, Pro features can be tried free but "won't be able to export the output without a subscription". OpenCut's README cites this paywalling as its reason to exist.

## 3. Keyboard model

- **Official source:** the capcut.com help page [Why Can't I Split the Subtitles in CapCut?](https://www.capcut.com/help/split-the-subtiltes) confirms **Ctrl+B / Cmd+B** splits the selected clip at the playhead, and Ctrl/Cmd + scroll zooms the timeline.
- **Third-party lists (not official):** these also report Q/W delete left/right, B/A split/select modes and Shift+Z fit. We did not verify them against an official CapCut keymap, so they're left out of the matrix.

## 4. Lessons for Hermes Studio

- **The context-sensitive right panel** (tabs change with selection) is the beginner-friendly inspector to copy.
- **Delete left / delete right of the playhead** as one-click toolbar buttons. These are the most common "tighten the edit" operations for talking-head video. OpenCut (q/w) and OpenShot (Q/W ripple) copy them.
- **Speed-curve presets** are attractive but need keyframes. That is **Phase 3** under the plan; Phase 1 has constant `speed` only.
- **An editable caption text list** is close to our Transcript tab; CapCut puts it on the captions layer rather than making it the primary edit surface.
- **Skip:** stock libraries, stickers, cloud space, copyright check and social upload. The upload items are out of scope and also on the plan's never-in-`tools/list` list (publish/upload/post).
