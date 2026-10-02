# Master feature matrix: video editors vs Hermes Studio

**Date:** Oct 1, 2026 (ET). Evidence for every ✓ is in the per-editor teardowns in this folder (`<editor>.md`), which cite the doc page, repo file or our own capture.

**Legend:**

| Mark | Meaning |
|---|---|
| ✓ | Documented in a source we fetched, or seen in our own capture |
| ~ | Partial or indirect (see the note) |
| — | Not offered |
| ? | **Not verified this pass.** It may well exist; we just didn't fetch proof. |

**Baseline rows.** Undo/redo, trim edges, split, text/title, clip volume and render are marked ✓ for every mature editor, even where we didn't fetch that exact page. A — means the editor clearly isn't built for it (e.g. LosslessCut has no compositing).

**Columns:**

| Code | Editor | Code | Editor |
|---|---|---|---|
| KD | Kdenlive | BL | Blender VSE |
| SC | Shotcut | DR | DaVinci Resolve |
| OS | OpenShot | FCP | Final Cut Pro |
| OL | Olive | CC | CapCut desktop |
| LC | LosslessCut | PR | Premiere |
| OC | OpenCut classic | DS | Descript |
| FB | Flowblade | **HS** | **Hermes Studio** |
| PI | Pitivi | | |

**How the HS column maps to PLAN-MERGED.md:**

| HS mark | Meaning |
|---|---|
| **must** | Needed for Phase 0/1 (slices 0–8 plus the ACP client and the Edit page/sidebar UI) |
| **v1** | The rest of Phase 1 polish, or Phase 2 (agent quality: contact sheets, scenes/silence/speaker data, presets, draft branch) |
| **later** | Phase 3+ (keyframes UI, more transitions, MLT, WebCodecs, multicam, ducking, generative plug-ins, macOS, OTIO/FCPXML/Kdenlive import/export) |
| **never** | On the plan's never-in-`tools/list` list (publish/upload/post) |
| *(proposed)* | **Not in the plan today.** This research suggests adding it at that tier. |

## A. Media and project

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Media bin / import | ✓ | ✓ | ✓ | ✓ | ~ one file | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (`media_import`, Media tab) |
| Proxy media | ✓ | ✓ | ? | ? | — | ? | ? | ? | ✓ | ✓ | ✓ | ? | ✓ | ? | **must** (540p H.264 proxies, slice 4) |
| Clip thumbnails on timeline | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ? | ? | ✓ | ✓ | ✓ | ✓ | ? | **must** |
| Audio waveforms | ✓ | ✓ | ✓ | ? | ✓ | ~ wavesurfer dep | ? | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** |
| Scene / shot detection | ? | ? | ? | ? | ✓ | ? | ? | ? | ? | ~ boring detector | ? | ? | ✓ | ? | **must** (Scenes tab, `scenes_get`); richer data **v1** |
| Silence / pause detection | ✓ non-speech | ? | ? | ? | ✓ | ? | ? | ? | ? | ? | ? | ? | ✓ | ✓ word gaps | **v1** (Phase 2 silence data) |

