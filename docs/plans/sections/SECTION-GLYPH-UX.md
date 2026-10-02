# Section: Edit page + agent sidebar UX (Glyph)

Reviewed: `REPO-AUDIT.md`, `RESEARCH.md` §5, `PLAN.md` §1–4, plus `hermes_studio/ui/index.html` on `main` via `gh api` (house tokens: `--bg #0b0b0c`, `--amber #ffc83d`, `--ember #cd8032`, Archivo + JetBrains Mono; left page rail).
Comp: `comps/COMP-GLYPH-EDIT-SIDEBAR.png` (source `.html`, 1280×800). One screen job: the Edit page with Hermes mid-run in Propose mode.

## Layout (1280×800 minimum)
- **Left rail:** the existing pages, plus a new **Edit** page between Clips and Design.
- **Left panel (270 px), tabs Media / Transcript / Scenes.** Transcript is the default tab. Clicking a word seeks; selecting text lets you Delete, Keep or "Ask Hermes about this". Struck-through words are cut; ember underline marks words the agent touched.
- **Centre:** preview at the project aspect, with transport and timecode under it.
- **Bottom (250 px):** the timeline with T1 text, V1 main, A1 voice and A2 music, a playhead and snap.
- **Right sidebar (360 px), full height:** Hermes. It collapses to a 48 px strip that keeps the status dot and **Stop** visible.

## Watching the agent
- **Who did what is shown on the clip.** Agent-touched clips get an ember outline plus a tag (`H · step 3`); your own last edit gets an ink outline. Colour is never the only signal, because the tag carries the name.
- **Follow mode.** While Hermes edits, the playhead jumps to each change ("Following Hermes" badge on the preview). The moment you scrub, click or type, follow turns off, so the agent never moves your playhead from under you. A "Follow Hermes" button turns it back on.
- **Sidebar thread, top to bottom:**
  1. Header: name, live status ("waiting on step 3"), **Stop**, and the Ask / Propose / Auto switch.
  2. Your message, with **Restore to here** (the checkpoint).
  3. **Plan card:** steps with done, current and next states.
  4. **One edit card per write tool call:** a plain-words summary, `v12 → v13`, before/after thumbnails, **Undo**, and **Show on timeline**.
  5. **Composer** with context chips for the attached selection (clips, a transcript range or a time range).

## Steering and handoff (the rules the UI enforces)
1. **Propose mode in Phase 1 means approve each step**, not a draft branch. Each write shows a "waiting for you" card (Apply / Skip / Apply the rest) driven by ACP `session/request_permission`. The draft-branch Keep/Discard view stays in Phase 2. **A waiting card never skips itself on a timeout.** The run pauses and the card waits until the person answers, because stepping away shouldn't silently change the plan. If ACP's permission request times out, the engine keeps the write parked, and Hermes resumes once it's answered. The header reads "Paused, waiting for you". **Gap: PLAN §4 makes Propose the default in Phase 1, but draft branches only arrive in Phase 2. This fixes that mismatch.**
2. **A human edit pauses the run.** If you edit while Hermes is working, its current op finishes or is rejected as stale, and the sidebar shows "You edited. Hermes paused." with **Continue from here**, which hands Hermes your changes as a `history_diff`. No silent re-read and retry while you're mid-gesture.
3. **Undo has two scopes.** ⌘Z / Ctrl+Z is the normal linear undo of the latest entry, whoever made it, and the history panel names the actor. A card's **Undo** reverses that step only if its inverse still applies cleanly. If a later step depends on it, the button becomes **Restore to before this step**, with a count of the later steps that would also go.
4. **Stop** sends `session/cancel`, keeps every applied step, and marks the remaining plan steps "not run".
5. **Ask mode** greys out write cards entirely; the agent can only read, look at frames and answer.

## Gaps and risks
- **Cards for macro ops.** `transcript_cut` "remove fillers" can be 40 ops. It must show as one card with one Undo, plus an expandable list. That needs grouped entries in the op log (Bay/Wire contract).
- **Thumbnail cost.** Before/after thumbnails on every card need cheap engine frames, cached per version, or the sidebar lags behind the timeline.
- **Small screens.** Below 1280 wide, the sidebar becomes an overlay drawer. The timeline doesn't shrink under four tracks.
- **Accessibility.** Each card needs focus order, keyboard Apply/Skip (Enter / Esc), live-region announcements for step status, and reduced motion for playhead jumps.

## Open questions for Pablo (2)
1. **Default view:** should the Edit page open on the **transcript** (Descript-style, my recommendation for talk footage) or on the **timeline**?
2. **Default mode:** **Propose** (approve each step, my recommendation) or **Auto** (applies live, undo after)?

## Size
- **Design:** about 1 week of Glyph comps. That covers the Edit page states (empty, importing, agent running, conflict pause, render), 6 card states, the collapsed sidebar and a keyboard map.
- **Build share:** the Edit page and sidebar are the largest UI slice of Phase 1, roughly 3–4 of its ~6 weeks. They can only start once the Phase 0 schema and op-log contract are frozen.
