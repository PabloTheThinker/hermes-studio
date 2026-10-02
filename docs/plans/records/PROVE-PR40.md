# PROVE — PR #40 "S2b: edit_text op (spec of record)"

**Verdict: PASS at `c1bbddb56564bd0d2fc7ead8496ae3eaa34ea7f6`** (off main `8d181ed`, tree 2f2518d).
No bugs found in S2b. One finding is older than this PR, out of scope, and noted below (OTIO import on an overlapping music clip).
Verified by Prove, 2026-10-01, 17:59–18:20 ET. Read-only on GitHub. Spec = PR body (identical to `S2B-PR-BODY.md` apart from a trailing newline).
Re-checked at the end: head is still c1bbddb, PR is OPEN / MERGEABLE / CLEAN, 4 ahead and 0 behind main 8d181ed.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Graph: 6a106a7 (parent 8d181ed) → 36e529b → 59fa7b1 → c1bbddb, linear, 0 behind / 4 ahead, 0 force-pushes. Files: `docs/oplog.md` +34, `hermes_studio/oplog.py` +22, `tests/test_oplog.py` +377 (433 / −0). S2b only. | PASS | 1-graph.txt, 1-src-docs.diff, 1-full.diff |
| 2 | pytest on 3.12.14 with ffmpeg: **742 passed** (Bay: 742). `ruff check .` clean; `ruff format --check` clean on oplog.py and test_oplog.py. | PASS | 6-pytest-ruff-revert.txt |
| 3 | Revert to 8d181ed's oplog.py, new tests kept: 52 new ids, 0 removed. **50 fail, 2 pass**: `test_a_noop_edit_text_has_empty_changed_ids_on_apply_undo_and_redo[set_fade]` and `test_the_docs_say_what_undo_blocked_op_ids_means_for_each_reason`. Exactly Bay's claim. | PASS | 6-pytest-ruff-revert.txt |
| 4 | Own probes against the spec: **116/116** | PASS | 2-probes.txt |
| 5 | Regression: c2_probes 78/78, c2b 76/76, c2b_junk 0 crashes (190 shapes), c2c 132/132, c2_order stable (2156/2156), p38_probes 39/39, p38_m0 unchanged, p39_probes 85/85 | PASS | 3-regression.txt |
| 6 | Fuzzes: p38_fuzz 1000 (5046 applied, 0 crashes, 0 violations); c2_fuzz 1200 (0 crashes, 0 violations) | PASS | 3-fuzz-p38.txt, 3-fuzz-c2.txt |
| 7 | Own edit_text fuzz, **1500 sequences / 17,174 entries**: 0 crashes, 0 violations | PASS | 4-edit-text-fuzz.txt |
| 8 | Doc note: one meaning of `op_ids` per `reason`. actor = other people's target entries; dependents = same list as `blocking_op_ids`, by seq; inverse_invalid = the entries being undone. Matches the 3 reasons in code (docs/oplog.md:214–216). | PASS | 2-probes.txt (last section) |
| 9 | CI on c1bbddb: ci, desktop, CodeQL all green; 0 open alerts on the PR refs | PASS (note) | 7-ci.txt |

## Probe coverage (2-probes.txt)
- **Check order, one fault at a time:**
  - `unknown_arg`, then `missing_arg` at `/ops/0/id`.
  - `bad_arg` at `/ops/0/id` with no `id` for each non-string id: 5, null, [], ["x5"], {}, {"id":…}, true, 1.5.
  - `not_found` at `/ops/0/id` with `id` for a missing id, a marker id and a track id.
  - `bad_arg` with `id` for a clip, a music clip and a transition.
  - `missing_arg` at `/ops/0` when no field is given.
  - Value errors at `/ops/0/text` or `/ops/0/style`, all carrying `id`:
    - `not_nfc` for NFD text or style;
    - `wrong_type` for a lone surrogate, empty style, numbers, null, lists, dicts, bools and bytes.
  - Empty `text` is OK.