## B. Transcript and AI

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Speech-to-text | ✓ VOSK/Whisper | ✓ | ? | — | — | ~ captions panel | — | ? | — | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (Whisper words → timeline time) |
| **Text-based editing** (delete words = cut media) | ~ speech editor | — | — | — | — | — | — | — | — | ✓ Studio | ? | ~ caption list | ✓ | ✓ | **must** (Transcript tab is the default) |
| Filler-word removal | ~ non-speech only | — | — | — | — | — | — | — | — | ? | ? | ? | ~ pauses | ✓ | **must** (`transcript_cut` / remove fillers, slice 7) |
| Auto captions + styles | ✓ | ✓ | ? | — | — | ✓ | — | ? | — | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (`captions_generate`, ASS burn-in) |
| Caption file export (SRT/VTT) | ? | ✓ | ? | — | ~ | ? | — | ? | — | ✓ | ✓ | ? | ✓ | ✓ | **v1** *(proposed)* |
| Caption translation | ✓ to English | ? | — | — | — | ? | — | — | — | ? | ? | ? | ✓ | ✓ | **later** |
| AI co-editor chat in app | — | — | — | — | — | — | — | — | — | — | ? | ? | ✓ beta | ✓ Underlord | **must** (Hermes sidebar) |
| Outside-agent API / MCP | — | — | — | — | ~ CLI/HTTP API | ~ planned (rewrite) | — | — | ~ Python | ~ Studio scripting API | ? | ? | ? | ✓ MCP + API | **must** (MCP + ACP, one registry) |
| Per-agent-edit undo / revert | — | — | — | — | — | — | — | — | — | — | — | — | ? | ✓ Revert per response | **must** (card Undo, group undo, checkpoints) |
| Ask / Propose / Auto gate | — | — | — | — | — | — | — | — | — | — | — | — | ? | — | **must** (engine-enforced; unique to HS) |
| Auto reframe (aspect + face) | ? | ? | ? | — | ~ lossless crop | ? | — | ? | — | ~ AI close-up | ✓ Smart Conform | ✓ | ✓ | ✓ via Underlord | **must** (`reframe`, 9:16/1:1/16:9) |
| Voice cleanup / denoise | ? | ✓ RNNoise | ? | — | — | ? | ? | ? | ? | ✓ Voice Isolation | ? | ✓ | ✓ Enhance Speech | ✓ Studio Sound | **later** *(proposed; not in plan)* |
| Generative media | — | — | — | — | — | — | — | — | — | ✓ voice/TTS | ? | ✓ stickers | ✓ Generative Extend | ✓ | **later** (optional plug-ins, new media only) |
| Content / face search | — | — | — | — | — | — | — | — | — | ✓ | ? | — | ✓ | ? | **later** |

## C. Timeline structure

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Multi-track | ✓ | ✓ | ✓ | ✓ | — segments | ✓ | ✓ | ✓ layers | ✓ channels | ✓ | ~ storyline + connected | ✓ | ✓ | ~ layers | **must** (T1/V1/A1/A2; `add/remove_track`) |
| Magnetic / auto-close-gap main track | ? | ~ ripple mode | ~ ripple keys | ~ ripple tool | — | ~ ripple toggle | ? | ? | ~ Remove Gaps | ? | ✓ | ? | ? | ✓ script order | **must**: ripple flags exist; **v1** *(proposed)*: make V1+A1 ripple by default |
| Connected / anchored clips | ? | ? | ? | ? | — | ? | ~ clip parenting | ? | ? | ? | ✓ | ? | ? | ✓ scene-attached layers | **v1** *(proposed)*: `anchor_clip_id` on T1/A2 items; decide before schema freeze |
| Snapping | ✓ | ✓ | ✓ | ✓ | ? | ✓ n | ? | ? | ✓ | ✓ | ✓ | ? | ✓ | ? | **must** |
| Markers | ✓ | ✓ | ✓ | ? | ~ labels | ? | ? | ? | ? | ✓ | ? | ✓ | ✓ | ✓ | **must** (`add_marker`) |
| Track lock / mute / hide | ✓ | ✓ | ✓ lock | ✓ | — | ✓ | ? | ✓ | ? | ✓ | ~ roles | ? | ✓ | ✓ | **v1** *(proposed)*; mute is useful even in Phase 1 |
| Nesting / compound / meta | ? | ? | ? | ? | — | ? | ? | ? | ✓ meta | ? | ? | ? | ✓ | ? | **later** |
| Timeline overview (mini-map / dual timeline) | ? | ? | ✓ zoom slider | ? | ? | ? | ? | ? | ? | ✓ dual timeline | ? | ? | ? | ? | **v1** *(proposed)* |

