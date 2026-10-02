# Section: Acceptance checklist per phase (Prove)

Reviewed: `REPO-AUDIT.md`, `RESEARCH.md`, `PLAN.md` §3–4, `SECTION-GLYPH-UX.md`, `SECTION-WIRE-AGENT-INTERFACE.md`, `SECTION-BAY-ENGINE.md`. Repo read only with `gh api` at `main` `be8a877`: `desktop.yml`, `NOTICE`, `pyproject.toml`, `electron-builder.json`, `scripts/build-engine-*`, `clean-test-linux.sh`, releases.
Ada's rulings applied:
- A parked write never applies or skips on its own when it times out.
- Slice 0 is the FFmpeg/PyAV notice; v0.5.3 goes to Pablo for sign-off.
- The native plugin stays, as a thin wrapper generated from the `api.py` registry.
- The live gate uses the desk's OpenRouter key.

Every item is PASS/FAIL and runs in CI unless marked. **GAP** = can't be verified yet, with the reason. `[Sn]` = Bay's slice number (Bay §6).

## Phase 0 (~4 weeks): slice 0, the license notices (Ada's ask) `[S0]`
What the repo shows today:
- `desktop.yml` L18–22 pins BtbN `autobuild-2026-09-30-13-08`, `ffmpeg-n9.0.2-17-g2a571b6068-{linux64,win64}-gpl-9.0`, with sha256.
- `NOTICE` has no FFmpeg or GPL entry.
- `build-engine-*` copies only the `ffmpeg`/`ffprobe` binaries (linux L71, win L60), and `electron-builder.json` `files` doesn't list NOTICE or `licenses/`.
- `pyproject.toml` pulls `faster-whisper` plus `av>=11,<19`, and PyAV wheels bundle LGPL FFmpeg libraries inside the process (Bay §5).
- **v0.5.0–v0.5.2 shipped without any of this.**

Checks:
- [ ] **N1 The packaging fix works.** Run the checks on the *built artifact*: AppImage `--appimage-extract` (as `clean-test-linux.sh` already does) and a silent NSIS install. NOTICE and `licenses/FFmpeg-GPL.txt` + the LGPL text must be present and byte-identical to the repo copies.
- [ ] **N2 The GPL FFmpeg section names the exact build.** It names release tag `autobuild-2026-09-30-13-08`, asset `n9.0.2-17-g2a571b6068`, and the sha256 values, and lists the bundled GPL libraries (x264, x265, libass…). A CI grep fails if `FFMPEG_*_URL` changes without NOTICE changing.
- [ ] **N3 The source links resolve.** `curl -sIL` returns 200 for:
  - FFmpeg commit `2a571b606854520cf89804d8030c8b328e621689`. The build is 17 commits *past* `n9.0.2`, so the tag alone isn't the matching source. The commit exists; checked.
  - The BtbN build-scripts tag (200; checked).
  - Any release tarball or written offer that Pablo's v0.5.3 approval adds.
- [ ] **N4 The binary matches.** `engine/bin/ffmpeg -version` in the artifact prints `n9.0.2-17-g2a571b6068`.
- [ ] **N5 The PyAV LGPL notice matches the app.** NOTICE has a PyAV/faster-whisper section whose PyAV version and FFmpeg library versions equal what the bundled Python reports (`av.__version__`, `av.library_versions`), with an LGPL source pointer that returns 200.