- **Several faults at once:** each case reports the earliest step. Covered: 1 before 2/5/6; 2 before 5/6; 3 before 5/6; 4 before 5 and before 6; `text` before `style`. With the error in op k, the path is `/ops/k/...` and `op_index` is k. Edit, delete and edit again gives `not_found` at op 2.
- **Nothing applied on any error:** the hash, version, entry count and log lines are unchanged.
- **Applies:**
  - Text only, style only and both. Also on an anchored item (x2), on a second text track (T2/y1), and on an item with `split_from` and fades.
  - Every other field and every other item is byte-identical.
  - `changed_ids` is `[id]`.
  - The inverse is exactly `set_fields{id, set: only the given fields' old values, unset: []}`.
  - Undo gives the base hash and redo the edited hash, with the same ids.
- **No-ops** (both fields, text only, style only):
  - The entry gets a new version, the hash is the same and `changed_ids` is `[]`.
  - Undo and redo also give `[]`.
  - An exact retry returns the cached result with no new entry (E3).
  - é vs e counts as a change.
- **Retries:**
  - An exact retry is cached, including style-only and with keys reordered.
  - These give `client_op_id_mismatch`: an NFD retry of an NFC edit, other text, an added style, another id, a dropped field, and a style-only retry with an added no-op text.
  - A rejected NFD edit is never cached.
- **Byte-exact storage:** the stored value, the log line (raw UTF-8), load and replay all match exactly. Covered: emoji, ZWJ family, flag, skin tone, NFC combining marks (Devanagari, Hebrew niqqud, Vietnamese), Arabic RTL, RTL/LTR mix with RLM, ZWSP/NBSP, control characters, JSON-like text, astral CJK, Hangul, a 200k-character string, and empty text.
- **Inverse round trip:** apply, undo, redo, undo gives h1, h0, h1, h0 for a 2-op edit.
- **E4:**
  - A client `set_fields` gets `unknown_op`.
  - Each tampered log line fails `Oplog.load` with "replay does not reproduce the entry": a widened inverse (adds `dur`), changed inverse text, an added `unset`, and changed op text.
- **E1:** undo of the edit after a delete gives `undo_blocked`, reason `dependents`, with `op_ids == blocking_op_ids == [delete]`, and nothing is applied.
- **E2:**
  - Edit, delete, undo the delete, undo the edit restores x5 exactly (base hash).
  - This survives a reload (same hash, 4 entries).
  - Undoing in the wrong order is blocked.
- **Dependents, actor and groups:**
  - A later edit blocks undo of an earlier one (dependents).
  - The agent can't undo a human's edit (actor), with `op_ids` = the target.
  - A group of two edits undoes as one.
- **Load, replay and #39 checkpoints:**
  - 70 mixed entries give the same hash on live, load and replay.
  - Checkpoints match between live and loaded (seqs, docs, retired), and each one equals a replay of its prefix.
  - After load, exact retries of all 70 calls return the original entries, and a changed retry gives a mismatch.
  - The OTIO round trip keeps the edited strings byte-for-byte.
- **Rule counts:** 17 op-level rules in the docs, all distinct; `T.RULES == 36`.

## Own fuzz (4-edit-text-fuzz.txt, scripts/p40_fuzz.py)
**What it generates:**
- About 65% `edit_text`: valid, no-op, bad values (NFD, surrogates, non-strings, empty style), clip or transition targets, junk or missing ids, extra args.
- The rest are other ops: move, trim or split clips, `add_text` on T1/T2, `delete_clip` of texts, `set_anchor`, markers. 15% of calls carry two ops.
- Exact and changed retries, immediate undo/redo, and undo of older entries.

**What it checks:**
- No crashes.
- A rejection leaves the hash, version, entries and log lines unchanged.
- A lone `edit_text` error matches an **independent oracle of the spec check order** (code, rule, path, id). An oracle-expected error that succeeds counts as a violation too.
- On success:
  - `changed_ids == [id]` exactly when bytes differ;
  - the item equals the old item with only the given fields replaced;
  - all other items are byte-identical;
  - the inverse has the right shape.
- For any op, JSON and span changes are a subset of `changed_ids`.
- Undo/redo round trips the hash with the same ids.
- An exact retry is cached and a changed retry gives a mismatch.
- At the end of each sequence: load and replay give the same hash, and the checkpoints match between live, loaded and a replay of the prefix.

**Results:**
- 1500 sequences, 17,174 entries.
- 5635 `edit_text` applies (970 no-ops) and 3450 `edit_text` rejections. All matched the oracle: bad_arg 980, wrong_type 871, missing_arg 764, unknown_arg 374, not_found 349, not_nfc 112.
- 3427 undo/redo round trips, 1573 exact retries, 690 changed retries, 1831 checkpoints.
- **0 crashes, 0 violations.**