## D. Cutting and trimming

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Split / blade at playhead | ✓ Shift+R, X | ✓ S | ✓ Ctrl+K | ✓ C | ✓ B | ✓ s | ✓ 5 | ✓ | ✓ K | ✓ | ✓ Cmd-B | ✓ Ctrl+B | ✓ Ctrl+K¹ | ✓ S/B | **must** (`split_clip`) |
| Split all tracks | ? | ✓ Shift+S | ✓ Ctrl+Shift+K | ? | — | ? | ? | ? | ? | ? | ✓ Shift-Cmd-B | ? | ✓¹ | ? | **must** (a grouped batch of `split_clip`) |
| **Delete left / right of playhead** | ✓ ( ) with ripple | ~ Shift+I/O ripple trim | ✓ W/Q ripple | — | — | ✓ q/w | — | — | — | ? | ~ Option-[ ] | ✓ buttons | ? | — | **must**: compiles to `split_clip` + `delete_clip{ripple}` in one group (no new op) |
| Ripple delete | ✓ | ✓ X | ✓ Shift+Del | ~ | — | ? | ? | ? | ✓ Remove Gaps | ✓ | ✓ magnetic | ? | ✓ Shift+Del | ✓ | **must** (`delete_clip{ripple}`) |
| Lift (leave gap) | ✓ | ✓ Z | ✓ Delete | ? | — | ✓ Delete | ? | ? | ✓ Delete | ✓ | ✓ Position tool | ✓ | ✓ | ✓ gap clip | **must** (`delete_clip{ripple:false}`) |
| Trim edges | ✓ | ✓ | ✓ | ✓ | ✓ segment ends | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (`trim_clip`) |
| Ripple trim | ✓ | ✓ Shift+I/O | ? | ✓ B | — | ? | ? | ? | ? | ✓ | ✓ | ? | ✓ | ? | **must** (`trim_clip{ripple}`) |
| Roll edit | ? | ? | ? | ✓ N | — | ? | ? | ? | ? | ✓ | ✓ | ? | ✓ | ? | **v1**: no `roll` op in Phase 1, but it equals two `trim_clip`s in one `group_id` ⚠ |
| Slip | ✓ | ? | ? | ✓ Y | — | ? | ? | ? | ✓ S | ✓ | ✓ | ? | ✓ | ✓ Y | **v1** ⚠ no Phase 1 op; needs `slip_clip` (shift source_in/out) |
| Slide | ? | ? | ? | ✓ U | — | ? | ? | ? | ? | ✓ | ✓ | ? | ✓ | ? | **later** ⚠ |
| Context-sensitive trim (no tool modes) | ? | ? | ? | ? | — | ? | ~ Multitrim | ? | ? | ✓ | ✓ Trim tool | ? | ? | ? | **v1** *(proposed UI)* |
| Insert edit | ✓ | ✓ V | ? | ? | — | ✓ | ✓ | ? | ? | ✓ | ✓ | ? | ✓ | ✓ paste | **must** (`insert_clip`) |
| Overwrite / replace / append | ✓ | ✓ B/R/A | ? | ? | — | ? | ✓ | ? | ? | ✓ | ✓ | ? | ✓ | ? | **v1** (append = insert at end, **must**) |
| 3-point editing / source monitor | ✓ | ✓ | ? | ✓ | — | ? | ✓ | ? | — | ✓ | ✓ | ? | ✓ | ? | **later**: skip for a beginner-first app |
| Nudge by frames | ? | ✓ | ✓ Ctrl+←/→ | ? | — | ? | ? | ? | ? | ? | ? | ? | ✓ | ? | **v1** (`move_clip`) |
| Copy / paste / duplicate | ? | ✓ | ✓ | ? | — | ✓ | ? | ? | ✓ | ? | ? | ? | ✓ | ✓ | **v1** |
| Multicam | ✓ | — | — | — | — | — | — | — | ✓ | ✓ | ✓ | ? | ✓ | ? | **later** (plan Phase 3) |
| A/B trim / precision editor | ? | ? | ? | ? | — | ? | ? | ? | ? | ✓ | ✓ | ? | ✓ Trim mode | ? | **later** |

