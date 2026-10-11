# Hermes Studio Editor 1.0: one goal, one finish line

**Written:** 2026-10-11 by ILO, at Sir's order: *"have a plan and one goal to reach and complete
the video editor."*
**Supersedes** the earlier phase plan (A–K), which is now mostly shipped.
**Branch:** `feat/video-editor` (181 commits as of `8f87fc5`).

---

## The goal

> **Editor 1.0: a person can cut, grade, mix, title and export a real 1080p film from start to
> finish in the Edit page, using the core toolset a Final Cut Pro or DaVinci Resolve editor
> expects. Every tool is undoable, and the export matches the preview.**

### How we know it is done: the acceptance film

1.0 is complete when this one test passes, run for real and recorded on video:

1. **Assemble.** Import 3 or more real clips into a new project (not the demo) and put a 2–4 minute piece together from the media
   bin, using insert, overwrite and append edits with In/Out marks.
2. **Cut.** Use trim, ripple, roll, slip and slide, plus multi-select, markers and snapping.
3. **Move.** Add a speed ramp, a freeze frame, a reverse, and a Ken Burns keyframed move.
4. **Grade.** Grade with wheels, curves and white balance, apply a LUT, and isolate one
   correction with a feathered mask. Check it on the scopes.
5. **Mix.** Mix voice and music: music ducks under voice, one stereo pan, and the loudness
   reads **−14 LUFS ±1** at export.
6. **Title.** Add an animated lower-third title and an end card.
7. **Export.** Export at two presets: 1080p H.264 and 1080p vertical. Verify both with
   `ffprobe` (size, fps, duration, audio). At least 5 timestamps match the paused preview
   within the grade tolerance (median Δ≤2 out of 255).
8. **Undo and recover.** Undo back to the empty timeline and redo to the end, losing nothing.
   Kill the server mid-edit and reopen: the log is intact.
