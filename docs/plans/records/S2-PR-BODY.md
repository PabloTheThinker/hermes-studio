Title: feat(editor): Slice 2 op log (ops and inverses, atomic batches, undo/redo, dedupe, actor rules)

Branch `feat/editor-s2-oplog` → `main`. Plan: PLAN-MERGED.md §4.3 and §5 slice 2, Prove gates C2–C6 (C3's `kill -9` and C4's snapshots finish in Slice 3). Full spec: `docs/oplog.md`. It builds on the merged Slice 1 timeline API (`validate`, `canonical_hash`, `stamp_hash`).

Head: `480a220c53c7a55bbeaa792634f957b6a41468db`. Commits:
- b6a6646: `oplog.py` and its tests.
- e87d64b: the C2 property test.
- 304c24d: `docs/oplog.md`.
- ab45e65: `blocking_op_ids`; changed_ids tests for anchored items.
- 077d3ff: a normal merge of `origin/main` at bbb7216 (S1 #35, squash-merged). The branch was cut from S1's pre-squash head `fbbb2c0`, so `timeline.py`, `tests/test_timeline.py` and `docs/timeline.md` came up as add/add conflicts. S2 never changed those files, so they were resolved by taking main's versions as they are; outside the oplog files, the tree equals main. The PR's commit list still shows S1's five pre-squash commits (cbebd79…fbbb2c0) because of that ancestry. **The diff is only the files below.**
- 91f94ca: a `summary` holding a lone surrogate is `invalid_op`, not a `UnicodeEncodeError` at the log write.
- ff59093: docs notes on `docs/timeline.md`, as Ada ruled.
- dc5a92e: a normal merge of `origin/main` at 898f6b9 (#36), no conflicts. It brings `tests/test_clean_test_script.py` and its script change from main; neither is in this PR's diff.
- caa2c83: docs only, in `docs/oplog.md`. It covers dedupe and stale retries, a note that `media.proxy` is in the hash until S4, `inverse_invalid` as only the fallback reason, and `run_id` staying out of the line.
- Fixes for the six mismatches Wire found at ff59093:
  - 25a3480: `changed_ids` diffs **resolved** start/end as well as stored JSON, so an item that moves with its anchor counts. `move_clip c2` with `x1` anchored to `c2` gives `[c2, x1]`, and the same holds for a trim that moves the start and for ripple shifts. Undo's dependents check uses the same set, so a later edit to `x1` blocks undoing the move.
  - 83241b4: `add_track` uses the never-reused, first-free id rule, so add/remove/add gives `A4`, also after `load`. A non-string `role` is `bad_track_role` at `/ops/k/role`, not `bad_arg`.
  - d501916: `inverse_invalid` carries `op_ids` set to the target entries, by `seq`. Every `undo_blocked` result now carries `path` (`/op_id` or `/group_id`) and `id`.
  - 6fe4150: an op-level `not_found` carries the missing `id`. `remove_track`'s path is now `/ops/k/id` (it was `/ops/k/track`).
  - c2a930f: the module docstring names `seconds_to_ticks_nearest`.
- aa6f6ce: Prove's C2 fails, plus Ada's two new rules.
  - **F1:** `_commit`, `load` and `replay` retire every id handed out or present at any point in a batch, so an id created and removed in one call is never handed out again.
  - **F2:** a non-string `id`/`track`/`between[i]`/`ids[i]`/`anchor.to` is `invalid_op`/`bad_arg` at its own path, before any lookup.
  - **`id_reused`:** an explicit id that existed earlier in the log, or earlier in the same batch, is refused at its path. Inverses still restore old ids.
  - **`client_op_id_mismatch`:** a retry must be the same call, with forged fields stripped first. One key covers apply, undo and redo. Sameness is decided from the log line, so it holds after `load`.
- 2f80bbd: `ruff format` on `oplog.py` and `test_oplog.py`. It's formatting only, and the AST is unchanged.
- 0b459c4: fixes a crash Wire found. A retry on a cached `client_op_id` with junk `ops` (`5`, `null`, `[5]`, …) or wrong-typed `base_version`/`op_id`/`group_id` raised `TypeError` in the mismatch comparison.
  - All shape checks now run before the dedupe lookup, so a junk retry gets `invalid_op`/`bad_arg` at `/ops`, `/ops/k` or the field, the same as a fresh call.
  - An undo with `group_id: null` is now `bad_arg`. Before, it matched every ungrouped entry.
  - `split_clip`'s `duplicate_id` now points at `/ops/k/ids/i`, like `bad_arg` and `id_reused`.
- 480a220: Prove's C2 retry and target checks (R1–R4, approved by Ada).
  - **R1:** junk `ops` (`5`, `null`, `1.5`, `True`, `-1`) on a cached key are `bad_arg`. The 1–500 length cap also runs before dedupe and before any log replay.
  - **R2:** the tool is always compared on a retry, even with a `summary`, so a redo reusing an undo's key is a mismatch. After `load` the tool comes from the line; only an undo of an undo entry (which undo and redo both produce) accepts either tool.
  - **R3:** a null or missing undo/redo target is `bad_arg` at its path before dedupe, including `{op_id: X, group_id: null}`.
  - **R4:** `group_id: null` never matches ungrouped entries.

Files (`git diff origin/main...HEAD --stat`): `hermes_studio/oplog.py` (new), `tests/test_oplog.py` (new), `docs/oplog.md` (new), `docs/timeline.md` (+17 −1, notes only). Diff base: main `898f6b9`.

## What's in it

`hermes_studio/oplog.py`: `Oplog`, `Session`, `Actor`, `PlanContext`, `OplogError`, `replay()`, `changed_ids()`. It is pure Python with no new dependencies; the project folder, lock, snapshots and event bus are Slice 3.

## API

```python
log = Oplog(base_doc, path="projects/<id>/oplog.jsonl")   # or Oplog.load(base_doc, path)
result = log.call(session, tool, args)  # tool: timeline_apply | history_undo | history_redo
session = Session(Actor(kind="human" | "agent", id="pablo"), plan=PlanContext(step=3) | None)
```

- **One entry point.** MCP, HTTP and ACP each resolve their token to a `Session` and call `Oplog.call`. Nothing else writes. `Oplog`'s public surface is `call`, `doc`, `version`, `history_list(since_version)`, `history_diff(since_version)` and `load`, and a test pins that.
- **`timeline_apply`** args: `base_version`, `ops` (1–500), `summary` (non-empty, NFC, UTF-8, ≤ 200 chars), `client_op_id`, optional `group_id` and `project_id`. The order of checks is: args → dedupe → `base_version` → ops → `validate()`.
- **Result:** `ok, op_id, group_id, seq, new_version, hash, tick_rate, summary, changed_ids, undoes, before_frame, after_frame` (both `null` until S5) `, warnings`.
- **Log line:** `seq, op_id, client_op_id, group_id, actor, summary, base_version, new_version, hash, ops, inverse, changed_ids, undoes`, plus an optional `step`. Each line is flushed and fsynced to `oplog.jsonl` before it takes effect; a failed write changes nothing.
- **Errors** (`OplogError`, a `HermesStudioError`):
  - `invalid_op`: carries `rule`, `path`, `op_index`, and for validator failures `id?` and `problems` verbatim from `validate()`.
  - `not_found`: carries `rule`, `path` and `id` (the id that wasn't found); op-level ones also carry `op_index`.
  - `conflict`: carries `current_version` and `history_diff`.
  - `undo_blocked`: carries `reason` (`actor` / `dependents` / `inverse_invalid`), `op_ids`, `path` (`/op_id` or `/group_id`) and `id` (the target named). It adds `blocking_op_ids` (ordered by `seq`) for `dependents`; for `inverse_invalid`, `op_ids` is the target entries and it adds `rule` and `problems`.
- **Ops** (in ticks; the tool layer converts seconds once):
  - insert/remove: `insert_clip`, `add_text`, `add_transition`, `add_marker`/`remove_marker`, `add_track`/`remove_track`, `delete_clip{ripple}`, `split_clip`.
  - edits: `move_clip`, `trim_clip{ripple}`, `set_props`, `set_fade`, `set_anchor`.

  The engine computes every inverse at apply time, and `split_clip` → `join_clips` restores the old id. The internal inverse ops are refused from callers (`unknown_op`).

## Actor and step (forged-field handling)

- `actor` is `session.actor` (`{"kind", "id"}`) and is never read from args.
- `step` is logged only for **agent** sessions whose `PlanContext.step` is set. A human op never gets `step`, even when its session has a plan context.
- An `actor` or `step` in the args or in any op is dropped before anything else runs, for all three tools. Each one dropped adds an `ignored_field` warning with its pointer (`/actor`, `/ops/0/step`).
- Dedupe keys on the session's actor, so a forged actor can't reach another actor's retry slot.

## Decisions

**Confirmed by Ada:**
- **`actor`** is an object `{kind, id}` taken from the session. `kind` is `human` or `agent`.
- **`undoes`** is `null` or a list of op_ids. A group undo is one entry naming every entry it reverses, newest first.
- **No `run_id`** in the log line. The line fields are the 13 locked ones plus an optional `step`.
- **Forged fields:** an `actor` or `step` in args or in any op is stripped before anything runs, with an `ignored_field` warning, on `timeline_apply`, `history_undo` and `history_redo`. `step` is logged only for agent sessions with a plan step, and never on human ops.
- **Delete with anchors:** items anchored to a deleted clip keep their position as an absolute `at`, so there's never an `anchor_target_missing` doc.
- **Split with anchors:** anchored items move to the piece their start falls in, with the offset adjusted so they don't move.
- **Split at speed ≠ 1:** a cut that isn't whole ticks is `invalid_op` / `non_integer_duration`, never rounded.
- **`undo_blocked` reasons:**
  - `actor`: an agent undoing anything but its own entries.
  - `dependents`: later live entries that changed or reference the target's ids, listed in `blocking_op_ids` ordered by `seq`.
  - `inverse_invalid`: the inverse no longer validates. This one is the fallback.
- **`changed_ids` includes anchored items:** it's computed by diffing the doc before and after, on stored JSON and resolved start/end. So it includes:
  - items moved by their anchor target (move, start trim, ripple);
  - items a delete frees to `at`;
  - items a split re-anchors.

  They're in the entry's `changed_ids` and in its undo's, and undo's dependents check uses the same set.

- **Id assignment:** without an `id`, the engine picks the first free `c<n>`/`x<n>`/`tr<n>`/`mk<n>`/`T<n>`/`A<n>`. An id that ever existed in the log is never handed out again. The id it picks is written into the logged op, so replay is exact.
- **Delete, ripple and trim:**
  - transitions touching a deleted item go with it;
  - a ripple delete shifts later items on the same track (those with their own `at`, from the deleted item's end minus its outgoing overlap) by the item's duration minus any transition overlaps, so the neighbours abut;
  - a ripple trim keeps the start and shifts later items by the change in duration;
  - a trim without ripple keeps the rest of the clip in place.
- **Split:**
  - pieces get `split_from`;
  - fades are clamped per piece;
  - an incoming transition goes to the first piece, and an outgoing one to the second.
- **Cancellation and group undo:**
  - an entry is live unless a live undo entry undoes it, so an undone undo cancels nothing;
  - an undo/redo pair after the target cancels out and doesn't block;
  - undoing a group applies its live entries' inverses, newest first, as one entry;
  - redo is the undo of an undo entry.
- **Stale retry:** a retry with the same `(actor, client_op_id)` returns the original result, even with a now-stale `base_version`. On `load`, the dedupe table is rebuilt from the log; a rebuilt entry doesn't carry the original warnings.
- **`id_reused`** (Ada, 12:58 ET): an explicit id that was retired (it existed earlier in the log or earlier in the same batch) is `invalid_op` / `id_reused` at that id's path. An id in the doc now is still `duplicate_id`.
- **`client_op_id_mismatch`** (Ada, 12:58 ET):
  - a retry under the same (actor, `client_op_id`) with different canonical args (forged fields stripped) is `invalid_op` / `client_op_id_mismatch`;
  - an identical retry still returns the cached result;
  - one key covers apply, undo and redo, and the check survives `load`.
- **Op-level rule ids:** there are 16 now, adding `id_reused` and `client_op_id_mismatch` (see `docs/oplog.md`).

All decisions above were confirmed by Ada as written at 12:09 ET, including `inverse_invalid` as the third, fallback reason.

## Tests

`tests/test_oplog.py`, 247 cases:
- **Line and result:** the exact field set; the write-result contract.
- **Actor and step** (C5):
  - a forged `actor` in args is ignored and doesn't unlock undoing a human's entry;
  - a forged `actor`/`step` inside an op is ignored;
  - a forged `step` is replaced by the plan step, which follows plan changes;
  - an agent without a plan step gets none;
  - a human op never gets a step (on apply and undo, even with a plan context);
  - forged fields are ignored on undo and redo;
  - `call` is the only way to write; sessions are checked.
- **Dedupe, conflict, atomicity** (C3, C5, C6):
  - a retry applies once, and another actor's key is separate;
  - a stale `base_version` gives `conflict` with `history_diff`, the hash unchanged and nothing logged, and the stale retry is refused again;
  - a batch failing at op k applies nothing;
  - an invalid result passes `problems` through;
  - the validator runs after the ops (`fade_too_long`, `anchor_target_not_main`, `overlap`, `not_nfc`, `anchor_before_zero` with the anchored item's id);
  - 9 bad-call cases;
  - a `summary` with a lone surrogate (with and without a log file, on apply and undo).
- **Ops and inverses:** every op round-trips (undo restores the hash, redo restores the new one):
  - insert gets a fresh id;
  - tracks keep role order;
  - trim ripple and its un-ripple;
  - split → join restores the old id, moves transitions and anchors to the right piece, and refuses a non-whole-tick point at speed;
  - delete frees anchored items and undo re-anchors them;
  - a ripple delete closes the hole and takes transitions along.
- **changed_ids:**
  - freed and re-anchored items are listed in the delete, the split, their undos and a redo;
  - items that move with their anchor are listed (move, start trim, ripple), on apply, undo and redo;
  - an unmoved anchored item is not listed;
  - a later edit to a moved anchored item blocks undoing the move;
  - property: over 300 seeded runs, `changed_ids` ⊇ every item whose resolved span changed, on apply and on undo.
- **add_track:** add/remove/add gives `A4` (`A5` after `load`), and the picked id is logged; first free never-seen id; a non-string `role` (`[]`, `{}`, `["main"]`, `1`, `None`, `True`) is `bad_track_role`.
- **Ids (Prove F1/F2, Ada):**
  - an id created and removed in one batch (marker, clip, track) is never handed out again, live and after `load`;
  - 20 id-taking op fields × `7`/`None`/`[]`/`{}`/`True` give `bad_arg` at the field's path (100 cases);
  - `id_reused` covers explicit retired marker/clip/track/split ids and the same-batch case (explicit and engine-picked), and holds after `load` while undo/redo still restore old ids.
- **client_op_id_mismatch:**
  - 6 kinds of changed args;
  - an identical retry, even with forged fields or naming the picked id, returns the cached result;
  - undo or redo reusing an apply key (and the reverse) is a mismatch, and undo vs redo of the same entry is too;
  - it holds after `load`.
- **Junk retries on a cached key (Wire):**
  - `ops` of `5`/`None`/`"x"`/`{}`/`[]`/`[5]`/`[None]`/mixed give `bad_arg` at `/ops` or `/ops/k`, cached or fresh;
  - 24 wrong-typed apply/undo/redo fields give `bad_arg`;
  - both or neither undo target gives `bad_arg`;
  - a 3000-run seeded fuzz of junk mutations on cached keys never crashes or writes;
  - split `duplicate_id` points at `/ops/0/ids/i`.
- **Retry and target checks (Prove R1–R4):**
  - scalar `ops` on a cached key give `bad_arg`;
  - an empty list or more than 500 ops give `bad_arg` before dedupe, cached or fresh, without any replay;
  - a redo reusing an undo key (same `summary` and `op_id`) is a mismatch, live and after `load`, and undo vs redo of an undo entry is too;
  - 10 null or missing target shapes give `bad_arg` on cached and fresh keys;
  - Prove's repro (apply A, B, C in `g1`, then undo `{group_id: null}`) gives `bad_arg` and undoes nothing, and the group match still refuses null.
- **Error shapes:**
  - `inverse_invalid` carries the target `op_ids`, `path`, `id`, `rule` and `problems` (single op and group);
  - `actor` and `dependents` blocks carry `path` and `id`;
  - an op-level `not_found` carries the missing `id` (item, track, marker, `remove_track`).
- **Undo rules:**
  - undo is a new entry, and history is never rewritten; `already_undone`;
  - a group undo is one entry, in reverse order;
  - an agent can't undo a human's or another agent's entry, and a human can undo an agent's;
  - dependents block, and come back as `blocking_op_ids` in `seq` order, an undone blocker dropping out;
  - a reference without a change also blocks;
  - an `actor` block has no `blocking_op_ids`;
  - redo needs an undo entry.
- **Persistence:** the log file replays to the live hash (`load` and `replay`); dedupe survives a reload; a tampered hash is refused; a failed log write changes nothing.
- **C2 property:** 1,000 seeded random runs of 2–6 batches over a dozen op kinds, as human and agent, with groups:
  - undo-all, newest first, lands on each previous hash and ends on the original;
  - a full replay equals the result;
  - group undos are one entry, and undoing them restores the hash;
  - blocked group undos have `blocking_op_ids` in `seq` order.

Full suite on the merged tree: `ruff check` clean and `ruff format --check` clean on `oplog.py`/`test_oplog.py`; **613 passed** (366 on main at 898f6b9 plus 247 op log).

## Notes

- **Ripple trim with an outgoing crossfade** (unchanged, waiting on Ada; a separate PR later): it currently gives `invalid_op`/`transition_overlap_mismatch`.
- **Explicit-id behaviour:** passing a caller-chosen id is unchanged apart from the new `id_reused` check.
- **Later PR:** `1` vs `1.0` and NFC vs NFD in retry comparisons are unchanged (per Ada).
- **Not in S2:** the project folder, `.lock`, snapshots every 50 versions, `checkpoint_restore`, the event bus and SSE (S3); the mode gate (S8).
- **No text edit op:** there's no op to change a text item's `text`/`style`; PLAN §4.5 doesn't list one.
- **`run_id`:** it stays out of the log line. Wire's `history_list` will need it from somewhere else if it still wants it.
- **`media.proxy` in the hash:** it's part of the hashed doc today. Ada ruled that it must not be, because a background job must never change the hash without an op. It moves to media state outside the doc in S4; S2 leaves it as it is (noted in `docs/oplog.md`).
- **otiotool:** `--stats` / `--list-markers` fail at 705600000/s (SMPTE timecode limit); the other otiotool commands pass. `--stats` stays in ticks, and frame-rate export is deferred.
- **OTIO precision** (docs note, as Ada ruled): OpenTimelineIO 0.18.1's JSON reader misreads values above about 7×10¹⁵ ticks when a `.otio` file is read back; the in-memory round trip is exact. Export will warn about this, not fix it. The warning goes in with whichever slice first touches `to_otio()`, not S2 or S2b.
- **Surrogates** (docs qualifier, as Ada ruled; no code change): a lone surrogate in `schema_version`, a track `role`, an item's `media`, or a transition's `kind`/`between` gets that field's own rule id (`bad_schema`, `bad_track_role`, `unknown_media`, `bad_transition`), not `wrong_type`.
- **Overlay role proposal** (`hs.timeline/2`): unchanged from the S1 notes.