## E. Transitions, effects, color

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Crossfade / dissolve | ✓ mix | ✓ overlap | ✓ | ✓ | — | ✓ | ✓ | ✓ overlap | ✓ Cross | ✓ | ✓ Cmd-T | ✓ | ✓ | ✓ | **must** (`xfade` only) |
| Audio crossfade | ✓ | ✓ | ? | ? | — | ? | ? | ? | ? | ✓ | ? | ? | ✓ | ? | **must** (`acrossfade`) |
| Other transitions (wipes, slides…) | ✓ | ✓ | ✓ | ? | — | ✓ | ✓ | ? | ✓ Wipe | ✓ | ✓ | ✓ | ✓ | ✓ | **later** ⚠ Phase 1 limit: crossfade only |
| Fade in/out handles (from/to black, audio) | ? | ✓ timeline handles | ✓ Fade menu | ? | — | ? | ? | ? | ? | ? | ? | ✓ | ✓ | ✓ | **v1** *(proposed)* as static `fade_in/fade_out` props, **not keyframes** ⚠ |
| Effects stack | ✓ | ✓ | ✓ | ✓ nodes | — | ✓ | ✓ | ✓ | ✓ modifiers | ✓ | ✓ | ✓ | ✓ | ✓ | **later** (Phase 1 has `look` only) |
| Basic look / color preset | ✓ | ✓ | ✓ | ? | — | ✓ adjustments | ✓ | ? | ✓ | ✓ | ✓ | ✓ | ✓ | ? | **must** (`set_props.look`) |
| Color wheels / curves / scopes | ✓ | ✓ | ✓ | ? | — | ? | ? | ? | ✓ | ✓ | ✓ | ✓ HSL/curves | ✓ Lumetri | ? | **later** |
| LUTs | ? | ✓ | ✓ | ~ OCIO color mgmt | — | ? | ? | ? | ? | ? | ? | ? | ✓ | ? | **later** (could back `look`) |
| Chroma key | ? | ✓ | ? | ? | — | ? | ✓ | ? | ? | ? | ? | ✓ | ✓ | ✓ | **later** |
| Masking | ? | ✓ | ✓ | ? | — | ✓ | ✓ RotoMask | ? | ✓ Mask strip | ✓ Magic Mask | ✓ | ✓ | ✓ object | ? | **later** (not in plan) |
| Stabilization | ? | ✓ | ? | ? | — | ? | ? | ? | ? | ✓ | ? | ✓ | ✓ | ? | **later** |
| Motion tracking | ? | ✓ | ? | ? | — | ? | ? | ? | ? | ✓ | ✓ | ✓ | ✓ masks | ? | **later** |
| Static transform / crop / PiP | ✓ | ✓ | ✓ | ✓ | ~ lossless crop | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (`set_props.crop`); position/scale **v1** *(proposed)* |
| Blend modes / compositing | ✓ | ✓ | ? | ✓ | — | ? | ✓ | ? | ✓ | ✓ | ? | ✓ | ✓ | ? | **later** |

## F. Keyframes and speed

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Keyframes | ✓ | ✓ easing | ✓ | ✓ | — | ✓ | ✓ tool 6 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ animations | **later** ⚠ Phase 1: no keyframes (`keyframe` op held to Phase 3) |
| Constant speed change | ✓ Ctrl+drag | ✓ | ✓ Timing tool | ? | ~ FPS change | ? | ? | ? | ✓ Set Speed | ✓ | ✓ | ✓ | ✓ Rate Stretch | ? | **must** (`set_props.speed`) |
| Speed ramp / curve / time remap | ✓ | ✓ | ~ | ? | — | ? | ? | ? | ✓ retiming keys | ✓ | ✓ | ✓ presets | ✓ | ? | **later** ⚠ needs keyframes |
| Reverse | ? | ✓ | ✓ | ? | — | ? | ? | ? | ? | ? | ✓ | ✓ | ? | ? | **v1** *(proposed, a static prop)* |
| Freeze frame | ? | ✓ | ✓ | ? | — | ? | ✓ filter | ? | ✓ | ? | ✓ hold | ✓ | ✓ | ? | **v1** *(proposed)* |

## G. Text and audio

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Text overlay / title | ✓ | ✓ | ✓ | ? | — | ✓ | ✓ | ? | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (`add_text` on T1) |
| Animated title templates | ? | ? | ✓ | ? | — | ? | ? | ? | — | ✓ Fusion | ? | ✓ | ✓ MOGRT | ? | **later** |
| Clip volume | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (`set_props.volume`) |
| Mixer / meters | ✓ | ✓ | ? | ✓ meters | — | ? | ? | ? | ? | ✓ | ? | ? | ✓ | ? | **v1** *(proposed: meters only)* |
| Auto-ducking | ? | ✓ | ? | — | — | ? | — | ? | — | ✓ | ? | ? | ✓ | ✓ via Underlord | **later** (plan Phase 3); static A2 volume works now |
| Loudness normalize | ? | ✓ | ? | — | — | ? | ? | ? | ? | ? | ? | ✓ | ✓ | ✓ Studio Sound | **v1** *(proposed: render-time `loudnorm`)* |
| Voiceover recording | ? | ✓ | ✓ 4.0 | ✓ Record tool | — | ? | ? | ? | ? | ✓ | ? | ✓ | ✓ | ✓ | **later** |

