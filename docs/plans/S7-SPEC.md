# S7 spec: `transcript_cut` (remove fillers, pauses or ranges as one batch)

Status: **draft, built on `feat/editor-s7-cuts` (stacked on S6). Not ruled.** Plan of record: PLAN-MERGED.md §5 row 7, SECTION-BAY-ENGINE.md §3 ("Remove fillers compiles into one batch = one entry = one card = one Undo"). Prove gate: **C12 (filler part)**.

## 1. What S7 adds

- **`transcript_cut {base_version, client_op_id, summary?, group_id?, fillers?, pauses?, ranges?, preview?}`** on /mcp and `POST /api/projects/<id>/transcript_cut` (`cuts.py`).
- **Finding cuts** on the words `get_transcript` maps onto the timeline (S4):
  - `fillers: true`: words `pacing.is_filler` matches (um, uh, uhm, umm, uhh, erm, er, hmm, hm, mm, mhm; punctuation and case ignored), each with up to 50 ms of the silence around it (never past the neighbouring words).
  - `pauses: true`: a gap over `pacing.MAX_PAUSE` (0.7 s) between spoken words of one clip is cut down to `pacing.KEEP_PAUSE` (0.26 s), half kept on each side.
  - `ranges: [{from_s, to_s}]`: timeline seconds (up to 500).
- **Compiling:** ranges are merged, clipped to each V1 clip they cross and snapped to the timeline's frame grid; each becomes `split_clip` (at its end, unless that's the clip's end) + `split_clip` (at its start, unless that's the clip's start) + `delete_clip {ripple: true}` of the middle, from the **last clip and last cut backwards**, so a ripple never moves a cut still to come. Piece ids are `<clip>.<sha256(client_op_id)[:6]><n>`, so the same call compiles to the same ops.
- **Writing:** the ops go through `Project.write_locked(session, "timeline_apply", …)`: one ordinary log entry, the token's actor, the engine's dedupe, conflict and validation, and (S8) the mode gate. Default summary: `Cut 16 fillers, 2 pauses (8.4 s)`.
- **Result:** the write result plus `cuts [{from, to, clip}]`, `skipped [{from, to, clip, why}]`, `removed` (ticks), `removed_s`, `applied`. `preview: true` returns the cuts and `ops` and writes nothing.

## 2. Decisions

- **D1. One entry.** A filler cut is one `timeline_apply` batch, so it is one `op.applied`, one card and one undo (C12). Undo restores the exact hash (tested).
- **D2. Skipped, not refused:** a range (after snapping) shorter than one frame, one that overlaps a transition, or one on a clip whose speed isn't 1. They are listed in `skipped` with the reason.
- **D3. Too big is refused whole.** The engine's `MAX_OPS` (500) caps a batch; a cut that needs more ops is `bad_arg` @ `/fillers` with the counts and a hint to cut in parts. Never a partial cut. (≈160 cuts fit.)
- **D4. Check order.** The engine's envelope first (`check_apply_envelope`, so `base_version`/`client_op_id`/`summary`/`group_id` answers are the engine's), then a stale `base_version` is the engine's `conflict` (with `history_diff`), then unknown args, `preview`, `fillers`/`pauses`, `ranges` (`bad_arg` @ `/ranges/<i>[/from_s|to_s]`), then "nothing asked" (`missing_arg` @ `/fillers`). Nothing found to cut → `applied: false`, no entry.
- **D5. Retries.** A retry with the same `client_op_id` is compiled against the doc at that entry's `base_version` (rebuilt from the log), so it yields the same ops and the engine returns the first result.
- **D6 (proposed). Only V1 ripples.** `delete_clip {ripple}` closes the hole on V1 only (S2 semantics). Items anchored to cut clips follow; unanchored text and audio-track items keep their times. Captions follow the words (they are mapped through the clips). A "ripple all tracks" option is S8+ material.

## 3. Engine diffs

None (no op or rule changes). `tools/list` has 20 tools.

## 4. Tests

`tests/test_s7_cuts.py` (21): C12 (80 words with 16 fillers → 46 ops in ONE entry, transcript afterwards has no fillers, duration shrinks by `removed`, one undo restores the hash), frame-grid cuts and a gap-free ripple, preview = the cut, retry, pauses, ranges across clips and at a clip start, transition skips, nothing to cut, stale `base_version` conflict, 8 refusals, the engine's envelope, REST with the token's actor, the compile order unit test, the 500-op cap.
