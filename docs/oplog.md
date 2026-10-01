# Op log (`hermes_studio/oplog.py`)

Slice 2 of the editor. The op log is the only way a timeline changes. It sits on the Slice 1
timeline API (`validate`, `canonical_hash`, `stamp_hash`; see [timeline.md](timeline.md)).

## One entry point

```python
log = Oplog(base_doc, path="projects/<id>/oplog.jsonl")
result = log.call(session, tool, args)  # tool: timeline_apply | history_undo | history_redo
```

MCP, HTTP and ACP each resolve their bearer token to a `Session` and call `Oplog.call`. Nothing
else writes. The public surface of `Oplog` is `call`, the reads `doc`, `version`,
`history_list(since_version)` and `history_diff(since_version)`, and `Oplog.load(base, path)`.

```python
Session(actor=Actor(kind="human" | "agent", id="pablo"), plan=PlanContext(step=3) | None)
```

### Actor and step come from the session only

- `actor` in a log line is `session.actor` as `{"kind", "id"}`. It is never read from the args.
- `step` is in a line only when the session is an **agent** with a `PlanContext` whose `step` is
  set (an integer ≥ 1, kept up to date by the session layer as Hermes works through its plan).
  A human op never gets `step`, even when its session carries a plan context.
- An `actor` or `step` key in the call's args, or in any op, is **dropped** before anything else
  happens. Each dropped key adds a warning to the result:
  `{"code": "ignored_field", "path": "/actor" | "/ops/<k>/step" | …, "message": …}`.
  The same rule holds for `timeline_apply`, `history_undo` and `history_redo`.
- Dedupe keys on the session's actor, so a forged actor can't hit another actor's retry slot.

## Log lines

One JSON object per line in `oplog.jsonl` (sorted keys, compact, UTF-8, flushed and fsynced
before the entry takes effect; a failed write changes nothing):

