S2b: a new `edit_text` op in the oplog, plus a doc note on `undo_blocked` `op_ids`. Base: main 8d181ed.

**This PR body is the spec of record for S2b.** PLAN-MERGED.md has no S2b section. Ada approved all 13 decisions below, with Rin's `changed_ids` wording.

## `edit_text` (commit 6a106a7)
`{"op": "edit_text", "id": <text item id>, "text"?: str, "style"?: str}`. At least one of `text`/`style` must be given. It works on a text item on any text track.

- **Update semantics:** each field given replaces the old value as a whole string. In the S1 schema `style` is a single non-empty style name, not an object, so there are no style sub-keys to merge. A field left out stays as it is, and so does everything else on the item (`dur`, `at`/`anchor`, `fade_in`/`fade_out`, `split_from`).
- **Checks, in order** (all `invalid_op` unless noted; nothing is applied on any of them):
  1. `unknown_arg` for any other arg (`/ops/k/<arg>`); `missing_arg` for no `id` (`/ops/k/id`).
  2. `bad_arg` at `/ops/k/id` if `id` isn't a string.
  3. `not_found` (code `not_found`) at `/ops/k/id`, `id` = the missing id.
  4. `bad_arg` at `/ops/k/id`, `id` = the item, if it's a clip or transition.
  5. `missing_arg` at `/ops/k` if neither `text` nor `style` is given.
  6. Each value, checked at the op's own arg (`/ops/k/text`, `/ops/k/style`) with the S1 validator's own rule ids and `id` = the text item:
     - `wrong_type` for a non-string, an empty `style`, or a lone surrogate;
     - `not_nfc` for a non-NFC string.
     - `text` may be `""`.
- **Strings are stored byte for byte.** Nothing is normalised: NFD is rejected, never converted.
- **Inverse:** internal `set_fields{id, set: <old values of the fields given>, unset: []}`. It never touches any field except `text`/`style`. Clients can't send `set_fields` (`unknown_op`), and `load` rejects a line whose stored inverse doesn't match the one re-derived from its ops. Undo and redo restore the doc and the hash exactly. `load` and `replay` reproduce the doc, and so does an OTIO round trip.
- **changed_ids:** `changed_ids` is `[id]` when the value changes and `[]` for a no-op (same hash), same as `set_fade`; undo and redo list the same ids as the apply. A **no-op** is an edit whose every given value is byte-for-byte equal to the old one, with no normalising (NFC/NFD are never folded, and NFD is rejected anyway). It's still an entry (a new version, the same hash), and an exact retry of it returns that entry without adding one.
- **Dedupe/same-call:** an exact retry returns the cached result; a changed retry is `client_op_id_mismatch` (canonical JSON, so NFC ≠ NFD). This survives `load`, and checkpoints work as before.
- **Dependents:** a later edit of the same item blocks undo of an earlier one (`dependents`), and the actor rule applies.
- **Rule ids:** no new ones. Still **17 op-level / 36 validator**.

## Follow-up (not in this PR)
`missing_arg` at `/ops/k` (when an op needs one of several optional args and gets none) is now the house rule. Moving `set_fade` (still `bad_arg` at `/ops/k/id`) and `add_text`'s arg paths (bad values still at the doc path) to it is a later cleanup. They're unchanged here, and docs/oplog.md says so.

## Doc note (commit 36e529b)
docs/oplog.md now says what `undo_blocked` `op_ids` means for each `reason`:
- `actor`: other people's entries;
- `dependents`: the blocking entries, the same as `blocking_op_ids`;
- `inverse_invalid`: the entries being undone.

## Tests
**742 passed** on Python 3.12.14 (main 8d181ed: 690), with no skips. `ruff check` is clean, and `ruff format --check` is clean on the changed files. There are 52 new tests. With oplog.py reverted to main 8d181ed (and these tests kept), 50 of them fail. The 2 that still pass don't depend on edit_text: the doc-note test and the `set_fade` comparison case of the no-op test.

How Prove's list is covered:
1. **Exact retry, NFD, style-only; changed retry is a mismatch:**
   - `test_an_exact_edit_text_retry_returns_the_cached_result`: a non-ASCII NFC text edit and a style-only edit return the cached result. A retry with the NFD form, other text, an added style or an added text is `client_op_id_mismatch`.
   - `test_an_nfd_edit_text_is_rejected_the_same_way_every_time`
   - `test_edit_text_retry_survives_load`
2. **Byte-for-byte storage; lone surrogates rejected cleanly:**
   - `test_edit_text_stores_strings_byte_for_byte` (8 cases: empty, accents, ZWJ emoji and a flag, CJK/Hangul, RTL, newlines/tabs/spaces, Å, quotes/backslash/`</script>`; checked in the live doc, the log line, `load` and `replay`).
   - `test_edit_text_bad_values_get_the_validators_rule_at_the_op_arg` (11 cases, including lone surrogates in `text` and `style` → `wrong_type`, and NFD → `not_nfc`).