## Bay's claims
- 742 tests: confirmed locally and in CI.
- Revert gives 50 of 52 failing, and the 2 passing tests are the doc-note test and the set_fade comparison: confirmed exactly.
- E1–E4: confirmed, both by Bay's tests and by my own probes.

## CI (7-ci.txt)
- **ci** (run 36931085181, 17:48:24–17:50:12 ET):
  - `secrets` and `test` passed.
  - Python 3.12.14; ffmpeg cache hit with sha256 OK and libass OK.
  - The apt fallback step was skipped.
  - ruff "All checks passed!"; **742 passed** with no skips.
- **desktop** (run 36931085192, 17:48:24–17:55:33 ET): `changes`, `linux` (AppImage, clean-machine and installer tests) and `windows` passed. `sources`, `release` and `publish` were skipped, as expected for a PR.
- **CodeQL:**
  - The Analyze jobs passed: python 17:48:27–17:49:24, javascript-typescript 17:48:28–17:49:27, actions 17:48:27–17:49:37 ET.
  - Uploads on refs/pull/40/head, 0 results each: actions 17:48:59, python 17:49:17, js 17:49:18 ET.
  - **The overall check-run** (github-advanced-security, "No new alerts in code changed by this pull request") ran 17:48:58 → **17:49:01 ET**. That is **before the python and js uploads**; only the actions upload came first. This matches #38 and #39: the overall green does not cover python or js on its own, but the per-language analyses (0 results) do.
- **Open alerts:** 0 on refs/pull/40/head and 0 on refs/pull/40/merge (no merge-ref analyses exist, as on earlier PRs). Repo-wide there are 3 older ones (#35–37, py/path-injection in `hermes_studio/studio.py`), a file this PR doesn't touch.

## Notes
1. **Older OTIO bug, out of scope for S2b** (5-otio-preexisting.txt): `T.from_otio(T.to_otio(d))` raises a bare `StopIteration` rather than a `TimelineError`.
   - Where: `hermes_studio/timeline.py:834` (`prev = next(i for i in out if i["id"] == t["between"][0])`, in `from_otio` at :808).
   - When: a music track has a clip (m0) at the same `at` as the outgoing clip of an xfade pair (ma/mb, `tab`).
   - It is identical on main 8d181ed. Without m0 the round trip is hash-exact.
   - Suggested follow-up ticket: look up the outgoing clip safely, or raise a typed error.
2. The code path: `op_edit_text` at oplog.py:669 is registered at oplog.py:712 with required `{id}` and optional `{text, style}`. It runs `_find` (not_found), then the type check (bad_arg with id), then the at-least-one-field check (missing_arg at `/ops/k`), then `T._Checker().string` per field, `text` first, with `empty=True` for text only. The checks use the validator's own rule ids, so no new rule is added (17/36 unchanged).
3. There is no length limit on text. The validator has none either; 200k characters stores and round-trips exactly.
4. The fuzz harness bugs I fixed along the way were on the probe side: the redo target is the undo entry's op_id, and text items are deleted with the public `delete_clip`, since `delete_item` is internal. The T2 fixture has to come first among the tracks, per `track_order`.

## Evidence (`/workspace/desk/hermes-studio/evidence/prove-pr40/c1bbddb/`)
- Graph and diffs: `1-graph.txt`, `1-src-docs.diff`, `1-full.diff`
- Probes: `2-probes.txt`
- Regression and fuzzes: `3-regression.txt`, `3-fuzz-p38.txt`, `3-fuzz-c2.txt`
- edit_text fuzz: `4-edit-text-fuzz.txt`
- Older OTIO bug: `5-otio-preexisting.txt`
- Tests, lint and revert: `6-pytest-ruff-revert.txt`
- CI: `7-ci.txt`
- `scripts/`: `p40_probes.py`, `p40_probes_lib.py`, `p40_fuzz.py`, `p40_otio_preexisting.py`, `p38lib.py`, `t.sh` (pytest, ruff, revert), `reg.sh` (regression runner). The S2/p38/p39 scripts are reused from `prove-s2/480a220/scripts`, `prove-pr38/36f8a87/scripts` and `prove-pr39/4bfd71f/scripts`.