## Phase 0: engine and contract checks (exit per PLAN §4: a script builds a 3-clip timeline over MCP, undoes it, renders it)
"Hash" means Bay's canonical sha256, which leaves out `version` and `hash` (Bay §2).
- [ ] **C1 Schema `[S1]`.** Bad documents → `code` + `hint`. Equal content → equal hash. `.otio` opens in `otiotool`.
- [ ] **C2 Undo round-trip `[S2]`.** 1,000 seeded random op runs. Every `hash(undo(apply(T)))` equals `hash(T)`, and so does undo-all. Undoing a group is one new entry that applies the inverses in reverse order.
- [ ] **C3 All-or-nothing batches `[S2,S3]`.** Inject a failure at op k in a batch, and separately `kill -9` the engine mid-batch. After restart the hash equals the pre-batch hash, no log line was written, and `timeline.json` is never half-written (tmp+replace).
- [ ] **C4 Replay and checkpoints `[S2,S3]`.** A full replay of `oplog.jsonl` gives the live hash. Snapshots are kept every 50 versions. Restoring to any version N, including N between snapshots (e.g. 73), gives the same hash as replaying from empty to N.
- [ ] **C5 Contract (Wire §1/§3, Bay §3) `[S2]`:**
  - `(actor, client_op_id)` retry → same `op_id`, applied once.
  - Actor comes from the token: a forged `actor` arg is ignored.
  - An agent undoing a human's op → `undo_blocked` with the dependent `op_id`s.
- [ ] **C6 A conflict pauses the run `[S2,S8]`.** A stale `base_version` returns `conflict` with `history_diff`. The hash is unchanged, no op is logged, and `run.paused` is emitted. The agent's next write without a new `base_version` is refused, so it can't silently retry.
- [ ] **C7 One writer `[S3]`.**
  - With the app running, a second engine opening the project is refused by `.lock`.
  - The stdio MCP reads `.lock` and attaches; strace shows it never opens `timeline.json`/`oplog.jsonl` for writing.
  - A stale lock left by a killed engine is recovered.
  - **With the app closed, every write tool returns refused (Phase 1 rule); reads still work.**
- [ ] **C8 Event bus `[S3]`.** Over 1,000 ops the `seq` numbers are contiguous. After a reconnect with `Last-Event-ID`, the replay has 0 gaps and 0 dupes.
- [ ] **C9 Tool lists `[S3,S8]`.**
  - MCP `tools/list` equals the checked-in allowlist (PLAN §3).
  - Any `publish|upload|post|shell|exec` tool fails the test.
  - **The MCP, native plugin and CLI tool sets all match the `api.py` registry**, so the audit's 18-vs-14 drift can't come back.
- [ ] **C10 Frame cache `[S5]`.** The key is the sha256 of the *visible recipe at t*, plus size. An edit at 0:40 leaves the cached frame at 0:05 cached. v12's "after" frame has the same key as v13's "before". The LRU cap holds.
- [ ] **C11 Render `[S6]`.** A 3-clip + xfade + text + captions timeline passes the ffprobe and SSIM checks below.
- [ ] **C12 Fillers and mode gate `[S4,S7,S8]`.**
  - A 40-op filler cut is 1 log entry, and one undo restores the hash.
  - Ask mode → `permission_denied`, including for plain-MCP clients.
  - The engine parks a Propose write (`approval.pending`).

