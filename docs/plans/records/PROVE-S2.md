# PROVE-S2: C2 verification of PR #37 (S2 oplog)

- **Head checked:** `c2a930fc176aab6ced082b9917e029bafff5cbf8` on `feat/editor-s2-oplog`. It was still the head, OPEN, CLEAN and MERGEABLE when I finished.
- **Main:** 898f6b9.
- **Verifier:** Prove. All work was read-only on GitHub, with scratch work on the box.
- **Times:** ET (UTC−4).
- **Evidence:** `evidence/prove-s2/c2a930f/`, with scripts in `scripts/`. The scripts are `c2lib.py`, `c2_probes.py`, `c2_order.py` and `c2_fuzz.py`. Run them with the repo at c2a930f on `PYTHONPATH`.

## Verdict: FAIL

There are 2 blocking failures:

- **F1:** ids that existed only inside a batch get reused.
- **F2:** a non-string id reaches `not_found` and comes back without `id` (steering a).

Everything else passes. HTTP/ACP/MCP is a GAP for S3, and there are some non-blocking notes.

Probe counts: 75/78 checks passed (`4-probes.txt`). The 3 failures are F1 (×2) and F2.

## F1: an id that existed only inside a batch is handed out again

- **Where:**
  - `hermes_studio/oplog.py:787` (`_commit`: `self._retired |= set(T._all_ids(new))`);
  - the same pattern in `load` at `oplog.py:894` and in `replay` at `oplog.py:909`.
- **Cause:** only ids in the *final* doc get retired. An id picked by `_Ctx.fresh` (`oplog.py:595`, `_handed`) and then removed in the same batch is never retired.
- **Rule broken:** `docs/oplog.md:95-96`, "An id that ever existed in this log is never handed out again".
- **Repro:**
  1. `timeline_apply ops=[{"op":"add_marker","at":..,"label":"t"}, {"op":"remove_marker","id":"mk2"}]` logs `add_marker ... "id":"mk2"`.
  2. A later `add_marker` picks **mk2** again.
  - Clips do the same: `insert_clip` + `delete_clip c4` in one batch, then a later `insert_clip` gets **c4**.
- **Fix idea:** in `_commit`, `load` and `replay`, also retire `ctx._handed` (or every `id` in the logged ops).
- **Evidence:** `4-probes.txt` (item 4 ids).

## F2 (steering a): a non-string id reaches not_found without `id`

- **Where:**
  - `_find` / `_track` (`oplog.py:133-145`; also `remove_marker` at `oplog.py:305-311`) raise not_found with `ident=<whatever was passed>`;
  - `_run` adds `id` only `if isinstance(e.ident, str)` (`oplog.py:741`).
- **No type gate:** none of these ops checks the id's type first. So no `bad_arg` or `wrong_type` comes back before `not_found`.
- **Rule broken:** `docs/oplog.md:119` says not_found carries `id`.
- **What I tested:** 11 ops × the values 7, ["c1"], None, True, {"x":1} and 1.5 = 66 cases. All 66 give `not_found/not_found` at `/ops/0/id` (or `/ops/0/track` for insert_clip/add_text) with **no `id` field**. The ops were move_clip, delete_clip, set_fade, set_props, trim_clip, split_clip, set_anchor, remove_marker, remove_track, insert_clip.track and add_text.track. None crash.
- **For contrast:** `history_undo op_id=7` *does* give `invalid_op/bad_arg` at `/op_id`.
- **Repro:** `timeline_apply ops=[{"op":"move_clip","id":7,"at":0}]` gives `{"code":"not_found","rule":"not_found","op_index":0,"path":"/ops/0/id"}` with no `id`.
- **Fix idea:** check that the id is a string (`_need_id`, as at `oplog.py:233`) before the lookup, so a wrong type is `bad_arg`. Or always put `id` on not_found.
- **Evidence:** `4-probes.txt` (section "Wire (4) + steering (a)").