3. **Apply → undo → redo gives identical state and hashes; a partial edit leaves the rest alone:**
   - `test_edit_text_undo_and_redo_restore_state_hashes_and_changed_ids`
   - `test_edit_text_apply_undo_redo_restores_hashes_over_300_seeds`, a fuzz test mixed with the other public ops (>300 edit_text applies; each apply is undone and redone, then replayed).
   - `test_edit_text_replaces_only_the_fields_given` (4 cases)
   - `test_edit_text_style_only_then_text_only_keep_each_other`
   - `test_edit_text_in_a_group_undoes_as_one_entry`
   - `test_edited_text_survives_the_otio_round_trip`
4. **`changed_ids` names the item and undo lists the same ids:** the undo/redo test, the fuzz test, the group test, `test_edit_text_to_the_same_values_is_an_entry_with_no_changed_ids`, and `test_a_noop_edit_text_has_empty_changed_ids_on_apply_undo_and_redo` (no-op with both fields, text only, style only, and `set_fade` for comparison).
5. **A non-text item or a missing id gives a clean error with id and path:**
   - `test_edit_text_on_a_non_text_item_or_a_missing_id_is_a_clean_error` (8 cases: clip, transition, missing id, no fields, no `id`, int id, null id, extra arg)
   - `test_edit_text_as_op_k_reports_op_k`
   - `test_a_later_edit_text_blocks_undo_of_an_earlier_one_as_a_dependent`
   - `test_an_agent_cannot_undo_a_humans_edit_text`
Prove's extra checks:
- **E1. Undo after the item was deleted:** `test_undo_of_edit_text_after_its_item_was_deleted_is_undo_blocked_and_applies_nothing` (`undo_blocked`/`dependents`, with `op_ids` = `blocking_op_ids` = the delete; nothing is applied).
- **E2. Edit, delete, then undo the delete and then the edit:** `test_edit_delete_then_undo_both_restores_the_old_text_and_style` (old text and style back, base hash restored, and it survives `load`).
- **E3. An exact retry of a no-op adds no entry:** `test_an_exact_retry_of_a_noop_edit_text_returns_the_cached_entry`.
- **E4. The inverse holds only the given fields; `set_fields` is internal:** `test_edit_text_inverse_only_holds_the_fields_given_and_clients_cannot_send_set_fields` (a client `set_fields` is `unknown_op`; a log line with a widened inverse fails `load`).
- **No-op `[]` on apply, undo and redo:** `test_a_noop_edit_text_has_empty_changed_ids_on_apply_undo_and_redo` (both fields, text only, style only, and `set_fade` for comparison).

6. **The doc note on `undo_blocked` `op_ids`:** `test_the_docs_say_what_undo_blocked_op_ids_means_for_each_reason`. The existing `inverse_invalid` tests check the behaviour itself.

## Decisions (approved by Ada)
1. **Op name and shape:** `edit_text{id, text?, style?}`, at least one of the two. `dur` stays with `trim_clip`, fades with `set_fade` and position with `move_clip`/`set_anchor`. There's no S2b section in PLAN-MERGED.md, so the shape comes from the existing op conventions.
2. **Any text track:** it works on a text item on any text track (T1, T2…), not only T1.
3. **Style is a whole string:** in the S1 schema `style` is a single non-empty style name, so "partial style" means editing `text` or `style` alone. There are no style sub-keys. Prove's "other style keys untouched" check becomes "the field not given and every other item field are untouched".
4. **Values checked at the op arg:** bad values are reported at `/ops/k/text` and `/ops/k/style` with the validator's own rule ids (`wrong_type`, `not_nfc`) and `id` = the text item, following #39's `unknown_media` ruling. The doc path is never used. `add_text` still reports bad values at the doc path; that's left unchanged as out of scope.
5. **NFD is rejected, never normalised:** NFD text gets `not_nfc` (the S1 rule). Prove's "exact retry including NFD text" can't succeed as an edit. Instead, NFD gets the same `not_nfc` every time, and an NFD retry of an NFC edit is `client_op_id_mismatch`.
6. **Lone surrogates:** a lone surrogate in `text`/`style` is `wrong_type`, the field's own validator rule, the same as the S1 behaviour noted in the carry-overs.
7. **Neither field given:** `missing_arg` at `/ops/k`, with no key, since neither field is required on its own. The alternative is `bad_arg` at `/ops/k/id`, as `set_fade` does today.
8. **Wrong item type:** a clip or transition id is `bad_arg` at `/ops/k/id` with `id` = that item, like `set_props`/`set_fade`, which use `bad_arg` for the wrong item type.
9. **Check order:** the id type and existence are checked before the item type, then whether any field was given, then the values (`text` before `style`).
10. **No-op edits:** an edit to the current values is accepted as an entry (a new version, the same hash, `changed_ids: []` on apply, undo and redo), matching `set_fade`. The alternative is to reject it or skip appending.
11. **Inverse:** `set_fields` with only the fields given (not the whole item), like `set_fade`/`set_props`.
12. **No new rule ids:** still 17 op-level and 36 validator.
13. **Empty text:** `text: ""` is allowed (the S1 validator allows an empty text), but `style` must not be empty.
