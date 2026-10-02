# Recovery notes: docs/plans (rebuilt Oct 1–2, 2026, ET)

The box rebooted at 10:28 PM ET on 2026-10-01 and wiped `/workspace/desk/hermes-studio/`. A backup was restored at about 10:44 PM ET (file mtimes 02:44–02:47 UTC on Oct 2), but it predates Ada's last rulings (about 8:28–9:02 PM ET). This file lists what each file under `docs/plans/` came from, and what is exact versus reconstructed.

## Sources and their limits

- **Agent transcripts: not read.** The transcript tool (`ReadTranscript`) wasn't available in the recovery session, so no transcript of Bay, Wire, Prove, Glyph, the Software Desk group or the parent agent was read. Every "final wording" below comes from files, not from transcripts.
- **Restored backup** (`/workspace/desk/hermes-studio/`, mtimes 02:44–02:47 UTC).
- **Wire's restored backups** in `/workspace/tmp/`: `WIRE-backup-2036.md`, `-2058.md`, `-2100.md` and `-2102.md` all came back with the restore (mtimes 02:47 UTC). They were thought lost.
- **Evidence**: `evidence/s3-spec`, `s3-build` (including `s11_rows/SUMMARY.out`, run 8:49 PM ET against `0282e9f` plus Bay's working tree), `prove-s3/0282e9f` (`PROVE-S3-PRE.md`), `prove-s3-spec`.
- **PR #42** at `0282e9f` (fetched read-only; no code from it is committed here) and its PR body.
- **Bay's uncommitted S3 worktree** `/workspace/hermes-studio-s3` (restored; 8 modified files plus `studio_limits.py` and `tests/test_s3_lock.py`). Read only, to check the as-built behaviour after the rulings. It wasn't changed.
- **`S3-RULINGS-ADDENDUM.md`** (already in this PR): Ada's post-backup rulings. Authoritative.

## Files

| File | Source | Exact or reconstructed |
|---|---|---|
| `PLAN-MERGED.md`, `PLAN.md` | restored backup (same bytes as in PR #43 at `25403b4`) | exact copy of the backup. No later version was found. |
| `sections/SECTION-*.md` (4) | restored backup (same bytes as in `25403b4`) | exact copy. They are the ~3 AM ET section finals that PLAN-MERGED.md merged (03:20 AM). No later edit was found, but without transcripts that can't be confirmed. |
| **S4 and Phase 1–3 slice plans** | none found | No separate S4 or Phase 1–3 plan file was found on the box (filename search of the whole box). The slice plan lives in `PLAN-MERGED.md` (slices, gates, Phase 1 exit, Phase 2) and `PLAN.md` (Phases 1–3), with estimates in `SECTION-BAY-ENGINE.md` §6. The only S4 item recovered is "`get_timeline{summary:true}` moves to S4" (addendum; contract 8:32 PM). |
| `S3-SPEC.md` | restored backup (Bay, revisions through 7:18 PM, plus §13 As built of 8:29 PM) **+ fold-in** | The backup text is exact. Every passage marked **[R]** was **reconstructed** during recovery from the addendum (Ada's rulings), Wire's 9:02 PM contract, Prove's pre-gate and the PR #42 body. Those passages state the rulings; they are **not Bay's own final wording**, which couldn't be recovered (his `/tmp/S3-SPEC.before-*.md` backups are gone). Folded in: §11 row 4 (GET checks, newline cap, no blank-line skip; Transfer-Encoding was already there), rows E (O2) and F (F1), the D27 HTTP check order for every method (§6 D27(d)), D26 decode, the "request body not allowed" message (§9), §10 notes, §13 updates (F1 note, decode, GET /mcp, REST GET order, newline cap, Windows lock blocks merge, `ruff format`), Q2/Q3 resolved, and §13.10 tests owed. |
| `S3-RULINGS-ADDENDUM.md` | unchanged from `25403b4` | kept as is; it wins over S3-SPEC.md wherever they differ. |
| `WIRE-S1-REGISTRY-CONTRACT.md` | `/workspace/tmp/WIRE-backup-2102.md` + one line | **Exact except for one merged line.** The 2102 backup has the ruled 103 (vi-a) row (9:02 PM: "request body not allowed", check order, `Content-Length: 2000000`), O2 RULED (8:59), 102(a)/(b)/(b2), 103(v)/(vi), 104, corrected 92 and 94, 104 tests, 17/36. It lacked the 9:02 PM revision-log line, which the previous PR #43 copy had, so that line was added from the previous copy. The previous PR #43 copy had the 9:02 log line but the **pre-9:02** 103 row ("FLAG", no message named). |
| `RESEARCH.md`, `REPO-AUDIT.md` | restored backup | exact copies. |
| `research/video-editors/*.md` and `screenshots/*/SOURCES.md` | restored backup | exact copies. **The 196 screenshots (~127 MB, mostly third-party product images) are not committed.** They still exist on the box at `/workspace/desk/hermes-studio/research/video-editors/screenshots/`. The notes refer to them by path. |
| `comps/COMP-GLYPH-EDIT-SIDEBAR.html`, `.png` | restored backup (Glyph's comp) | exact copies. |
| `records/*-PR-BODY.md` (S1, S2, S2B, XFADE, FOLLOWUP) | restored backup | exact copies. These are records, not plans. |
| `records/S3-PR42-BODY.md` | PR #42 body via `gh pr view 42` (the same as `/workspace/prove-s3/pr42-body.md`) | exact copy. |
| `records/PROVE-*.md` (Slice 0/PR33, PR34, S1, PR36, S2, PR38, PR39, PR40) | restored backup | exact copies. |
| `records/PROVE-S3-PRE.md` | `evidence/prove-s3/0282e9f/PROVE-S3-PRE.md` | exact copy. Prove's pre-gate of #42, ~8:55 PM ET. It's not a verdict. |
| `records/CI-FFMPEG.md` | restored backup | exact copy (a CI diagnosis note; the fix merged in #39). `ci.proposed.yml` and `test_ci_ffmpeg_pin.py` are code and were left out. |

## Not recovered

- Bay's final S3-SPEC wording after 7:18 PM (except §13), and his `/tmp/S3-SPEC.before-*.md` backups.
- The "S3 build report" that S3-SPEC §13.9 Q3 cites. No copy was found.
- Any transcript-only text: rulings said in chat but never written to a file.
- A ruling on **§13.9 Q1** (the control token on `GET /mcp`, `resources/list` and `resources/read`). It is still open. The addendum only rules that the control token gets `permission_denied` on every tool.

## Contradictions found between sources

1. **Wire backups:** the brief said 2036/2058/2100/2102 were lost. They were restored in `/workspace/tmp/`.
2. **Contract in `25403b4`:** it had the 9:02 PM log line but the pre-9:02 103 (vi-a) row ("FLAG"). The 2102 backup has the opposite. They were merged as described above.
3. **Ruling times:** the contract dates F1 and O4 to 8:58 PM and O2 to 8:59 PM. Bay's worktree code comments date both F1 and O2 to "Ada 9:02 PM". The addendum gives only the 8:28–9:02 window. The spec cites the contract's times.
4. **§13 approval time:** 8:29 PM in S3-SPEC, 8:28 in the addendum.
5. **Path decoding:** restored §13.4 says only the `<id>` segment is decoded. The addendum and Bay's worktree (`path_segments`) decode **each segment** after the split. The spec now follows the addendum.
6. **§13 vs PR #42 at `0282e9f`:** §13 describes behaviour that isn't in `0282e9f`: no blank-line skip (still at `mcp.py:319–320`), GET /mcp following later projects (`http_engine.py:212` still snapshots), the GET decode fix, the Windows lock test and 0600 on exports. All of it is in Bay's **uncommitted** worktree. So §13 records the build as approved, not the pushed head.
7. **Closed-app fast path vs F1:** §13.1 and §12 finding 8 describe a closed read that trusts `timeline.json` when it matches the head (the accepted gap for a tampered middle hash). F1 says `doc_at_head` checks every line as `Oplog.load` does. Bay's worktree drops the fast path entirely (always a full replay). No recovered ruling says finding 8 is closed, so it is still recorded as accepted, with a note.
8. **§10 states:** the spec lists "19 open". The PR #42 body says Ada approved all 31 decisions at 7:33 PM. A note was added. The row states were left as the 7:18 PM record.
9. **Contract test 101** still says "waits on Bay's next S3-SPEC revision (on hold)", and test 89's text doesn't carry the addendum's "real ops with valid args … `bad_arg` at `/ops/0/id`". Wire's 2102 text was kept as is, so the addendum's "tests owed" list (S3-SPEC §13.10) is the fuller source.
10. **PR #42 body** says "against Wire's contract (tests 1–103)". The contract is now at 104 (test 104 added 8:36 PM).