## Items

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Head c2a930f. dc5a92e's parents are ff59093 and 898f6b9. A fresh `merge-tree` matches dc5a92e's tree 33ffdc6. ab45e65, ff59093 and 077d3ff are ancestors, so no force-push. The diff vs main (both 2-dot and 3-dot) is exactly the 4 files docs/oplog.md, docs/timeline.md, hermes_studio/oplog.py and tests/test_oplog.py. The later commits caa2c83…c2a930f touch only those files. | PASS | `0-pr.txt`, `1-graph-diff.txt` |
| 2 | C5 forged step/actor. Through `Oplog.call` they are dropped with `ignored_field` warnings in args and ops (apply, undo, redo). A human never gets a step; neither does an agent with no plan. A forged actor can't take another actor's dedupe slot or get past the actor block. **No HTTP, ACP or MCP timeline entry point exists at this head**, so those are a **GAP for S3**. | PASS (Oplog) / GAP (HTTP/ACP/MCP → S3) | `2-entry-points.txt`, `4-probes.txt` |
| 3 | Every line has actor and changed_ids; step appears only on agent-with-plan lines; keys stay within LINE_FIELDS; there is no run_id. | PASS | `4-probes.txt` |
| 4 | Ada's rulings. The id picks fail (**F1**). Everything else passes: delete, ripple and trim; split (split_from, clamped fades, transitions in/out); undo/redo cancelling; group undo newest first as one entry; stale retry returns the original; the 3 undo_blocked reasons; changed_ids from the diff including re-anchored items, and undo is the same; blocking_op_ids in seq order; no run_id. | **FAIL** (F1) | `4-probes.txt` |
| 5 | Wire's items. (1) move c2 gives [c2, x1]; a later x1 edit blocks the undo with dependents; trim-start and ripple covered on apply, undo and redo. (2) add_track. (3) inverse_invalid. (5) bad_track_role. (6) the docstring at `oplog.py:17`. Wire's tests are in the repo: collection positions 72–74 are the last three `test_an_op_level_not_found_carries_the_missing_id` params, and all 15 related Wire tests pass. (4) passes for string ids but **fails for non-string ids (F2)**. | PASS except (4) → **FAIL** (F2) | `5-wire-tests.txt`, `4-probes.txt` |
| 5b | Steering (b): changed_ids order. See the rule below. | PASS | `5b-changed-ids-order.txt` |
| 6 | Bay's 300-seed property test passes. With 25a3480's oplog.py change reverted in a scratch worktree, it **fails**, and so do the 3 anchor-param tests and the blocks-undo test (5 failed). My fuzz: 1200 sequences, 3329 applies, 840 undo→redo→undo round trips and 1051 undo-last checks; 1121 logs reloaded with `Oplog.load`. Result: **0 crashes, 0 violations**. That covers span ⊆ changed_ids (key union, so stricter than Bay's), sorted order, line == result, hash back/forward and load hash/version. | PASS | `6-bay-property-and-revert.txt`, `6-fuzz.txt` |
| 7 | A lone surrogate in summary (apply or undo, with a log file) gives `invalid_op/bad_arg` at `/summary` and nothing is logged. In a doc value it gives `invalid_op` wrong_type with no encode crash. | PASS | `4-probes.txt` |
| 8 | CI. Details below. | PASS (with notes) | `8-ci-jobs.txt`, `8-ci-attempt1-test-job.log`, `8-codeql.txt` |
| 9 | Local pytest: 440 passed (74 in test_oplog). `ruff check` is clean. | PASS | `9-pytest.txt` |

### undo_blocked shape: not identical across the three reasons

- **Shared core:** `code, message, hint, reason, op_ids, path, id`.
- **`dependents`** adds `blocking_op_ids` (equal to `op_ids`, in seq order).
- **`inverse_invalid`** adds `rule` and `problems`.
- **`actor`** has neither.

So the shape is the same core plus extras that depend on the reason. In the fuzz, inverse_invalid showed up 10 times in 1200 runs. Every case was a real fallback: a later new item took the freed gap, a track was added that broke track order, or a moved clip broke an xfade overlap.

### Steering (b): the changed_ids order rule

- **Rule:** `changed_ids` is `sorted()` of the id strings (`oplog.py:215`). That is plain Python string order: neither numeric order nor doc order. For example, `"c10"` sorts before `"c3"`.
- **Undo and redo:** they compute the same before/after diff in reverse, so they list the same ids in the same order. The log line is the same as the result.
- **Wire's ripple trim of c1** (tests' base doc): apply, undo, redo and all 3 log lines are `[c1, c2, c3, x1]`. That was identical in 50 out of 50 fresh runs.
- **Wider check:** across 2156 apply/undo results, the sorted order held every time, and the undo id set equalled the original's every time.

