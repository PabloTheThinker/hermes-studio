# Recommendation: what to copy, what to skip (one page)

**Scope:** 14 editors.
- **Open source:** Kdenlive, Shotcut, OpenShot, Olive, LosslessCut, OpenCut, Flowblade, Pitivi, Blender VSE.
- **Commercial, docs only:** DaVinci Resolve, Final Cut Pro, CapCut, Premiere, Descript.

Evidence is in each `<editor>.md`, `MASTER-FEATURE-MATRIX.md` and `UI-UX-PATTERNS.md`.

## The short version

The plan's shape (transcript-first Edit page, preview, 4-track timeline, agent sidebar on the right with Propose by default) is what the market is converging on. **Descript already ships it** with a cloud agent (Underlord) and an MCP, and **Premiere** has text-based editing plus an AI Assistant beta. Hermes Studio wins on four things: **local, MIT, per-op approval, and one engine for humans, Hermes and any MCP client.** Spend Phase 1 on making cutting by words feel effortless and safe, not on matching pro tool counts.

## Copy these (from whom)

1. **Descript: transcript and agent UX.**
   - Ignore = strike-through; "Restore removed".
   - Filler review list with per-item Delete / Replace with gap / Keep.
   - Per-response **Revert** and a checkpoint shown *before* the edit applies.
   - Cmd/Ctrl+K action search.
2. **Final Cut Pro: magnetic behaviour.** V1+A1 ripple by default, and T1 text / A2 music **anchored** to V1 clips so word cuts never desync captions or music cues. Hold-B temporary blade. Option-[ / ] trim to playhead.
3. **DaVinci Resolve (Cut page):**
   - trim chosen by cursor zone, with no tool modes
   - a **1-row overview** above the timeline (dual-timeline idea)
   - a **clip tool strip under the viewer** as the Phase 1 inspector
   - boring/jump-cut detection shown as timeline tints
4. **CapCut / OpenCut / OpenShot:** one-click **Delete left / Delete right of playhead** (keys Q / W). It is a grouped `split_clip` + `delete_clip{ripple}`, so no new op.
5. **Shotcut:** the single-key edit grammar, a visible History panel (our oplog), and "overlap = crossfade".
6. **LosslessCut:**
   - silence/scene detection → segments
   - a "last FFmpeg command" transparency log
   - a searchable, rebindable shortcuts dialog keyed by action id
   - the same shape as us: Electron spawning bundled FFmpeg
7. **OpenCut classic (MIT):**
   - its **action registry** (`actions/definitions.ts`: id, label, default keys) as the model for one id shared by MCP/ACP/keyboard
   - its `Command` / `BatchCommand` undo shape, which confirms our oplog/group design

## Skip

- Source/record dual monitors, 3-point editing, workspaces inside Edit, multicam, node graphs (Olive).
- Stock libraries, stickers, social upload. Upload/publish is on the plan's never-list anyway.
- Pro grading and Fairlight-style mixing.
- Generative tools, except as Phase 3 optional plug-ins.

## Reuse and licensing bottom line

| What | License (verified Oct 1, 2026) | Can MIT Hermes Studio use it? |
|---|---|---|
| OpenCut, opencut-classic | MIT | **Yes, copy with the notice kept.** Classic is archived. Its UI is React/Next.js, but Hermes's UI is vanilla JS with no build step, so it's not drop-in; borrow patterns and logic. Watch the deps: mediabunny is MPL-2.0 and soundtouchjs is LGPL-2.1 |
| MLT | LGPL-2.1 | Only as a dynamically linked library or the separate `melt` executable, as a render-v2 option (already in RESEARCH.md) |
| GES / Pitivi | LGPL-2.1(+) | Same LGPL rules. Not recommended (it would be a second media stack) |
| libopenshot | LGPL-3.0, but it depends on **libopenshot-audio (GPL-3.0)** | **No.** The GPL dependency taints it |
| Kdenlive, Shotcut, Olive, OpenShot-qt, Flowblade (GPL-3), LosslessCut (GPL-2.0-only), Blender (GPL-2.0-or-later) | GPL | **Ideas only.** No code, no in-process linking |
| FFmpeg (GPL build) | GPL | Already handled in v0.5.3 as a separate executable (LosslessCut does the same) |

## Decisions this research asks for

1. **Anchoring:** should T1/A2 items carry `anchor_clip_id` + offset? Decide before the slice-1 schema freeze; it is hard to retrofit.
2. **Fades without keyframes:** allow static `fade_in` / `fade_out` in `set_props` in Phase 1? These are the most-missed "keyframe" use and render cleanly with FFmpeg `fade`/`afade`.
3. **Slip/roll timing:** roll is two trims in one group (any time). Slip needs a `slip_clip` op, proposed for Phase 2.
4. **Delete key semantics:**
   - Timeline: Delete = lift, Shift+Delete = ripple (industry norm).
   - Transcript tab: Delete = ripple (Descript).
   OK?

## Top risks

1. **Descript is already there.** Its agent + transcript + MCP overlaps our pitch, so differentiation must be visible in the first minute: offline, free, approve-each-edit, open.
2. **OpenCut's rewrite** (MIT, 91k stars) lists an MCP server, headless mode and an Editor API as planned. If it ships first, it competes for the same "agent-drivable open editor" slot.
3. **Desync on transcript cuts** if overlays aren't anchored (decision 1). This is the most likely Phase 1 quality bug.
4. **Scope creep toward CapCut parity** (masks, speed curves, effects). The matrix shows the long tail; hold Phase 1 to the plan's op list and these four decisions.
5. **Preview performance** with a vanilla-JS UI and proxy seeking (already a plan risk). The pro editors all lean on GPU pipelines we don't have.