## Phase 1 headline end-to-end run (PLAN §1, scripted)
**Fixture A:** *Tears of Steel* 720p (CC-BY 3.0), `download.blender.org/demo/movies/ToS/tears_of_steel_720p.mov`, 372,178,639 B, **sha256 `efa9062d9cdb7a338e40ad530dfdf234806743f29ae6a1a136b97ece4e588e8f`** (hashed today), using a fixed 60 s dialogue excerpt.
**Fixture B** (to pick): public-domain spontaneous speech with at least 5 fillers, pinned by sha256. Scripted dialogue may have no "um"s to remove.
**Script:** import → trim to 45 s → remove fillers (1 batch) → add a title → `render_final 9:16-1080`. Run it twice: **(a)** Hermes over ACP in the sidebar, **(b)** a plain-MCP client (Claude Code or Cursor).
- [ ] **E1 Cards.** There is exactly one card per engine `op.applied`, matched by `op_id`. A card shows "done" only after the engine event: if the event is held back, the card stays pending. The filler cut shows as one card with one Undo and an expandable list (Glyph).
- [ ] **E2 Undo.** Undoing each card in reverse order restores the hash from before that step. The group undo is atomic. Ctrl+Z is linear undo, whoever made the edit.
- [ ] **E3 Frames.** Each card's before/after refs resolve to cached frames (C10).
- [ ] **E4 Render (ffprobe).** Duration within ±1 frame of the timeline, 1 video + 1 audio stream, h264/aac, 1080×1920, frame count within ±1. SSIM checked at 5 known timestamps against reference frames from the same pinned build.
- [ ] **E5 Propose (Ada's rule).**
  - Apply, Skip and Apply the rest each do what they say.
  - **At timeout the write stays parked:** the hash is unchanged, no op is logged, and the sidebar shows "Paused, waiting for you".
  - MCP returns `needs_approval` + `pending_id` rather than hanging.
  - After an ACP expiry, Hermes resumes once the person answers.
  - A late answer applies or skips **exactly once**; repeating the same `pending_id` does nothing.
- [ ] **E6 A human edit wins.** A UI trim mid-run → the agent gets `conflict` → C6 behaviour, the "You edited. Hermes paused." banner, and the human's op stays in the log.
- [ ] **E7 Safety.**
  - Outbound traffic goes only to declared hosts (`openrouter.ai` for the live gate).
  - All file writes land inside the project or `cache/` (strace/inotify; Procmon on Windows).
  - The source sha256 is the same before and after.
- [ ] **E8 Platforms.** E1–E7 pass on clean Linux AppImage and Windows NSIS machines.
- **Live gate:** uses the desk's OpenRouter key if one is present; otherwise E1–E6 are **GAP**, and the run falls back to a scripted MCP replay labelled as such.

## Phase 2
- [ ] **Q1** Eval set: 20 pinned tasks, each scored for correctness, steps and undo rate, stored per model and build.
- [ ] **Q2** Draft branch: Discard returns the main hash exactly; Keep equals replaying the branch.
- [ ] **Q3** Presets: one group, one atomic undo.

## Measurements
| Metric | How | Threshold |
|---|---|---|
| Undo, replay and checkpoint hash match | C2, C4, E2 | 100% |
| Partial batches, duplicate applies, ops on conflict or timeout | C3, C5, C6, E5 | 0 |
| Render duration and frame count | ffprobe | ±1 frame |
| Frame spot-check | SSIM, same FFmpeg build | ≥0.98 *(proposal)* |
| SSE gaps or dupes | `seq` audit | 0 |
| Engine op → sidebar card | Electron trace | p95 < 250 ms *(proposal for Pablo/Ada)* |
| Undeclared hosts or out-of-project writes | capture + file trace | 0 |

## Gaps and risks
- **Renders aren't byte-identical across FFmpeg builds or threads.** Compare with ffprobe + SSIM, and regenerate the references when the BtbN pin changes.
- **The live gate depends on the OpenRouter key** being present; without it, it's GAP (above).
- **Electron UI checks need a desktop driver** (Playwright-Electron under Xvfb, or a Windows VM). Until then they're manual, with screenshots.
- **VFR source footage** (Bay §7) can drift. Add a VFR phone clip to the E4 fixtures.

## Open questions for Pablo
None remain. Ada settled the model and key, and v0.5.3 is part of Pablo's sign-off on slice 0.

## Size (verification work, in step with Bay's slices)
- **Phase 0 (~4 weeks): about 2 weeks of Prove time**, running alongside S0–S8.
  - Slice 0 artifact checks: 1–2 days.
  - C1–C12 harness: property tests, kill/fault injection, the checkpoint sweep, lock/strace, and the 3-way tool-list diff.
- **Phase 1: about 2 weeks.** Fixtures and references, the end-to-end runs for both clients, the Electron driver, safety tracing, and Windows.
- **Phase 2: about 1 week.** Eval scoring, draft-branch and preset checks.