### CI (all times ET)

**ci run 36890895604** (attempt 2: success)
- **Attempt 1:** `secrets` succeeded. `test` was **cancelled** by `timeout-minutes: 15`.
  - It sat in the `Install` step from 12:17:50 to 12:33:00.
  - `Lint` and `Tests` were **skipped**, so it died before pytest.
  - Caveat: `Install` runs apt (`apt-get update && install ffmpeg >/dev/null`) and then pip (`-q`) in **one step**, and all output is silenced. The log's last line before the cancel is the step header at 12:17:50 and then `The operation was canceled` at 12:33:00. So the logs prove it died in Install, before pytest. They **can't tell apt apart from pip**. "apt" is the likely cause, not proven.
- **Attempt 2:** `test` succeeded from 12:34:00 to 12:39:39. Install took 4m44s, Lint 1s and Tests 38s. `secrets` was carried over from attempt 1.

**desktop run 36890895585** (success)
- changes: success.
- linux: success (12:18:34–12:27:32).
- windows: success (12:18:33–12:27:06).
- sources, publish and release: skipped, as expected on a PR.

**CodeQL run 36890891868** (success)
- Analyze (actions): success, finished 12:18:30.
- Analyze (javascript-typescript): success, finished 12:18:37.
- Analyze (python): success, finished 12:18:42.

**Overall `CodeQL` check** (github-advanced-security): success, "No new alerts in code changed by this pull request", 12:18:19–12:18:22.
- Timing note: it finished **before** the javascript upload (12:18:29) and the python upload (12:18:34). Only the actions upload (12:18:20) was in.
- Both later analyses have `results_count` 0 and no error, so the outcome still holds.