## H. Export and interop

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Render MP4 (H.264/AAC) | ✓ | ✓ | ✓ | ✓ | ✓ copy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (filter graph → libx264 + AAC) |
| Aspect presets 9:16 / 1:1 / 16:9 | ? | ✓ | ? | ? | — | ? | ? | ? | ? | ✓ TikTok preset | ✓ | ✓ | ✓ | ✓ | **must** |
| Lossless / stream-copy fast path | — | — | — | — | ✓ | — | — | — | — | — | — | — | ~ smart render | — | **later** *(proposed)* |
| OTIO export | ? | — | — | ? | — | — | — | ~ GES | ? | ? | ? | — | ? | — | **must** (C1: `.otio` opens in `otiotool`) |
| EDL / FCPXML / XML cut lists | ? | ✓ EDL | ✓ EDL/FCP/Adobe partial | ? | ✓ CSV/XML | — | ? | ? | ? | ? | ? | — | ✓ EDL/FCP XML/AAF | ? | **later** (plan Phase 3) |
| Direct social upload | — | — | — | — | — | — | — | — | — | ✓ | ? | ✓ | ? | ✓ web link | **never** (never-list) |

## I. UX infrastructure

| Feature | KD | SC | OS | OL | LC | OC | FB | PI | BL | DR | FCP | CC | PR | DS | **HS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Undo / redo | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ Command/Batch | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **must** (oplog with inverses) |
| Visible history list | ? | ✓ History | ? | ✓ History | — | — | ? | ? | ? | ? | ? | ? | ✓ History | ~ chat checkpoints | **v1** (the oplog is there; cards cover agent ops) |
| JKL shuttle | ✓ | ✓ | ~ J/L | — | ✓ j/k/l | ~ j/l seek 1 s | ? | ? | ? | ✓ | ✓ | ? | ✓ | ~ Shift+J/K/L | **must** (keyboard shortcuts are in Phase 1 scope) |
| Single-key tools / edits | ✓ S/X/M | ✓ A/V/B/S/X/Z | ✓ C/T/S | ✓ V/B/N/C/Y/U | ✓ | ✓ s/q/w/n | ✓ 1–6 | ? | ✓ G/E/S/K | ✓ | ✓ A/T/P/R/B | ✓ | ✓ | ✓ A/R/B/H/Y | **must** (keyboard map; see UI-UX-PATTERNS.md) |
| Customizable shortcuts | ✓ (+ Premiere keymap) | ? | ✓ | ? | ✓ searchable dialog | ✓ action registry | ? | ? | ? | ✓ (+ other-app presets) | ✓ | ? | ✓ | ? | **v1** |
| Command palette / action search | — | — | — | — | ~ shortcut search | — | — | — | ? | ? | ? | ? | ? | ✓ Cmd+K | **v1** *(proposed; reuses the tool registry)* |
| Workspaces / pages | ✓ | ✓ | ~ Simple/Color view | ? | ? | ? | ? | ? | ✓ | ✓ pages | ? | ? | ✓ 16 | ? | **later** (the Edit page is one layout) |
| Hover-scrub preview | ? | ? | ✓ transitions | ? | — | ? | ? | ? | ? | ✓ effects | ✓ skimmer | ? | ✓ Project panel | ? | **later** |

¹ Premiere: Ctrl+K / Ctrl+Shift+K appear in the Sequence-menu shortcut table, but our text extraction dropped the row labels ("Add Edit" / "Add Edit to All Tracks" is our reading). See `premiere-pro.md`.

## Addendum: Montaj (added 2026-10-01)

Montaj is not a column above. It's an agent-first short-form tool, covered in `montaj.md`. Its two layers:
- an MIT engine exposed over CLI, MCP and HTTP
- a Mac app on a waitlist