9. **Keyboard.** The whole film can be cut with the keyboard (J/K/L, I/O, B/A, comma/period,
   W/D/E for insert/overwrite/append (Final Cut's keys)), and a shortcut sheet lists every key.

If any step fails, 1.0 is not done.

### What is NOT in 1.0 (said now, so the goal can actually finish)

- Fusion-class node compositing, motion tracking, stabilisation, rotoscoping.
- Multicam, proxies and collaboration.
- GPU playback engine and HDR/ACES colour management.
- Fairlight-depth audio (buses, plugins, ADR).
- Long-form performance beyond about 30 minutes of timeline.

Each of these is a 1.x item after 1.0 ships.

---

## Where it stands today (verified against the code, `8f87fc5`)

| Area | Shipped | Missing for 1.0 |
|---|---|---|
| Timeline editing | trim, split, lift, ripple delete, move, nudge, **roll, slip, slide**, multi-select (marquee, shift-click, group move/delete), markers (colour, rename, jump), snapping, In/Out range, **bin (import/upload) + source viewer + insert W / overwrite D / append E** (3-point editing, frame-grid edit points) | shortcut sheet (M9); drag from bin to timeline |
| Playback | real preview mix on the audio clock, J/K/L shuttle, frame step, timecode, adaptive ruler | — |
| Transitions | all 58 ffmpeg xfade kinds, picker, drag to resize | — |
| Keyframes | position, scale, rotate, Ken Burns, curve editor, diamonds, drag handles, volume rubber band | opacity keyframes; easing (ease in/out) |
| Speed | constant 0.1–10×, **speed ramps** (graph UI), **reverse**, **freeze frame** (Option+F), sound follows picture, retime ripples, one time map for render/preview/split, frame-accurate render | — (M1 done) |
| Colour | primary grade (lift/gamma/gain/sat), wheels, curves (M/R/G/B), white balance + eyedropper, 5 looks, scopes (waveform/parade/vectorscope), live graded preview | **LUT (.cube) import; masks** |
| Audio | track mixer (mute/solo/gain), meters, waveforms, fades, volume keys, loudnorm | **pan, ducking (sidechain), export loudness readout** |
| Text | caption track (burned ASS, word styles) | **title objects**: position, size, font, colour, animate-in/out, lower-third + end-card templates |
| Export | one mp4 (x264), range render | **presets** (1080p, 4K, vertical, ProRes), fps, quality tier, progress + cancel, ffprobe report |
| Safety | op log only writer, per-project lock, demo-only reset, per-media frame cache | crash-recovery test (kill mid-edit) |
| UI/UX | inspector, tabs, resizable panels and tracks | **workspace pass**: Edit / Colour / Audio layouts, empty states, shortcut overlay, consistent inspector |

Roughly **70% of the 1.0 toolset is built.** What's left is mostly the edit workflow (bin and
3-point editing), titles, export and the finishing pass.

---

## The order of work (ten milestones, each pushed with proof)

Ordered so the editor becomes usable for a real film as early as possible. Each milestone
follows the house rule: op log, then render, then view(), then UI. Each is proved by a real
render or real CDP input before its commit.

| # | Milestone | Done when |
|---|---|---|
| **M1** ✅ | **Speed finish**: reverse, freeze frame (hold N seconds), sound handled (reversed / silence) | a reversed clip renders frames in reverse order (frame-number probe); a freeze holds one frame for its length. **Done** `1b3b641`, `775a541` + the freeze commit |
| **M2** ✅ | **Media bin + source viewer + 3-point editing**: bin of imported media, source monitor with its own In/Out, insert (ripple), overwrite, append, keys W / D / E (Final Cut) | a cut is built entirely from the bin with the keyboard; each edit is one undo step. **Done** `b0a8e4d` + the UI commit |
| **M3** (part 1 ✅) | **Titles**: text objects on T1 (font, size, colour, position, box), fade/slide in-out, lower-third and end-card templates. Built as ONE canvas PNG per title drawn by the Design renderer, overlaid by the render and shown by the page (not drawtext/ASS: that can't match the browser) | a title appears at the same place and size in the preview and the export (pixel-checked). **Part 1 done:** 3 templates, words, accent, fade / slide-up / slide-left / cut in and out, Alt+T, inspector; render = preview PNG (test median <2 levels; CDP side-by-side). **Part 2:** drag to position in the viewer, size, font, box on/off |
| **M4** | **Audio finish**: pan, ducking (music under voice, sidechaincompress), export loudness (ebur128) shown after a render | music measurably drops under voice; the export reads −14 LUFS ±1 |
| **M5** | **Export presets**: 1080p H.264, 4K, 1080p vertical, ProRes 422, custom fps/quality; progress bar, cancel, ffprobe summary | each preset verified with ffprobe; cancel leaves no half file |
| **M6** | **LUT import**: .cube 3D LUT on a clip, preview via the same LUT sampled, intensity | preview matches export within grade tolerance |
| **M7** | **Masks**: rectangle and ellipse, feather, invert, position/size keyframable; isolates the grade or a blur | half-frame correction with a soft edge, preview = export |
| **M8** | **Keyframe finish**: opacity keys, easing (linear / ease in / ease out / ease in-out) on every keyframe kind | an eased push-in's motion curve measured off the frames |
| **M9** | **Workspace and UI/UX pass**: Edit / Colour / Audio layouts (Resolve pages, FCP-clean), shortcut sheet (`?`), empty states, consistent inspector, crash-recovery test | screenshot set of every layout; full keyboard pass; kill-and-reopen test |
| **M10** | **The acceptance film**: run the nine-step test above on real footage, fix whatever it breaks, record it | all nine steps pass; video plus ffprobe report delivered to Sir |

**AI chat rail** (Sir's 2026-10-10 ask: left sidebar, Hermes agent plus API-key models) is a
product feature of its own, not a requirement for an editor to be "Final Cut class", so it
comes **after** 1.0 unless Sir moves it ahead. Its open blocker: the agent's chat path needs
an auth route the desk can use.

---

## Rules that hold until 1.0

- Op log first, then render, then view(), then UI. Never write `timeline.json` directly.
- Prove every step with a real render or real CDP input. A length check is not a frame check:
  the speed ramp passed its length test while showing frames 38 off.
- Test on scratch projects (`demo`, throwaway desks). Never on Sir's films.
- Bump `editor.js?v=N` with every JS change. Restart the service after Python changes.
- Push each milestone to `feat/video-editor`. Merging to `main` happens only after M10, with
  Sir's word.
