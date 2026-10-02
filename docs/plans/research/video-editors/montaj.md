# Montaj teardown (open-core: MIT engine + commercial Mac app; reference only)

*Added 2026-10-01 (ET). We read it only. We did not join the waitlist, install it, create an account or start a trial.*

**What it is:** "an open-source video and carousel editing toolkit for AI agents. It is CLI-first, agent-native, and runs entirely on your local machine" (docs intro, as indexed). The repo README calls it "a video editing CLIP for AI agents", meaning "a CLI Program for agents" that "clips onto your existing AI agent (Claude Code, OpenClaw, Cursor, or any harness)". It also says: "**The fundamental dependency is an agent.** Montaj doesn't edit on its own" ([README](https://github.com/theSamPadilla/montaj)).

**Two layers under one name.** The [README](https://github.com/theSamPadilla/montaj) says: "Montaj is also a free video editor for Mac, built on this engine: montaj.ag".
- **The engine:** [`theSamPadilla/montaj`](https://github.com/theSamPadilla/montaj).
  - MIT, "Copyright (c) 2026 Sam Padilla" (`LICENSE`).
  - Python CLI + Node render + React editor. The editor is also published as the npm package `@bycrux/editor` (CHANGELOG).
  - We cloned HEAD on Oct 1, 2026: `v5.18.1`, last commit 4:56 AM ET Oct 1.
  - A search-index snapshot showed about 21 stars and a creation date of Apr 3, 2026. We did not re-check this: the GitHub API was rate-limited.
- **The app:** [montaj.ag](https://montaj.ag/), a Mac app by **ByCrux LLC / By Crux** ([terms](https://montaj.ag/terms), last updated Sep 30, 2026; [By Crux page](https://montaj.ag/bycrux)).
  - The site's call to action is "Join the waitlist".
  - It adds the consumer UI plus paid **Hub** (trends, scripts, calendar) and **Studio** (teams) tiers.

**Identification (confirmed).** Pablo's capture (`screenshots/montaj/00-…`) shows a @techbyjaz carousel ending "This carousel was created by Montaj", with the same M logo.
- montaj.ag hosts a carousel template with the same photo and the @techbyjaz handle (`08-template-carousel-1.jpg`, "I use Montaj to edit my videos for me").
- [Pricing](https://montaj.ag/pricing) lists @techbyjaz under "Creators using Montaj", next to @theSamPadilla and @explorebyjaz.
- @techbyjaz is Jazmine Adamson's business handle (her [LinkedIn post](https://www.linkedin.com/posts/jazmine-adamson-97304619a_ai-tech-automation-activity-7463218320989773824-y3Vg) is credited "BY CRUX").
- Unknown whether "jazzerkay", a minor repo contributor in the search-index snapshot, is the same person.

**Not this product (same name, unrelated):**
- [montaj.pro](https://montaj.pro/) and its [iOS app](https://apps.apple.com/us/app/montaj-video-editor/id6759311034): a manual pro-style editor from an indie developer. It has Free, Pro $9.99/mo and $79 lifetime on Mac, and from $3.99/mo on iOS.
- [MONTAJ+](https://play.google.com/store/apps/details?id=com.naguib.montaj&hl=en_US): a generic Android video-tools app.
- "Montaj" is also the Turkish/Romanian word for editing or montage.

**Screenshots:** `screenshots/montaj/` holds 28 images:
- 1 capture from Pablo
- 15 official images (marketing, carousel deck, talking-head frames, logos)
- 12 of our own captures of public montaj.ag pages

**Caveat:** the "app windows" on montaj.ag are HTML marketing mock-ups, not real app screenshots. We found no real UI screenshot in public. Details are in `SOURCES.md`.

**Docs note:** the docs.montaj.ag pages (`/quickstart`, `/cli`, `/projects/carousel`, `/ui`) appeared in search results. On Oct 1 (ET), though, fetching `docs.montaj.ag/ui` returned the montaj.ag marketing homepage. UI details below are therefore cited from the repo copy, [`docs/UI.md`](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md), which says it is a "local quick-reference" of the canonical docs.

## 1. What it does, and for whom

- **Target users:**
  - App: "content creators like you": Reels, TikToks, YouTube, tutorials, vlogs, carousels ([home](https://montaj.ag/)). Pitched at people who have "never edited a video".
  - Engine: "AI agent developers", "content creators who use AI coding assistants" and "developers building video processing pipelines" (docs intro).
- **Core loop (app, [home](https://montaj.ag/)):**
  1. Drop in footage ("It stays there").
  2. "Tell AI what you want. Plain words."
  3. "Get a polished video in minutes … change anything you want."
- **Project types (engine):** `editing`, `music_video`, `ai_video`, `carousel`. All four follow the same flow: upload, then `project.json [pending]`, then the agent edits and marks `[draft]`, then the human reviews and marks `[final]`, then render (docs intro, as indexed).
- **Inputs:** local clips, photos, logos and screenshots. Optional reference images for carousels. A prompt. A workflow (a recipe of steps). An optional creator style profile.
- **Outputs:**
  - Video: MP4 in any aspect ("16:9 YouTube · 1:1 LinkedIn & X · 4:5 Instagram · 9:16 TikTok, Reels & Shorts", [home](https://montaj.ag/)). The engine's Export dialog offers source-capped resolution, fps capped at the project fps, and an HDR/SDR/Both choice for HDR projects ([UI.md §Render](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md)).
  - **Carousels:** "One PNG per slide at twice the posting size … Or grab all of them in a single .zip". Sizes are square 1:1, portrait 4:5 or vertical 9:16, picked at creation and locked ([carousel page](https://montaj.ag/use-cases/instagram-carousel); `montaj init --workflow carousel --carousel-aspect …` per the [CLI docs](https://docs.montaj.ag/cli)).
  - Example slide files on the page are `slide_01.png` … at 2160×2700. Pablo's capture is also 2160×2700.
- **Use cases with their own pages ([use cases](https://montaj.ag/use-cases)):** talking head, captions, carousel, B-roll, lower thirds, motion graphics, text animation, AI video.
- **Talking-head pitch ([page](https://montaj.ag/use-cases/talking-head)):** "Drop in every take. Montaj keeps the best one, trims the pauses and cuts the ums."

## 2. UI patterns and workflow

**App editor (marketing mock-up, `17-capture-home-03.png`):**
- **Title bar:** project name, a **`draft`** badge, **Re-run** and **Export**.
- **Left:** Media and Captions tabs, a clip list with durations, and caption-style chips (Aa).
- **Centre:** a 9:16 preview with burned captions.
- **Right:** a **Prompt** panel ("turn this into a reel.") with **progress chips**: ✓ cutting pauses, ✓ adding captions, ✓ matching your style.
- **Bottom:** the timeline with **V1 / A1 / CC** (caption) tracks.

The carousel editor mock-up (`20-…`) swaps the timeline for a slide strip (left) and a slide canvas (centre). It keeps the prompt on the right and adds **Schedule** beside Export.

**Engine UI (`montaj serve`, [UI.md](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md)):** "Not a final review step — the UI is the control plane." It has four modes:
1. **Upload:** clips, a prompt and a workflow picker.
2. **Live view:** the agent writes `project.json`, a file watcher pushes each write over SSE, and the timeline and preview re-render as the edit "takes shape".
   - The pending screen shows the command to hand to your agent.
   - It also has a **"Start editing manually"** button, which moves the project into the same `draft` state with an empty timeline.
3. **Review:**
   - Left panel: tabbed browser (Media / Captions / Versions; "Audio, Effects and Text are the obvious future tabs").
   - Right panel: "properties only".
   - Caption editing: inline, plus drag to retime.
   - Overlay editor.
   - **Prompt bar to modify the prompt and re-run the agent.**
4. **Render:** progress streams over SSE.

**Other tabs:**
- **Workflows:** an n8n-style node graph of steps with params rendered from the step schema.
- **Overlays:** live JSX overlay preview with hot recompile.
- **Profiles:** creator style profiles covering pacing, palette, editorial direction and caption style.

**Timeline ([UI.md §Timeline](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md)):**
- Canvas-drawn tracks with filmstrips over waveforms.
- **Tiered snapping:** a strong magnet to the neighbour on the same track, a faint one to other tracks or the playhead, and a visible snap indicator.
- Overlap bands.
- Per-track volume, mute and skip.
- Ripple, roll, slip and slide gestures (CHANGELOG `rippleDelete/rollEdit/slipItem/slideItem`).

**Caption panel:**
- **Format**: fine controls.
- **Styles**: a card grid where each card renders the style's real export template on a four-word sample, so "the preview and the burned-in output can't drift". Hovering plays the animation.
- **Captions**: the transcript list with search, filters and per-segment edits.
- An **"Apply to all"** checkbox.

**Versions ([UI.md §Version history](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md)):**
- Git-backed snapshots on every agent run, every status change and every export.
- Named manual saves.
- **Restore** is non-destructive: uncommitted edits are auto-saved first.
- **Compare** is a two-pane visual diff of any two versions (or the working state) with a shared time-scrub slider.

**Host pins (CHANGELOG):** read-only flags on the timeline ruler that the host supplies. They "never enter the project document", so they can't mark it dirty or change a render.

**Keyboard ([UI.md §Keyboard shortcuts](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md)):**

| Keys | Action |
|---|---|
| S | Split |
| Delete | Delete |
| ⇧Delete | Ripple delete |
| ←/→ | Step one frame (⇧ for ten) |
| J/K/L | Shuttle at 1×/2×/4× |
| ⌘C / ⌘V / ⌘D | Copy / paste / duplicate |
| ⌘⌥V | Paste attributes |
| F | Fullscreen |
| ⌘Z / ⌘⇧Z | Undo / redo |
| ⌘K | Command palette (state-aware; clicking the timecode opens "go to time") |

## 3. AI features

- **Bring-your-own agent.** "Claude, ChatGPT or Gemini. Connect the one you already use. It is free on every plan" ([home](https://montaj.ag/)). The engine exposes the same steps over **CLI, MCP and HTTP**, which "all wrap the same underlying executables" (docs intro).
- **Steps the agent calls.** Taken from the repo `steps/`:
  - Speech: `transcribe` (whisper.cpp, word-level), `rm_fillers`, `rm_nonspeech`
  - Audio: `waveform_trim` (silence), `detect_beats`, `stem_separation`
  - Media: `detect_shots`, `shot_sheet`, `analyze_media`, `snapshot`
  - Render: `contact_sheet`, `sample_frame`, `sample_diff`
  - Edit and transform: `jump_cut`, `cross_cut`, `montage`, `reframe`, `resize`, `generate_captions`, `remove_bg`
  - Generate: `kling_generate`, `seedance_generate`, `generate_image`, `generate_music`, `generate_sfx`, `generate_voiceover`
  - Misc: `capture_site`, `search_images`, `search_news`
  - The quickstart pipeline also lists `select_takes`, which picks the best take from repeats.
- **Workflows are "suggested editing plans".** "The agent reads the plan, reads the prompt, and decides the actual execution" ([README](https://github.com/theSamPadilla/montaj)). Built-in workflows include `clean_cut`, `overlays` (the default), `ai_video`, `lyrics_video`, `animations`, `explainer` and `floating_head`. The repo `workflows/` folder today holds `ai_video`, `blank`, `carousel` and `overlays`.
- **Style profiles.** "Pick your favorite fonts, colors, text overlays and caption styles … When AI edits your videos, it uses your style" ([home](https://montaj.ag/)). The engine profile also covers pacing and editorial direction ([UI.md §Profiles](https://github.com/theSamPadilla/montaj/blob/main/docs/UI.md)).
- **Carousels.** The agent generates slide backgrounds, writes overlays as JSX, builds `project.slides[]`, and sets `status: "final"`. The pending screen flips to a "live status" view while it works ([carousel docs](https://docs.montaj.ag/projects/carousel)).
- **Generative video.** "Bring your own models … like Kling and Seedance, with your own keys" ([home](https://montaj.ag/)).
- **Content hub (Hub tier, [content hub](https://montaj.ag/content-hub)):** trend search, brain-dump notes, AI script drafts "in your voice", a pipeline board (Idea → Scripted → Recorded → Edited → Ready), a calendar, a teleprompter, "one idea, two posts" (script → reel + carousel), and auto-scheduling via Sprout Social or Metricool.
- **Studio (coming soon, [studio](https://montaj.ag/studio)):** review links where "clients comment at the exact moment", and "Review comments land on your timeline. Ask your AI to fix them in one message."

## 4. Pricing and availability (as stated publicly, Oct 1, 2026 ET)

**Plans ([pricing](https://montaj.ag/pricing)):**

| Plan | Price | What's included |
|---|---|---|
| **Free** | $0 | "No account needed": full editor, captions, full-quality saves, BYO AI and keys |
| **Hub** | $14.99/mo, or $12.42/mo billed annually ($149/yr per [hub](https://montaj.ag/hub)) | 7-day trial (card required) |
| **Studio** | $49.99/mo for 3 seats, or $40/mo billed annually ($479/yr) | Coming soon. Extra seats $9.99/mo or $99/yr |

**Platform:** "Mac. Windows is coming later" ([vs CapCut](https://montaj.ag/vs/capcut)). The engine CLI runs on macOS and Linux (docs, as indexed).

**Availability:** the site's buttons say "Join the waitlist", and Pablo's capture says "You must be on the waitlist for free access". Two things are **unknown**:
- whether the Mac app can be downloaded publicly today, or only by waitlist invite
- why the waitlist is needed when the Free plan is described as free with no account

The open-source engine can be installed now via pip, Homebrew or source ([README](https://github.com/theSamPadilla/montaj)). We did not install it.

**Inconsistency in the changelog:**
- An older entry (v4.6.5) says connecting your own AI through the app's generated MCP config "requires a Studio subscription".
- A later entry removes that check: "The desktop app's Free tier now works without an account".

The current public line is "free on every plan".

## 5. License and openness

- **Engine:** MIT ([LICENSE](https://github.com/theSamPadilla/montaj/blob/main/LICENSE)). Reuse would be legally fine with attribution. This pass is **ideas only: no code was copied**, and Hermes Studio has its own engine plan.
- **Mac app, Hub and Studio:** proprietary, under ByCrux LLC [terms](https://montaj.ag/terms). Hub templates may not be redistributed. Plans are limited to a number of Macs.
- **Unknown:** which app-only parts (Hub, scheduling, packaging) are closed. The README implies the editor UI is shared: `@bycrux/editor` is in the MIT repo.

**Unknowns:**
- real app UI (no genuine screenshots)
- user counts
- export limits beyond "no cap"
- Windows timing
- the waitlist rules
- the date of the TikTok post. The search engine attributed a Sep 24, 2026 @techbyjaz post, but we did not see it.

## 6. Worth borrowing as ideas for Hermes Studio

Each idea maps to our plan: transcript-first left panel, preview, 4-track timeline, agent sidebar on the right, and Propose with approval for each edit.

| # | Montaj idea | Where it fits in Hermes Studio | Tier |
|---|---|---|---|
| 1 | **Progress chips in the agent panel** (✓ cutting pauses / ✓ adding captions / ✓ matching your style), plus **Re-run** with an edited prompt and a **`draft` badge** in the title bar | Right sidebar: show each step of a Hermes plan as a chip that turns into its Propose card(s). The title bar shows `draft` while agent edits are unapproved. | **must** (sidebar UI) |
| 2 | **Project lifecycle `pending → draft → final`**: the agent may only ever produce `draft`, and only a human makes `final`. "Start editing manually" lands in the same state, so nothing downstream can tell the two paths apart. | Matches Propose: agent output is a draft that a human finalises. Reinforces the Phase 2 **draft branch**. Use one state model for both agent and manual paths. | **v1** (Phase 2 draft branch) |
| 3 | **Style profile as a standing agent input** (fonts, colours, caption style, pacing, editorial direction), applied on every edit | Phase 2 **presets**: a per-user or per-channel `style.json` that Hermes reads before proposing captions or cuts | **v1** *(proposed)* |
| 4 | **Caption style cards render the real export template**, so the preview can't drift from the burn-in | Captions UI over our ASS burn-in: render style thumbnails through the same ASS path as export | **v1** |
| 5 | **Visual version Compare** (two frames at time T from any two versions), plus **non-destructive Restore** (auto-save before restore) | Checkpoints/oplog: "compare checkpoint vs now" on a scrub slider, and always snapshot before a restore | **v1** *(proposed)* |
| 6 | **Host pins**: read-only ruler flags that never enter the project document | Show agent analysis (scenes, silences, filler words, review notes) as ruler pins that don't touch the oplog until someone acts on them. A clean fit for pattern P13. | **must**/v1 |
| 7 | **Best-take selection** (`select_takes`) for repeated takes | A transcript-level tool: group near-duplicate sentences and propose keeping one. Shown as a grouped Propose card. | **v1** *(proposed)* |
| 8 | **Workflows as suggested plans the agent may deviate from** (not rigid macros) | Phase 2 presets: a preset is a plan plus default params, and Hermes still proposes each op | **v1** |
| 9 | **One tool surface over CLI, MCP and HTTP** ("all wrap the same underlying executables") | Already our approach (MCP + ACP over one registry). Montaj confirms it. Add a CLI wrapper later for headless runs. | must (confirms) / later (CLI) |
| 10 | **Tiered snapping**, **state-aware ⌘K palette**, and **click the timecode for go-to-time** | Timeline polish and the proposed command palette | v1 |
| 11 | **Carousel output**: the same project or script becomes N PNG slides (1:1 / 4:5 / 9:16, 2× posting size, zip) | Not a video-editor feature. A **later** export: transcript sections → captioned stills on the T1 style. | **later** *(proposed)* |
| 12 | **Review links with timestamped comments that the AI fixes** (Studio) | Comments become pins (idea 6) that turn into a Hermes task. Hosted sharing is out of scope for a local editor. | **later** |

**Skip:**
- Trend search, the posting calendar and auto-scheduling via Sprout Social or Metricool: publishing is on the never-in-`tools/list` list.
- The teleprompter: out of Edit page scope.
- Hosted Hub templates.
- Generative-video keys (Kling, Seedance): already "later, optional plug-ins".
- The engine's "agent decides everything, human reviews after" default. Hermes's per-edit Propose gate is the stronger trust model, and Montaj has no per-op approval: review happens after the whole draft.
