# HANDOFF: Hermes Studio editor build

## 0. Update 2026-10-03 (read this first)

The owner (Pablo) asked to keep going on the editor. S3's owed fixes are pushed to PR #42, and Phase 1 (S4–S8 plus the Edit page) and Phase 2 presets are built, **each on its own branch, stacked in order**. Nothing new is merged, tagged or released. Every branch's head passes the full suite (1194 passed at the top; the one skip is the 20-minute S4 gate, which CI runs with `HERMES_SLOW_TESTS=1`).

| Branch (stacked) | What | Gate evidence | Spec |
|---|---|---|---|
| `feat/editor-s3-store-mcp` = **PR #42** @ `1f854ea` | All §3 owed fixes (F1, F2, O1–O4, decode, 104, Windows lock, blank lines, tests 89/92/101/102/103, As built) | CI green on Linux, Windows (lock test), test, CodeQL; **`sources` needs one re-run** (zlib.net served an 11 KB page; nothing in the PR) | `docs/plans/S3-SPEC.md` §13 |
| `feat/editor-s4-media` | probe, `add_media` op, import job (proxy, thumbs, wave, words), progress events | 20-min fixture imports with monotonic progress (78 s) | `S4-SPEC.md` |
| `feat/editor-s5-frames` | frame cache, `timeline_frames`, contact sheet, `history_frames` | C10 tests | `S5-SPEC.md` |
| `feat/editor-s6-render` | render v1 (two-pass graph, segments), render jobs | C11: duration/frames ±1, h264/aac 1080×1920, SSIM 0.993–0.994 | `S6-SPEC.md` |
| `feat/editor-s7-cuts` | `transcript_cut` (fillers, pauses, ranges) | C12 filler: 46 ops = 1 entry, 1 undo restores the hash | `S7-SPEC.md` |
| `feat/editor-s8-gate` | Ask / Propose / Auto, parked writes | C12 gate, E5 | `S8-SPEC.md` |
| `feat/editor-ui-edit` | the Edit page + sidebar, token delivery, `project_list/new`, captions in clip styles, Phase 1 headline test | `tests/test_phase1_e2e.py` (E1, E2, E4); `scripts/check-edit-page.js` (Playwright) | `EDIT-PAGE-SPEC.md` |
| `feat/editor-presets` | `apply_preset` (Phase 2 Q3) | one entry, one undo per preset | `presets.py` docstring |
| `feat/editor-polish` | `hermes-studio cache [--clear [--all]]`; Phase 2 Q1 eval set (`evals/`: 20 pinned tasks, checks, reference solutions, `python -m evals.run`); latency measurement | reference 20/20, a do-nothing agent passes only the 2 no-change tasks; engine op → SSE event p95 ≈ 10 ms (< 250 ms) | `evals/run.py` docstring |
| `feat/editor-drafts` | Phase 2 Q2 draft branches (`draft_new/list/keep/discard`, internal op `replace_body`, `call(..., "keep_body")`), Edit page draft banner | Discard keeps the main hash exactly; Keep equals the branch in one entry, one undo | `DRAFTS-SPEC.md` |
| `feat/editor-scenes` | Shot changes: S4 `scenes` stage (FFmpeg scene score 0.3), `get_scenes` through the clips, REST, Edit page Scenes tab with thumbnails and "Split at every shot change" (one entry) | cuts found at 3 s / 6 s on a 3-shot fixture; mapping through clips and speed | `media.py` / `media_jobs.py` docstrings |
| `feat/editor-markers` | `edit_marker` op (move and/or rename; inverse is the old values; `at_s` over MCP); Edit page markers on the ruler (add, select, drag, rename, delete, Item tab), frame/second stepping, [ ] edit points, Alt-arrow nudges, Keys list; drags hold redraws (fixes a drag lost to a mid-drag reload); top bar and toolbar no longer stretch or wrap | `tests/test_markers.py`; `check-edit-page.js` step 8 | `EDIT-PAGE-SPEC.md` |
| `feat/editor-slip-roll` | public ops `slip_clip` and `roll_edit` (`by_s` over MCP; media bounds and crossfade lengths checked in the op); Edit page Slip / Roll buttons, , and . keys, Alt-drag | `tests/test_slip_roll.py`; `check-edit-page.js` step 9 | `docs/oplog.md`, `EDIT-PAGE-SPEC.md` |
| `feat/editor-snapping` | Edit page: magnetic snapping (8 px to item edges, markers, the playhead; snap line; Shift or the **snap** box turns it off); a reload cancels queued reloads (no double redraw from our own write's echo); compact one-line toolbar | `check-edit-page.js` snap step | `EDIT-PAGE-SPEC.md` |
| `feat/editor-close-gaps` | preset `close_gaps` (V1 clips close up from 0, crossfades and anchors kept, other tracks stay); in the Presets menu and the MCP enum | `tests/test_presets.py` close-gaps tests | `presets.py` docstring |

**What only people can do now:**
1. Re-run the failed `sources` job on PR #42 (run 36996418254), then have the **verifier gate `1f854ea`** and merge pinned to it. That ends Phase 0; the Phase 0 release needs Pablo's yes.
2. **Ada's rulings** listed in each spec's "Decisions" (S4 D1/D7, S5 D2, S6 D4/D8, S7 D6, S8 D1–D3, S3 §13.9 Q1).
3. Then each later branch becomes a PR in order (merge `main` in first, never rebase), with its own verifier gate.

**Not built:** the ACP client and composer (Hermes chat over ACP), running the eval set against real models (the harness is ready), Phase 3 (keyframes, masks), and the Electron half of card latency (the engine half is measured).

---

This file is for any engineer or AI who picks up the editor work with no prior context. Read all of it before you touch code. Last updated 2026-10-01 at 11:30 PM ET.

## 1. What this is
Hermes Studio turns long video into captioned short clips on the user's own machine. It also has a design editor. It ships as a CLI, an MCP server and an Electron desktop app for Linux and Windows. See [README.md](README.md) and [AGENTS.md](AGENTS.md).

**The editor goal:** a real timeline video editor that people and AI agents can both drive. Agents use MCP tools and an `/mcp` endpoint, and they work from a watch-and-chat sidebar.

One engine is the only writer. Every change is an op in an append-only log, so changes can be undone, redone and replayed. Each one is checked against a canonical hash.

The full plan is [docs/plans/PLAN-MERGED.md](docs/plans/PLAN-MERGED.md). The user story is in [docs/plans/PLAN.md](docs/plans/PLAN.md).

## 2. Phase and slice map
See [PLAN-MERGED.md §3 and §5](docs/plans/PLAN-MERGED.md).

| Phase | Slices | State |
|---|---|---|
| 0 Foundations | S0: licenses and packaging, v0.5.3 (#33). S1: `timeline.py` (#35). S2: `oplog.py` (#37, #38, #39). S2b: `edit_text` (#40). Fixes: #34 and #36 | **Merged.** main is at `c6de84e`. v0.5.3 is released |
| 0 Foundations | **S3:** the project store, `.lock`, stdio attach, and the event bus (seq plus SSE replay), with Wire's `/mcp` endpoint (token and scopes) | **In progress as PR #42. Not mergeable yet** (see section 3) |
| 1 MVP editor and sidebar | S4 media services, S5 frame cache, S6 render v1, S7 transcript cut, S8 engine mode gate. Also the ACP client, the approval bridge, and the Edit page and sidebar | Not started |
| 2 Agent quality | A 20-task eval set, draft branches and presets | Not started |
| 3 Pro and reach | Keyframes, transitions, speed and masks | Not specified yet |

Phase 0 ends when S3 merges. Every phase exit is a release, and each release needs the owner's yes (see section 4).

## 3. S3 state, exactly
- **Spec:** [docs/plans/S3-SPEC.md](docs/plans/S3-SPEC.md). It has 31 decisions.
  - §11 lists the engine diffs that are allowed. §13 is the As built section, and §13.10 lists the tests still owed.
  - Passages marked **[R]** were rebuilt after a data loss. Where the spec and [S3-RULINGS-ADDENDUM.md](docs/plans/S3-RULINGS-ADDENDUM.md) disagree, the addendum wins.
  - [RECOVERY-NOTES.md](docs/plans/RECOVERY-NOTES.md) gives the source of each file and lists the contradictions that are known.
- **Contract:** [docs/plans/WIRE-S1-REGISTRY-CONTRACT.md](docs/plans/WIRE-S1-REGISTRY-CONTRACT.md). It has 104 tests and 17 op-level and 36 validator rule ids.
- **PR #42** (`feat/editor-s3-store-mcp`) is at head `0282e9f`. **That head is NOT the merge candidate.**
  - CI is green there.
  - The verifier's pre-gate ([records/PROVE-S3-PRE.md](docs/plans/records/PROVE-S3-PRE.md)) found the fixes listed below. All of them are ruled.
- **Branch `wip/s3-bay-uncommitted`** (`431cb3f`, built on `0282e9f`) holds the builder's uncommitted work, saved as it was found after a machine reboot.
  - It is unverified and was never reviewed. It may be incomplete.
  - Start from it, but don't trust it.

**Fixes still owed before S3 merges** (all go into PR #42):
1. **F1 (§11 row F).** `_replay_from` and `doc_at_head` in `project.py` must check every log line exactly the way `Oplog.load` does, `inverse` included. A tampered middle line gets `failed` with `seq: 2`, whether the app is open or closed.
2. **F2 (D27).** HTTP checks run for every method before routing, in this order:
   1. Any `Transfer-Encoding` gets 400 "unsupported transfer encoding".
   2. There must be exactly one valid Content-Length (read with `get_all`, and matching `[0-9]+` with at most 8 digits). Anything else gets 400 "invalid content length".
   3. A GET with a length above 0 gets 400 "request body not allowed".
   4. A POST over the cap gets "request body too large".

   HTTP /mcp answers -32700 with id null instead. Every refusal closes the connection.
3. **O1.** In stdio newline mode, read at most `MAX_BODY + 1` bytes per line. A longer line gets -32700 with id null, a stderr log, and a nonzero exit.
4. **O2 (§11 row E).** A `base.json` without a `hash` gets `invalid_doc` `hash_mismatch` at `/hash`.
5. **O3.** `ruff format --check` must pass on every touched file.
6. **O4.** Test 92 asserts `/markers/1/label` and `mk1` literally.
7. **Decode.** Split the URL path first, then decode each segment.
8. **Test 104.** A project opened after a GET /mcp stream starts still gets `resources/updated`. Today `http_engine.py:212–215` snapshots the projects when the stream opens.
9. **Windows `.lock`.** Add a byte-range lock test that runs in the windows CI job. **This blocks the merge.**
10. **stdio blank lines.** Remove the skip at `mcp.py:319–320`. Stray lines between frames get -32700 and a nonzero exit.
11. **Tests in §13.10.**
    - Rebuild test 89 with real ops, so that it reaches `bad_arg` at `/ops/0/id`.
    - Add the extra cases in 101, 102(a/b/b2) and 103(v/vi).
    - Add the D26 decode case.
12. **As built.** Spec §13 must match the code. Add one probe for each §11 row under `evidence/s3-build/s11_rows/`.

**Open question (the lead, Ada, must rule):** spec §13.9 Q1. Today a `control` token passes `GET /mcp` and `resources/list`, and it gets -32602 rather than `permission_denied` on `resources/read`. Ask before you change this.

**Later:** issue #41 (an OTIO `StopIteration`) goes into the first slice that touches OTIO.

## 4. Gates (non-negotiable)
- **One slice per branch and per PR.**
- **An independent verifier must PASS the exact head commit before the merge.** Then merge pinned to that head:

  ```
  gh pr merge N --squash --delete-branch --match-head-commit <sha>
  ```
- **Never rebase or force-push.** To catch up, merge `main` into the branch.
- **Replay gate:** any engine behavior that differs from `c6de84e` and isn't listed in §11 is a FAIL.
- **Thresholds:** render SSIM must be at least 0.98. Agent card latency p95 must be under 250 ms.
- **No tag, release, spend or sign-up without the owner's (Pablo's) yes.**
- **No cloud coding agents.**
- **Code sources:** OpenCut (MIT) may be used as a pattern only, with attribution. Use nothing from GPL editors.
- **Old releases:** leave the v0.5.0 to v0.5.2 release pages untouched.

## 5. Run the tests and CI
```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[reframe,dev]'
.venv/bin/python -m pytest -q -rs
.venv/bin/ruff check hermes_studio tests hermes_plugin
.venv/bin/ruff format --check <touched files>
```
- **FFmpeg** must be on PATH. CI pins a specific build. See `.github/workflows/ci.yml` and [records/CI-FFMPEG.md](docs/plans/records/CI-FFMPEG.md).
- **CI checks:** every PR runs `ci.yml` (test, secrets, sources), `desktop.yml` (the linux and windows builds) and CodeQL.
- **Baseline:** at `0282e9f`, 923 tests passed and 0 were skipped.
- **Install check:** `hermes-studio doctor --json` verifies an install.

## 6. Where things live
- **Plans** are in [docs/plans/](docs/plans/):
  - the architecture, slices and acceptance IDs in [PLAN-MERGED.md](docs/plans/PLAN-MERGED.md)
  - the engine, agent interface, UX and acceptance sections in [sections/](docs/plans/sections/)
  - research in [RESEARCH.md](docs/plans/RESEARCH.md) and [research/](docs/plans/research/)
  - the Edit page mockup in [comps/](docs/plans/comps/)
  - [REPO-AUDIT.md](docs/plans/REPO-AUDIT.md)
- **Specs of record:** [docs/timeline.md](docs/timeline.md), [docs/oplog.md](docs/oplog.md) and [docs/FRAMING.md](docs/FRAMING.md).
- **Records:** [docs/plans/records/](docs/plans/records/) has the PR bodies and the verifier reports for every slice merged so far.
- **Evidence is NOT in the repo.** The probes, their outputs and the replay corpora are on the team's working machine only. The reports in records/ quote the key results. To check a result, rerun the probes those reports describe.

## 7. Your first three steps
1. **Get the owner's go.** S3 and S4 are paused until Pablo says to resume.
2. **Finish S3.**
   - Check out `feat/editor-s3-store-mcp` at `0282e9f`.
   - Diff it against `wip/s3-bay-uncommitted` and take only what matches the section 3 fixes.
   - Finish every fix, then push normal commits to PR #42 (no force-push).
   - Get CI green on Linux, Windows and CodeQL.
3. **Verify, merge, then stop.**
   - Have the verifier gate the green head SHA. The gate covers the replay against `c6de84e`, the §11 row probes, contract tests 88–104, and the HTTP and stdio framing probes.
   - On a PASS, merge pinned to that SHA. That completes Phase 0.
   - Propose the Phase 0 release to the owner. Don't start S4 until he says yes.
