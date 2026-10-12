# Plan: Hermes Studio — pro-class editor + AI chat

**Status:** PLAN ONLY. No code, no branch, no PR. For Sir's approval.
**Written:** 2026-10-10, by ILO.
**Trigger:** Sir, 2026-10-10 — "I want a 1920x1080 video not a phone preview… a complete video
editor experience from everything you have learned… and if it's not invented than created it from
all the editors you have researched. As well integrate a ai chat integration like from Hermes
Desktop on the side like the left side to be able to chat with any ai model with an API key or a
direct connection to the backend like Hermes Desktop to their Hermes agent."

**Sir's decisions (answered 2026-10-10):**
1. Target = **pro editors** (Resolve / Premiere / CapCut class): full toolset, keyframes,
   transitions, speed ramps, audio mixer, color grading, masks.
2. Chat panel = **left sidebar, always visible, collapsible**, like Hermes Desktop.
3. Chat backend = **both**: Hermes agent as default *and* a model picker for any API-key provider.
4. Deliver the **plan first**, for approval — no code until Sir says go.

---

## 0. What is true today (verified, not assumed)

**Shipped and proven on `feat/video-editor` (PR #44, commits `bd531b8`…`116f6fd`):**
trim, split, lift, undo/redo via the op log; playhead frame preview; library film import;
audio that survives a split; canvas presets + typed size (Phone/Desktop/Square) with undo;
**render to a real mp4** (`render_timeline.py`); **transcript tab** (words under the right
picture); **activity panel** (who changed what, from `history_diff`); **draggable panel split**
with a persisted layout and a Hide/Show fold.

**Studio already has, in code:**
- 8 colour looks in `look.py` (`FILTERS`) — punch, warm, cool, cinematic, vintage, bw, bright.
- Word-highlight ASS captions with styles (`captions.py`, `STYLES`: pop, impact, …).
- Audio clean-up chain: `highpass` + `afftdn` + `loudnorm` (`look.py:AUDIO_CLEAN`).
- Face-aware framing (`framing.py` + YuNet) and layout auto/fill/split/fit.
- Progress bar, caption placement that clears platform UI.
- Tight pacing that drops ums/uhs on real words (`pacing.py`).
- 5 tool modes: clip, captions, reframe, tighten, transcript.

**ffmpeg capability in this build — verified with `ffmpeg -filters`:**

| Need | Filter | Present |
|---|---|---|
| Transitions | `xfade` (fade, dissolve, wipe*, slide*, circle*, and more) | yes |
| Ken Burns / motion | `zoompan` | yes |
| Colour grading | `curves`, `lut3d`, `colorchannelmixer`, `vibrance`, `colortemperature` | yes |
| Keyframable | `rotate`, `scale`, `crop`, `eq`, `hue`, `drawtext`, `overlay` (all accept `enable`/expressions) | yes |
| Speed | `setpts`, `atempo`, `rubberband` (pitch-preserved) | yes |
| Motion interpolation | `minterpolate` | yes |
| Audio mixer | `volume`, `adelay`, `amix`, `apad`, `atrim`, `afade`, `atempo` | yes |
| Audio FX | `acompressor`, `agate`, `aphaser`, `flanger`, `aecho`, `dynaudnorm`, `afftdn` | yes |
| Ducking | `sidechaincompress` | yes |
| Metering | `ebur128`, `astats` | yes |
| Blur / vignette | `boxblur`, `gblur`, `vignette` | yes |

> *`xfade` ships fade/dissolve plus a set of named wipes/slides in this build; the exact list is
> confirmed at build time, and the UI reads what exists rather than hardcoding names.

**Not present:** `saturation`/`brightness` as standalone filters (use `eq`), `transform`,
`displano`. None of these block the plan.

**AI side — verified:**
- A **Hermes agent is running locally on `127.0.0.1:9119`**, v0.21.5, and answers
  `/api/health` and `/api/status` unauthenticated. It exposes **299 OpenAPI paths**.
- `/api/sessions`, `/api/providers`, `/api/model`, `/api/config` all return **401 Unauthorized**,
  so the chat panel **cannot** reuse an existing browser session — it needs either a loopback
  token or its own key path. **This is the one real unknown in the plan** (see §6, R1).
- There is **no `POST /api/chat`** in the OpenAPI surface; chat in Hermes Desktop goes through
  the web UI / a websocket, not a documented REST turn endpoint. So "direct connection to the
  Hermes agent" most likely means **the gateway's own chat path**, which we must confirm before
  building against it.
- Studio's only existing AI path is the clip **namer** (`namer.py`), which already speaks
  OpenAI-compatible HTTP and Ollama through `net.post_json` (scheme-checked, size-capped). The
  chat backend should reuse that same one-way-out helper, not a new HTTP client.
- Provider keys live outside the repo (`the secrets folder`); Studio has **no** `.env` today.

---

## 1. Non-negotiable house rules (unchanged by this plan)

- **The op log is the only writer.** Every edit lands in `oplog.jsonl` through
  `/api/editor`; the desk never writes `timeline.json`. New features add ops, they do not
  bypass the log. This is what makes undo/redo and the Activity panel keep working.
- **`tl-` class prefix only** on the Edit page. `ed-`/`ed-top` belong to the Design grid.
- **Media paths stay inside the project.** No absolute paths, no `..` (`resolve_media`).
- **All outbound HTTP goes through `net.py`** — http(s) only, response capped.
- **Secrets never in the repo.** Provider keys come from `the secrets folder` or the environment;
  nothing is committed, nothing is echoed to a transcript.
- **Main is protected.** Work lands on a branch, via PR, with `test` + `secrets` + `linux` +
  `windows` + CodeQL green. Never commit on local `main`.
- **One product.** Edit page, Design page and Studio share the Vektra-amber visual language and
  the same `contain`-not-`cover` framing rule.
- **No fabricated output.** Every claim in a report is backed by real tool output.

---

## 2. The gap, honestly stated

| Capability | Today | Target |
|---|---|---|
| Timeline tools | trim, split, lift, move, nudge | + ripple/roll, slip, slide, multi-select, snap to playhead/clips/zero, markers |
| Transitions | none | cross-dissolve + wipes/slides at a cut, with duration, undoable |
| Keyframes | none | animate position, scale, rotation, opacity, volume over time, with easing |
| Speed | none | constant 0.1×–10×, reverse, freeze frame, **speed ramps** |
| Colour | 8 preset looks | 3-way colour wheels, curves editor, HSL, white balance, LUT import, scopes (waveform/parade) |
| Masks | none | shape + feathered mask, per-clip effect isolation |
| Audio | clean-up + loudnorm | real mixer: per-track gain/pan/mute/solo, fades, ducking, meters, keyframe volume |
| Text | burn-in captions | title/text objects on their own track, style, position, animation |
| Preview | playhead frame | **real playback** of the assembled cut in the canvas |
| Export | one mp4 | resolution/format/fps choices, quality tiers, progress, cancel |
| AI chat | none | left sidebar chat, Hermes agent by default + any API-key provider, with edit context |
| Default canvas | Phone 1080×1920 | **Desktop 1920×1080 as the default** (Sir's explicit ask) |

That is a lot. §4 sequences it so each phase ships something real and provable.

---

## 3. Architecture

The editor today is: `timeline.py` (doc) → `oplog.py` (ops) → `editor.py` (store) →
`studio.py` (HTTP) → `ui/editor.js` (page) → `render_timeline.py` (ffmpeg).

**The rule for every new feature: it is an op in the op log first, a render path second, a UI
third.** That ordering is what keeps undo, the Activity panel and the transcript honest.

```
timeline.py    doc schema: transitions[], keyframes[], speed, audio mix, text objects
oplog.py       one op per feature, each with an inverse for undo
editor.py      the store call the desk uses (set_transition, add_keyframe, …)
render_timeline.py   turns the doc into an ffmpeg graph
studio.py      POST /api/editor op dispatch + GET for media/frame/transcript/history/render
ui/editor.js   the page: preview, timeline, inspector, tabs, chat rail
ai.py  (new)   one chat backend: Hermes agent + OpenAI-compatible providers, via net.py
```

**Preview is the hard part.** Today the page shows a JPEG at the playhead. A pro editor plays
the cut. Two honest options (see R2): (a) play the **rendered** file for full fidelity, or
(b) a lightweight in-browser compositor that plays the clips with transitions applied. (b) is
what CapCut-class editors feel like; (a) is far cheaper and always correct. Recommend (a) first,
(b) as a later phase.

---

## 4. Phased plan (each phase = one branch, one PR, real proof)

### Phase A — Desktop-first canvas + real playback preview
- Default new projects to **1920×1080**; Phone/Square remain one click away.
- Add a **playback preview**: assemble and play the cut in the canvas (see R2), with a working
  playhead, scrub, and in/out markers.
- Fix the one thing a reviewer will hit immediately: the inspector's 280px column competes with
  the picture; make it collapsible.
- **Proof:** a 1920×1080 cut plays start to finish in the desk; screenshot + a real play.

### Phase B — Timeline tools that professionals expect
- Ripple and roll trim, slip and slide, multi-clip selection, markers.
- Snap targets: playhead, clip edges, zero, markers (already partly there).
- Keyboard: J/K/L, I/O, comma/period, plus the existing space/S/N/Ctrl-Z set.
- **Proof:** the same operations demonstrated, each undoable, each logged in Activity.

### Phase C — Transitions
- New op `set_transition` with a duration; renders through `xfade`.
- Placed at a cut; undo restores the hard cut.
- **Proof:** a dissolve and a wipe, before/after frames, both undoable.

### Phase D — Keyframes
- New op `add_keyframe` / `set_keyframes` for position, scale, rotation, opacity, volume, with
  easing. Renders through ffmpeg expressions on keyframable filters.
- A keyframe lane under the clip, draggable.
- **Proof:** a push-in and a fade that animate, exported and matching the preview.

### Phase E — Speed
- Constant speed (0.1×–10×) with pitch-preserved audio (`atempo`/`rubberband`), reverse,
  freeze frame, and **speed ramps** (keyframed speed).
- **Proof:** a ramp from 1× to 0.25× and back, audio still in sync.

### Phase F — Colour
- 3-way wheels, curves, HSL, white balance, LUT (.cube) import, plus waveform/parade scopes.
- Existing 8 looks stay as presets on top of the real controls.
- **Proof:** a graded clip, scope reading shown next to the picture.

### Phase G — Masks
- Shape + feathered mask, per-clip effect isolation.
- **Proof:** an effect applied to half the frame with a soft edge.

### Phase H — Audio mixer
- Per-track gain/pan/mute/solo, fades, keyframe volume, **ducking** via `sidechaincompress`,
  meters, loudness normalise on export.
- **Proof:** music ducking under voice, meters moving, output measured with `ebur128`.

### Phase I — Text objects
- Real text on its own track: content, style, position, size, animation — not just captions.
- **Proof:** an animated title that survives re-render.

### Phase J — Export
- Resolution / format / fps / quality choices, progress, cancel, and a "matches preview" check.
- **Proof:** an export at each tier, verified with `ffprobe`.

### Phase K — The AI chat rail (left sidebar)
- Collapsible left rail, always available, Hermes Desktop in feel.
- **Backend:** `ai.py` — Hermes agent by default, plus a picker for OpenAI-compatible providers
  (Anthropic / xAI / OpenAI / any base URL + key). All outbound via `net.py`.
- **Context awareness:** the chat knows the open project — canvas, duration, clip count, the
  selected clip, the transcript. It can answer "what's at 0:22?" and propose edits.
- **Act, don't just talk:** an "apply" affordance that turns a suggestion into real ops through
  the op log — so AI edits are undoable and appear in Activity, exactly like Sir's own.
- **Proof:** a real conversation that makes a real, undoable edit; keys never printed.

**Sequencing note:** A–E are the core editing feel; F–J are depth; K is the AI rail and can be
built in parallel once `ai.py` exists. If Sir wants something in his hands fastest, the order is
**A → C → K**: desktop canvas with playback, transitions, then the chat — that already feels like
a real editor.

---

## 5. What "created, not copied" means here

Sir said: if it isn't invented, create it from what the research shows. Concretely:

- **A draggable, persisted panel layout** — already built, ahead of CapCut's presets.
- **An op log with a real inverse for every op** — so *every* AI action and every tool action is
  undoable and attributable. Resolve and Premiere do not expose this; it is the thing that makes
  "let the AI edit" safe.
- **An Activity panel that reads the log** — who changed what, struck through when undone.
- **Transcript and activity as first-class tabs** in the same sheet as the timeline.
- **The chat that acts through the op log** rather than mutating files — the same discipline the
  house already uses for every other write.

---

## 6. Open questions for Sir (need answers before Phase A/K code)

- **R1 — Hermes agent auth.** `/api/sessions`, `/api/providers`, `/api/model` are 401. To chat
  with the local agent I need either (a) a loopback token from the Hermes config stored in
  `the secrets folder`, or (b) permission to use provider keys directly (Anthropic/xAI/OpenAI)
  from the house keyring. Which does Sir want as the default backend?
- **R2 — Preview fidelity vs cost.** Play the **rendered** file (always correct, cheap, but a
  re-render per change) or a **live compositor** in the browser (instant, CapCut-like, much more
  work)? Recommend rendered-first.
- **R3 — Scope of one push.** Pro-class is many phases. Does Sir want all of A–K planned and
  built in order, or A + C + K first (desktop playback, transitions, chat) as "feels like a real
  editor," with the rest to follow?
- **R4 — Local models.** Ollama is deliberately off (GPU saved). The chat can offer it later as a
  provider, but it stays off unless Sir asks to wake it.

---

## 7. Cost and risk, honestly

- **This is not a small build.** A–K is realistically several PRs, each with tests and proof. The
  plan is written so every phase is independently shippable and revertible.
- **Main risk: preview.** Everything else is a filter graph, which ffmpeg already supports. A
  live compositor (R2 option b) is the one genuinely hard piece; the rendered-file approach
  sidesteps it.
- **Second risk: the Hermes chat backend.** Until R1 is answered, Phase K has no confirmed
  transport. `ai.py` will be written so the provider is pluggable, so this cannot block A–J.
- **Testing.** Each phase gets real proof: `ffprobe` on exports, `ebur128` on audio, before/after
  frames for transitions, and the browser driven for UI. No "it renders" claims.

---

## 8. What I will not do without Sir's word

- Touch `grid-boot` or wake Ollama (standing order from 2026-10-07).
- Merge PR #44 or any of this work — main is protected and every merge is Sir's call.
- Put any provider key in the repo, a log, or a transcript.
- Publish or post anything. Studio stays local; Sir posts.

---

**Recommendation:** approve **Phase A + C + K** as the first push (desktop canvas with real
playback, transitions, and the AI chat rail), with F–J queued behind. Answer **R1** (chat
backend) and **R2** (preview approach) and I will start on a branch.