The rows below are ones it adds that the 14 editors don't cover. Everything else it has (transcribe, filler/silence removal, captions, reframe, J/K/L, ⌘K, ripple/roll/slip/slide) is already in the matrix.

| Feature | Montaj | **HS** |
|---|---|---|
| Agent progress chips + Re-run with an edited prompt in the agent panel | ✓ (site mock-up; `serve` prompt bar) | **must** (sidebar: plan steps → Propose cards) |
| Project status `pending → draft → final` (agent writes draft, human finalises; manual start reaches the same state) | ✓ | **v1** (Phase 2 draft branch) |
| Style profile applied to every agent edit (fonts, colours, captions, pacing) | ✓ | **v1** *(proposed; Phase 2 presets)* |
| Caption style picker renders the real export template | ✓ | **v1** *(proposed)* |
| Visual compare of two versions at time T + auto-save before restore | ✓ | **v1** *(proposed; checkpoints)* |
| Read-only ruler pins outside the project document | ✓ | **v1** *(proposed; shows detections and notes without touching the oplog)* |
| Best-take selection across repeated takes | ✓ `select_takes` | **v1** *(proposed)* |
| Carousel export (N PNG slides, 1:1 / 4:5 / 9:16) | ✓ | **later** *(proposed)* |
| Auto-schedule posts (Sprout Social / Metricool) | ✓ | **never** (never-list) |

## Conflicts and tensions with PLAN-MERGED.md Phase 1 limits

| # | Item | Why it conflicts | Suggested resolution |
|---|---|---|---|
| 1 | **Keyframes** | Every editor here except LosslessCut (and DS, mostly) has them. Users expect at least fades and simple zoom-ins. Plan: no keyframes in Phase 1; `keyframe` op held to Phase 3. | Keep the limit. Cover the 80% case with **static props that the renderer expands**: `fade_in` / `fade_out` (video from/to black, audio volume) and an optional "Ken Burns" start/end crop, à la Resolve's Dynamic Zoom. These are still `set_props`, need no keyframe UI, and stay inside the "no keyframes" rule. **Decision needed:** is `fade_in/out` acceptable as a Phase 1 prop? |
| 2 | **Transitions beyond crossfade** | All mainstream editors ship wipes etc. | Keep the limit (Phase 3). FFmpeg `xfade` has many `transition=` types, so lifting it later is cheap on the engine side. |
| 3 | **Roll / slip / slide** | All pro editors (DR, FCP, PR, OL) have them. Phase 1 ops have none. | Roll = two `trim_clip`s in one group (no schema change). **Slip** needs a new op or a `trim_clip` mode that shifts source_in/out while keeping timeline position. Propose `slip_clip` for Phase 2 (v1). Slide stays Phase 3. |
| 4 | **Delete left/right of playhead** | Very common (CC, OC, OS, KD). Not named in the plan. | No conflict: compile it to `split_clip` + `delete_clip{ripple}` in one group, and give it keys (q / w, matching OpenCut and the OpenShot ripple pair). |
| 5 | **Speed ramps / curves** | CapCut, DR, FCP, PR and Blender have them; they need keyframes. | Phase 3. Phase 1's constant `speed` plus a Rate-Stretch-style edge drag is enough. |
| 6 | **Masking, tracking, stabilization** | Common in CC/DR/PR. Not in the plan at any phase. | Treat as **later / plug-in**. Note it as a gap in PLAN.md Phase 3. |
| 7 | **Auto-ducking** | Plan puts it in Phase 3. It is a top Descript/Underlord request ("lower audio on other layers"). | Phase 1 workaround: a static A2 volume. Consider moving ducking (FFmpeg `sidechaincompress`) to Phase 2 presets. It is a render-graph change, not a keyframe UI. |
| 8 | **Anchored (connected) overlays** | FCP and Descript keep B-roll/captions attached when the main edit ripples. The plan's T1/A2 items have absolute `at` times. | Decide **before the slice-1 schema freeze** whether T1/A2 items can carry `anchor_clip_id` + offset. Otherwise transcript cuts on V1/A1 will desync text and music cues. |
