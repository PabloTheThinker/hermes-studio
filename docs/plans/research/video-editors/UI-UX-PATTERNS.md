# UI/UX patterns across 14 editors, and a recommended Hermes Studio Edit page

Paths are relative to this folder. "Own" marks a capture we made on the research box; everything else is an official image (see each folder's `SOURCES.md`).

## Part 1: Recurring patterns and why they recur

### P1. Four zones: media, preview, inspector, timeline

Almost every editor uses the same four zones: media/library top-left, preview top-centre or right, inspector/properties at the side, and a full-width timeline at the bottom.

**Examples:**
- Kdenlive (`screenshots/kdenlive/01-ui-screen-layout.png`)
- Shotcut (`screenshots/shotcut/10-own-main-window-split-clip-history.png`)
- Olive (`screenshots/olive/10-own-main-window-sequence.png`)
- Resolve Edit (`screenshots/davinci-resolve/01-overview-edit-page.png`)
- FCP (`screenshots/final-cut-pro/01-main-window-annotated.png`)
- CapCut (`screenshots/capcut/11-howto-fig1.png`)
- OpenCut (`screenshots/opencut/10-own-editor-two-tracks.png`)
- Pitivi (`screenshots/pitivi/01-main-window-2020.05.png`)

**Why it recurs:**
- Time is horizontal, so the timeline wants full width.
- The preview is the thing being judged, so it sits at eye level.
- Picking things (media) and tuning things (inspector) flank it.

The plan's Edit page is this pattern, except the inspector slot holds the **Hermes sidebar**, so the inspector needs a new home (see Part 2).

### P2. Single viewer (consumer) vs source + record monitors (pro)

| Viewer model | Editors | Notes |
|---|---|---|
| Two monitors (source + program) | Kdenlive, Resolve Edit, Premiere, FCP (optional event viewer) | Needed for 3-point editing |
| One viewer | Shotcut (Source/Project tabs, P to switch), CapCut, OpenCut, Descript, Resolve Cut | Shotcut and Resolve Cut both chose this for speed |

**Why it differs:** source/record needs 3-point editing skills, while consumer apps cut straight on the timeline. **For Hermes, use one viewer**; the transcript acts as the "source monitor".

### P3. Three timeline models

1. **Tracks** (Kdenlive, Shotcut, OpenShot, Olive, Flowblade, Resolve, Premiere, CapCut, OpenCut). These are explicit V/A rows. Ripple is a mode or flag (Shotcut has three ripple toggles; OpenCut has a ripple toggle).
2. **Magnetic storyline** (FCP `05-magnetic-timeline-annotated.png`):
   - the primary storyline closes gaps automatically
   - B-roll/titles/music are *connected* to a storyline clip
   - Descript's script order behaves the same way
3. **Layers/segments** (Pitivi layers with A+V together; LosslessCut's single segment list, `screenshots/losslesscut/10-own-main-window-segments-advanced-view.png`).

**Why it matters for us:** transcript-first editing *is* storyline editing. Deleting words must ripple V1+A1 and keep overlays attached. A track UI (the plan's 4 fixed tracks) with **V1/A1 ripple-by-default and T1/A2 anchored to V1 clips** gives FCP's behaviour in a familiar track look.

### P4. Overlap or adjacency = transition

Several editors make a transition by overlapping two clips or by dropping onto a cut point:
- Shotcut (overlap on the same track → dissolve)
- Kdenlive "mixes"
- Pitivi (orange overlap handles)
- Blender (Cross strip)
- FCP Cmd-T / Resolve drag to the cut point

**Why:** it is the cheapest mental model, and it matches the plan's `transition` item that "sits `between` two clip ids" with `xfade` only.

### P5. Tool modes vs context-sensitive trimming

| Approach | Editors |
|---|---|
| Explicit tool modes with single-letter keys | Olive V/B/N/C/Y/U (`screenshots/olive/14-own-tools-menu.png`), Kdenlive S/X/M + Slip/Ripple (`screenshots/kdenlive/40-own-tool-menu.png`), Flowblade 1–6 (`screenshots/flowblade/11-own-edit-tool-menu.png`), FCP A/T/P/R/B/Z/H (`screenshots/final-cut-pro/07-timeline-tools-menu.png`) |
| The cursor zone picks the trim | Resolve (ripple at an edge, roll on the cut, slip mid-clip; Cut page `16-cut-trimming.png`); FCP's single Trim tool and Flowblade's Multitrim are similar |

**Why the trend:** modes cause "wrong tool" errors, and zones remove them. **For Hermes, start with no modes**:
- Select by default; edges trim with ripple on V1.
- Hold **B** for a temporary blade (FCP / Descript "hold B").
- Add Resolve-style zones when roll/slip land.

### P6. A shared keyboard grammar

| Action | Convergent keys (source) |
|---|---|
| Play / shuttle | **J / K / L**: Kdenlive (`monitormanager.cpp`), Shotcut, FCP, LosslessCut (K/L/J speed), OpenShot (J/L), Premiere ("J-K-L dynamic trimming"), Resolve ("JKL trimming"). Descript and OpenCut deviate (Shift+J/K/L speed; j/l = ±1 s) |
| Play/pause | **Space** in every editor here |
| Frame step | **← / →** (Kdenlive, Shotcut, OpenShot, OpenCut, Descript) |
| Split at playhead | **S** (Shotcut, OpenCut, Descript); **Ctrl/Cmd+B** (FCP, CapCut); **Ctrl+K** (OpenShot, Premiere¹); **K** (Blender); **B** in LosslessCut |
| Blade tool | **B** (FCP, Descript, CapCut per third parties), **C** (Olive, OpenShot), **X** (Kdenlive) |
| Delete left / right of playhead | **Q / W** (OpenCut: q removes left, w removes right; OpenShot: Q = keep right (ripple), W = keep left (ripple), i.e. the same effect); Kdenlive **( / )** with ripple |
| Ripple delete | **Shift+Delete** (OpenShot, Premiere, Kdenlive Extract; Shotcut also X) |
| In / out | **I / O** (Shotcut, Resolve, Premiere Mark In/Out) |
| Marker | **M** (Shotcut, OpenShot) |
| Snap toggle | **N** (OpenCut), **S** (Olive, OpenShot) |
| Zoom | **= / −** and a fit key (Shotcut `0`, OpenShot `\`) |
| Show shortcuts | **?** (Shotcut `?` or `/`, LosslessCut Shift+/) |
| Command search | **Cmd/Ctrl+K** "Search actions" (Descript) |

¹ Label unconfirmed (see premiere-pro.md).

**Why it converges:** editors switch apps, so new apps copy the incumbents' keys. Resolve and Kdenlive even ship other-app keymaps (Kdenlive ships a Premiere keymap; Resolve has "presets for other application shortcuts").

### P7. Workspaces and pages

Kdenlive (`screenshots/kdenlive/02-workspaces.png`), Shotcut layouts (`14/15/16-own-*-layout.png`), Premiere (16 default workspaces) and Resolve pages (Media/Cut/Edit/Fusion/Color/Fairlight/Deliver/Photo) all offer task-specific layouts over one project.

**Why:** one layout can't serve logging, cutting, color and audio well. Hermes already has page-level separation (Clips / Edit / Design) in the left rail, so **don't add workspaces inside Edit** in Phase 1.

### P8. Transcript-first editing has gone mainstream

| Editor | How the transcript is used |
|---|---|
| **Descript** | The script is the primary surface; timeline optional (`screenshots/descript/11-editor-interface-tour-help.png`, `06-transcript-editing-with-timeline.png`, `08-script-view-with-timeline.png`) |
| **Premiere** | Text-Based Editing: transcribe, delete pauses, remove a speaker, Paper Edit |
| **Resolve Studio** | Text-based editing |
| **Kdenlive** | Speech Editor as a side panel (`screenshots/kdenlive/17-speech-editor.png`, own `31-own-speech-editor-tab.png`) |
| **CapCut** | Editable caption text list (`screenshots/capcut/06-captions-text-list-panel.png`) |

**Recurring details:**
- click a word to seek
- select, then delete, to cut media
- strike-through for "ignored" text (Descript **Ignore**; the plan's struck-through cut words)
- filler-word review lists with per-item actions (`screenshots/descript/14-remove-filler-words-sidebar.png`)
- "replace with gap" as an alternative to ripple

**Why:** for talking-head and podcast content, words are the natural unit, and LLM agents reason over text far better than over pixels.

### P9. The agent chat sits in a right sidebar, next to the document

- **Descript Underlord** lives in the right-hand sidebar beside the script (`screenshots/descript/01-underlord-chat-beside-transcript-editor.png`, `02-meet-underlord-agent-panel.png`).
  - It has a model picker (`12-underlord-model-picker.png`).
  - Each response has an action bar with **Revert** and thumbs (`13-underlord-revert-button.png`).
  - Checkpoints are shown in the chat before edits apply.
- Premiere has an "AI Assistant (beta)" (guide topic; no image available).
- *(Added 2026-10-01)* Montaj's mock-up editor puts a **Prompt** panel on the right with step progress chips (✓ cutting pauses / ✓ adding captions) and **Re-run**. See `screenshots/montaj/17-capture-home-03.png`. Review is of the whole draft afterwards, not per op.

**Why the right side:** reading order goes from content on the left to a conversation about it on the right. That keeps the transcript/preview stable while the chat scrolls.

**What nobody ships:**
- Descript's caveat that Underlord "might overpromise" shows the gap: no consumer editor shows **per-op approval** (Propose).
- None of the editors here has an Ask/Propose/Auto gate.
- That gap is Hermes Studio's opening.

### P10. Visible history

- Shotcut has a History panel listing every command (`screenshots/shotcut/10-own-main-window-split-clip-history.png`).
- Olive has a History tab beside the bin (`screenshots/olive/10-own-main-window-sequence.png`).
- Premiere has a History panel, and "Track trimming actions in the History panel" is a guide topic.
- LosslessCut shows "last FFmpeg commands".

**Why:** trust and recovery. The plan's oplog plus per-card Undo is the agent-era version.

### P11. A context-sensitive inspector

CapCut's right panel switches tabs to suit the selection (Video / Audio / Speed / Adjustment; `screenshots/capcut/16-howto-fig6.png`, `22-howto-fig12.png`). OpenCut does the same (`screenshots/opencut/11-own-clip-selected-inspector-split.png`), and so does Resolve's inspector (Video / Sizing / Audio / Effects / File).

Resolve also has a **tool strip under the viewer** for quick transform, crop, audio, speed and zoom (Cut page text), so common props don't need the inspector at all.

### P12. Ways to beat timeline zoom

- Resolve's **dual timeline** (overview + zoomed; `screenshots/davinci-resolve/19-cut-timelines-dual.png`).
- OpenShot's zoom slider that doubles as a mini-map (`screenshots/openshot/20-own-main-window-2-tracks.png`).
- **Why:** zoom/scroll is the most common timeline friction; a 1-row overview fixes most of it.

### P13. Detections become timeline objects

- LosslessCut turns black/silence/scene detection into segments.
- Resolve's boring detector paints long shots grey and jump cuts red.
- Descript underlines filler words.
- **Why:** analysis is only useful when it is visible and actionable. In Hermes, the agent's `scenes_get` / silence data should show the same way: markers or tinted ranges that the user can see before approving a cut.

### P14. Edit-type pickers for beginners

- Resolve's drop overlay (insert / overwrite / replace / fit to fill / place on top / append / ripple overwrite).
- CapCut's one-click toolbar (Split / Delete left / Delete right / Freeze / Reverse / Mirror / Rotate / Crop; `screenshots/capcut/15-howto-fig5.png`).
- **Why:** both expose edit semantics without shortcuts.

### P15. Agent-first lifecycle: the agent drafts, the human finalises *(added 2026-10-01)*

**Montaj** (`montaj.md`) makes the project status the contract:
- The agent writes `project.json` and may only reach `draft`.
- The UI live-updates over SSE while the agent works.
- A human reviews in the timeline and marks it `final`.
- "Start editing manually" lands in the same `draft` state, so nothing downstream can tell the two paths apart.
- The title bar shows a `draft` badge.
- Every agent run and status change is a snapshot you can compare visually and restore safely.

**Why:** it gives users one clear signal of "has a human signed this off?". For Hermes, this is the coarse layer above Propose. Per-op approval stays the fine-grained gate, and the project or draft branch carries `draft`/`final` on top.

## Part 2: Recommended Hermes Studio Edit page layout

This keeps the plan comp (`../../comps/COMP-GLYPH-EDIT-SIDEBAR.png`) and its dimensions and fills the gaps the research exposed:
- **(a)** no inspector slot
- **(b)** no timeline toolbar
- **(c)** no keyboard map

```
┌──┬────────────────────────────────────────────────────────────────────┬───────────────────────────┐
│R │ Title · 9:16 · v14 saved   Undo/Redo  History   [Render MP4]       │ Hermes ● waiting  [Stop]  │
│a ├───────────────┬────────────────────────────────────────────────────┤ [Ask][Propose][Auto]      │
│i │ Media │Transcript│Scenes │            PREVIEW (single viewer)       │                           │
│l │  (270 px)       │       "Following Hermes" badge when agent drives│  plan card (steps)        │
│  │ • click word→seek│                                                │  step cards: before/after │
│C │ • select→Delete │                                                 │   thumbs · Undo · Show on │
│l │   /Keep/Ask     │        ◀◀ ▶ 0:12.40/0:58.00                     │   timeline                │
│i │ • struck = cut  ├────────────────────────────────────────────────┤  waiting card: Apply /    │
│p │ • ember = agent │ CLIP STRIP (36 px, shows on selection):        │   Skip / Apply the rest   │
│s │ • filler list   │  vol · speed · crop · look · fade in/out(v1) ▸ │                           │
│E │   (Descript P8) │  (Resolve viewer tool strip, P11)              │  (360 px; 48 px collapsed │
│d ├─────────────────┴────────────────────────────────────────────────┤   strip keeps ● + Stop)   │
│i │ TL TOOLBAR (28 px): Select·hold-B blade | Split S | ⌫L Q | ⌫R W │                           │
│t │   | Ripple(on V1) | Snap N | Marker M | − zoom ▭ + | overview ▬ │  context chips:           │
│  │ T1 text   [Captions · Bold Pop ⚓→V1 clip]                         │  [Transcript 0:17–0:21]   │
│D │ V1 main   [talk 0:00–0:09][talk 1:42][talk 3:05 (you trimmed)]    │  composer                 │
│e │ A1 voice  [voice ▁▃▅▃▁…]                                          │                           │
│s │ A2 music  [bed.mp3 −18 dB ⚓]          (timeline 250 px total)     │                           │
└──┴───────────────────────────────────────────────────────────────────┴───────────────────────────┘
```

**Decisions, and where each comes from:**

1. **Agent sidebar on the right, 360 px.** Keep it (Descript P9). Never put the inspector there, so the agent's thread never jumps away during manual edits. The collapsed 48 px strip keeps the status dot and Stop (plan).
2. **Transcript tab on the left, the default** (plan; Descript/Premiere P8). Add these from Descript:
   - a **filler review list** that expands from the Remove-fillers card, or as a mode of the Transcript tab, with per-item Delete / Replace with gap / Keep
   - **Ignore** as strike-through
   - "Restore removed" on a struck range
3. **Inspector = a clip strip under the preview** (Resolve viewer tool strip, P11). It holds only the Phase 1 `set_props` fields: volume, speed, crop, look (plus fade in/out if approved). A ▸ opens a popover for more. This adds no new column and keeps the 270/360 widths.
4. **Timeline toolbar inside the 250 px timeline**, as a 28 px row. It holds:
   - Select, with hold-B blade (FCP/Descript)
   - Split, Delete-left and Delete-right (CapCut/OpenCut/OpenShot)
   - a ripple indicator (on for V1/A1)
   - Snap, Marker, zoom and a **1-row overview** (Resolve dual timeline / OpenShot mini-map, P12)
   With 4 tracks of about 50 px each, it fits.
5. **Anchoring.** T1 and A2 items show a small ⚓ when anchored to a V1 clip (FCP connected clips, P3). This only works if the schema adds `anchor_clip_id` (see the MASTER-FEATURE-MATRIX conflict #8).
6. **Agent visibility on the timeline:**
   - the plan's "H · step 3" badge on agent-touched items
   - Scenes/silence detections drawn as tinted ranges and markers (P13)
   - "Show on timeline" on cards scrolls and highlights the range

**Proposed keyboard map** (Phase 1, from P6 convergence; final names should come from the tool registry so MCP/ACP/keys share ids, like OpenCut's `actions/definitions.ts` and LosslessCut's action ids):

| Key | Action | Precedent |
|---|---|---|
| Space / K | Play-pause | all / Kdenlive, Shotcut, FCP, LosslessCut |
| J / L | Shuttle back / forward (repeat = faster) | FCP, Shotcut, Kdenlive, LosslessCut |
| ← / → (Shift: 1 s) | Step frame | Kdenlive, Shotcut, OpenCut, Descript |
| I / O | Range in / out (for "Ask Hermes about this range") | Shotcut, Resolve, Premiere |
| S | Split at playhead (selected track, or V1+A1 linked) | Shotcut, OpenCut, Descript |
| Q / W | Delete left / right of playhead, ripple | OpenCut q/w; OpenShot Q/W (ripple) |
| Delete / Shift+Delete | Lift (leave gap) / ripple delete | Premiere, OpenShot, Kdenlive |
| hold B | Temporary blade | FCP, Descript |
| N | Snap toggle | OpenCut |
| M | Add marker | Shotcut, OpenShot |
| = / − / \\ | Zoom in / out / fit | Shotcut, OpenShot |
| Ctrl+Z / Ctrl+Shift+Z | Undo / redo (oplog) | universal |
| Enter / Esc | Apply / Skip the focused "waiting" card | plan accessibility spec |
| Ctrl+K | Action search (also searches MCP tool names) | Descript |
| ? | Shortcut sheet (searchable, rebindable later) | Shotcut, LosslessCut |

**Transcript tab keys** (only while the Transcript tab has focus; Descript scopes single-letter keys the same way):
- Delete cuts the selection (ripple) — the Descript behaviour.
- Enter keeps the selection.
- Ctrl+Enter sends "Ask Hermes about this".
