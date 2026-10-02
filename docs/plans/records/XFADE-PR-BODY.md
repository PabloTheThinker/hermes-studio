Branch `fix/ripple-trim-crossfade` → `main` (off `e274051`, after #37). Head: `36f8a876e88c20620b70f8bcb863d779d771592d`.

Commits:
- 3c9c9d0: the fix.
- 36f8a87: too-short trims are `transition_too_long` (Ada and Glyph's ruling). Files: `hermes_studio/oplog.py`, `tests/test_oplog.py`, `docs/oplog.md`, `docs/timeline.md`.

Ada ruled that this follows Glyph's version: **the crossfade stays with the cut**.

## The bug

`trim_clip{ripple: true}` on a clip with an outgoing xfade was refused with `transition_overlap_mismatch`. The ripple only shifted items starting at or after the clip's *old end*, and the next clip starts before that (by the crossfade's `dur`), so it stayed put and the overlap broke.

## The fix

The ripple point is now the start of the outgoing overlap, which is the next clip's start. The next clip, the crossfade (a transition has no `at`; it starts with its second clip) and everything after them shift together by the change in duration. The crossfade keeps its `dur` and its `between` pair. The change is about 20 lines in `op_trim_clip`, plus an up-front length check.

## Spec decisions

Decisions 1, 2, 4, 5 and 6 are confirmed. Decision 3 follows Ada's ruling.

1. **Which end moves.** A ripple trim keeps the clip's start (as already confirmed), so trimming either `src_in` or `src_out` moves the clip's **end**. The "symmetric start-trim case" is therefore:
   - an **outgoing** crossfade follows the moved end, the same as an end trim;
   - an **incoming** crossfade stays exactly where it is, because the clip's start doesn't move.
2. **Ripple point.** With an outgoing crossfade, later items are those starting at or after the overlap's start, not the old end. On a track that allows overlaps (music), anything else starting inside that overlap now shifts too.
3. **Too short: `transition_too_long`** (Ada and Glyph's ruling). The trimmed clip must be longer than each of its crossfades and at least as long as both together. Anything shorter is refused before anything moves, as `invalid_op` / `transition_too_long` at `/ops/k`, with `id` set to the crossfade:
   - if one crossfade doesn't fit on its own, its id; if neither fits on its own, the outgoing one's;
   - if each fits on its own but not both together, the outgoing crossfade's id.

   `transition_too_long` isn't an S1 validator rule: S1's only `*_too_long` rule is `fade_too_long`. It's added as an op-level rule (17 now) with the same result shape as a validator problem on one item (`rule`, `path`, message, `id`). The S1 rule set (36) is unchanged.
4. **Non-ripple trims are unchanged.** Without `ripple` nothing shifts, so an end trim of a clip with an outgoing crossfade still fails validation with `transition_overlap_mismatch`. "Stays with the cut" is applied to ripple trims only.
5. **What moves and what doesn't.** Anchored items move only through their target: anything anchored to a shifted clip moves, and anything anchored to the trimmed clip keeps its place, because its start doesn't move. Markers have no anchor and don't ripple, as before.
6. **changed_ids** comes from the existing resolved-span diff. A ripple trim with a crossfade lists the trimmed clip, every shifted item, the crossfade and any items anchored to shifted clips, for example `[c1, c2, c3, t12, x1]`. Its undo and redo list the same ids.

## Tests (`tests/test_oplog.py`, 23 new; 636 in the full suite)

- `test_ripple_end_trim_with_an_outgoing_crossfade_is_no_longer_rejected` is the regression test.
- `test_ripple_end_trim_moves_the_crossfade_with_the_cut[shorter|longer|quarter]` covers several things:
  - the start is kept;
  - the crossfade sits at the new cut with the same `dur` and pair;
  - c2, the crossfade, c3 and x1 (anchored to c2) shift by Δ;
  - mu1 (anchored to c1) and the markers stay;
  - the exact `changed_ids`;
  - undo and redo round-trip both the hash and `changed_ids`.
- `test_ripple_start_trim_with_an_outgoing_crossfade_moves_it_too`.
- `test_ripple_start_trim_with_an_incoming_crossfade_keeps_it_at_the_clip_start`.
- `test_ripple_trim_of_a_clip_with_both_crossfades`.
- `test_a_ripple_trim_shorter_than_its_crossfades_need_is_transition_too_long` (6 cases × the op at index 0 and 1 = 12):
  - shorter than the outgoing crossfade, as an end trim and as a start trim;
  - exactly the outgoing crossfade's `dur`;
  - exactly the incoming crossfade's `dur`;
  - each fits alone but not both together;
  - neither fits alone.

  Each checks the rule, the path `/ops/k`, `op_index`, the crossfade's `id`, and that nothing is applied.
- `test_a_ripple_trim_exactly_as_long_as_both_crossfades_is_allowed` (the previous and next clips then abut).
- `test_a_non_ripple_end_trim_with_an_outgoing_crossfade_is_still_rejected` (decision 4).
- `test_crossfade_ripple_trims_survive_load_and_replay`.
- `test_random_ripple_trims_with_crossfades_cover_changed_ids_and_round_trip_over_300_seeds`:
  - random crossfades on c1→c2 and c2→c3, with random ripple `src_in`/`src_out` trims;
  - `changed_ids` ⊇ every moved span on apply, undo and redo;
  - undo restores the hash and redo restores the new one;
  - rejections are only ever `transition_too_long`.

On `e274051`, every new test fails except two. The two that pass guard behaviour that was already right: the incoming-crossfade start trim and the non-ripple rejection.

`ruff check` is clean, `ruff format --check` is clean on `oplog.py`/`test_oplog.py`, and **636 passed**.
