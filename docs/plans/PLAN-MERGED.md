# Hermes Studio editor: merged plan

Oct 1, 2026 (ET). Planning only: no code changed, nothing cloned, nothing pushed.
Merges: `REPO-AUDIT.md`, `RESEARCH.md`, `PLAN.md` (Rin), `SECTION-GLYPH-UX.md`, `SECTION-WIRE-AGENT-INTERFACE.md`, `SECTION-BAY-ENGINE.md`, `SECTION-PROVE-ACCEPTANCE.md` (final, 03:20 AM ET).

---

## 1. The one seal

> **Approve building the editor inside the existing Hermes Studio repo and app (no fork of Kdenlive/Shotcut/OpenCut, no switch to Remotion), starting with slice 0: fix the FFmpeg/PyAV license notices and packaging, then cut v0.5.3 so the already-published v0.5.0–v0.5.2 binaries are covered?**

**Yes** starts slice 0 right away: the notices, the license texts inside the built app, and a v0.5.3 release. After that, the editor work begins with the timeline schema (slice 1).
**No** means nothing gets built and nothing gets released. The published v0.5.0–v0.5.2 binaries keep shipping GPL FFmpeg without its notice until you decide something else.

## 2. What we're building

- **A timeline video editor inside Hermes Studio.** It adds a new Edit page with a transcript, a preview and a 4-track timeline. You can use it entirely by hand.
- **Agents can drive the same editor end to end.** Hermes connects over ACP and other models connect over MCP. Every edit goes through one engine, shows up live, and can be undone.
- **A sidebar where you watch and chat with the agent.** It shows the plan, one card per edit with Undo, and Stop. The default mode is Propose: the agent asks before each edit.

## 3. Phases