| Field | |
|---|---|
| `seq` | 1, 2, 3 … with no gaps |
| `op_id` | engine-made (`op-<16 hex>`) |
| `client_op_id` | from the caller; `(actor, client_op_id)` is unique |
| `group_id` | from the caller, or `null` |
| `actor` | `{"kind": "human" \| "agent", "id": …}` from the session |
| `step` | optional: agent ops with a plan step only |
| `summary` | from the caller (undo/redo default to `Undo: …` / `Redo: …`) |
| `base_version` → `new_version` | `new_version = base_version + 1`; the doc's `version` |
| `hash` | `canonical_hash` of the new doc |
| `ops` | the ops as applied: forged fields dropped, engine-assigned ids filled in |
| `inverse` | ops that undo this entry, computed at apply time |
| `changed_ids` | sorted ids added, removed or changed (media, tracks, items, markers), worked out by diffing the doc before and after. Items are compared by their stored JSON **and** their resolved start/end, so side effects count: items that move because their anchor target moved (a `move_clip`, a trim that moves the clip's start, a ripple shift), items a delete turns from `anchor` into `at`, and items a split re-anchors to a piece. An undo entry lists the same ids. Undo's dependents check uses this same set |
| `undoes` | `null`, or the list of `op_id`s this entry undoes (one for an op, all of a group's newest first) |

`undoes` is a list so a group undo is one entry that names every entry it reverses.

## timeline_apply

Args: `base_version`, `ops` (1–500), `summary` (non-empty NFC, ≤ 200 chars), `client_op_id`
(`[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`), optional `group_id` (a string like `client_op_id`; leave it out for no group, `null` is `bad_arg`), optional `project_id` (must be this
timeline's `id`). Anything else is `invalid_op` / `unknown_arg`.

Order of checks: args → dedupe (a retry returns the original result, even with a now-stale
`base_version`) → `base_version` (`conflict`) → ops → validate.

A batch is atomic: the ops run on a copy, the copy must pass `validate()`, then it gets
`version + 1` and `stamp_hash`. Any failure leaves the doc and the log as they were.

Result: `ok, op_id, group_id, seq, new_version, hash, tick_rate, summary, changed_ids, undoes,
before_frame, after_frame` (both `null` until Slice 5) `, warnings`.

### Ops (times in integer ticks; the tool layer converts seconds once)

| Op | Args | Inverse |
|---|---|---|
| `insert_clip` | `track, media, src, at \| anchor, id?, fade_in?=0, fade_out?=0, props?` | `delete_item{id}` |
| `add_text` | `dur, text, style, at \| anchor, id?, track?=first text track, fade_in?, fade_out?` | `delete_item{id}` |
| `add_transition` | `between, dur, id?, track?=V1, kind?=xfade` | `delete_item{id}` |
| `add_marker` / `remove_marker` | `at, label, id?` / `id` | `remove_marker` / `insert_marker{index, marker}` |
| `add_track` / `remove_track` | `role, id?` / `id` | `remove_track` / `insert_track{index, track}` |
| `move_clip` | `id, at` (items with their own `at`) | `move_clip` with the old `at` |
| `trim_clip` | `id, src_in? src_out?` (clip) or `dur` (text), `ripple?` | `set_fields` with the old values (+ `shift_items` back) |
| `split_clip` | `id, at` (strictly inside), `ids?` | `join_clips`, which restores the old id |
| `delete_clip` | `id, ripple?` | `insert_item` at the old index (+ `shift_items`, re-anchoring) |
| `set_props` | `id, props` (merged into the clip's props) | `set_fields` with the old `props` |
| `set_fade` | `id, fade_in?, fade_out?` (clips and text) | `set_fields` with the old values |
| `set_anchor` | `id, anchor` or `anchor: null, at` | `set_fields` with the old `at`/`anchor` |
| `edit_text` | `id, text?, style?` (a text item; at least one of `text`/`style`) | `set_fields` with the old values of the fields given |

Internal ops (`set_fields`, `shift_items`, `delete_item`, `insert_item`, `insert_marker`,
`insert_track`, `join_clips`) only appear in inverses and undo entries; a caller sending one gets
`unknown_op`.

Decisions:

- **Ids.** Without an `id`, the engine picks the first free `c<n>` (clips), `x<n>` (text),
  `tr<n>` (transitions), `mk<n>` (markers), `T<n>`/`A<n>` (tracks). An id that ever existed in
  this log is never handed out again, and that includes an id that existed only inside one batch
  (created and removed by the same call). `_commit`, `load` and `replay` all retire every id handed
  out or present at any point during a batch. The id goes into the logged op, so replay is exact.
  A caller can't name a retired id either (`id_reused`).
- **Split.** Pieces get `split_from: <old id>`. The first piece keeps `fade_in`, the second
  `fade_out` (each clamped to its piece). A transition into the clip moves to the first piece, one
  out of it to the second. An item anchored to the clip moves to the piece its start falls in,
  with its offset adjusted so it doesn't move; its id is in the entry's `changed_ids` (and in the
  undo entry's, which re-anchors it to the old id). At speed ≠ 1 a cut whose source point isn't whole
  ticks is `invalid_op` / `non_integer_duration`; the engine never rounds.
- **Delete.** Transitions touching the item go with it. Items anchored to it keep their place as
  an absolute `at` (never an `anchor_target_missing` doc); their ids are in the entry's
  `changed_ids`, and in the undo entry's, which anchors them again. With `ripple`, items on the same track
  starting at or after its end shift left by its duration minus any transition overlaps, so the
  neighbours abut.
- **Trim.** Without `ripple`, trimming the start keeps the rest of the clip where it is (`at`, or
  an anchor's offset, moves by `Δin / speed`). With `ripple`, the start stays and later items on
  the track shift by the change in duration.
- **Ripple trim and crossfades** (Glyph's rule, ruled by Ada: the crossfade stays with the cut).
  - With `ripple` the start stays, so a trim of either end (`src_in` or `src_out`) moves the
    clip's **end**.
  - An **outgoing** crossfade moves with that end. The ripple point is the start of the overlap
    (the next clip's start), not the old end, so the next clip, the crossfade and everything
    after them shift together by the change in duration. The crossfade keeps its `dur` and its
    `between` pair.
  - An **incoming** crossfade stays at the clip's start, unchanged.
  - **Too short:** the trimmed clip must be longer than each of its crossfades and at least as
    long as both together, so the previous and next clips can abut but never overlap. Anything
    shorter is `invalid_op` / `transition_too_long` at the op (`/ops/k`), with `id` set to the
    crossfade that doesn't fit (Ada and Glyph's ruling). It's checked before anything moves.
    - If one crossfade doesn't fit on its own, `id` is that crossfade's id. If neither fits on
      its own, it's the outgoing one.
    - If each fits on its own but not both together, `id` is the outgoing crossfade's id.
    - `transition_too_long` is an op-level rule, not a timeline (validator) rule. It has the same
      shape as a validator problem on one item (`rule`, `path`, message, `id`), like
      `fade_too_long`.
  - **Without `ripple`:** nothing shifts. An end trim of a clip with an outgoing crossfade still
    fails validation with `transition_overlap_mismatch`, as before.
  - `changed_ids` comes from the resolved diff, so it lists the trimmed clip, the shifted items,
    the moved crossfade and anything anchored to a shifted clip. Markers don't move.
  - **Check order** (Ada's ruling): `transition_too_long` is checked before `empty_range`. A ripple
    trim of a clip with a crossfade down to an empty or zero-length source range (`src_out` at or
    before `src_in`) is `transition_too_long` at `/ops/k` naming the crossfade, not the
    validator's `empty_range` on the clip's `src`. The same trim of a clip without crossfades is
    `empty_range` as before.
  - **Known limit: a neighbour that only overlaps** (Ada's ruling). On a track where clips may
    overlap (music), a ripple trim never moves a neighbour that only overlaps the trimmed clip
    without a crossfade of its own; it shifts only the items starting at or after the ripple
    point. If that pulls one clip of a crossfade pair away from the other (e.g. `m0` overlaps
    `ma`, and `ma`→`mb` has a crossfade: trimming `m0` shifts `mb` but not `ma`), the result is
    rejected with the **existing** `transition_overlap_mismatch` (at the crossfade's `dur`, `id` =
    the crossfade), and nothing changes. A non-ripple trim of the same clip is fine. Changing this
    would be an S4 behaviour decision; no rule id is added for it (17 op-level, 36 validator).

### Errors

`OplogError` (a `HermesStudioError`); `as_dict()` adds the extra fields.

| `code` | When | Extra |
|---|---|---|
| `invalid_op` | bad args or ops, or the result fails `validate()` | `rule`, `path`, `op_index`; for validator failures also `id?` and `problems` verbatim from `validate()`; for `transition_too_long` also `id` (the crossfade) |
| `not_found` | unknown item, track, marker, entry, group or project | `rule`, `path`, and `id` (the id that wasn't found); op-level ones also `op_index` |
| `conflict` | `base_version` isn't the current version | `current_version`, `history_diff` |
| `undo_blocked` | see below | `reason`, `op_ids`, `path` (`/op_id` or `/group_id`) and `id` (the op_id or group_id asked for); with `reason: "dependents"` also `blocking_op_ids` (by `seq`); with `reason: "inverse_invalid"` also `rule` and `problems` |

Op-level `rule`s (17): `unknown_tool`, `unknown_op`, `unknown_arg`, `missing_arg`, `bad_arg`,
`not_integer_ticks`, `negative_time`, `bad_id`, `duplicate_id`, `id_reused`, `bad_track_role`,
`non_integer_duration`, `not_found`, `already_undone`, `not_an_undo`, `client_op_id_mismatch`,
`transition_too_long`, plus every timeline rule.

- **`edit_text`** (S2b) changes a text item's `text` and/or `style` on any text track.
  - Each field given replaces the old value as a whole string. `style` is a single style name in
    the S1 schema, not an object, so there are no style sub-keys to merge. A field left out
    stays as it is, and so does everything else on the item (`dur`, `at`/`anchor`, fades,
    `split_from`).
  - Checks, in order:
    1. the usual `unknown_arg`/`missing_arg` (`id`);
    2. `id` must be a string (`bad_arg` at `/ops/k/id`);
    3. it must exist (`not_found` at `/ops/k/id`, `id` = the missing id);
    4. it must be a text item (`bad_arg` at `/ops/k/id`, `id` = the clip or transition);
    5. at least one of `text`/`style` is needed (`missing_arg` at `/ops/k`);
    6. then each value, at the op's own arg (`/ops/k/text`, `/ops/k/style`), with the validator's
       rule ids and `id` = the text item: not a string, an empty `style`, or a lone surrogate is
       `wrong_type`; non-NFC is `not_nfc`. `text` may be `""`.
  - Strings are never normalised. What's stored is exactly what was sent (NFD is rejected, not
    converted). No new rule id.
  - The inverse is `set_fields` with the old values of just the fields given, so undo and redo
    restore the hash exactly.
  - `changed_ids` is `[id]` when something changed. An edit to the same values is still an entry
    (a new version, the same hash, `changed_ids: []`), like `set_fade` with its current values.
- **Media:** `insert_clip`'s `media` must be the id of an entry in the doc's `media`. Anything
  else (an unknown or empty string, a number, `null`, a list, an object or a bool) is
  `invalid_op` / `unknown_media` at the op's own arg, `/ops/k/media`, with no `id`, checked
  before the doc is validated (so never at the doc path `/tracks/…/media`). `unknown_media` is the
  existing timeline rule, so no new rule id.
- **Id types:** every id an op names must be a string. That covers `id`, `track`, each entry
  of `between` and `ids`, and `anchor.to`. Anything else (a number, `null`, a list, an object
  or a bool) is `invalid_op` / `bad_arg` at that id's own path (`/ops/k/id`, `/ops/k/anchor/to`,
  `/ops/k/between/1`). This is checked before any lookup, so it's never a `not_found`. It
  matches what `history_undo` does with a non-string `op_id`.
- `id_reused`: a caller named an id that is in the doc's past but not in the doc now. It existed
  earlier in the log, or earlier in the same batch (including an id the engine handed out and the
  batch then removed). The path is at that id (`/ops/k/id`, `/ops/k/ids/i`). An id that's in the
  doc now is still `duplicate_id`. For `split_clip`'s `ids`, every id error (`bad_arg`,
  `duplicate_id`, `id_reused`) points at the entry (`/ops/k/ids/i`). Inverses (undo, redo, `load`, `replay`) restore old ids on
  purpose and skip this check.

## Undo and redo

`history_undo{op_id | group_id, client_op_id, summary?, base_version?}` appends a new entry whose
`ops` are the target's `inverse` (a group: every live entry of the group, newest first, as one
entry). `history_redo{op_id}` takes an undo entry and undoes it. History is never rewritten.

- An entry is **live** unless a live undo entry undoes it (so an undone undo cancels nothing).
  Undoing a non-live entry is `invalid_op` / `already_undone`.
- **Actor rule:** an agent may undo only entries with its own actor; anything else is
  `undo_blocked` with `reason: "actor"` and `op_ids` = the entries it doesn't own. A human may
  undo anyone's.
- **Dependents:** a later live entry blocks the undo when it changed one of the target's
  `changed_ids` or its ops refer to one (an anchor, a transition end, a target id). An
  undo/redo pair after the target cancels out and doesn't count. Result: `undo_blocked`,
  `reason: "dependents"` and `blocking_op_ids` = those entries' `op_id`s, ordered by `seq`
  (Glyph's "Restore to before this step"; `op_ids` carries the same list).
- **Fallback only:** if the actor and dependents checks pass but the inverse still fails to
  validate, the result is `undo_blocked`, `reason: "inverse_invalid"`. `op_ids` holds the target
  entries (by `seq`), with the failing `rule` and the validator's `problems`.

## Replay

`Oplog.load(base, path)` re-applies every line and checks its sequence, versions, hash and
inverse. `replay(base, entries)` re-applies them and checks each hash. Snapshots, the project
store and the lock are Slice 3.

### Dedupe and stale retries

- Shape checks run **before** the dedupe lookup, so a junk retry on a cached key gets the same
  `invalid_op` / `bad_arg` as a fresh call and never reaches the mismatch comparison. That covers
  `ops` (a list of 1–500 objects, each with a string `op`; `/ops` or `/ops/k`), `base_version`,
  `summary`, `group_id`, and undo/redo's `op_id`/`group_id` (strings, exactly one of them).
  A null `op_id` or `group_id` is `bad_arg` at its path, never "missing", and a null group
  never matches the ungrouped entries.
- `timeline_apply` with `group_id: null` is `bad_arg` at `/group_id` (Ada's ruling), fresh or
  on a cached key. Leave the field out for an ungrouped entry; the entry and result then carry
  `group_id: null`.
- The **tool** is always part of "same call", even when a `summary` is given. The dedupe
  table records which tool made each entry. After `load`, the tool comes from the line: an
  apply has no `undoes`, and an undo of a group or of a normal entry is `history_undo`. The
  only case the line can't settle is an undo of an *undo entry*, which `history_undo` and
  `history_redo` both produce. There, a reloaded key accepts either tool, as long as every
  other field matches.

- A retry with the same `(actor, client_op_id)` returns the original result, even when its
  `base_version` is now stale. It doesn't raise `conflict` and doesn't append a line.
- `load` rebuilds the dedupe table from the log. A rebuilt entry doesn't carry the original
  `warnings` (for example `ignored_field`), because warnings aren't logged.
- The retry must be the **same call**. Otherwise it's `invalid_op` / `client_op_id_mismatch` at
  `/client_op_id` (with `op_ids` = the cached entry), and nothing is applied. Forged fields
  (`actor`, `step`) are stripped first, so a retry that differs only in them is still the same
  call. One key (actor, `client_op_id`) covers all three tools, so an undo or redo that reuses an
  apply's `client_op_id`, or the other way round, is a mismatch. "Same" is decided from the log
  line alone, so it holds after `load` exactly as it does live:
  - `timeline_apply`:
    - `base_version`, `summary` and `group_id` are equal;
    - the ops, re-run on the doc and retired ids as they were before that entry, produce exactly
      the logged ops. So leaving out an id the engine picked, or naming that same id, both match.
      The doc and retired ids are kept as a checkpoint after every 16th entry (live and after
      `load`), so a retry re-runs at most 15 entries from the nearest one instead of the whole
      log. The result is the same as re-running from `base`.
  - `history_undo` / `history_redo`:
    - the target is the same (`op_id`, or `group_id` for an undo);
    - `summary` is the same; without one, the line's summary must be that tool's default
      (`Undo: …` / `Redo: …`), which is how an undo and a redo of the same entry differ;
    - `base_version`, if given, equals the line's.
  - "Equal" means equal as canonical JSON (sorted keys, `(',', ':')`, UTF-8 as is, no NaN), the
    same encoding as the log line and `canonical_hash`. There's no numeric or Unicode folding, so
    `1`, `1.0` and `true` are three different values, and an NFC string and its NFD form are
    different strings, exactly as they'd give different hashes. A fresh call can't carry those
    values anyway (no floats in a doc; `not_integer_ticks`, `not_nfc`, `wrong_type`, or `bad_arg`
    for `base_version`/`summary`), so on a cached key a retry that differs only that way is
    `client_op_id_mismatch` (or the same `bad_arg`, for the top-level fields, since shape checks
    come first), never the cached result.

## `media.proxy` and the hash

`media.proxy` is currently part of the hashed doc. Ada has ruled that it must not be, because a
background job must never change the hash without an op. It moves to media state outside the doc
in S4. S2 leaves it as it is.

## Not in this slice

The project folder, `.lock`, snapshots and the event bus (S3); the mode gate (S8); editing a
text item's `text`/`style` (no op in PLAN §4.5); `run_id` in lines (it stays out of the log line;
Wire's `history_list` lists it, but it isn't in the locked line fields).