**Alerts**
- Open alerts on `refs/pull/37/head`: **0**.
- Open alerts on `refs/pull/37/merge`: **0**.
- Repo-wide open alerts: 3, all already there before this PR (#35, #36, #37 `py/path-injection` in `hermes_studio/studio.py`, created 02:26 ET).

## Non-blocking notes

1. `ruff format --check` would reformat oplog.py and test_oplog.py. Probably not enforced, since CI runs only `ruff check`.
2. A caller-supplied id equal to a retired id (for example c10, after c10 was deleted) is accepted. `_new_id` (`oplog.py:247-254`) checks only the current doc. The docs say "handed out", so this is allowed, but worth a ruling.
3. A retry with **different** ops under the same client_op_id returns the original result. Nothing checks for a mismatch.
4. The dedupe key (kind, actor id, client_op_id) is shared between apply, undo and redo.
5. Python-only callers: an op or args dict with mixed str/int keys raises `TypeError` from `sorted(...)` (`oplog.py:612`, `oplog.py:694`). JSON callers can't send this.
6. `Oplog.load` checks seq, versions, hash and inverse, but does not recompute `changed_ids` or check that actor/step are valid on loaded lines.
7. A ripple trim of a clip that has an outgoing xfade gives `invalid_op/transition_overlap_mismatch`. The overlapping next clip starts before the old end, so it doesn't shift. This is consistent with the docs ("later items"), but Ada may want to rule on it.
8. In `_id_map`, `T.resolve` failures quietly become `spans={}`. That is safe because both sides of a commit are valid docs.

**Final: FAIL** (F1 transient-id reuse, oplog.py:787/894/909; F2 non-string id gives not_found without `id`, oplog.py:741).

---

## Re-verify, Thursday 1 Oct 2026, 13:15–13:50 ET: PR #37 pinned at `2f80bbd8018cccede70ed5611ceb0b5f5cd1b149`

- **Evidence:** `evidence/prove-s2/2f80bbd/`. Scripts are in `scripts/`.
  - Run `c2b_junk.py` with `PYTHONPATH=<repo>`. It is self-contained and its exit code is the number of crashes. It is meant to be re-run on Bay's next head.
  - Run the others with `PYTHONPATH=<repo>:<scripts>`.
- **Head moved during the run:** the PR head is now `0b459c4` (17:22Z = 13:22 ET, "check ops and undo/redo arg shapes before dedupe; split duplicate_id points at ids/i"; parent 2f80bbd). mergeStateStatus is BLOCKED, presumably while its CI runs. Everything below is about 2f80bbd only. When I started (13:15 ET), 2f80bbd was the head and the PR was CLEAN and MERGEABLE.

### Verdict at 2f80bbd: FAIL

- F1 and F2 from C2 are fixed.
- 4 new failures, R1–R4 below. R1 is Wire's crash; R4 also existed at c2a930f and I missed it in C2.

| Failure | What | Where | Repro |
|---|---|---|---|
| **R1** (crash, Wire's report) | A retry on a cached apply key with a non-iterable `ops` raises an uncaught `TypeError`. The 5 crashing shapes are `ops` = 5, None, 1.5, True and -1. | `_same_call` re-runs the ops at `oplog.py:867`, then `_run` does `enumerate(ops)` at `oplog.py:892`, before the `ops` shape check in `_apply` | `timeline_apply {base_version:0, ops:[add_marker], summary:"s", client_op_id:"K"}`, then the same call with `ops: 5` (or `null`) gives `TypeError: 'int' object is not iterable`. With a fresh key these give `invalid_op/bad_arg` at `/ops`. |
| **R2** | `history_redo` that reuses an undo's key, with the same explicit summary and the same `op_id`, returns the cached UNDO result instead of `client_op_id_mismatch`. The same call under a new key gives `not_an_undo`. | `_same_call` at `oplog.py:871-883`: with a `summary`, the tool is never checked | apply A; `history_undo {client_op_id:"ku", op_id:A, summary:"same words"}`; then `history_redo {client_op_id:"ku", op_id:A, summary:"same words"}` returns the undo's result. |
| **R3** | In the history_undo/redo target, `op_id: null` and `group_id: null` are treated as absent instead of `bad_arg`. | `_check_args` at `oplog.py:791` (`args.get(k) is not None`) | `history_redo {op_id: null}` gives `not_found` at `/op_id` with `id: None`. On a cached undo key, `{op_id:<any other op>, group_id:null}` returns the cached result: `group_id` in args skips the op_id compare at `oplog.py:877`. A fresh call gives `bad_arg`. |
| **R4** (already at c2a930f) | `history_undo {group_id: null}` with no `op_id` **undoes every ungrouped entry as one group**. | `oplog.py:791` lets null through; then `oplog.py:1024` matches `e["group_id"] == None` | apply A, apply B, apply C with `group_id:"g1"`; `history_undo {client_op_id:"x", group_id:null}` applies with undoes [B, A]. An agent gets `undo_blocked/actor` with `id: None`. The output is the same at c2a930f. |

**Also, in the spirit of F2:** `project_id` of any non-matching value or type gives `not_found` at `/project_id` with `id` stringified (`"5"`, `"None"`), not `bad_arg` (`oplog.py:804-810`). This is unchanged since S1. I'm calling it a note, not a FAIL, because the docs' "Id types" list only covers op ids.

### Checks

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | **Graph and diff.** The head was 2f80bbd. Parents: 2f80bbd → aa6f6ce → c2a930f. c2a930f, dc5a92e, ff59093 and ab45e65 are ancestors, so nothing was force-pushed. 0 behind and 21 ahead of main 898f6b9. The 2-dot and 3-dot diffs vs 898f6b9 are exactly the 4 files.<br>**2f80bbd is layout only:** it touches only oplog.py and test_oplog.py. `ast.dump` is identical for both files (aa6f6ce vs 2f80bbd), and so are the comment tokens (same text, same order; 27 and 63). | PASS | `0-pr.txt`, `1-graph-diff-ast.txt` |
| 2 | **F1.** Live, after load and after a reload: [add_marker, remove mk2] then add gives mk3. Insert+delete c4 then insert gives c5. Tracks the same (A3 added and removed, then the next add isn't A3). Split pieces removed in the same batch: the next insert is c6. Multi-batch: the next marker is mk5. Undo of an add: the next is mk3. `replay` hash matches. A rejected batch does not retire ids (the next add is still mk2), including when another batch commits in between. | PASS | `2-5-probes.txt` §2 |
| 3 | **F2.** 25 id fields × 6 values = 150 cases, all `invalid_op/bad_arg` at the field's own path, with no crash and no not_found. The fields are id, track, `ids[i]`, `between[i]` and `anchor.to` across every public op. `history_undo`/`history_redo` `op_id`/`group_id` of 7, list, True, dict or 1.5 give bad_arg, **but null does not (R3, R4)**. Container junk (a non-list `between`/`ids`, `anchor` of 7, None or with no `to`, wrong lengths) is all refused with no crash. An invalid id string gives `bad_id` where an id is created, and `not_found` on lookup. The docs (`docs/oplog.md:131-135`) match for op ids. | PASS for op ids; history target → FAIL (R3/R4) | `2-5-probes.txt` §3, `5b-junk-args.txt`, `3-4-5-docs.txt` |
| 4 | **id_reused.** It fires (`invalid_op/id_reused` at the id path) for ids retired earlier in the log (marker, clip, track, transition, text), for ids removed earlier in the same batch, for engine-picked ids removed in the same batch, for an explicit id named and then removed in the same batch, and for split `ids/1`. Ids in the doc now still give `duplicate_id` (marker, clip, track; a marker id equal to a clip id too). Undo, redo, load and replay restore old ids with no error. After load, an explicit retired id is still `id_reused`. The docs (`docs/oplog.md:96-99`, `136-140`) match. | PASS | `2-5-probes.txt` §4 |
| 5 | **client_op_id_mismatch.** What passes:<br>• an identical retry returns the cached result and appends no line;<br>• a retry differing only in forged actor/step (in args and ops) counts as identical;<br>• naming the engine-picked id counts as identical; a different id is a mismatch;<br>• different at, summary, base_version or group_id are mismatches, with `op_ids` = [cached];<br>• a different actor isn't a match;<br>• key order doesn't matter;<br>• a retry after the doc changed is still identical, and a stale base_version retry returns the original (Ada);<br>• after load: identical, mismatch and omitted/named id all hold;<br>• undo↔apply, redo↔apply and undo↔redo (without summary) are mismatches; group undo retry works.<br>What fails: R1 crash, R2 undo/redo blur, R3 null target. | **FAIL** (R1, R2, R3) | `2-5-probes.txt` §5, `5b-junk-args.txt` |
| 6 | **Earlier C2 bar.** My C2 probes: 78/78. Rulings, delete/ripple/trim/split, undo rules, the undo_blocked shapes (unchanged: same core plus reason-specific extras), Wire 1–5, and the summary surrogate all pass.<br>**changed_ids order:** sorted string order; undo and redo are identical; Wire's ripple trim gives [c1, c2, c3, x1] in 50 of 50 runs; 2156 out of 2156 results sorted.<br>**Tests:** Bay's 300-seed test, the anchor tests and Wire's tests: 21/21 pass.<br>**New tests vs c2a930f:** run against c2a930f code, 2f80bbd's test file gives 115 failed and 74 passed, and all 115 failures are in the 9 added tests plus the 1 changed one. Bay's "115" is confirmed. The only added test that also passes on c2a930f is `test_an_identical_retry_still_returns_the_cached_result_even_with_forged_fields`, which is expected.<br>**My fuzz:** 1200 sequences, now with explicit ids and repeated client_op_ids. 0 crashes and 0 violations. That covered 3490 applies (191 with explicit ids), 37 id_reused and 460 duplicate_id, 3418 identical retries (cached), 3418 mutated retries (mismatch), 3418 undo-on-apply-key (mismatch), 2714 retries after load (cached), 1129 loads plus replays with matching hashes, 1129 post-load new ids never reused, and 844 round trips. | PASS | `6-old-probes-rerun.txt`, `6-changed-ids-order.txt`, `6-bay-wire-tests.txt`, `6-new-tests-vs-c2a930f.txt`, `6-fuzz.txt` |
| 7 | **CI, all first attempt, all success.** All times ET.<br>• **ci 36896703709:** secrets; test (Install 55 s; `ruff check` "All checks passed"; pytest "555 passed").<br>• **desktop 36896703707:** changes, linux (13:04:51–13:13:03), windows (13:04:52–13:13:41); sources, release and publish skipped.<br>• **CodeQL 36896700416:** Analyze actions (finished 13:05:16), javascript-typescript (13:05:33) and python (13:05:46).<br>• **Overall `CodeQL` check:** success, "No new alerts", 13:05:06–13:05:08. That is again **before** the javascript (13:05:25) and python (13:05:36) uploads; only actions (13:05:07) was in. All 3 analyses have 0 results.<br>• **Alerts:** 0 open on `refs/pull/37/head` and `/merge`. 3 repo-wide alerts that predate this PR (#35–37, path-injection, studio.py). | PASS | `7-ci.txt` |
| 8 | **Local tests and lint.** pytest: 555 passed (189 in test_oplog). `ruff check .` is clean. `ruff format --check` on the 2 files is clean. | PASS | `8-pytest-ruff.txt` |

### Bay's claims

| Claim | Result |
|---|---|
| 555 passed / 189 in test_oplog | ✓ |
| ruff check clean | ✓ |
| ruff format clean | ✓ for the two oplog files. Repo-wide `ruff format --check .` would reformat 38 other files, which were there before and aren't enforced. |
| 115 new/changed tests fail on c2a930f | ✓ |
| CI green first attempt | ✓ |
| 0 alerts | ✓ (on the PR refs) |
| PR CLEAN | ✓ at 13:15. The head has since moved to 0b459c4 and the PR is BLOCKED. |
| diff only the 4 files | ✓ |

### Notes (non-blocking)

1. **split `duplicate_id` path:** it points at `/ops/k/ids` (`oplog.py:511`), while `id_reused` and `bad_arg` use `/ops/k/ids/i`. 0b459c4's message says this is fixed there; I haven't verified it.
2. **The cached path judges before arg validation.** On a cached key, junk `base_version`, `ops`, no target, or both targets give `client_op_id_mismatch`, where a fresh key gives `bad_arg`. That is harmless, apart from R1 and R3.
3. **Strict "same call":** 1 vs 1.0 (an `at` or `base_version`) and an NFC vs NFD label count as a mismatch. An NFD summary is `bad_arg`.
4. **Cost of a retry:** `_same_call` replays the whole log from base on every apply retry (O(n) per retry), and it doesn't cap `ops` at MAX_OPS before replaying (a 600-op retry got replayed and then reported as a mismatch).
5. **`insert_clip.media` junk** gives `invalid_op/unknown_media` at the doc path (`/tracks/1/items/5/media`), not `/ops/k/media`. It isn't in `_check_refs`, and the docs don't list it.
6. **`project_id` junk** gives `not_found` with `id` stringified (see above).
7. **Undo of `remove_track`** after another track was removed can be `inverse_invalid`/`track_order` (the inverse inserts by index). It's a legitimate fallback: 10 out of 1200 fuzz runs.
8. **Python-only:** the mixed str/int key `TypeError` from C2 is unchanged.

**Final (2f80bbd): FAIL.** R1 is the crash on a cached-key retry with non-iterable `ops` (`oplog.py:867`→`892`). R2 is a redo that reuses an undo's key with an explicit summary getting the undo's cached result (`oplog.py:871-883`). R3 is null `op_id`/`group_id` treated as absent (`oplog.py:791`). R4 is `history_undo {group_id:null}` undoing every ungrouped entry (`oplog.py:791` + `1024`; already at c2a930f). F1 and F2 are fixed.

---

## Delta re-verify, Thursday 1 Oct 2026, 13:48–13:56 ET: PR #37 pinned at `480a220c53c7a55bbeaa792634f957b6a41468db`

- **Scope:** only what changed since 2f80bbd; that full run carries forward.
- **Evidence:** `evidence/prove-s2/480a220/`, with scripts in `scripts/`. `c2c_probes.py` is new; the others are the 2f80bbd scripts, re-run unchanged.
- **Head at the end:** still 480a220, and the PR was OPEN, MERGEABLE and **CLEAN** at 13:56 ET.

### Verdict at 480a220: PASS

R1–R4 are fixed, along with the pre-dedupe shape check, the ops cap and the split path. There are no regressions. 0 crashes and 0 violations.

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | **Graph.** `2f80bbd..480a220` is exactly [0b459c4, 480a220] (parents 2f80bbd → 0b459c4 → 480a220). 2f80bbd, aa6f6ce, c2a930f and 898f6b9 are ancestors, so nothing was force-pushed. 0 behind and 23 ahead of main. The diff vs 898f6b9 is the 4 files; the delta touches docs/oplog.md, oplog.py and test_oplog.py.<br>**Delta read:** everything is R1–R4, the pre-dedupe shape checks, the ops cap, the split path, tests or docs. That includes `_base_version_type`, `_ops_shape`, `_undo_shape`, the `_tools` table with `_tool_of` on load, the redo-target check in `_same_call`, the null-group guard, and `_commit(tool)`.<br>**Two small extras, flagged as benign:** `_check_args` now sorts unknown *top-level* args with `key=repr` (oplog.py:785), which fixes the args-level half of my C2 mixed-key note; and `same()` catches TypeError/ValueError from `json.dumps` and treats that as a mismatch. | PASS | `1-graph.txt`, `1-delta-src-docs.diff` |
| 2 | **R1.** The saved `c2b_junk.py`, run against 480a220, reports **0 crashes** (exit 0) over 190 shapes, each on a fresh key and 3 cached keys.<br>Every junk-shaped value gives the same `bad_arg` at the same path on a cached key as on a fresh one.<br>The only 9 rows where cached differs from fresh are well-formed values that really differ (base_version 5, a string summary/group_id/op_id). Those correctly give `client_op_id_mismatch`. | PASS | `2-junk-args.txt` |
| 3 | **R2.** A redo that reuses the key of an undo of a normal entry (same summary and op_id) is a mismatch, live and after load. So is an apply that reuses an undo key.<br>Live, an undo of an undo entry knows its tool, so the other tool is a mismatch.<br>**Ada's exception, after load:** a key whose line is an undo of an undo entry accepts history_undo *or* history_redo when every other field matches (tested for a redo-written line and for a history_undo-written line).<br>It is limited to exactly that case:<br>• a different summary, op_id or base_version is a mismatch;<br>• the key used as timeline_apply is a mismatch;<br>• with no summary, the default "Redo: …" line only matches history_redo;<br>• an undo of a normal entry is still a mismatch as redo;<br>• apply keys used as undo or redo are mismatches;<br>• a group-undo key used as redo, or with op_id instead of group_id, is a mismatch.<br>The docs describe it at `docs/oplog.md:177-182`. | PASS | `3-7-delta-probes.txt` (R2) |
| 4 | **R3.** I sent each of these on 4 keys (a fresh key and cached apply, undo and redo keys), for both history_undo and history_redo: op_id null, group_id null, both null, both given, neither given, 7, a list, True, a dict, 1.5, and `{op_id:other, group_id:null}`. All give `invalid_op/bad_arg` at `/op_id`, `/group_id` or `""` as appropriate. The cached `{op_id:other, group_id:null}` case gives bad_arg at `/group_id`. history_redo with a string group_id gives bad_arg. | PASS (89 checks) | `3-7-delta-probes.txt` (R3) |
| 5 | **R4.** `history_undo {group_id:null}` gives bad_arg at `/group_id`; the hash is unchanged and no line is added. An agent gets the same bad_arg, not undo_blocked. An unknown string group gives `not_found` with `id`. | PASS | `3-7-delta-probes.txt` (R4) |
| 6 | **Ops cap.** I instrumented `Oplog._run` to count calls.<br>• 0, 501 and 5000 ops give `bad_arg` at `/ops` with **0 `_run` calls**, on fresh and cached keys.<br>• 500 ops are accepted.<br>• A cached 500-op key retried with 501 ops gives bad_arg with no replay.<br>• Cached key with `ops` of `[5]`, `[{"op":5}]`, `[{}]`, `"x"` or `{}` gives bad_arg with no replay.<br>• Note: an *identical* 500-op retry on a 31-entry log does replay (31 `_run` calls, about 33 ms), as designed. | PASS | `3-7-delta-probes.txt` (ops cap) |
| 7 | **Split path.** split_clip `duplicate_id` is at `/ops/k/ids/i` (ids/0, ids/1, and `/ops/1/ids/1` in a 2-op batch). The docs at `docs/oplog.md:139-140` match. | PASS | `3-7-delta-probes.txt`, `8-f1-f2-idreused-mismatch-probes.txt` |
| 8 | **Regression.** My original probes: 78/78. The F1/F2/id_reused/mismatch probes: 76/76.<br>**Fuzz:** 800 sequences with explicit ids and repeated keys: **0 crashes, 0 violations**. It covered 2375 applies (131 with explicit ids), 22 id_reused, 322 duplicate_id, 2274 identical retries (cached), 2274 mutated retries (mismatch), 2274 undo-on-apply-key (mismatch), 1826 retries after load (cached), 758 loads and replays with matching hashes, and 545 round trips. | PASS | `8-old-probes.txt`, `8-f1-f2-idreused-mismatch-probes.txt`, `8-fuzz.txt` |
| 9 | **Local tests and lint.** pytest: 613 passed (247 in test_oplog). `ruff check .` is clean. `ruff format --check` on the 2 files is clean.<br>**R-tests on 2f80bbd** (480a220's test file run against 2f80bbd code): 45 failed and 202 passed, and all 45 failures are in the 11 added tests plus the 1 changed one (59 ids in total).<br>Bay's "19 of 20" matches the r1 (5) + r2 (2) + r3 (10) + r4 (1) + split (2) = 20 ids. 19 fail; the one that passes is `test_r2_an_apply_key_reused_by_undo_with_a_summary_is_a_mismatch`, which was already a mismatch at 2f80bbd.<br>The extra hardening tests behave as follows: the junk-ops, cap, both/neither and 3000-seed tests all fail on 2f80bbd; `wrong_typed_fields…` fails 12/24, since half its params were already bad_arg there. | PASS | `9-pytest-ruff.txt`, `9-rtests-on-2f80bbd.txt` |
| 10 | **CI, all attempt 1, success.** All times ET.<br>• **ci 36900074294:** secrets; test ("All checks passed", "613 passed").<br>• **desktop 36900074279:** changes, windows (13:32:19–13:40:42), linux (13:32:19–13:45:55); sources, release and publish skipped.<br>• **CodeQL 36900067264:** Analyze actions (finished 13:32:39), javascript-typescript (13:32:55) and python (13:32:58).<br>• **Overall `CodeQL` check:** success, "No new alerts", 13:32:28–13:32:30. That is again **before** the javascript (13:32:45) and python (13:32:49) uploads; only actions (13:32:28) was in. All 3 analyses have 0 results.<br>• **Alerts:** 0 open on `refs/pull/37/head` and `/merge`. 3 repo-wide alerts that predate this PR (#35–37, studio.py). | PASS | `10-ci.txt` |

### Bay's claims

All confirmed:
- 2f80bbd + [0b459c4, 480a220]; the diff is the 4 files.
- 613 passed / 247 in test_oplog.
- ruff check and format are clean.
- 19 of 20 R-tests fail on 2f80bbd (using the counting in row 9).
- CI passed on attempt 1.
- The PR is CLEAN.

### Notes (non-blocking)

1. **Wire's note, confirmed:** an op containing a non-string arg name raises a raw `TypeError` at `oplog.py:700` (`sorted(set(a) - req - opt - {"op"})`, with no `key=repr`). Examples: `{1:…, "zz":…}`, or a tuple key.
   - It's **not a FAIL**: only an in-process Python caller can hit it.
   - Through JSON, `json.loads` gives only string keys. The same op after a JSON round trip gives `invalid_op/unknown_arg` at `/ops/0/1`.
   - At 480a220 nothing outside `oplog.py` and its tests calls `Oplog`, `timeline_apply` or `history_*`; the HTTP/ACP/MCP entry points are still the S3 GAP.
   - `load()` reads lines with `json.loads` (oplog.py:1138).
   - The only non-JSON decoder in the repo is `tomllib` in `scripts/mirror-sources.py`, which has nothing to do with ops.
   - So no JSON or HTTP path can reach it today. S3's entry points must stay JSON-only, or the fix (`key=repr`, as at oplog.py:785) should land first. Bay has it in the post-S2 follow-up.
   - Evidence: `note-nonstring-op-keys.txt`.
2. `timeline_apply` with `group_id: null` is accepted as "no group". `_check_args` still skips None for apply's group_id. That's consistent, but it doesn't follow the undo/redo "null is bad_arg" rule.
3. An identical apply retry still replays the log from the start (O(n)). It is now capped by the 500-op limit and runs only after the shape checks.
4. The overall CodeQL check keeps finishing before the javascript and python uploads. This is harmless here (0 results), but worth knowing if that check is ever relied on alone.
5. The carried-forward notes from 2f80bbd (strict 1 vs 1.0 and NFC/NFD, `project_id` stringified in not_found, media junk path, remove_track inverse fallback) are unchanged.

**Final (480a220): PASS.**