| Phase | Exit test (all PASS/FAIL, Prove's IDs) | Size |
|---|---|---|
| **0 Foundations** (slices 0–3) | Slice 0: N1–N5 pass on the built AppImage and NSIS, and v0.5.3 is out. Then a script builds a 3-clip timeline over MCP and undoes it, and the hash round-trips: C1–C9 pass | **~4 weeks.** Engine ~4 wk (Bay S0–S3); Wire ~1.5 wk and Prove ~2 wk run in parallel |
| **1 MVP editor + sidebar** (slices 4–8, plus ACP and UI) | The PLAN §1 scenario, scripted (E1–E8) on clean Linux and Windows, run (a) by Hermes over ACP and (b) by a plain-MCP client. C10–C12 gate slices 5–8 | **~6 weeks calendar.** Engine ~5.5 wk (S4–S8); Wire ~2; Prove ~2; Glyph ~1 design + 3–4 build |
| **2 Agent quality** | Q1 eval set (20 tasks), Q2 draft branch, Q3 presets | ~4 weeks calendar (PLAN §4). Wire ~1, Prove ~1 |
| **3 Pro and reach** | Not specified yet | Not sized |
| **Total** | | **~10 engineer-weeks of engine work** (Bay §6: 2 S + 5 M + 2 L), which is the critical path. Wire (~4.5), Prove (~5) and Glyph (~4–5) work alongside it |

---

## 4. Architecture

**The stack.** We keep the Python engine (`api.py` first), FFmpeg called as a subprocess, and the Electron shell. There is no new runtime (SECTION-BAY-ENGINE.md §1). The Edit page talks to the same loopback engine that `desktop/main.js` already starts, using REST + SSE, with no IPC to Python. The sidebar's ACP client runs in Electron main and spawns `hermes acp`, passing it our MCP server (RESEARCH.md §4.2, PLAN.md §2).

```
Edit page ──REST ops / SSE events──┐
Sidebar ⇄ Electron main ⇄ hermes acp ──MCP──┐
Other MCP clients (Claude/Cursor/Grok) ─────┤
   stdio `hermes-studio mcp` (attaches) ────┤
                                            ▼
             Engine (Python, loopback): api.py registry → mode gate → oplog → timeline.json
                                            ├─ event bus (seq) → SSE / MCP resources
                                            ├─ media jobs (probe, proxy, thumbs, wave, Whisper)
                                            ├─ frame cache
                                            └─ render queue (FFmpeg filter graph)
```

### 4.1 Engine: the only writer
- **Project folder** `~/.hermes/clips/projects/<id>/` holds `timeline.json` (written atomically with tmp+replace, as `design.py` already does), `oplog.jsonl`, `snapshots/` (one every 50 versions) and `cache/` (SECTION-BAY-ENGINE.md §2, §4).
- **Per-project lock.** `.lock` holds the pid, port and token hash, and is backed by an OS file lock. One engine owns each project. The stdio `hermes-studio mcp` reads `.lock` and **attaches to the running engine**. It never opens the project files for writing itself. A stale lock left by a killed engine is recovered (Bay §2, Wire Gaps, Prove C7).
- **Engine is the only writer.** The Streamable HTTP endpoint `127.0.0.1:<port>/mcp` serves MCP clients. The recommended route is the official `mcp` Python SDK with pinned protocol versions (Wire Gaps).
- **When the app is closed (Phase 1),** reads still work but every write tool is refused (see Decisions).

### 4.2 Timeline document
The document is OTIO-shaped JSON, `"schema":"hs.timeline/1"`, with `version` (a monotonic integer) and `hash`. The full example is in Bay §2.
- `hash` is the sha256 of canonical JSON, leaving out `version` and `hash`. Equal content gives an equal hash, so undoing back to a state gives back its hash.
- `media` is a map of `m1` → path, duration, fps and proxy.
- Tracks hold items with stable ids. A `clip` has `src:[in,out]` in media seconds and `at` in timeline seconds. Gaps are implied by `at`.
- A `transition` (Phase 1: `xfade` only) sits `between` two clip ids. `text` items have `at`, `dur`, `text` and `style`.
- Effects are a small `props` map: volume, speed, crop, look.
- OTIO export maps clips to Clip + `source_range` and gaps to Gap. `.otio` must open in `otiotool` (Prove C1).

### 4.3 Op log
Each line of `oplog.jsonl` has `seq`, `op_id`, `client_op_id`, `group_id`, `actor`, `summary`, `base_version` → `new_version`, `hash`, `ops`, `inverse`, `changed_ids` and `undoes` (Bay §3, Wire §1).
- **Actor comes from the session token, never from tool arguments.** A forged `actor` argument is ignored (Wire §1, Prove C5).
- **Inverses are computed by the engine at apply time:**
  - insert/add → delete by the new id
  - delete/remove → re-insert at the old place, and un-ripple
  - move/trim/set_props → the same op with the old values
  - `split_clip` → `join_clips`, which restores the old id (Bay §3)
- **Batches are atomic.** One `timeline_apply` batch is all ops or none, including on a fault at op k or a `kill -9` (Prove C3). Calls that belong together share a `group_id`. "Remove fillers" compiles through `pacing.keep_intervals` into one batch: one entry, one card, one Undo (Bay §3, Glyph Gaps).
- **Dedupe.** `(actor, client_op_id)` is unique. A retry returns the original result and does not apply again.
- **Undo is a new reverse entry** (`undoes: op_id`). History is never rewritten.
  - Undoing a group applies all the inverses in reverse order as one entry.
  - Agents may undo only their own entries. Humans may undo anyone's.
  - If an inverse no longer applies cleanly, the result is `undo_blocked` with the dependent `op_id`s (Wire §3, Bay §3).
- **Checkpoints** are a version number. Restoring one means taking the nearest snapshot at or below it, replaying the log forward, and appending the result as a new entry. `checkpoint_restore` is human-only in Phase 1 (Wire §3).

### 4.4 Event bus
- One append-only bus, fed by the op log. Every event carries a monotonic `seq` plus `op_id`, `actor` and `version`.
- Event types: `op.applied`, `op.undone`, `timeline.changed`, `approval.pending`, `run.paused`, `job.progress`.
- **UI:** SSE. A reconnect with `Last-Event-ID` replays from the log with 0 gaps and 0 duplicates (Prove C8).
- **MCP:** `notifications/progress` for jobs (already in `mcp.py`), plus a `timeline://<project>` resource with `resources/updated`, so non-ACP agents notice human edits (Wire §2).

### 4.5 Tool contract and error codes
- **Every tool:** JSON in, JSON out (`structuredContent` plus a text copy). Times are float seconds on the timeline clock, and everything is addressed by stable id (PLAN §3).
- **One registry in `api.py`** generates MCP `tools/list`, the CLI and the native plugin (Wire §1).
- **Write tools take:** `project_id`, `base_version`, ops/args, a user-facing `summary`, optional `group_id`, and `client_op_id`.
- **Write tools return:** `op_id`, `group_id`, `new_version`, `summary`, `changed_ids`, `before_frame`/`after_frame` refs (bytes only through `timeline_frames`), and `warnings`.
- **Tools:**
  - **Read:** `project_list/open/new`, `timeline_get` (`summary=true` for an outline), `media_list/probe`, `transcript_get`, `scenes_get`, `timeline_frames`, `timeline_contact_sheet`, `history_list/diff`.
  - **Write:** `media_import`, `timeline_apply`, `transcript_cut`, `captions_generate`, `reframe`, `history_undo/redo`, `checkpoint_restore` (human-only).
  - **Render:** `render_preview`, `render_final`, `job_status`, `export_project` (PLAN §3).
- **Phase 1 ops in `timeline_apply`:** `insert_clip`, `move_clip`, `trim_clip{ripple}`, `split_clip`, `delete_clip{ripple}`, `set_props`, `add_text`, `add_transition{kind:"xfade"}`, `add_track/remove_track`, `add_marker`. `keyframe` is held until Phase 3.
- **Never in `tools/list`:** publish, upload, post, shell, exec, or file writes outside the project. A contract test checks the exact allowlist and checks that the MCP, plugin and CLI tool sets match (Prove C9).
- **Error codes** (existing `code` + `hint`):

| Code | When | Extra fields |
|---|---|---|
| `conflict` | stale `base_version`; the run pauses | `current_version`, `history_diff` |
| `invalid_op` | validation failed; nothing applied | `hint`, the failing op index |
| `permission_denied` | Ask mode write, or a missing scope | — |
| `needs_approval` | Propose write is parked | `pending_id` |
| `undo_blocked` | the inverse doesn't apply cleanly, or an agent tries to undo a human's entry | dependent `op_id`s |
| `project_locked` | another engine owns the project | owner pid/port |
| `engine_offline` | write attempted through stdio while the app is closed | `hint`: open the app |

Results also have one non-error status: `skipped`, when a person skips a parked write. `project_locked` and `engine_offline` are names I chose for the lock and app-closed refusals, which the sections describe but don't name.

### 4.6 Ask / Propose / Auto, enforced in the engine
The mode lives in the engine because MCP clients never pass through ACP (Wire §4).
- **Ask:** writes return `permission_denied`.
- **Propose (the default):**
  - A write parks as `approval.pending`, and the MCP call returns `needs_approval` + `pending_id` instead of hanging.
  - Apply, Skip or Apply the rest resolves it.
  - For Hermes, ACP `session/request_permission` is the same prompt, so the person is never asked twice (Wire §4).
  - The timeout rule is under Decisions.
- **Auto:** writes apply live, and each one can still be undone.
- **Tokens:** a bearer token per launch and per session, scoped `read`/`write`/`render`. Loopback only, with the `studio.py` Host/Origin checks, and caps on ops per batch and on render size.

### 4.7 Media and frame cache
- **Import** runs as background jobs on the existing queue (Bay §4):
  - `ffprobe` (including the VFR flag)
  - a proxy: 540p H.264, 0.5 s GOP, CFR
  - a thumb strip: 1 frame every 2 s, as a 160 px sprite
  - a waveform: 16 kHz peaks, via `transcribe.extract_wav`
  - Whisper words, mapped to timeline time
- **Frame key** = `sha256(the visible recipe at t)` + size. The recipe is what's visible at `t`, not the whole timeline. An edit at 0:40 leaves the 0:05 frame cached, and v12's "after" is v13's "before" (Bay §4, Prove C10).
- **Making a frame:** one `ffmpeg -ss` on the proxy, about 50–150 ms, to a 320 px JPEG. Card frames are made eagerly at the first changed time.
- **Cache size:** frames and previews are LRU with a 2 GB cap. Proxies, thumbs and waveforms are kept while their media is referenced. `hermes-studio cache clear` deletes it all.
- **Preview v1:** a sequence player over the proxies, with canvas text and captions. Anything it can't show exactly gets a short 540p preview segment rendered by the engine and cached by recipe hash.

### 4.8 Render v1 (FFmpeg filter graph)
- One graph per timeline, extending `render.py`: per-clip `trim/atrim` → `xfade`/`acrossfade` or `concat` → `overlay` text → `ass` captions → `amix` → the existing `_encode_tail` (libx264 + AAC).
- Above about 40 clips, it renders per segment and joins them with the concat demuxer.
- The job queue reports progress.
- Golden tests use ffprobe + SSIM, never file hashes (Bay §4, Prove Gaps).

### 4.9 License fix (slice 0)
The GPL FFmpeg build stays as a separate executable (Decisions). The packaging needs these changes:
- **NOTICE gets an FFmpeg section** with:
  - GPL-3.0-or-later as built, and the bundled GPL libraries: x264, x265, libass…
  - BtbN release `autobuild-2026-09-30-13-08`, asset `n9.0.2-17-g2a571b6068`, and the sha256 values
  - source links to **FFmpeg commit `2a571b606854520cf89804d8030c8b328e621689`** (not the `n9.0.2` tag) and to the BtbN build-scripts tag
- **NOTICE gets a PyAV/faster-whisper LGPL section** whose versions match `av.__version__` / `av.library_versions` in the bundled Python.
- **The license texts ship inside the app:** `licenses/FFmpeg-GPL.txt` plus the LGPL text.
- **Packaging:** `electron-builder.json` `files` and `scripts/build-engine-linux.sh` (L71) / `build-engine-windows.ps1` (L60) must copy NOTICE and `licenses/` into the app. Today they copy only the binaries.
- Bump `plugin.yaml` to match the package version (0.5.1 vs 0.5.2 drift; audit §7).
- Cut **v0.5.3** with release notes saying it carries the notices missing from v0.5.0–v0.5.2. Sources: SECTION-BAY-ENGINE.md §5, SECTION-PROVE-ACCEPTANCE.md N1–N5, REPO-AUDIT.md §6.

---

## 5. Build slices (one PR each, in order)

S ≈ 2–3 days, M ≈ 1 week, L ≈ 2 weeks (SECTION-BAY-ENGINE.md §6; Bay's heading there says "Phase 2", but its text puts slices 1–3 in Phase 0 and 4–8 in Phase 1).

| # | PR | Phase | Size | Prove gate |
|---|---|---|---|---|
| 0 | FFmpeg + PyAV notices, license texts in the app, packaging, v0.5.3 | 0 | S | N1–N5 |
| 1 | `timeline.py`: schema, validator, canonical hash, OTIO export | 0 | M | C1 |
| 2 | `oplog.py`: ops + inverses, groups, append-only undo/redo, dedupe, actor rules, conflict | 0 | L | C2–C6 |
| 3 | Project store, `.lock`, stdio attach, event bus (seq + SSE replay) | 0 | M | C3, C4, C7, C8, C9 (with Wire's registry) |
| 4 | Media services: probe, proxy, thumbs, waveform, transcript→timeline | 1 | M | 20-min fixture imports with progress |
| 5 | Frame cache + `timeline_frames` / contact sheet | 1 | M | C10 |
| 6 | Render v1 (filter graph + segment fallback) | 1 | L | C11 |
| 7 | `transcript_cut` / remove fillers as one batch | 1 | S | C12 (filler) |
| 8 | Engine mode gate (Ask/Propose/Auto, parked writes) | 1 | M | C6, C12 (gate), E5 |

Wire's work lands as its own PRs on top of slices 3, 5 and 8:
- **Phase 0:** the registry, the `/mcp` endpoint with token and scopes, and the contract tests.
- **Phase 1:** the ACP client in Electron, the approval bridge, and joining cards on `op_id`.

Glyph's UI starts once slices 1–3 are frozen (Glyph Size).

---

## 6. Edit page and sidebar UX (Glyph)

The comp is `comps/COMP-GLYPH-EDIT-SIDEBAR.png`: 1280×800, Propose mode, Hermes waiting on step 3. It uses the house tokens (`--bg #0b0b0c`, `--amber #ffc83d`, `--ember #cd8032`, Archivo + JetBrains Mono).

- **Layout:**
  - Left rail: a new **Edit** page between Clips and Design.
  - Left panel (270 px) with tabs Media / **Transcript (default)** / Scenes. Click a word to seek. Select text to Delete, Keep or "Ask Hermes about this". Cut words are struck through; words the agent touched have an ember underline.
  - Centre: the preview with transport and timecode.
  - Bottom (250 px): the timeline with T1 text, V1 main, A1 voice and A2 music, plus a playhead and snap.
  - Right (360 px): the Hermes sidebar. It collapses to a 48 px strip that keeps the status dot and Stop visible.
- **Who did what:**
  - Agent clips get an ember outline plus a tag (`H · step 3`). Your last edit gets an ink outline. The tag carries the name, so colour is never the only signal.
  - Follow mode: the playhead jumps to each agent change. Any scrub, click or keypress turns it off; a "Follow Hermes" button turns it back on.
- **Sidebar thread:**
  1. Header: status, Stop, and the Ask/Propose/Auto switch.
  2. Your message, with **Restore to here**.
  3. The plan card: done, current and next steps.
  4. One **edit card** per write: summary, `v12 → v13`, before/after thumbnails, Undo, and Show on timeline. A macro is one card with an expandable op list.
  5. The composer, with context chips for clips, transcript ranges or time ranges.
- **Cards and engine events.** A card joins the ACP `tool_call` (the live text) with the engine `op.applied` (the truth) on `op_id`. It shows "done" only after the engine event (Wire §2, Prove E1).
- **Steering rules:**
  - Propose in Phase 1 means you approve each step with a "waiting for you" card: Apply / Skip / Apply the rest.
  - A human edit pauses the run: "You edited. Hermes paused." with **Continue from here**, which hands Hermes a `history_diff`.
  - Ctrl+Z is linear undo, whoever made the edit. A card's Undo reverses that step only. If later steps depend on it, the button becomes **Restore to before this step**, with a count of the later steps that would go.
  - Stop sends `session/cancel`, keeps the applied steps, and marks the rest "not run".
  - Ask mode greys out write cards.
- **Accessibility and small screens:**
  - Cards have a focus order, and Enter = Apply, Esc = Skip.
  - Step status is announced through live regions, and playhead jumps respect reduced motion.
  - Below 1280 px wide, the sidebar becomes a drawer. The timeline keeps all 4 tracks.

---

## 7. Acceptance checks per phase (Prove)

All checks are PASS/FAIL and run in CI unless marked. **GAP** means it can't be verified yet, with the reason given. Full text: SECTION-PROVE-ACCEPTANCE.md.

**Slice 0, run on the installed or extracted app** (AppImage `--appimage-extract`, silent NSIS install):
- **N1** NOTICE, `licenses/FFmpeg-GPL.txt` and the LGPL text are present in the artifact and byte-identical to the repo copies. This proves electron-builder and the build-engine scripts package them.
- **N2** NOTICE names tag `autobuild-2026-09-30-13-08`, asset `n9.0.2-17-g2a571b6068`, the sha256 values and the GPL libraries. A CI grep fails if `FFMPEG_*_URL` changes without NOTICE changing.
- **N3** `curl -sIL` returns 200 for the **source link to commit `2a571b6068…`** (not the `n9.0.2` tag), for the BtbN scripts tag, and for any tarball or offer link.
- **N4** The bundled `ffmpeg -version` prints `n9.0.2-17-g2a571b6068`.
- **N5** The versions in the PyAV LGPL section equal `av.__version__` / `av.library_versions` in the bundled Python, and its source pointer returns 200.

**Phase 0 exit (slices 1–3):**
- **C1** Schema rejects bad docs; equal content gives equal hash; `.otio` opens in `otiotool`.
- **C2** 1,000 seeded random runs: undo restores the hash; a group undo is one entry.
- **C3** A batch that fails partway (op k fault or `kill -9`) applies nothing and logs nothing, and `timeline.json` is never half-written.
- **C4** A full replay equals the live hash. Restoring to a version between snapshots (e.g. v73) equals a replay from empty.
- **C5** A retry with the same `client_op_id` applies once; a forged actor is ignored; an agent undoing a human's entry gets `undo_blocked`.
- **C6** A conflict pauses the run: `conflict` + `history_diff`, the hash is unchanged, nothing is logged, and `run.paused` fires. A stale retry is refused.
- **C7** A second engine is refused by the lock. The stdio MCP only goes through the engine (strace shows no write opens). A stale lock is recovered. With the app closed, writes are refused and reads work.
- **C8** SSE `seq` is contiguous over 1,000 ops, and replay after a reconnect has 0 gaps and 0 dupes.
- **C9** `tools/list` equals the allowlist, with no publish/upload/post/shell/exec tools. MCP, plugin and CLI match the registry.

**Slice gates landing in Phase 1:**
- **C10** Frame cache keys (S5).
- **C11** A 3-clip + xfade + text + captions render passes ffprobe + SSIM (S6).
- **C12** A 40-op filler cut is 1 entry; Ask mode returns `permission_denied` even over plain MCP; Propose parks the write (S7, S8).

**Phase 1 exit (E1–E8).** Fixture A is *Tears of Steel* 720p, sha256 `efa9062d…8e8f`, using a 60 s dialogue excerpt. Fixture B is still to be picked (Appendix). The script is: import → trim to 45 s → remove fillers → title → `render_final 9:16-1080`. It runs (a) through Hermes over ACP and (b) through a plain-MCP client.
- **E1** One card per `op.applied`, and a card is never "done" before the engine event.
- **E2** Undoing each card restores the earlier hash; the group undo is atomic.
- **E3** Frame refs resolve.
- **E4** ffprobe matches within ±1 frame, h264/aac at 1080×1920, and SSIM passes at 5 timestamps.
- **E5** At timeout the write stays parked; a late answer acts exactly once.
- **E6** A human edit wins.
- **E7** Network goes only to declared hosts (`openrouter.ai`); writes stay inside the project/cache; the source sha256 is unchanged.
- **E8** All of the above pass on clean Linux and Windows.
- **Live gate:** see Decisions. Electron UI checks are manual with screenshots until there is a Playwright-Electron driver.

**Phase 2:**
- **Q1** Eval set of 20 tasks, scored per model and build.
- **Q2** Discard returns the main hash; Keep equals a replay of the branch.
- **Q3** Each preset is one group with one undo.

**Thresholds:**
- Hash match 100%.
- 0 partial batches, 0 duplicate applies, 0 SSE gaps, 0 undeclared hosts or out-of-project writes.
- SSIM ≥0.98 and card p95 <250 ms are still proposals.

---

## 8. Decisions settled by Ada (nothing for Pablo to do)

1. **Propose timeout.** A Propose write that times out stays parked and the run pauses ("Paused, waiting for you"). It never applies or skips on its own, and a late answer applies or skips exactly once. Glyph, Wire and Bay agreed (Glyph §Steering 1, Wire Gaps, Bay §3, Prove E5).
2. **Defaults.** Propose is the default mode, and the Edit page opens on the Transcript tab. This answers Glyph's 2 questions and PLAN Q2.
3. **App closed.** Outside agents can't write while the app is closed in Phase 1; reads still work. A headless engine gets reconsidered in Phase 2 (answers Wire Q1).
4. **Native Hermes plugin.** It stays, as a thin wrapper generated from the `api.py` registry (answers Wire Q2 and PLAN Q4).
5. **FFmpeg build.** The GPL FFmpeg build stays as a separate executable (x264 quality), and PyAV's LGPL notice is added (answers Bay Q2).
6. **Conflicts and checkpoints.** On a conflict the run pauses; there is no automatic retry (this replaces PLAN §2.2's "re-reads and retries"). A checkpoint is a version number plus a snapshot every 50 versions (this replaces PLAN §2.1's snapshot per chat message).
7. **Phase 1 limits.** No keyframes, and no transitions beyond crossfade.
8. **AgentDrive.** It stays out of the edit path. It is optional from Phase 2 only, with Pablo's OK (Wire §5).
9. **Live-agent gate.** It uses the desk's existing OpenRouter key from env if one is present. A key is never committed. Without one, live runs are marked GAP, not PASS.
10. **v0.5.3.** Covering v0.5.0–v0.5.2 with v0.5.3 is folded into the seal (answers Bay Q1 and the original Prove Q1).

---

## Appendix: open items (later, not blocking)

1. **Fixture B.** Pick a public-domain clip of spontaneous speech with ≥5 fillers (e.g. a US-government briefing) and pin it by sha256 (Prove §Phase 1). Also pick a VFR phone clip for E4 (Prove Gaps, Bay §7).
2. **Source delivery for v0.5.3.** Attach a source tarball to the release, or use a 3-year written offer (Bay §5). The default proposal is the tarball.
3. **Phase 1 thresholds.** Ada still needs to confirm the two proposed thresholds: SSIM ≥0.98 and card latency p95 <250 ms.
4. **Phase 0 exit wording.** PLAN §4's exit includes "renders it", but render v1 is slice 6 in Phase 1. In this plan the render check moves to the S6 gate (C11), so Phase 0 stays ~4 weeks. If you want render inside Phase 0, Phase 0 grows to about 6 weeks.
5. **Later choices.** macOS timing, whether a clipper run opens as a timeline by default, and which models go in the Phase 2 eval set (PLAN §6 Q1, Q3, Q5).
